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
from pytribeam.external_oem.edax.types import (
    EdaxConnectionSettings,
    EdaxProjectInfo,
)

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
    project = EdaxProjectInfo(
        guid=Constants.EDAX_GUID,
        name=config.project_name,
        num_slices=general_settings.max_slice_number,
        slice_thickness_um=general_settings.slice_thickness_um,
    )
    with EdaxClient(connection_settings(config)) as client:
        mapping.run_ebsd_preflight(
            EdaxEbsdController(client),
            folder=Path(config.save_directory),
            project=project,
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
