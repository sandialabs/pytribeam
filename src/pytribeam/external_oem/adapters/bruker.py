"""
Bruker ESPRIT adapter
=====================

Native Bruker backend, through the ESPRIT API DLL
(`pytribeam.external_oem.bruker`). Bruker has no LaserControl fallback.

All settings come from `Bruker_settings` in the experiment YAML: the shared
`session`, plus an `eds` and/or `ebsd` section.

Sessions: closing an ESPRIT API connection can grey out parts of the ESPRIT
GUI, so one session per set of session settings is kept open for the life of
the process and re-checked before each use (reconnecting if it dropped). Set
`session.close_on_exit: true` to close after every call instead.

EDS output: ESPRIT saves the native `.bcf` HyperMap under `eds.output.root_dir`.
Each map's element arrays, settings (password removed) and provenance are also
written to their own HDF5 file in `<exp_dir>/Bruker_EDS/`, one file per map.

EBSD runs on the existing scaffold and is not yet validated on hardware.

See the adapter contract in `pytribeam.external_oem.dispatch`.
"""

# Default python modules
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Iterator, List

# Local scripts
import pytribeam.insertable_devices as devices
import pytribeam.types as tbt
from pytribeam.constants import Constants
from pytribeam.external_oem.bruker.detector_motion import (
    BrukerDetectorMotionController,
)
from pytribeam.external_oem.bruker.ebsd import BrukerEBSDController
from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.h5_output import BrukerElementMap, write_eds_map_h5
from pytribeam.external_oem.bruker.image_config import BrukerImageConfigController
from pytribeam.external_oem.bruker.output import (
    make_file_prefix,
    make_run_paths,
    now_stamp,
)
from pytribeam.external_oem.bruker.readback import BrukerEDSReadbackController
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.spectrometer import BrukerSpectrometerController
from pytribeam.external_oem.bruker.types import (
    BrukerDetectorMotionSettings,
    BrukerEBSDAcquisitionSettings,
    BrukerEBSDDetectorMotionSettings,
    BrukerEDSProfileMapSettings,
    BrukerSessionSettings,
)
from pytribeam.external_oem.core.errors import ConfigurationError, DetectorError

STATE = tbt.RetractableDeviceState

#: Folder under the experiment directory for per-map HDF5 files.
EDS_H5_FOLDER = "Bruker_EDS"

#: ESPRIT EDS detector position name as pyTriBeam's generic device state.
_EDS_POSITION_STATE = {"acquire": STATE.INSERTED, "park": STATE.RETRACTED}

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


# ----------------------------------------------------------------------
# Sessions and errors
# ----------------------------------------------------------------------


def _new_session(settings: BrukerSessionSettings) -> BrukerSession:
    session = BrukerSession(settings)
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
    settings = general_settings.Bruker_settings.session
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
        try:
            yield session
        finally:
            if settings.close_on_exit:
                _SESSIONS.pop(settings, None)
                session.close()


def close_sessions() -> None:
    """Close every open session (for shutdown and tests)."""
    while _SESSIONS:
        _, session = _SESSIONS.popitem()
        try:
            session.close()
        except Exception as error:  # closing is best effort
            print(f"\tWARNING: closing Bruker session failed: {error}")


def _eds(general_settings: tbt.GeneralSettings):
    eds = general_settings.Bruker_settings.eds
    if eds is None:
        raise ConfigurationError("Bruker EDS needs a 'Bruker_settings.eds' section.")
    return eds


def _ebsd(general_settings: tbt.GeneralSettings):
    ebsd = general_settings.Bruker_settings.ebsd
    if ebsd is None:
        raise ConfigurationError("Bruker EBSD needs a 'Bruker_settings.ebsd' section.")
    return ebsd


def _require_no_collision(
    microscope: tbt.Microscope, detector: tbt.DetectorType
) -> None:
    if devices.detectors_will_collide(
        microscope=microscope, detector_to_insert=detector
    ):
        raise DetectorError(
            f"Cannot insert the {detector.value} detector, which may collide with "
            "another detector. Disallowed combinations are: "
            f"{Constants.detector_collisions}"
        )


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


def preflight_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: List[tbt.EDSSettings],
) -> bool:
    """Check the spectrometer is ready and the output folders are writable."""
    eds = _eds(general_settings)
    with _session(general_settings) as session, _as_detector_error():
        status = BrukerSpectrometerController(session).get_spectrometer_status(
            spu=eds.map.spu_device
        )
        if not status.ready:
            raise DetectorError(
                f"The Bruker spectrometer (SPU {eds.map.spu_device}) is not ready "
                f"(status {status.status})."
            )
        for folder in (
            Path(eds.output.output_dir),
            Path(general_settings.exp_dir) / EDS_H5_FOLDER,
        ):
            folder.mkdir(parents=True, exist_ok=True)
    return True


def preflight_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: List[tbt.EBSDSettings],
) -> bool:
    """Check the DLL exports the EBSD functions and the output folder is writable."""
    ebsd = _ebsd(general_settings)
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
        Path(ebsd.output.output_dir).mkdir(parents=True, exist_ok=True)
    return True


# ----------------------------------------------------------------------
# EDS state and motion
# ----------------------------------------------------------------------


def _eds_position(session, eds) -> tbt.RetractableDeviceState:
    position = BrukerDetectorMotionController(session).get_eds_detector_position(
        eds.detector.detector_index
    )
    return _EDS_POSITION_STATE.get(position.position_name, STATE.INDERTERMINATE)


def _move_eds(session, eds, target: str) -> None:
    BrukerDetectorMotionController(session).move_eds_detector(
        BrukerDetectorMotionSettings(
            detector_index=eds.detector.detector_index,
            target_position=target,
            timeout_s=eds.detector.timeout_s,
            poll_interval_s=eds.detector.poll_interval_s,
        )
    )


def get_eds_detector_state(
    general_settings: tbt.GeneralSettings,
) -> tbt.RetractableDeviceState:
    """``acquire`` reads as inserted and ``park`` as retracted.

    ESPRIT's "acquire" can cover several physical positions, so this is a
    safety check, not a guarantee of the working distance.
    """
    eds = _eds(general_settings)
    with _session(general_settings) as session, _as_detector_error():
        return _eds_position(session, eds)


def insert_eds_detector(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Move the EDS detector to acquire, under the live chamber CCD.

    With ``detector.move_to_acquire_before: false`` (simulator configs) the
    detector is not moved. Unless ``detector.verify_park_before`` is false, it
    must report ``park`` before moving.
    """
    eds = _eds(general_settings)
    if not eds.detector.move_to_acquire_before:
        print("\tBruker EDS detector motion is disabled; not inserting.")
        return True
    _require_no_collision(microscope, tbt.DetectorType.EDS)
    with _session(general_settings) as session, _as_detector_error():
        state = _eds_position(session, eds)
        if state == STATE.INSERTED:
            return True
        if state != STATE.RETRACTED and eds.detector.verify_park_before:
            raise DetectorError(
                "The Bruker EDS detector is not parked, so it will not be moved."
            )
        with devices.ccd_live_view(microscope=microscope):
            _move_eds(session, eds, "acquire")
    return True


def retract_eds_detector(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Park the EDS detector, under the live chamber CCD.

    With ``detector.park_after: false`` (simulator configs) the detector is not
    moved.
    """
    eds = _eds(general_settings)
    if not eds.detector.park_after:
        print("\tBruker EDS detector motion is disabled; not parking.")
        return True
    with _session(general_settings) as session, _as_detector_error():
        if _eds_position(session, eds) == STATE.RETRACTED:
            return True
        with devices.ccd_live_view(microscope=microscope):
            _move_eds(session, eds, "park")
    return True


# ----------------------------------------------------------------------
# EBSD state and motion (not yet hardware-validated)
# ----------------------------------------------------------------------


def ebsd_state(position_mm: float, detector) -> tbt.RetractableDeviceState:
    """Classify an EBSD camera position against the configured positions."""
    if abs(position_mm - detector.inserted_position_mm) <= detector.tolerance_mm:
        return STATE.INSERTED
    if abs(position_mm - detector.retracted_position_mm) <= detector.tolerance_mm:
        return STATE.RETRACTED
    return STATE.INDERTERMINATE


def _move_ebsd(session, detector, target_mm: float) -> None:
    result = BrukerEBSDController(session).move_detector_position_tolerant(
        BrukerEBSDDetectorMotionSettings(
            target_position_mm=target_mm,
            speed_mm_per_s=detector.speed_mm_per_s,
            tolerance_mm=detector.tolerance_mm,
            timeout_s=detector.timeout_s,
            poll_interval_s=detector.poll_interval_s,
            stable_polls=detector.stable_polls,
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
    detector = _ebsd(general_settings).detector
    with _session(general_settings) as session, _as_detector_error():
        position = BrukerEBSDController(session).get_detector_position_mm()
    return ebsd_state(position, detector)


def insert_ebsd_camera(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Move the EBSD camera to its inserted position, under the live chamber CCD."""
    detector = _ebsd(general_settings).detector
    _require_no_collision(microscope, tbt.DetectorType.EBSD)
    with _session(general_settings) as session, _as_detector_error():
        position = BrukerEBSDController(session).get_detector_position_mm()
        state = ebsd_state(position, detector)
        if state == STATE.INSERTED:
            return True
        if state != STATE.RETRACTED:
            raise DetectorError(
                f"The Bruker EBSD camera is at {position} mm, neither inserted nor "
                "retracted, so it will not be moved."
            )
        with devices.ccd_live_view(microscope=microscope):
            _move_ebsd(session, detector, detector.inserted_position_mm)
    return True


def retract_ebsd_camera(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Move the EBSD camera to its retracted position, from any position."""
    detector = _ebsd(general_settings).detector
    with _session(general_settings) as session, _as_detector_error():
        position = BrukerEBSDController(session).get_detector_position_mm()
        if ebsd_state(position, detector) == STATE.RETRACTED:
            return True
        with devices.ccd_live_view(microscope=microscope):
            _move_ebsd(session, detector, detector.retracted_position_mm)
    return True


# ----------------------------------------------------------------------
# Parameters
# ----------------------------------------------------------------------


def set_eds_parameters(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
) -> bool:
    """
    Apply the map's image configuration and confirm ESPRIT accepted it.

    For profile maps, also has ESPRIT build the element profile, which rejects
    invalid element settings before any data is collected.
    """
    map_settings = _eds(general_settings).map
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
        if isinstance(map_settings, BrukerEDSProfileMapSettings):
            BrukerEDSController(session).create_hymap_profile(map_settings)
    return True


def _require_ebsd_profile(session, profile_name: str) -> None:
    profiles = BrukerEBSDController(session).get_profiles_raw()
    if profile_name not in profiles:
        raise ConfigurationError(
            f"ESPRIT has no EBSD acquisition profile named '{profile_name}' "
            "(Bruker_settings.ebsd.acquisition.profile_name)."
        )


def set_ebsd_parameters(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
) -> bool:
    """Configure the scan area and select the acquisition profile."""
    ebsd = _ebsd(general_settings)
    with _session(general_settings) as session, _as_detector_error():
        _require_ebsd_profile(session, ebsd.profile_name)
        controller = BrukerEBSDController(session)
        controller.configure_scan_area(ebsd.scan_area)
        controller.select_profile(ebsd.profile_name)
    return True


# ----------------------------------------------------------------------
# Mapping
# ----------------------------------------------------------------------


def _read_element_maps(session, map_settings) -> List[BrukerElementMap]:
    """Read every element plane; one failure does not lose the others."""
    readback = BrukerEDSReadbackController(session)
    width, height = BrukerEDSReadbackController._effective_readback_dimensions(
        map_settings
    )
    element_maps = []
    for index, element in enumerate(map_settings.elements):
        try:
            data = readback.get_element_data_array(
                element_index=index, width_px=width, height_px=height
            )
            element_maps.append(BrukerElementMap(index, element, data=data))
        except Exception as error:
            element_maps.append(
                BrukerElementMap(
                    index, element, error=f"{type(error).__name__}: {error}"
                )
            )
    return element_maps


def map_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
    slice_number: int,
    on_metric: Callable[[str, float], None],
) -> bool:
    """
    Collect one EDS map, save the native ``.bcf``, and write the map's HDF5 file.

    A missing ``.bcf`` or a failed element readback is reported and recorded in
    the HDF5 file, but does not stop the experiment.
    """
    eds = _eds(general_settings)
    stamp = now_stamp()
    output = eds.output._replace(slice_number=slice_number)
    errors = []

    with _session(general_settings) as session, _as_detector_error():
        paths = make_run_paths(output, stamp)
        map_settings = eds.map._replace(
            output_bcf_path=str(paths["bcf_path"]),
            output_image_path=str(paths["bmp_path"]) if output.save_image else None,
            output_image_format=output.image_format if output.save_image else None,
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
            errors.append("BCF file missing after acquisition")

        element_maps = []
        if eds.readback.enabled and isinstance(
            map_settings, BrukerEDSProfileMapSettings
        ):
            element_maps = _read_element_maps(session, map_settings)
            errors.extend(
                f"Element {m.element_index} (Z={m.element.atomic_number}, "
                f"{m.element.line}) readback failed: {m.error}"
                for m in element_maps
                if m.error is not None
            )
        query_info = session.query_info()

    h5_path = (
        Path(general_settings.exp_dir)
        / EDS_H5_FOLDER
        / f"{make_file_prefix(output)}_{stamp}.h5"
    )
    write_eds_map_h5(
        h5_path,
        settings=eds._replace(map=map_settings, output=output),
        element_maps=element_maps,
        slice_number=slice_number,
        timestamp=stamp,
        query_info=query_info,
        bcf_path=outputs.output_bcf_path,
        image_path=outputs.output_image_path,
        errors=errors,
    )
    for error in errors:
        print(f"\tWARNING: Bruker EDS slice {slice_number}: {error}")
    return True


def map_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
    slice_number: int,
    on_metric: Callable[[str, float], None],
) -> bool:
    """Collect one EBSD map with the configured profile and save it (scaffold)."""
    ebsd = _ebsd(general_settings)
    output = ebsd.output._replace(slice_number=slice_number)
    with _session(general_settings) as session, _as_detector_error():
        paths = make_run_paths(output, now_stamp())
        BrukerEBSDController(session).run_profile_acquisition(
            BrukerEBSDAcquisitionSettings(
                profile_name=ebsd.profile_name,
                scan_area=ebsd.scan_area,
                output_path=str(paths["bcf_path"]),
                with_edx=bool(step_settings.enable_eds),
                with_patterns=ebsd.with_patterns,
                poll_interval_s=ebsd.poll_interval_s,
                timeout_s=ebsd.timeout_s,
            )
        )
    return True
