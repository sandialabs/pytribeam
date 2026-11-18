"""
Bruker ESPRIT adapter
=====================

Native Bruker backend, through the ESPRIT API DLL
(`pytribeam.external_oem.bruker`). Bruker has no LaserControl fallback.

Only what varies is configured:

- `Bruker_settings` (once per instrument): DLL folder, local/TCP connection,
  EDS detector index, and whether pyTriBeam moves the EDS detector.
- each EDS/EBSD step's `bruker_settings`: output folder and map size/dwell
  (plus, for EBSD, the ESPRIT acquisition profile and pattern saving).

Everything else ESPRIT needs is a fixed default below, as in the custom-step
version that preceded this adapter. The vendor's own EDS settings are built
from them with `bruker.config.parse_bruker_eds_config`, so the vendor's
validation still applies.

Sessions: closing an ESPRIT API connection can grey out parts of the ESPRIT
GUI, so one session per instrument is kept open for the life of the process,
re-checked before each use, and reconnected if it dropped.

EDS output: ESPRIT saves the native `.bcf` HyperMap and a `.bmp` overview per
map under the step's `output_path`. Element maps are not read back.

EBSD runs on the existing scaffold and is not yet validated on hardware. The
ESPRIT API positions the EBSD camera in millimeters only, so the camera's
measured inserted and retracted positions are required in `Bruker_settings`
for Bruker EBSD; its state is classified against them.

See the adapter contract in `pytribeam.external_oem.dispatch`.
"""

# Default python modules
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional

# Local scripts
import pytribeam.types as tbt
from pytribeam.constants import Constants
from pytribeam.external_oem.bruker.config import parse_bruker_eds_config
from pytribeam.external_oem.bruker.detector_motion import (
    BrukerDetectorMotionController,
)
from pytribeam.external_oem.bruker.ebsd import BrukerEBSDController
from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.image_config import BrukerImageConfigController
from pytribeam.external_oem.bruker.output import make_run_paths, now_stamp
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.spectrometer import BrukerSpectrometerController
from pytribeam.external_oem.bruker.types import (
    BrukerDetectorMotionSettings,
    BrukerEBSDAcquisitionSettings,
    BrukerEBSDDetectorMotionSettings,
    BrukerEBSDScanAreaSettings,
    BrukerEDSOutputSettings,
    BrukerEDSProfileMapSettings,
    BrukerEDSWorkflowSettings,
    BrukerSessionSettings,
)
from pytribeam.external_oem.core.errors import ConfigurationError, DetectorError

STATE = tbt.RetractableDeviceState

# ----------------------------------------------------------------------
# Fixed defaults (not configured)
# ----------------------------------------------------------------------

SERVER = "Lokaler Server"
USER = "edx"
PASSWORD = "edx"
DETECTOR_MOVE_TIMEOUT_S = 60.0
POLL_INTERVAL_S = 2.0
EBSD_CAMERA_SPEED_MM_PER_S = 2.0
EBSD_CAMERA_STABLE_POLLS = 2

#: The HyperMap profile needs at least one element. Element maps are not read
#: back; the .bcf holds the full spectra.
PLACEHOLDER_ELEMENT = {
    "atomic_number": 6,
    "symbol": "C",
    "line": "KA",
    "energy_keV": 0.0,
    "width": 1.0,
}
PROFILE_OPTIONS = {
    "image_filter": 0,
    "map_filter": 0,
    "map_filter_width": 3,
    "color_mix_method": 0,
    "brightness": 0.0,
    "gamma": 1.0,
    "color_saturation": 1.0,
    "absolute_scaling": False,
    "normalization": True,
    "deconvolution": False,
}

#: A map may take this multiple of its nominal time (pixels x dwell), and
#: never less than the floor, before it is abandoned.
MAP_WAIT_SCALAR = 3.0
MIN_EDS_MAP_WAIT_S = 600.0
MIN_EBSD_MAP_WAIT_S = 3600.0

#: EBSD functions the scaffold needs from the DLL.
_EBSD_REQUIRED_EXPORTS = (
    "has_get_profiles",
    "has_select_profile",
    "has_start_acquisition",
    "has_stop_acquisition",
    "has_get_state",
    "has_save_to_file",
    "has_get_detector_position",
    "has_set_detector_position",
    "has_image_set_configuration",
)

#: ESPRIT EDS detector position name as pyTriBeam's generic device state.
_EDS_POSITION_STATE = {"acquire": STATE.INSERTED, "park": STATE.RETRACTED}


def session_settings(config: tbt.BrukerConfig) -> BrukerSessionSettings:
    """ESPRIT session settings: the configured connection plus fixed defaults."""
    return BrukerSessionSettings(
        dll_dir=str(config.dll_dir),
        mode=config.mode.value,
        server=SERVER,
        user=USER,
        password=PASSWORD,
        host=config.host,
        port=config.port,
        close_on_exit=False,
        keep_connection_open=True,
    )


def map_wait_s(map_settings: tbt.BrukerMapSettings, floor_s: float) -> float:
    """Longest a map of this size and dwell may take."""
    nominal_s = map_settings.width_px * map_settings.height_px * map_settings.dwell_us
    return max(floor_s, MAP_WAIT_SCALAR * nominal_s * 1e-6)


def eds_workflow_settings(
    config: tbt.BrukerConfig,
    step: tbt.BrukerEDSStepSettings,
    slice_number: Optional[int] = None,
) -> BrukerEDSWorkflowSettings:
    """
    The vendor's complete EDS settings for one step (and slice).

    Built as the standalone Bruker EDS YAML would be, then parsed, so the
    vendor's validation (ROI bounds, element ranges, ...) still applies.
    """
    map_name = "preflight" if slice_number is None else f"{slice_number:04d}"
    db = {
        "session": session_settings(config)._asdict(),
        "output": {
            "root_dir": str(step.output_path),
            "run_name": step.run_name,
        },
        "detector": {
            "detector_index": config.detector_index,
            "move_detector": config.move_detector,
            "move_timeout_s": DETECTOR_MOVE_TIMEOUT_S,
            "poll_interval_s": POLL_INTERVAL_S,
        },
        "map": {
            "mode": "profile",
            "name": map_name,
            "width_px": step.map.width_px,
            "height_px": step.map.height_px,
            "pixel_time_us": step.map.dwell_us,
            "real_time_s": 0,
            "spu_device": config.detector_index,
            "save_bcf": True,
            "save_image": True,
            "image_format": "bmp",
            "poll_interval_s": POLL_INTERVAL_S,
            "max_wait_s": map_wait_s(step.map, MIN_EDS_MAP_WAIT_S),
            "profile": {"elements": [dict(PLACEHOLDER_ELEMENT)], **PROFILE_OPTIONS},
        },
        "readback": {
            "save_element_npy": False,
            "save_element_images": False,
            "log_element_stats": False,
        },
    }
    settings = parse_bruker_eds_config(db)
    if slice_number is not None:
        settings = settings._replace(
            output=settings.output._replace(slice_number=slice_number)
        )
    return settings


# ----------------------------------------------------------------------
# Sessions and errors
# ----------------------------------------------------------------------


def _new_session(settings: BrukerSessionSettings) -> BrukerSession:
    try:
        # Loads the ESPRIT DLL. Off Windows, or with a wrong dll_dir, this fails
        # with whatever ctypes / os raise, so report all of them the same way.
        session = BrukerSession(settings)
    except Exception as error:
        raise DetectorError(
            f"Could not load the Bruker ESPRIT API from '{settings.dll_dir}': "
            f"{type(error).__name__}: {error}"
        ) from error
    session.connect()
    return session


#: Builds and connects a session. Replaced in tests.
session_factory: Callable[[BrukerSessionSettings], BrukerSession] = _new_session

#: Open sessions, keyed by their settings.
_SESSIONS: Dict[BrukerSessionSettings, BrukerSession] = {}


@contextmanager
def _as_detector_error() -> Iterator[None]:
    """Re-raise the Bruker wrapper's plain exceptions as DetectorError."""
    try:
        yield
    except DetectorError:
        raise
    except (RuntimeError, TimeoutError, OSError, ValueError) as error:
        raise DetectorError(f"{type(error).__name__}: {error}") from error


@contextmanager
def _session(general_settings: tbt.GeneralSettings) -> Iterator[BrukerSession]:
    """Yield a live session, reusing the open one when it still answers."""
    settings = session_settings(general_settings.Bruker_settings)
    with _as_detector_error():
        session = _SESSIONS.get(settings)
        if session is not None:
            try:
                session.check_connection()
            except DetectorError:
                _SESSIONS.pop(settings, None)
                session = None
        if session is None:
            session = session_factory(settings)
            _SESSIONS[settings] = session
        yield session


def close_sessions() -> None:
    """Close every open session (for shutdown and tests)."""
    while _SESSIONS:
        _, session = _SESSIONS.popitem()
        try:
            session.close()
        except Exception as error:  # closing is best effort
            print(f"\tWARNING: closing Bruker session failed: {error}")


def _step(step_settings, technique: str):
    """The step's Bruker settings, or a clear error if the step has none."""
    if step_settings.bruker is None:
        raise ConfigurationError(
            f"A Bruker {technique} step needs a 'bruker_settings' block "
            "(output_path and map width_px / height_px / dwell_us)."
        )
    return step_settings.bruker


# ----------------------------------------------------------------------
# Connection and preflight
# ----------------------------------------------------------------------


def test_connection(
    general_settings: tbt.GeneralSettings,
    technique: tbt.ExternalTechnique,
) -> bool:
    """Connect (or reuse the open session) and check ESPRIT answers."""
    with _session(general_settings) as session:
        with _as_detector_error():
            session.check_connection()
    return True


test_connection.__test__ = False


def _make_output_folders(steps) -> None:
    for step in steps:
        Path(step.output_path).mkdir(parents=True, exist_ok=True)


def preflight_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: List[tbt.EDSSettings],
) -> bool:
    """Check the spectrometer is ready and every step's output folder is writable."""
    config = general_settings.Bruker_settings
    steps = [_step(settings, "EDS") for settings in step_settings]
    with _session(general_settings) as session, _as_detector_error():
        status = BrukerSpectrometerController(session).get_spectrometer_status(
            spu=config.detector_index
        )
        if not status.ready:
            raise DetectorError(
                f"The Bruker spectrometer (SPU {config.detector_index}) is not "
                f"ready (status {status.status})."
            )
        _make_output_folders(steps)
    return True


def preflight_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: List[tbt.EBSDSettings],
) -> bool:
    """Check the camera positions are set, the DLL exports the EBSD functions,
    and each step's output folder is writable."""
    _camera_positions(general_settings.Bruker_settings)
    steps = [_step(settings, "EBSD") for settings in step_settings]
    with _session(general_settings) as session, _as_detector_error():
        exports = BrukerEBSDController(session).export_status()
        missing = [
            name for name in _EBSD_REQUIRED_EXPORTS if not getattr(exports, name)
        ]
        if missing:
            raise DetectorError(
                f"The ESPRIT API does not export the EBSD functions this needs: "
                f"{missing}"
            )
        _make_output_folders(steps)
    return True


# ----------------------------------------------------------------------
# EDS state and motion
# ----------------------------------------------------------------------


def _eds_position(session, config: tbt.BrukerConfig) -> tbt.RetractableDeviceState:
    position = BrukerDetectorMotionController(session).get_eds_detector_position(
        config.detector_index
    )
    return _EDS_POSITION_STATE.get(position.position_name, STATE.INDERTERMINATE)


def _move_eds(session, config: tbt.BrukerConfig, target: str) -> None:
    BrukerDetectorMotionController(session).move_eds_detector(
        BrukerDetectorMotionSettings(
            detector_index=config.detector_index,
            target_position=target,
            timeout_s=DETECTOR_MOVE_TIMEOUT_S,
            poll_interval_s=POLL_INTERVAL_S,
        )
    )


def get_eds_detector_state(
    general_settings: tbt.GeneralSettings,
) -> tbt.RetractableDeviceState:
    """``acquire`` reads as inserted and ``park`` as retracted.

    ESPRIT's "acquire" can cover several physical positions, so this is a
    safety check, not a guarantee of the working distance.
    """
    with _session(general_settings) as session, _as_detector_error():
        return _eds_position(session, general_settings.Bruker_settings)


def insert_eds_detector(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Move the EDS detector to acquire, from park.

    With `move_detector: false` (the ESPRIT simulator) the detector is not
    moved. The dispatcher checks for collisions and shows the chamber CCD.
    """
    config = general_settings.Bruker_settings
    if not config.move_detector:
        print("\tBruker EDS detector motion is disabled; not inserting.")
        return True
    with _session(general_settings) as session, _as_detector_error():
        state = _eds_position(session, config)
        if state == STATE.INSERTED:
            return True
        if state != STATE.RETRACTED:
            raise DetectorError(
                "The Bruker EDS detector is not parked, so it will not be moved."
            )
        _move_eds(session, config, "acquire")
    return True


def retract_eds_detector(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Park the EDS detector, from any position. Not moved if motion is disabled."""
    config = general_settings.Bruker_settings
    if not config.move_detector:
        print("\tBruker EDS detector motion is disabled; not parking.")
        return True
    with _session(general_settings) as session, _as_detector_error():
        if _eds_position(session, config) == STATE.RETRACTED:
            return True
        _move_eds(session, config, "park")
    return True


# ----------------------------------------------------------------------
# EBSD camera (not yet hardware-validated)
# ----------------------------------------------------------------------


def _camera_positions(config: tbt.BrukerConfig):
    inserted = config.ebsd_inserted_position_mm
    retracted = config.ebsd_retracted_position_mm
    if inserted is None or retracted is None:
        raise ConfigurationError(
            "Bruker EBSD needs the camera's measured positions: set "
            "Bruker_settings 'ebsd_inserted_position_mm' and "
            "'ebsd_retracted_position_mm'."
        )
    return inserted, retracted


def ebsd_state(
    position_mm: float, config: tbt.BrukerConfig
) -> tbt.RetractableDeviceState:
    """Classify an EBSD camera position against the configured positions."""
    inserted, retracted = _camera_positions(config)
    tolerance = Constants.bruker_ebsd_position_tolerance_mm
    if abs(position_mm - inserted) <= tolerance:
        return STATE.INSERTED
    if abs(position_mm - retracted) <= tolerance:
        return STATE.RETRACTED
    return STATE.INDERTERMINATE


def _move_ebsd(session, target_mm: float) -> None:
    result = BrukerEBSDController(session).move_detector_position_tolerant(
        BrukerEBSDDetectorMotionSettings(
            target_position_mm=target_mm,
            speed_mm_per_s=EBSD_CAMERA_SPEED_MM_PER_S,
            tolerance_mm=Constants.bruker_ebsd_position_tolerance_mm,
            timeout_s=DETECTOR_MOVE_TIMEOUT_S,
            poll_interval_s=POLL_INTERVAL_S,
            stable_polls=EBSD_CAMERA_STABLE_POLLS,
        )
    )
    if not result.within_tolerance:
        raise DetectorError(
            f"The Bruker EBSD camera stopped at {result.final_position_mm} mm, "
            f"not {target_mm} mm."
        )


def get_ebsd_camera_state(
    general_settings: tbt.GeneralSettings,
) -> tbt.RetractableDeviceState:
    config = general_settings.Bruker_settings
    _camera_positions(config)
    with _session(general_settings) as session, _as_detector_error():
        position = BrukerEBSDController(session).get_detector_position_mm()
    return ebsd_state(position, config)


def insert_ebsd_camera(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Move the EBSD camera to its inserted position, from retracted.

    The dispatcher checks for collisions and shows the chamber CCD.
    """
    config = general_settings.Bruker_settings
    inserted, _ = _camera_positions(config)
    with _session(general_settings) as session, _as_detector_error():
        position = BrukerEBSDController(session).get_detector_position_mm()
        state = ebsd_state(position, config)
        if state == STATE.INSERTED:
            return True
        if state != STATE.RETRACTED:
            raise DetectorError(
                f"The Bruker EBSD camera is at {position} mm, neither inserted nor "
                "retracted, so it will not be moved."
            )
        _move_ebsd(session, inserted)
    return True


def retract_ebsd_camera(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Move the EBSD camera to its retracted position, from any position."""
    config = general_settings.Bruker_settings
    _, retracted = _camera_positions(config)
    with _session(general_settings) as session, _as_detector_error():
        position = BrukerEBSDController(session).get_detector_position_mm()
        if ebsd_state(position, config) == STATE.RETRACTED:
            return True
        _move_ebsd(session, retracted)
    return True


# ----------------------------------------------------------------------
# Parameters
# ----------------------------------------------------------------------


def set_eds_parameters(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
) -> bool:
    """
    Apply the step's map size and dwell, and confirm ESPRIT accepted the size.

    Also has ESPRIT build the HyperMap profile, which rejects invalid settings
    before any data is collected.
    """
    settings = eds_workflow_settings(
        general_settings.Bruker_settings, _step(step_settings, "EDS")
    )
    map_settings = settings.map
    with _session(general_settings) as session, _as_detector_error():
        accepted = BrukerImageConfigController(session).set_image_configuration(
            map_settings.width_px, map_settings.height_px, map_settings.pixel_time_us
        )
        if (accepted.width_px, accepted.height_px) != (
            map_settings.width_px,
            map_settings.height_px,
        ):
            raise ConfigurationError(
                f"ESPRIT set the map to {accepted.width_px}x{accepted.height_px} "
                f"pixels, not the requested {map_settings.width_px}x"
                f"{map_settings.height_px}. Choose a size the hardware supports."
            )
        BrukerEDSController(session).create_hymap_profile(map_settings)
    return True


def _require_ebsd_profile(session, profile_name: str) -> None:
    profiles = BrukerEBSDController(session).get_profiles_raw()
    if profile_name not in profiles:
        raise ConfigurationError(
            f"ESPRIT has no EBSD acquisition profile named '{profile_name}' "
            "(the step's bruker_settings.profile_name)."
        )


def _scan_area(step: tbt.BrukerEBSDStepSettings) -> BrukerEBSDScanAreaSettings:
    return BrukerEBSDScanAreaSettings(
        width_px=step.map.width_px,
        height_px=step.map.height_px,
        pixel_time_us=step.map.dwell_us,
    )


def set_ebsd_parameters(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
) -> bool:
    """Configure the scan area and select the step's acquisition profile."""
    step = _step(step_settings, "EBSD")
    with _session(general_settings) as session, _as_detector_error():
        _require_ebsd_profile(session, step.profile_name)
        controller = BrukerEBSDController(session)
        controller.configure_scan_area(_scan_area(step))
        controller.select_profile(step.profile_name)
    return True


# ----------------------------------------------------------------------
# Mapping
# ----------------------------------------------------------------------


def map_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
    slice_number: int,
    on_metric: Callable[[str, float], None],
) -> bool:
    """
    Collect one EDS map; ESPRIT saves the ``.bcf`` and a ``.bmp`` overview.

    A missing ``.bcf`` afterwards is reported but does not stop the experiment
    (ESPRIT can hold the file briefly after saving it).
    """
    settings = eds_workflow_settings(
        general_settings.Bruker_settings,
        _step(step_settings, "EDS"),
        slice_number,
    )
    with _session(general_settings) as session, _as_detector_error():
        paths = make_run_paths(settings.output, now_stamp())
        map_settings = settings.map._replace(
            output_bcf_path=str(paths["bcf_path"]),
            output_image_path=str(paths["bmp_path"]),
            output_image_format=settings.output.image_format,
        )
        controller = BrukerEDSController(session)
        acquire = (
            controller.acquire_map_with_profile
            if isinstance(map_settings, BrukerEDSProfileMapSettings)
            else controller.acquire_map
        )
        outputs = acquire(
            settings=map_settings,
            poll_interval_s=map_settings.poll_interval_s,
            max_wait_s=map_settings.max_wait_s,
        )
    if not (outputs.output_bcf_path and Path(outputs.output_bcf_path).exists()):
        print(
            f"\tWARNING: Bruker EDS slice {slice_number}: no .bcf file found at "
            f"{outputs.output_bcf_path}"
        )
    return True


def map_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
    slice_number: int,
    on_metric: Callable[[str, float], None],
) -> bool:
    """Collect one EBSD map with the step's profile and save it (scaffold)."""
    step = _step(step_settings, "EBSD")
    output = BrukerEDSOutputSettings(
        output_dir=str(step.output_path),
        run_name=step.run_name,
        slice_number=slice_number,
    )
    with _session(general_settings) as session, _as_detector_error():
        paths = make_run_paths(output, now_stamp())
        BrukerEBSDController(session).run_profile_acquisition(
            BrukerEBSDAcquisitionSettings(
                profile_name=step.profile_name,
                scan_area=_scan_area(step),
                output_path=str(paths["bcf_path"]),
                with_edx=bool(step_settings.enable_eds),
                with_patterns=step.save_patterns,
                poll_interval_s=POLL_INTERVAL_S,
                timeout_s=map_wait_s(step.map, MIN_EBSD_MAP_WAIT_S),
            )
        )
    return True
