"""
TFS LaserControl adapter
========================

Fallback backend for EDAX and Oxford configurations without a native settings
block. Detector motion, state and mapping go through ThermoFisher's
LaserControl, via the existing functions in `pytribeam.laser` and
`pytribeam.insertable_devices`; those already check for collisions and show
the chamber CCD during motion.

LaserControl cannot set EBSD or EDS parameters: the vendor software's current
settings apply. Preflight says so once, and `set_*_parameters` accepts any step.

See the adapter contract in `pytribeam.external_oem.dispatch`.
"""

# Default python modules
from contextlib import contextmanager
from typing import Callable, List

# Local scripts
import pytribeam.insertable_devices as devices
import pytribeam.laser as fs_laser
import pytribeam.types as tbt
from pytribeam.external_oem.core.errors import DetectorError

_PARAMETER_NOTICE = (
    "\tLaserControl cannot set {technique} parameters; the settings currently "
    "in the vendor software will be used for every {technique} map."
)


@contextmanager
def _as_detector_error(*also):
    """Re-raise LaserControl failures as DetectorError.

    LaserControl reports problems as SystemError or ConnectionError; the map
    functions also raise ValueError when a map finishes implausibly fast, which
    callers opt into with ``also``.
    """
    try:
        yield
    except (SystemError, ConnectionError, *also) as error:
        raise DetectorError(str(error)) from error


def _require_laser_control():
    if devices.external is None:
        raise DetectorError(
            "LaserControl is not available: the TFS Laser API could not be "
            "imported. Open LaserControl, or configure the vendor's native API."
        )


def _map_status(technique: tbt.ExternalTechnique) -> tbt.MapStatus:
    _require_laser_control()
    status = (
        devices.external.EBSD_MappingStatus()
        if technique == tbt.ExternalTechnique.EBSD
        else devices.external.EDS_MappingStatus()
    )
    return tbt.MapStatus(status)


# ----------------------------------------------------------------------
# Connection and preflight
# ----------------------------------------------------------------------


def test_connection(
    general_settings: tbt.GeneralSettings,
    technique: tbt.ExternalTechnique,
) -> bool:
    """Check LaserControl answers and can reach the technique's software."""
    if not fs_laser.laser_connected():
        return False
    with _as_detector_error():
        if technique == tbt.ExternalTechnique.EBSD:
            devices.connect_EBSD()
        else:
            devices.connect_EDS()
    return True


test_connection.__test__ = False


def _preflight(technique: tbt.ExternalTechnique) -> bool:
    with _as_detector_error():
        status = _map_status(technique)
    if status != tbt.MapStatus.IDLE:
        raise DetectorError(
            f"{technique.value} mapping is '{status.value}', not "
            f"'{tbt.MapStatus.IDLE.value}'. Reset the vendor software before "
            "starting."
        )
    print(_PARAMETER_NOTICE.format(technique=technique.value))
    return True


def preflight_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: List[tbt.EBSDSettings],
) -> bool:
    """Check the EBSD software is idle, and note that parameters are not set."""
    return _preflight(tbt.ExternalTechnique.EBSD)


def preflight_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: List[tbt.EDSSettings],
) -> bool:
    """Check the EDS software is idle, and note that parameters are not set."""
    return _preflight(tbt.ExternalTechnique.EDS)


# ----------------------------------------------------------------------
# State and motion
# ----------------------------------------------------------------------


def get_ebsd_camera_state(
    general_settings: tbt.GeneralSettings,
) -> tbt.RetractableDeviceState:
    with _as_detector_error():
        return devices.connect_EBSD()


def get_eds_detector_state(
    general_settings: tbt.GeneralSettings,
) -> tbt.RetractableDeviceState:
    with _as_detector_error():
        return devices.connect_EDS()


def insert_ebsd_camera(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    with _as_detector_error():
        return devices.insert_EBSD(microscope=microscope)


def insert_eds_detector(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    with _as_detector_error():
        return devices.insert_EDS(microscope=microscope)


def retract_ebsd_camera(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    with _as_detector_error():
        return devices.retract_EBSD(microscope=microscope)


def retract_eds_detector(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    with _as_detector_error():
        return devices.retract_EDS(microscope=microscope)


# ----------------------------------------------------------------------
# Parameters and mapping
# ----------------------------------------------------------------------


def set_ebsd_parameters(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
) -> bool:
    """Nothing can be set through LaserControl; the vendor settings apply."""
    return True


def set_eds_parameters(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
) -> bool:
    """Nothing can be set through LaserControl; the vendor settings apply."""
    return True


def map_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
    slice_number: int,
    on_metric: Callable[[str, float], None],
) -> bool:
    """Collect an EBSD map (with concurrent EDS if the vendor software has it on)."""
    _require_laser_control()
    with _as_detector_error(ValueError):
        return fs_laser.map_ebsd()


def map_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
    slice_number: int,
    on_metric: Callable[[str, float], None],
) -> bool:
    _require_laser_control()
    with _as_detector_error(ValueError):
        return fs_laser.map_eds()
