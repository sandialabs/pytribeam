"""
EDAX IPAPI adapter
==================

Native EDAX backend: everything, including EBSD camera motion, runs over the
EDAX IPAPI (TEAM/APEX). LaserControl is never used.

Mostly a thin layer over `pytribeam.external_oem.edax.workflow`, which already
handles preflight, EDS motion and both maps. This module adds EBSD camera
motion and state over the IPAPI, translates EDAX states to
`tbt.RetractableDeviceState`, and applies EBSD step parameters.

See the adapter contract in `pytribeam.external_oem.dispatch`.
"""

# Default python modules
from typing import Callable, List

# Local scripts
import pytribeam.types as tbt
from pytribeam.external_oem.core.errors import DetectorError
from pytribeam.external_oem.edax import mapping
from pytribeam.external_oem.edax import workflow as edax_workflow
from pytribeam.external_oem.edax.client import EdaxClient
from pytribeam.external_oem.edax.ebsd import EdaxEbsdController
from pytribeam.external_oem.edax.eds import EdaxEdsController
from pytribeam.external_oem.edax.errors import EdaxStateError
from pytribeam.external_oem.edax.types import (
    EdaxCameraStatus,
    EdaxDetectorSlideStatus,
    EdaxDetectorStatus,
    EdaxEdsMapParams,
    EdaxEdsResolution,
    EdaxMappingStatus,
)

STATE = tbt.RetractableDeviceState

#: EDAX EBSD camera slide status as pyTriBeam's generic device state. Every
#: EdaxCameraStatus member must appear here (checked by the tests).
CAMERA_STATE = {
    EdaxCameraStatus.SLIDE_IN: STATE.INSERTED,
    EdaxCameraStatus.SLIDE_OUT: STATE.RETRACTED,
    EdaxCameraStatus.SLIDE_MOVING_IN: STATE.BUSY,
    EdaxCameraStatus.SLIDE_MOVING_OUT: STATE.BUSY,
    EdaxCameraStatus.SLIDE_MOVE_MID_IN: STATE.BUSY,
    EdaxCameraStatus.SLIDE_MOVE_MID_OUT: STATE.BUSY,
    EdaxCameraStatus.SLIDE_ERROR: STATE.ERROR,
    EdaxCameraStatus.SLIDE_NO_POWER: STATE.ERROR,
    EdaxCameraStatus.SLIDE_WATCHDOG: STATE.ERROR,
    EdaxCameraStatus.SLIDE_MOVE_WDOG: STATE.ERROR,
    EdaxCameraStatus.SLIDE_DISABLED: STATE.ERROR,
    EdaxCameraStatus.SLIDE_MOVE_TOUCH: STATE.ERROR,
    EdaxCameraStatus.SLIDE_TOUCH_SENSE: STATE.ERROR,
    EdaxCameraStatus.SLIDE_MID: STATE.INDERTERMINATE,
    EdaxCameraStatus.SLIDE_STOPPED: STATE.INDERTERMINATE,
    EdaxCameraStatus.SLIDE_INIT: STATE.INDERTERMINATE,
    EdaxCameraStatus.SLIDE_HIGH_COUNT: STATE.INDERTERMINATE,
    EdaxCameraStatus.UNKNOWN: STATE.INDERTERMINATE,
}

#: Map statuses during which a detector must not be moved.
MAP_BUSY = frozenset(
    {
        EdaxMappingStatus.SETUP_ACTIVE,
        EdaxMappingStatus.SETUP_PAUSED,
        EdaxMappingStatus.MAPPING_ACTIVE,
        EdaxMappingStatus.MAPPING_PAUSED,
        EdaxMappingStatus.MAPPING_RESUMED,
    }
)


def _client(general_settings: tbt.GeneralSettings, quiet: bool = False) -> EdaxClient:
    """Return an unopened client; use it with ``with`` so it always closes."""
    return EdaxClient(
        edax_workflow.connection_settings(general_settings.EDAX_settings),
        quiet=quiet,
    )


def _require_eds_ready(eds: EdaxEdsController) -> None:
    status = eds.detector_status()
    if status is not EdaxDetectorStatus.READY:
        raise EdaxStateError(
            f"The EDS detector reports '{status.value}'. Check that it is cooled "
            "and that APEX shows it ready before collecting."
        )


def ebsd_map_params(step_settings: tbt.EBSDSettings):
    """Translate an EBSD step into IPAPI mapping parameters."""
    return mapping.ebsd_map_params(
        scan_box=step_settings.scan_box,
        grid_type=step_settings.grid_type,
        save_patterns=step_settings.save_patterns,
        enable_eds=step_settings.enable_eds,
    )


# ----------------------------------------------------------------------
# Connection and preflight
# ----------------------------------------------------------------------


def test_connection(
    general_settings: tbt.GeneralSettings,
    technique: tbt.ExternalTechnique,
) -> bool:
    """Open, unlock and close an IPAPI connection. EBSD and EDS share it."""
    connection = edax_workflow.connection_settings(general_settings.EDAX_settings)
    return edax_workflow.check_connection(connection.host, connection.port)


test_connection.__test__ = False


def preflight_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: List[tbt.EBSDSettings],
) -> bool:
    """Set headless access, the save folder and the project; check concurrent EDS."""
    edax_workflow.preflight(general_settings)
    if any(settings.enable_eds for settings in step_settings):
        with _client(general_settings, quiet=True) as client:
            _require_eds_ready(EdaxEdsController(client))
    return True


def preflight_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: List[tbt.EDSSettings],
) -> bool:
    """Set APEX's EDS side headless, pointed at the experiment; check the detector."""
    edax_workflow.preflight_eds(general_settings)
    with _client(general_settings, quiet=True) as client:
        _require_eds_ready(EdaxEdsController(client))
    return True


# ----------------------------------------------------------------------
# State and motion
# ----------------------------------------------------------------------


def get_ebsd_camera_state(
    general_settings: tbt.GeneralSettings,
) -> tbt.RetractableDeviceState:
    with _client(general_settings, quiet=True) as client:
        return CAMERA_STATE[EdaxEbsdController(client).camera_status()]


def get_eds_detector_state(
    general_settings: tbt.GeneralSettings,
) -> tbt.RetractableDeviceState:
    return edax_workflow.eds_detector_state(general_settings)


def insert_ebsd_camera(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """
    Insert the EBSD camera over the IPAPI, under the live chamber CCD.

    Refuses while a map is running, or unless the slide reports fully out (an
    unknown or intermediate position could not be confirmed). The dispatcher
    checks for collisions first and shows the chamber CCD around this call.
    """
    with _client(general_settings) as client:
        ebsd = EdaxEbsdController(client)
        status = ebsd.camera_status()
        if status is EdaxCameraStatus.SLIDE_IN:
            return True
        if status is not EdaxCameraStatus.SLIDE_OUT:
            raise EdaxStateError(
                f"The EBSD camera slide reports '{status.value}', so it will not be "
                "inserted. Check the camera in TEAM/APEX."
            )
        if ebsd.map_status() in MAP_BUSY:
            raise EdaxStateError(
                "An EBSD map or setup is running, so the camera will not be moved."
            )
        ebsd.insert_camera()
    return True


def insert_eds_detector(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Insert the EDS detector over the IPAPI, under the live chamber CCD."""
    try:
        return edax_workflow.insert_eds_detector(general_settings, microscope)
    except SystemError as error:  # the workflow's collision refusal
        raise DetectorError(str(error)) from error


def retract_ebsd_camera(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Retract the EBSD camera over the IPAPI, under the live chamber CCD.

    Retraction is the safe direction, so it proceeds from any slide state.
    """
    with _client(general_settings) as client:
        ebsd = EdaxEbsdController(client)
        if ebsd.camera_status() is EdaxCameraStatus.SLIDE_OUT:
            return True
        ebsd.retract_camera()
    return True


def retract_eds_detector(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Retract the EDS detector over the IPAPI, from any slide state.

    Done here rather than through edax.workflow, whose retraction insists on
    showing the CCD itself: the dispatcher shows it around this call, and
    still retracts if it cannot (for example after the microscope client has
    disconnected following an error).
    """
    with _client(general_settings) as client:
        eds = EdaxEdsController(client)
        if eds.slide_status() is EdaxDetectorSlideStatus.SLIDE_OUT:
            return True
        eds.retract_detector()
    return True


# ----------------------------------------------------------------------
# Parameters and mapping
# ----------------------------------------------------------------------


def set_ebsd_parameters(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
) -> bool:
    """Apply the step's scan box, grid, pattern and spectra settings."""
    with _client(general_settings, quiet=True) as client:
        EdaxEbsdController(client).apply_map_parameters(ebsd_map_params(step_settings))
    return True


def eds_map_params(step_settings: tbt.EDSSettings) -> EdaxEdsMapParams:
    """Translate an EDS step's `edax_settings` into IPAPI map parameters.

    Unset values are None and are not sent, so APEX keeps its own; with no
    `edax_settings` at all, nothing is sent.
    """
    edax = step_settings.edax
    if edax is None:
        return EdaxEdsMapParams()
    resolution = None
    if edax.resolution is not None:
        resolution = next(
            preset
            for preset in EdaxEdsResolution
            if f"{preset.points}x{preset.lines}" == edax.resolution
        )
    return EdaxEdsMapParams(
        resolution=resolution,
        num_frames=edax.num_frames,
        preset_dwell_us=edax.dwell_us,
    )


def set_eds_parameters(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
) -> bool:
    """Apply the step's map resolution, frames and dwell; unset ones keep
    APEX's own values."""
    params = eds_map_params(step_settings)
    if params == EdaxEdsMapParams():
        return True
    with _client(general_settings, quiet=True) as client:
        EdaxEdsController(client).apply_map_parameters(params)
    return True


def map_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
    slice_number: int,
    on_metric: Callable[[str, float], None],
) -> bool:
    """
    Collect one EBSD map over the IPAPI.

    Reports camera saturation and average CI through ``on_metric``. As proven
    on hardware, the map retracts the camera itself when it finishes, so a
    rejected map still leaves the camera out.
    """
    edax_workflow.map_ebsd(general_settings, step_settings, slice_number, on_metric)
    return True


def map_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
    slice_number: int,
    on_metric: Callable[[str, float], None],
) -> bool:
    edax_workflow.map_eds(
        general_settings,
        step_settings,
        slice_number,
        params=eds_map_params(step_settings),
    )
    return True
