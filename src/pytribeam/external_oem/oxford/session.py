"""Connection to an AZtec instance and entry point to all controllers."""

from __future__ import annotations

import logging
import socket
import threading
from typing import Optional

from .acquisition import AcquisitionController
from .data import DataManager
from .detectors import DetectorManager, EbsdDetector, EdsDetector, Interlock
from .enums import AcquisitionType, DataType
from .errors import AztecConnectionError, AztecError, NotConnectedError, ScanExportError
from .models import AcquisitionConfig, ScanResult, SystemStatus, TechniqueReadiness

log = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 22201

_CONNECT_HINT = (
    "Check that AZtec is running at {addr} with the Plugin licence active, that TCP port "
    "{port} is open in both directions, and that no other plugin client is connected "
    "(AZtec allows one session at a time)."
)


def check_port(
    host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 2.0
) -> bool:
    """True if something accepts TCP connections at host:port. Pure Python; useful
    to tell 'network/AZtec down' apart from 'plugin refused us'."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class AztecSession:
    """A connection to one AZtec instance.

        with AztecSession("10.0.0.5") as az:
            print(az.status())
            az.ebsd.insert()
            result = az.acquisition.run(AcquisitionConfig(AcquisitionType.EBSD_MAP))
            az.data.export_acquisition_h5oina(result, r"D:\\exports")

    Parameters
    ----------
    host, port:
        AZtec PC address. The plugin listens on 22201.
    api:
        Backend. Default: the real .NET assemblies via pythonnet (loaded on connect).
        Use :meth:`simulated` for an offline simulator.
    dll_dir:
        Folder containing OINA.Plugin.AcquisitionClient.dll (else $AZTEC_PLUGIN_DIR
        or the SDK install folder).
    interlock:
        Optional ``fn(detector, action) -> bool`` consulted before inward detector
        motion (see :mod:`oxford_aztec.detectors`).
    retract_on_disconnect:
        Retract all detectors before disconnecting. Off by default because AZtec
        users often want detectors left in place between scripted runs.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        *,
        api=None,
        dll_dir: Optional[str] = None,
        interlock: Optional[Interlock] = None,
        retract_on_disconnect: bool = False,
        pythonnet_runtime=None,
    ):
        self.host = host
        self.port = int(port)
        self._api = api
        self._dll_dir = dll_dir
        self._runtime = pythonnet_runtime
        self._interlock = interlock
        self.retract_on_disconnect = retract_on_disconnect
        self._native = None
        self._detectors: Optional[DetectorManager] = None
        self._acquisition: Optional[AcquisitionController] = None
        self._data: Optional[DataManager] = None
        self._lock = threading.RLock()

    @classmethod
    def simulated(cls, simulator=None, **kwargs) -> "AztecSession":
        """A session backed by the in-process simulator (no AZtec, no .NET)."""
        from .simulator import SimulatedApi

        return cls(api=SimulatedApi(simulator), **kwargs)

    # -- properties -----------------------------------------------------------------

    @property
    def address(self) -> str:
        return "%s:%d" % (self.host, self.port)

    @property
    def api(self):
        if self._api is None:
            from ._dotnet import load_dotnet_api

            self._api = load_dotnet_api(self._dll_dir, runtime=self._runtime)
        return self._api

    @property
    def native(self):
        """The underlying .NET ``Session`` (escape hatch for unwrapped features)."""
        return self._require()

    @property
    def aztec_is_local(self) -> bool:
        """True when AZtec runs on this machine (real API, loopback address), so
        AZtec-side paths can be checked locally before sending them."""
        return bool(getattr(self.api, "uses_network", False)) and self.host.lower() in (
            "127.0.0.1",
            "localhost",
            "::1",
        )

    @property
    def is_connected(self) -> bool:
        n = self._native
        if n is None:
            return False
        try:
            return bool(n.IsConnected)
        except Exception:
            return False

    def _require(self):
        n = self._native
        if n is None:
            raise NotConnectedError("Not connected to AZtec (call connect())")
        return n

    # -- connect / disconnect ------------------------------------------------------------

    def connect(self, preflight: bool = True) -> "AztecSession":
        """Connect to AZtec. Raises AztecConnectionError with a diagnostic hint."""
        with self._lock:
            if self._native is not None:
                return self
            api = self.api
            hint = _CONNECT_HINT.format(addr=self.address, port=self.port)
            if (
                preflight
                and getattr(api, "uses_network", False)
                and not check_port(self.host, self.port)
            ):
                raise AztecConnectionError(
                    "Nothing is listening at %s. %s" % (self.address, hint)
                )
            log.info("Connecting to AZtec at %s", self.address)
            try:
                native = api.Session.Connect(self.address)
            except Exception as e:
                raise AztecConnectionError(
                    "Could not connect to AZtec at %s: %s. %s"
                    % (self.address, api.message(e), hint)
                ) from e
            if native is None:
                raise AztecConnectionError(
                    "Could not connect to AZtec at %s. %s" % (self.address, hint)
                )
            self._native = native
            log.info(
                "Connected to AZtec %s (client %s)",
                self.server_version,
                self.client_version,
            )
            return self

    def disconnect(self):
        """Release the acquisition client and detector controls, then disconnect.
        Safe to call more than once; never raises."""
        with self._lock:
            if self._native is None:
                return
            if self.retract_on_disconnect and self._native is not None:
                try:
                    errs = self.detectors.retract_all()
                    for e in errs:
                        log.error("Retract on disconnect: %s", e)
                except Exception:
                    log.exception("Retract on disconnect failed")
            if self._acquisition is not None:
                if self._acquisition.is_running:
                    log.warning(
                        "Disconnecting while an acquisition is running; stopping it"
                    )
                    try:
                        self._acquisition.stop(immediate=True)
                    except Exception:
                        log.exception("Stop on disconnect failed")
                self._acquisition.release()
                self._acquisition = None
            if self._detectors is not None:
                self._detectors.close()
                self._detectors = None
            self._data = None
            native, self._native = self._native, None
            try:
                self.api.Session.Disconnect(native)
            except Exception as e:
                log.warning("Disconnect reported: %s", self.api.message(e))
            log.info("Disconnected from AZtec at %s", self.address)

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.disconnect()
        return False

    # -- controllers --------------------------------------------------------------------------

    @property
    def detectors(self) -> DetectorManager:
        with self._lock:
            self._require()
            if self._detectors is None:
                self._detectors = DetectorManager(self, interlock=self._interlock)
            return self._detectors

    @property
    def ebsd(self) -> EbsdDetector:
        """Shortcut for ``detectors.ebsd()`` (first EBSD detector)."""
        return self.detectors.ebsd()

    @property
    def eds(self) -> EdsDetector:
        """Shortcut for ``detectors.eds()`` (first EDS detector)."""
        return self.detectors.eds()

    @property
    def acquisition(self) -> AcquisitionController:
        """The acquisition controller. Created on first use; this takes the AZtec
        acquisition lock (AZtec's Start buttons are disabled until release)."""
        with self._lock:
            self._require()
            if self._acquisition is None:
                self._acquisition = AcquisitionController(self)
            return self._acquisition

    def release_acquisition(self):
        """Give the acquisition lock back to the AZtec UI without disconnecting."""
        with self._lock:
            if self._acquisition is not None:
                self._acquisition.release()
                self._acquisition = None

    @property
    def data(self) -> DataManager:
        with self._lock:
            self._require()
            if self._data is None:
                self._data = DataManager(self)
            return self._data

    # -- single scan (entry point for higher-level control software) -------------------------

    def scan(
        self,
        description: str,
        config: Optional[AcquisitionConfig] = None,
        *,
        item_name: Optional[str] = None,
        timeout="auto",
        require_patterns: bool = True,
        export_timeout: float = 3600.0,
    ) -> ScanResult:
        """Acquire one scan and have AZtec export every map it produced.

        Files land in the current project's ``data`` folder (choose its location with
        ``data.create_project(name, folder)``), written by AZtec itself:

        * EBSD map: ``{description}_{short_id}.h5oina`` next to ``<map id>.ebsp``
        * EDS map:  ``{description}_{short_id}.h5oina``

        ``short_id`` is the first 8 hex digits of that map's id, so each .h5oina visibly
        pairs with its .ebsp. A sequence (e.g. EBSD_MAP | EDS_MAP) gives one file per map.
        An EDS map created through AZtec's "Include EDS" option is exported too.

        ``description`` may contain anything; characters Windows forbids in file names
        become "_". It's validated before acquiring. ``item_name`` names the AZtec data
        item (default: the description; AZtec may append a counter). Detector insertion
        is the caller's job, as is pattern saving (an AZtec GUI/profile setting). With
        ``require_patterns`` (default) an EBSD export whose .ebsp is missing fails;
        that can only be checked when the project folder is visible from this machine.

        Raises AcquisitionError if the acquisition fails. Raises ScanExportError if any
        export fails, after attempting the others; ``.scan_result`` lists what was written.
        """
        from .data import windows_safe

        desc = windows_safe(description or "")
        if not desc:
            raise ValueError(
                "description must contain at least one valid file-name character"
            )
        config = config or AcquisitionConfig()
        result = self.acquisition.run(config, name=item_name or desc, timeout=timeout)
        out = ScanResult(description=desc, acquisition=result)
        maps = []
        if result.ebsd_map_id is not None:
            maps.append((result.ebsd_map_id, DataType.EBSD_MAP))
        if result.eds_map_id is not None and result.eds_map_id != result.ebsd_map_id:
            maps.append((result.eds_map_id, DataType.ED_MAP))
        if not maps:
            raise ScanExportError(
                "Scan %r finished but AZtec reported no EBSD/EDS map to export "
                "(acquisition type %s)" % (desc, config.acquisition_type),
                out,
            )
        errors = []
        for map_id, dtype in maps:
            try:
                out.files.append(
                    self.data.export_to_project(
                        map_id,
                        scan_name="{description}_{short_id}",
                        fields={"description": desc},
                        data_type=dtype,
                        require_patterns=require_patterns,
                        timeout=export_timeout,
                    )
                )
            except AztecError as e:
                errors.append(
                    "%s map %s: %s"
                    % ("EBSD" if dtype == DataType.EBSD_MAP else "EDS", map_id, e)
                )
        if errors:
            raise ScanExportError(
                "Scan %r: %d of %d exports failed: %s"
                % (desc, len(errors), len(maps), "; ".join(errors)),
                out,
            )
        log.info("Scan %r done: %s", desc, ", ".join(out.paths))
        return out

    # -- status -------------------------------------------------------------------------------

    @property
    def client_version(self) -> Optional[str]:
        try:
            return str(self._require().ClientVersion)
        except Exception:
            return None

    @property
    def server_version(self) -> Optional[str]:
        try:
            return str(self._require().ServerVersion)
        except Exception:
            return None

    def ping(self) -> bool:
        """Liveness check: the session reports connected and the server version can be
        read. False if the link is dead. Never raises."""
        if self._native is None:
            return False
        try:
            return (
                bool(self._native.IsConnected)
                and self._native.ServerVersion is not None
            )
        except Exception as e:
            log.warning("Ping failed: %s", self.api.message(e))
            return False

    def technique_readiness(self, technique: AcquisitionType) -> TechniqueReadiness:
        """AZtec's readiness report for EDS_MAP or EBSD_MAP."""
        native = self._require()
        try:
            s = native.GetDetectorStatus(self.api.to_net(AcquisitionType(technique)))
            return TechniqueReadiness(
                bool(s.IsDetectorReady), s.StatusDescription or None
            )
        except Exception as e:
            return TechniqueReadiness(None, self.api.message(e))

    def status(self, include_detectors: bool = True) -> SystemStatus:
        """Gather connection, readiness and detector state. Never raises."""
        st = SystemStatus(connected=self.ping(), address=self.address)
        if not st.connected:
            st.errors.append(
                "not connected" if self._native is None else "connection not responding"
            )
            return st
        st.client_version = self.client_version
        st.server_version = self.server_version
        for attr, tech in (
            ("eds", AcquisitionType.EDS_MAP),
            ("ebsd", AcquisitionType.EBSD_MAP),
        ):
            setattr(st, attr, self.technique_readiness(tech))
        if include_detectors:
            try:
                st.detectors = self.detectors.statuses()
                st.errors.extend(
                    "%s: %s" % (d.info.name, d.error) for d in st.detectors if d.error
                )
            except Exception as e:
                st.errors.append("detectors: %s" % e)
        if self._acquisition is not None:
            st.acquisition_running = self._acquisition.is_running
            try:
                st.current_site = self._acquisition.current_site
            except Exception as e:
                st.errors.append("current site: %s" % e)
        return st

    def __repr__(self):
        return "<AztecSession %s %s>" % (
            self.address,
            "connected" if self._native is not None else "disconnected",
        )
