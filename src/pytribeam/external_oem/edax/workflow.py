#!/usr/bin/python3
"""
EDAX Workflow Glue
==================

Bridges pyTriBeam's experiment settings and microscope to the EDAX IPAPI
wrapper. This is the only module in :mod:`pytribeam.external_oem.edax` that
depends on AutoScript; the orchestration it calls lives in the standard-library
:mod:`pytribeam.external_oem.edax.mapping`, where it is unit-tested.

Callers should reach these functions through
:mod:`pytribeam.external_oem.dispatch`, which decides whether the native IPAPI
or the TFS LaserControl fallback handles a given operation.

Functions
---------
connection_settings(config) -> EdaxConnectionSettings
    Build IPAPI connection settings from the experiment's EDAX block.

check_connection(host, port) -> bool
    Open, unlock, and close a connection, to validate a configuration.

preflight(general_settings) -> bool
    Point EDAX at the experiment folder and project before the first slice.

measure_camera_saturation(microscope, ebsd) -> float
    Scan the beam and read the EBSD camera saturation, restoring the imaging
    state afterwards.

map_ebsd(general_settings, step_settings, slice_number) -> EdaxMapResult
    Collect one EBSD map over the IPAPI.

preflight_eds(general_settings) -> bool
    Put APEX's EDS side in headless mode, pointed at the experiment folder.

eds_detector_state(general_settings) -> tbt.RetractableDeviceState
    Report the EDS detector slide position.

insert_eds_detector(general_settings, microscope) -> bool
    Insert the EDS detector over the IPAPI, under the live chamber CCD.

retract_eds_detector(general_settings, microscope) -> bool
    Retract the EDS detector over the IPAPI, under the live chamber CCD.

map_eds(general_settings, step_settings, slice_number) -> EdaxMapResult
    Collect one EDS map over the IPAPI.
"""

# Default python modules
import time
from pathlib import Path
from typing import Callable, Optional

# Local scripts
import pytribeam.image as img
import pytribeam.insertable_devices as devices
import pytribeam.types as tbt
from pytribeam.constants import Constants, Conversions
from pytribeam.external_oem.edax import mapping
from pytribeam.external_oem.edax.client import EdaxClient
from pytribeam.external_oem.edax.ebsd import EdaxEbsdController
from pytribeam.external_oem.edax.eds import EdaxEdsController
from pytribeam.external_oem.edax.errors import EdaxStateError
from pytribeam.external_oem.edax.types import (
    EdaxConnectionSettings,
    EdaxDetectorSlideStatus,
    EdaxEdsMapParams,
    EdaxMappingStatus,
    EdaxProjectInfo,
)

# EDS map statuses during which the detector must not be inserted.
_EDS_BUSY = frozenset(
    {
        EdaxMappingStatus.SETUP_ACTIVE,
        EdaxMappingStatus.SETUP_PAUSED,
        EdaxMappingStatus.MAPPING_ACTIVE,
        EdaxMappingStatus.MAPPING_PAUSED,
        EdaxMappingStatus.MAPPING_RESUMED,
    }
)

# EDS slide status as pyTriBeam's generic device state.
_SLIDE_STATE = {
    EdaxDetectorSlideStatus.SLIDE_IN: tbt.RetractableDeviceState.INSERTED,
    EdaxDetectorSlideStatus.SLIDE_OUT: tbt.RetractableDeviceState.RETRACTED,
    EdaxDetectorSlideStatus.UNKNOWN: tbt.RetractableDeviceState.INDERTERMINATE,
}

# Default IPAPI service port, used when a configuration omits one.
DEFAULT_PORT = 8301


def connection_settings(config: tbt.EDAXConfig) -> EdaxConnectionSettings:
    """
    Build IPAPI connection settings from the experiment's EDAX block.

    Parameters
    ----------
    config : tbt.EDAXConfig
        The ``EDAX_settings`` block from the experiment configuration.

    Returns
    -------
    EdaxConnectionSettings
        Host and port, with the wrapper's default timing.
    """
    connection = config.connection
    return EdaxConnectionSettings(
        host=connection.host,
        port=DEFAULT_PORT if connection.port is None else int(connection.port),
    )


def check_connection(host: str, port: int) -> bool:
    """
    Open, unlock, and close a connection, to validate a configuration.

    Nothing is outstanding when the connection closes, so this is safe to run
    against a live service.

    Parameters
    ----------
    host : str
        Host running the IPAPI service.
    port : int
        IPAPI service port.

    Returns
    -------
    bool
        True when the service accepted the connection.

    Raises
    ------
    EdaxConnectionError
        If the service is unreachable or refuses the unlock.
    """
    settings = EdaxConnectionSettings(host=host, port=int(port))
    with EdaxClient(settings, quiet=True):
        pass
    return True


def _project(general_settings: tbt.GeneralSettings) -> EdaxProjectInfo:
    """Return the EDAX project for this experiment, shared by EBSD and EDS."""
    return EdaxProjectInfo(
        guid=Constants.EDAX_GUID,
        name=general_settings.EDAX_settings.project_name,
        num_slices=general_settings.max_slice_number,
        slice_thickness_um=general_settings.slice_thickness_um,
    )


def preflight(general_settings: tbt.GeneralSettings) -> bool:
    """
    Point EDAX at the experiment folder and project before the first slice.

    Parameters
    ----------
    general_settings : tbt.GeneralSettings
        Experiment settings carrying the ``EDAX_settings`` block, the slice
        count, and the slice thickness.

    Returns
    -------
    bool
        True on success.
    """
    config = general_settings.EDAX_settings
    with EdaxClient(connection_settings(config)) as client:
        mapping.run_ebsd_preflight(
            EdaxEbsdController(client),
            folder=Path(config.save_directory),
            project=_project(general_settings),
        )
    return True


def measure_camera_saturation(
    microscope: tbt.Microscope,
    ebsd: EdaxEbsdController,
    hfw_mm: float = Constants.ebsd_camera_saturation_hfw_mm,
    delay_s: float = Constants.ebsd_camera_saturation_delay_s,
) -> float:
    """
    Scan the beam and read the EBSD camera saturation.

    The reading is only meaningful while the beam scans, so this switches to
    the ETD at a small field width, scans, reads the camera, and then restores
    the original detector and field width. The restore runs even when the
    reading fails, so a fault here cannot leave the microscope imaging at the
    saturation field width for every step that follows.

    Parameters
    ----------
    microscope : tbt.Microscope
        The connected microscope.
    ebsd : EdaxEbsdController
        Controller over a connected client.
    hfw_mm : float, optional
        Horizontal field width to scan while measuring.
    delay_s : float, optional
        Scan time before reading, and after restoring.

    Returns
    -------
    float
        Camera saturation in the range [0, 1].
    """
    img.set_beam_device(microscope=microscope, device=tbt.Device.ELECTRON_BEAM)
    initial_hfw_m = microscope.beams.electron_beam.horizontal_field_width.value
    initial_detector = tbt.DetectorType(microscope.detector.type.value)
    beam = tbt.ElectronBeam(settings=tbt.BeamSettings())

    try:
        img.detector_type(microscope=microscope, detector=tbt.DetectorType.ETD)
        img.beam_hfw(beam=beam, microscope=microscope, hfw_mm=hfw_mm)
        microscope.imaging.start_acquisition()
        time.sleep(delay_s)
        try:
            saturation = ebsd.camera_saturation()
        finally:
            microscope.imaging.stop_acquisition()
    finally:
        img.detector_type(microscope=microscope, detector=initial_detector)
        img.beam_hfw(
            beam=beam,
            microscope=microscope,
            hfw_mm=initial_hfw_m * Conversions.M_TO_MM,
        )
        microscope.imaging.start_acquisition()
        time.sleep(delay_s)
        microscope.imaging.stop_acquisition()

    return saturation


def map_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
    slice_number: int,
    on_metric: Optional[Callable[[str, float], None]] = None,
) -> mapping.EdaxMapResult:
    """
    Collect one EBSD map over the IPAPI.

    The client is scoped with ``with``, so the connection is quiesced before it
    closes even when collection fails. Closing under an outstanding request is
    what stops the IPAPI Windows service.

    The camera retraction at the end of the map runs inside the live chamber
    CCD view in the lower-right quadrant, like every LaserControl insertion and
    retraction, so the operator can watch for a collision.

    Parameters
    ----------
    general_settings : tbt.GeneralSettings
        Experiment settings carrying the ``EDAX_settings`` block.
    step_settings : tbt.EBSDSettings
        The EBSD step's scan box, grid, pattern, and concurrent-EDS settings.
    slice_number : int
        The slice being collected, which determines the map's tag.
    on_metric : callable, optional
        Called with ``(name, value)`` as each metric is measured, so the caller
        can log it immediately.

    Returns
    -------
    EdaxMapResult
        Status, timing, and metrics for the collected map.
    """
    plan = mapping.EbsdMapPlan(
        tag=mapping.slice_tag(slice_number),
        params=mapping.ebsd_map_params(
            scan_box=step_settings.scan_box,
            grid_type=step_settings.grid_type,
            save_patterns=step_settings.save_patterns,
            enable_eds=step_settings.enable_eds,
        ),
        start_delay_s=Constants.edax_map_start_delay_s,
        poll_interval_s=Constants.edax_map_status_interval_s,
        timeout_scalar=Constants.edax_timeout_scalar,
    )
    microscope = step_settings.image.microscope

    with EdaxClient(connection_settings(general_settings.EDAX_settings)) as client:
        ebsd = EdaxEbsdController(client)
        return mapping.run_ebsd_map(
            ebsd,
            plan,
            measure_saturation=lambda: measure_camera_saturation(microscope, ebsd),
            on_metric=on_metric,
            motion_guard=lambda: devices.ccd_live_view(microscope=microscope),
        )


# ----------------------------------------------------------------------
# EDS
# ----------------------------------------------------------------------
def preflight_eds(general_settings: tbt.GeneralSettings) -> bool:
    """
    Put APEX's EDS side in headless mode, pointed at the experiment folder.

    EDS maps are stored in the same folder and project as the EBSD maps, under
    their own tags. Without this, APEX saves EDS maps wherever its own EDS
    settings point, or nowhere once another client has set NoWait access.

    Parameters
    ----------
    general_settings : tbt.GeneralSettings
        Experiment settings carrying the ``EDAX_settings`` block.

    Returns
    -------
    bool
        True on success.

    Raises
    ------
    EdaxStateError
        If APEX is not running or the EDS detector is not ready.
    """
    config = general_settings.EDAX_settings
    with EdaxClient(connection_settings(config)) as client:
        mapping.run_eds_preflight(
            EdaxEdsController(client),
            folder=Path(config.save_directory),
            project=_project(general_settings),
        )
    return True


def eds_detector_state(
    general_settings: tbt.GeneralSettings,
) -> tbt.RetractableDeviceState:
    """
    Report the EDS detector slide position.

    Parameters
    ----------
    general_settings : tbt.GeneralSettings
        Experiment settings carrying the ``EDAX_settings`` block.

    Returns
    -------
    tbt.RetractableDeviceState
        ``INSERTED`` or ``RETRACTED``, or ``INDERTERMINATE`` when EDAX cannot
        report the position.
    """
    with EdaxClient(
        connection_settings(general_settings.EDAX_settings), quiet=True
    ) as client:
        return _SLIDE_STATE[EdaxEdsController(client).slide_status()]


def insert_eds_detector(
    general_settings: tbt.GeneralSettings,
    microscope: tbt.Microscope,
) -> bool:
    """
    Insert the EDS detector over the IPAPI, under the live chamber CCD.

    Carries over every safeguard of the LaserControl insertion it replaces:
    the CBS collision check, refusing while an EDS map is running, and the live
    CCD view in the lower-right quadrant for the duration of the move. It also
    refuses to insert a detector whose position EDAX cannot report, since the
    move could then not be confirmed.

    Parameters
    ----------
    general_settings : tbt.GeneralSettings
        Experiment settings carrying the ``EDAX_settings`` block.
    microscope : tbt.Microscope
        The microscope, for the collision check and the CCD view.

    Returns
    -------
    bool
        True once the detector is inserted.

    Raises
    ------
    SystemError
        If inserting could collide with another detector.
    EdaxStateError
        If an EDS map is running, or the slide position cannot be read.
    """
    if devices.detectors_will_collide(
        microscope=microscope, detector_to_insert=tbt.DetectorType.EDS
    ):
        raise SystemError(
            "Cannot insert the EDS detector, which may collide with another "
            f"detector. Disallowed combinations are: {Constants.detector_collisions}"
        )

    with EdaxClient(connection_settings(general_settings.EDAX_settings)) as client:
        eds = EdaxEdsController(client)
        position = eds.slide_status()
        if position is EdaxDetectorSlideStatus.SLIDE_IN:
            return True
        if position is EdaxDetectorSlideStatus.UNKNOWN:
            raise EdaxStateError(
                "EDAX cannot report the EDS detector position, so it will not be "
                "inserted. Check the detector in APEX."
            )
        if eds.map_status() in _EDS_BUSY:
            raise EdaxStateError(
                "An EDS map or setup is running, so the detector will not be moved."
            )
        with devices.ccd_live_view(microscope=microscope):
            eds.insert_detector()
    return True


def retract_eds_detector(
    general_settings: tbt.GeneralSettings,
    microscope: tbt.Microscope,
) -> bool:
    """
    Retract the EDS detector over the IPAPI, under the live chamber CCD.

    Retraction is the safe direction, so unlike insertion it proceeds even when
    EDAX cannot report the position.

    Parameters
    ----------
    general_settings : tbt.GeneralSettings
        Experiment settings carrying the ``EDAX_settings`` block.
    microscope : tbt.Microscope
        The microscope, for the CCD view.

    Returns
    -------
    bool
        True once the detector is retracted.
    """
    with EdaxClient(connection_settings(general_settings.EDAX_settings)) as client:
        eds = EdaxEdsController(client)
        if eds.slide_status() is EdaxDetectorSlideStatus.SLIDE_OUT:
            return True
        with devices.ccd_live_view(microscope=microscope):
            eds.retract_detector()
    return True


def map_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
    slice_number: int,
    params: EdaxEdsMapParams = None,
) -> mapping.EdaxMapResult:
    """
    Collect one EDS map over the IPAPI.

    Parameters
    ----------
    general_settings : tbt.GeneralSettings
        Experiment settings carrying the ``EDAX_settings`` block.
    step_settings : tbt.EDSSettings
        The EDS step's settings.
    slice_number : int
        The slice being collected, which determines the map's tag.
    params : EdaxEdsMapParams, optional
        EDS map parameters to apply before collecting. None leaves APEX's own
        EDS map settings in force, which is what LaserControl collection did.

    Returns
    -------
    EdaxMapResult
        Status and timing for the collected map.
    """
    plan = mapping.EdsMapPlan(
        tag=mapping.eds_slice_tag(slice_number),
        params=EdaxEdsMapParams() if params is None else params,
        start_delay_s=Constants.edax_map_start_delay_s,
        poll_interval_s=Constants.edax_map_status_interval_s,
        timeout_scalar=Constants.edax_timeout_scalar,
        start_timeout_s=Constants.edax_eds_map_start_timeout_s,
    )
    with EdaxClient(connection_settings(general_settings.EDAX_settings)) as client:
        return mapping.run_eds_map(EdaxEdsController(client), plan)
