"""Map acquisition (EBSD maps, EDS maps, electron images) via the plugin
``IAcquisitionClient``.

Holding the acquisition client disables the Start buttons in the AZtec UI, so the
controller should be released (``release()`` or session disconnect) when done.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Callable, Dict, List, Optional, Union

from ._events import EventWaiter, safe, subscribe, translate, wait_interruptibly
from .enums import (
    AcquisitionState,
    AcquisitionType,
    DataType,
    EdResultType,
    ProfileChangeState,
    coerce,
)
from .errors import (
    AcquisitionBusyError,
    AcquisitionError,
    AcquisitionTimeoutError,
)
from .models import AcquisitionConfig, AcquisitionProgress, AcquisitionResult, ProfileInfo

log = logging.getLogger(__name__)

#: AZtec needs a moment after one acquisition finishes before it accepts the next
#: (the SDK sample sleeps 1 s); starting too early finishes immediately with ERROR.
DEFAULT_SETTLE_S = 1.0
_EVENTS = ("started", "acquired", "progress", "finished")


class AcquisitionJob:
    """Handle for one running acquisition."""

    def __init__(self, controller: "AcquisitionController", config: AcquisitionConfig, name: Optional[str]):
        self._ctl = controller
        self.config = config
        self.name = name
        self.started_at = time.time()
        self.progress: Optional[AcquisitionProgress] = None
        #: State from the "Acquired" event (acquisition done, processing may continue).
        self.acquired_state: Optional[AcquisitionState] = None
        self.result: Optional[AcquisitionResult] = None
        self._done = threading.Event()
        #: Map ids in the data tree before starting, per DataType (for the id fallback).
        self._ids_before: Dict = {}
        self._ids_checked = False

    def done(self) -> bool:
        return self._done.is_set()

    def wait(self, timeout: Optional[float] = None) -> AcquisitionResult:
        """Block until the experiment finishes (data processing complete)."""
        if not wait_interruptibly(self._done, timeout):
            raise AcquisitionTimeoutError(
                "Acquisition %r did not finish within %s s (last progress: %s)"
                % (self.name, timeout, self.progress))
        if not self._ids_checked:
            # Runs on the caller's thread: querying AZtec from inside the .NET
            # Finished callback could deadlock the WCF duplex channel.
            self._ids_checked = True
            self._ctl._fill_missing_ids(self)
        return self.result

    def stop(self, immediate: bool = False):
        self._ctl.stop(immediate=immediate)

    def _complete(self, result: AcquisitionResult):
        self.result = result
        self._done.set()

    def __repr__(self):
        return "<AcquisitionJob %s name=%r done=%s progress=%s>" % (
            self.config.acquisition_type, self.name, self.done(), self.progress)


class AcquisitionController:
    """Configure, start, stop and wait for plugin acquisitions."""

    def __init__(self, session):
        self._session = session
        self._api = session.api
        native = session._require()
        with translate(self._api, AcquisitionBusyError,
                       "Get acquisition client (is another plugin client holding the acquisition lock?)"):
            self._client = native.GetAcquisitionClient()
        self.settle_time_s = DEFAULT_SETTLE_S
        self._job: Optional[AcquisitionJob] = None
        self._lock = threading.Lock()
        self._last_finished = 0.0
        self._listeners: Dict[str, List[Callable]] = {k: [] for k in _EVENTS}
        self._unsubs = [
            subscribe(self._client, "Starting", safe(self._on_starting, "Starting")),
            subscribe(self._client, "Acquired", safe(self._on_acquired, "Acquired")),
            subscribe(self._client, "ProgressChanged", safe(self._on_progress, "ProgressChanged")),
            subscribe(self._client, "Finished", safe(self._on_finished, "Finished")),
        ]
        self._released = False

    @property
    def native(self):
        """The underlying .NET IAcquisitionClient (escape hatch)."""
        self._check()
        return self._client

    def _check(self):
        if self._released:
            raise AcquisitionError("Acquisition client has been released")

    # -- listeners --------------------------------------------------------------

    def add_listener(self, event: str, fn: Callable) -> Callable[[], None]:
        """Register a callback. Events and callback args:

        * ``"started"``  -> fn(job)
        * ``"acquired"`` -> fn(job, AcquisitionState)
        * ``"progress"`` -> fn(job, AcquisitionProgress)
        * ``"finished"`` -> fn(job, AcquisitionResult)

        Callbacks run on a .NET thread; keep them short. Returns a remover.
        """
        if event not in self._listeners:
            raise ValueError("event must be one of %s" % (_EVENTS,))
        self._listeners[event].append(fn)
        return lambda: self._listeners[event].remove(fn) if fn in self._listeners[event] else None

    def _emit(self, event, *args):
        for fn in list(self._listeners[event]):
            try:
                fn(*args)
            except Exception:
                log.exception("Error in %s listener", event)

    # -- .NET event handlers (run on .NET threads) ----------------------------------

    def _on_starting(self, sender, args):
        job = self._job
        log.info("Acquisition starting: %s", job)
        if job:
            self._emit("started", job)

    def _on_acquired(self, sender, args):
        job = self._job
        state = coerce(AcquisitionState, args.AcquisitionState)
        if job:
            job.acquired_state = state
            self._emit("acquired", job, state)

    def _on_progress(self, sender, args):
        p = args.AcquisitionProgress
        prog = AcquisitionProgress(int(p.ProgressPercentage), int(p.EstimatedSecondsToCompletion))
        job = self._job
        if job:
            job.progress = prog
            self._emit("progress", job, prog)

    def _on_finished(self, sender, args):
        job = self._job
        result = self._to_result(args.AcquisitionStatus, job)
        log.info("Acquisition finished: %s", result)
        with self._lock:
            self._last_finished = time.monotonic()
            self._job = None
        if job:
            job._complete(result)
            self._emit("finished", job, result)

    def _to_result(self, status, job: Optional[AcquisitionJob]) -> AcquisitionResult:
        api = self._api
        images = {}
        for key, attr in (("electron_image", "ElectronImage"), ("eds_map", "EdsMap"), ("ebsd_map", "EbsdMap")):
            b = api.to_bytes(getattr(status, attr, None))
            if b:
                images[key] = b
        err = getattr(status, "Error", None)
        return AcquisitionResult(
            state=coerce(AcquisitionState, status.State),
            item_name=status.AcquiredItemName or None,
            message=status.Message or None,
            error=api.message(err) if err is not None else None,
            eds_map_id=api.uuid(status.EdsMapId),
            ebsd_map_id=api.uuid(status.EbsdMapId),
            images=images,
            acquisition_type=job.config.acquisition_type if job else AcquisitionType.NONE,
            started_at=job.started_at if job else None,
            finished_at=time.time(),
        )

    # -- configuration ----------------------------------------------------------------

    @property
    def current_site(self) -> Optional[str]:
        """Name of the site currently selected in the AZtec data tree."""
        self._check()
        with translate(self._api, AcquisitionError, "Read current site"):
            return self._client.CurrentSite or None

    @property
    def aspect_ratio(self) -> float:
        """Field-of-view aspect ratio (width / height); use it to build square regions."""
        self._check()
        with translate(self._api, AcquisitionError, "Read aspect ratio"):
            return float(self._client.AspectRatio)

    def configure(self, config: AcquisitionConfig):
        """Push settings to the acquisition client.

        Always sent: acquisition type, region (``None`` = full field), project and
        specimen (``None`` = the ones selected in AZtec), master site number
        (``None`` = continue from the current site). Every other ``None`` field is
        left unchanged. Technique settings (binning, pattern size, step size,
        resolution, dwell...) are never touched; the plugin API cannot set them.
        """
        self._check()
        c, api = self._client, self._api
        log.info("Sending to AZtec: type=%s region=%s site=%s project=%s specimen=%s autolock=%s "
                 "status_images=%s master_site=%s",
                 config.acquisition_type, config.region or "full field",
                 "<current>" if config.use_current_site else (config.site_name or "<unchanged>"),
                 config.project_id or "<selected>", config.specimen_id or "<selected>",
                 config.auto_lock.name if config.auto_lock is not None else "<unchanged>",
                 config.status_images if config.status_images is not None else "<unchanged>",
                 config.master_site_number)
        with translate(api, AcquisitionError, "Configure acquisition"):
            c.AcquisitionType = api.to_net(config.acquisition_type)
            c.AcquisitionRegion = api.region(config.region)  # None = full field
            if config.use_current_site:
                c.SiteName = c.CurrentSite
            elif config.site_name is not None:
                c.SiteName = config.site_name
            c.ProjectId = api.guid(config.project_id)
            c.SpecimenId = api.guid(config.specimen_id)
            if config.auto_lock is not None:
                c.AutoLockMode = api.to_net(config.auto_lock)
            if config.status_images is not None:
                c.StatusImageTypes = api.to_net(config.status_images)
            # Nullable<int>: None means "continue from current site"; set it every time
            # so a value from a previous config doesn't silently persist.
            c.MasterSiteNumber = config.master_site_number
            if config.auto_increment_site_number is not None:
                c.IsAutoIncrementSiteNumber = bool(config.auto_increment_site_number)
            if config.reset_acquisition_number_for_each_site is not None:
                c.IsResetAcquisitionNumberForEachSite = bool(config.reset_acquisition_number_for_each_site)
            if config.site_thickness_um is not None:
                c.SiteThickness = float(config.site_thickness_um)
            if config.auto_contrast_brightness is not None:
                c.IsAutoContrastBrightness = bool(config.auto_contrast_brightness)
            if config.english_image_names is not None:
                c.IsAllEnglishInImageName = bool(config.english_image_names)

    def estimate_time(self, acquisition_type: Optional[AcquisitionType] = None) -> Optional[float]:
        """AZtec's estimated acquisition time in seconds for the given technique(s),
        or None if AZtec can't estimate it (e.g. technique not configured)."""
        native = self._session._require()
        try:
            if acquisition_type is None:
                return self._api.seconds(native.GetAcquisitionTime())
            return self._api.seconds(native.GetAcquisitionTime(self._api.to_net(AcquisitionType(acquisition_type))))
        except Exception as e:
            log.warning("Could not estimate acquisition time: %s", self._api.message(e))
            return None

    # -- profiles (the plugin's way to switch technique parameters) -------------------

    def profiles(self) -> List[ProfileInfo]:
        native = self._session._require()
        with translate(self._api, AcquisitionError, "List profiles"):
            return [ProfileInfo(str(p.Name), self._api.uuid(p.Id), p.Description or None)
                    for p in list(native.Profiles)]

    def _find_profile(self, profile: Union[str, uuid.UUID, ProfileInfo]) -> ProfileInfo:
        if isinstance(profile, ProfileInfo):
            return profile
        for p in self.profiles():
            if profile in (p.name, p.id) or (isinstance(profile, str) and p.id and profile == str(p.id)):
                return p
        raise AcquisitionError("No AZtec profile named %r" % (profile,))

    def load_profile(self, profile: Union[str, uuid.UUID, ProfileInfo], timeout: float = 60.0) -> ProfileInfo:
        """Load a saved AZtec settings profile (by name, id or ProfileInfo) and wait
        for AZtec to confirm. This is how technique parameters (step size, dwell,
        resolution, binning, pattern saving...) are switched through the plugin.

        This REPLACES the current AZtec settings, including any unsaved changes made
        in the GUI. To keep GUI changes, re-save the profile in AZtec first, or
        don't load one.
        """
        p = self._find_profile(profile)
        log.warning("Loading AZtec profile %r: this replaces the current AZtec settings", p.name)
        native = self._session._require()
        with EventWaiter(native, "ProfileStateChanged") as w:
            with translate(self._api, AcquisitionError, "Load profile %r" % p.name):
                native.LoadProfile(self._api.guid(p.id))
            try:
                args = w.wait(timeout)
            except TimeoutError:
                raise AcquisitionTimeoutError("AZtec did not confirm loading profile %r" % p.name)
        state = coerce(ProfileChangeState, args.Status)
        if state != ProfileChangeState.LOADED:
            raise AcquisitionError("Loading profile %r failed: %s %s" % (p.name, state.name, args.Message or ""))
        return p

    def create_profile(self, name: str):
        """Save AZtec's current settings as a new profile."""
        native = self._session._require()
        with translate(self._api, AcquisitionError, "Create profile %r" % name):
            native.CreateProfile(name)

    # -- run ------------------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._job is not None

    @property
    def current_job(self) -> Optional[AcquisitionJob]:
        return self._job

    def start(self, config: Optional[AcquisitionConfig] = None, name: Optional[str] = None) -> AcquisitionJob:
        """Start an acquisition and return immediately with a job handle.

        ``name`` names the new data item in the AZtec tree (auto-named if None).
        If ``config`` is None the client's current settings are used.
        """
        self._check()
        config = config or AcquisitionConfig()
        with self._lock:
            if self._job is not None:
                raise AcquisitionBusyError("An acquisition is already running: %r" % self._job)
            wait = self.settle_time_s - (time.monotonic() - self._last_finished)
        if wait > 0:
            time.sleep(wait)
        self.configure(config)
        job = AcquisitionJob(self, config, name)
        job._ids_before = self._snapshot_map_ids(config.acquisition_type)
        with self._lock:
            self._job = job  # set before starting: Finished may fire before StartAcquisition returns
        try:
            with translate(self._api, AcquisitionError, "Start acquisition"):
                if name:
                    self._client.StartAcquisition(name)
                else:
                    self._client.StartAcquisition()
        except Exception:
            with self._lock:
                if self._job is job:
                    self._job = None
            raise
        log.info("Started %s acquisition%s", config.acquisition_type, " %r" % name if name else "")
        return job

    # -- map id fallback ---------------------------------------------------------------

    @staticmethod
    def _tracked_maps(acquisition_type: AcquisitionType):
        """(result attribute, data type, required) for the maps an acquisition can create.
        An EBSD map may also produce an EDS map (AZtec's "Include EDS"), so EBSD scans
        watch for one too, as optional."""
        tracked = {}
        if acquisition_type & AcquisitionType.EBSD_MAP:
            tracked["ebsd_map_id"] = (DataType.EBSD_MAP, True)
            tracked["eds_map_id"] = (DataType.ED_MAP, False)
        if acquisition_type & AcquisitionType.EDS_MAP:
            tracked["eds_map_id"] = (DataType.ED_MAP, True)
        return [(attr, dtype, req) for attr, (dtype, req) in tracked.items()]

    def _snapshot_map_ids(self, acquisition_type: AcquisitionType) -> Dict:
        snap = {}
        for _, dtype, _ in self._tracked_maps(acquisition_type):
            try:
                snap[dtype] = {it.id for it in self._session.data.items(dtype)}
            except Exception as e:
                log.debug("Could not snapshot %s items: %s", dtype.name, e)
        return snap

    def _fill_missing_ids(self, job: AcquisitionJob):
        """AZtec doesn't always put the new map ids in the acquisition status (seen
        when no status images were requested). Recover them by diffing the data tree
        against the pre-start snapshot; the acquisition lock means any new map is ours."""
        r = job.result
        if r is None or not r.ok:
            return
        for attr, dtype, required in self._tracked_maps(job.config.acquisition_type):
            if getattr(r, attr) is not None:
                continue
            before = job._ids_before.get(dtype)
            if before is None:
                continue
            try:
                new = [it for it in self._session.data.items(dtype) if it.id not in before]
            except Exception as e:
                log.warning("Could not look up the new %s in the data tree: %s", dtype.name, e)
                continue
            if len(new) > 1 and r.item_name:
                named = [it for it in new if r.item_name in it.label]
                new = named or new
            if len(new) == 1:
                setattr(r, attr, new[0].id)
                r.ids_from_tree = True
                log.warning("AZtec's status had no %s; found it in the data tree: %s (%s)",
                            attr, new[0].label, new[0].id)
            elif required or new:
                log.warning("AZtec's status had no %s and the data tree has %d new %s items; "
                            "leaving it unset", attr, len(new), dtype.name)

    def stop(self, immediate: bool = False):
        """Stop the running acquisition. Maps stop at end of frame unless
        ``immediate`` (AZtec treats a second stop call as "stop now")."""
        self._check()
        with translate(self._api, AcquisitionError, "Stop acquisition"):
            self._client.StopAcquisition()
            if immediate:
                self._client.StopAcquisition()

    def run(self, config: Optional[AcquisitionConfig] = None, name: Optional[str] = None,
            timeout: Union[float, str, None] = "auto", raise_on_error: bool = True,
            stop_on_timeout: bool = True) -> AcquisitionResult:
        """Start an acquisition and block until it finishes.

        ``timeout="auto"`` uses AZtec's estimate x1.5 + 5 min (no limit if AZtec can't
        estimate); ``None`` waits forever. On timeout or Ctrl+C the acquisition is
        stopped (if ``stop_on_timeout``) before the error propagates.
        """
        config = config or AcquisitionConfig()
        if timeout == "auto":
            est = self.estimate_time(config.acquisition_type)
            timeout = est * 1.5 + 300.0 if est else None
        job = self.start(config, name)
        try:
            result = job.wait(timeout)
        except (AcquisitionTimeoutError, KeyboardInterrupt):
            if stop_on_timeout:
                log.warning("Stopping acquisition after timeout/interrupt")
                try:
                    self.stop(immediate=True)
                except Exception:
                    log.exception("Stop failed")
            raise
        if raise_on_error and not result.ok:
            raise AcquisitionError("Acquisition finished with %s: %s %s" % (
                result.state.name, result.message or "", result.error or ""), result)
        return result

    def run_series(self, configs: List[AcquisitionConfig], names: Optional[List[Optional[str]]] = None,
                   **run_kwargs) -> List[AcquisitionResult]:
        """Run acquisitions back-to-back (with the settle delay between them)."""
        names = names or [None] * len(configs)
        if len(names) != len(configs):
            raise ValueError("names must match configs")
        return [self.run(c, n, **run_kwargs) for c, n in zip(configs, names)]

    # -- EDS data ----------------------------------------------------------------------------

    def get_ed_data(self, item_id: uuid.UUID, result_type: EdResultType = EdResultType.COUNTS):
        """Raw .NET IEdMapData/IEdLineData for an acquired EDS map/line id.
        Prefer :meth:`DataManager.eds_data`, which converts to numpy."""
        self._check()
        with translate(self._api, AcquisitionError, "Get EDS data"):
            return self._api.impl(self._client.GetAcquiredEdData(self._api.guid(item_id),
                                                                 self._api.to_net(result_type)))

    # -- teardown ----------------------------------------------------------------------------

    def release(self):
        """Release the acquisition client (re-enables AZtec's Start buttons)."""
        if self._released:
            return
        if self._job is not None:
            log.warning("Releasing acquisition client while an acquisition is running")
        for u in self._unsubs:
            u()
        self._unsubs = []
        native = self._session._native
        try:
            if native is not None:
                native.ReleaseAcquisitionClient(self._client)
            else:
                self._client.Release()
        except Exception as e:
            log.warning("Release acquisition client failed: %s", self._api.message(e))
        self._released = True
