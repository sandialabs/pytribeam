"""
Oxford AZtec adapter
====================

Native Oxford backend, through the AZtec plugin API
(`pytribeam.external_oem.oxford`). LaserControl is never used.

AZtec's plugin API cannot set technique parameters (step size, dwell,
resolution...). Parameters are applied by loading the AZtec profile named in
`Oxford_settings` (`ebsd_profile` / `eds_profile`). Loading a profile replaces
AZtec's current settings, including unsaved GUI changes.

AZtec only reports a technique "ready" once its detector is inserted (and, for
EDS, cold), so preflight checks what does not depend on insertion, and each map
checks AZtec's readiness just before collecting.

Each call opens its own session and disconnects afterwards. `session_factory`
builds that session; tests replace it to run against the in-process simulator.

See the adapter contract in `pytribeam.external_oem.dispatch`.
"""

# Default python modules
from contextlib import contextmanager
from typing import Callable, Iterator, List

# Local scripts
import pytribeam.insertable_devices as devices
import pytribeam.types as tbt
from pytribeam.constants import Constants
from pytribeam.external_oem.core.errors import ConfigurationError, DetectorError
from pytribeam.external_oem.oxford.enums import (
    AcquisitionType,
    InsertionActivity,
    InsertionPositionState,
    OperatingState,
)
from pytribeam.external_oem.oxford.models import AcquisitionConfig
from pytribeam.external_oem.oxford.session import AztecSession

STATE = tbt.RetractableDeviceState

_MOVING = frozenset(
    {
        InsertionActivity.MOVING_IN,
        InsertionActivity.MOVING_OUT,
        InsertionActivity.AUTO_RETRACTING,
        InsertionActivity.HOMING,
    }
)

#: AZtec insertion position as pyTriBeam's generic device state, when the
#: detector is neither moving nor faulted. An auto-retracted detector is
#: physically out, so it reads as retracted.
_POSITION_STATE = {
    InsertionPositionState.IN: STATE.INSERTED,
    InsertionPositionState.OUT: STATE.RETRACTED,
    InsertionPositionState.AUTO_RETRACTED: STATE.RETRACTED,
}


def _new_session(general_settings: tbt.GeneralSettings) -> AztecSession:
    config = general_settings.Oxford_settings
    return AztecSession(
        host=config.connection.host,
        port=config.connection.port,
        dll_dir=None if config.dll_dir is None else str(config.dll_dir),
    )


#: Builds an unconnected session for the experiment. Replaced in tests.
session_factory: Callable[[tbt.GeneralSettings], AztecSession] = _new_session


@contextmanager
def _session(general_settings: tbt.GeneralSettings) -> Iterator[AztecSession]:
    """Connect for the duration of one call; always disconnects."""
    with session_factory(general_settings) as session:
        yield session


def device_state(insertion_state) -> tbt.RetractableDeviceState:
    """Translate an AZtec EBSD or EDS insertion state."""
    if getattr(insertion_state, "is_touching", False):
        return STATE.ERROR
    if insertion_state.state == InsertionPositionState.FAULT:
        return STATE.ERROR
    if insertion_state.activity in _MOVING:
        return STATE.BUSY
    return _POSITION_STATE.get(insertion_state.state, STATE.INDERTERMINATE)


def _profile(general_settings: tbt.GeneralSettings, technique: str) -> str:
    name = getattr(general_settings.Oxford_settings, f"{technique}_profile")
    if not name:
        raise ConfigurationError(
            f"Oxford {technique.upper()} parameters are applied by loading an AZtec "
            f"profile, but 'Oxford_settings.{technique}_profile' is not set."
        )
    return name


def _acquisition_type(step_settings) -> AcquisitionType:
    if isinstance(step_settings, tbt.EBSDSettings):
        if step_settings.enable_eds:
            return AcquisitionType.EBSD_MAP | AcquisitionType.EDS_MAP
        return AcquisitionType.EBSD_MAP
    return AcquisitionType.EDS_MAP


def _require_idle(session: AztecSession) -> None:
    if session.acquisition.is_running:
        raise DetectorError("An AZtec acquisition is already running.")


def _require_eds_cold(session: AztecSession) -> None:
    eds = session.eds
    if not eds.has_thermal_control:
        return
    state = eds.thermal_state().operating_state
    if state != OperatingState.COLD:
        raise DetectorError(
            f"The EDS detector is '{state.name}', not COLD. Wait for it to cool "
            "before starting."
        )


def _require_ready(session: AztecSession, acquisition_type: AcquisitionType) -> None:
    # AZtec reports readiness per technique, so check each flag on its own.
    for technique in (AcquisitionType.EBSD_MAP, AcquisitionType.EDS_MAP):
        if not acquisition_type & technique:
            continue
        readiness = session.technique_readiness(technique)
        if readiness.ready is not True:
            raise DetectorError(
                f"AZtec reports {technique.name} not ready: "
                f"{readiness.description or 'no reason given'}"
            )


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
    """Connect, check the link answers, and check the technique's detector exists."""
    with _session(general_settings) as session:
        detector = (
            session.ebsd if technique == tbt.ExternalTechnique.EBSD else session.eds
        )
        return session.ping() and bool(detector.name)


test_connection.__test__ = False


def preflight_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: List[tbt.EBSDSettings],
) -> bool:
    """Check AZtec is idle, and the EDS detector is cold for concurrent EDS."""
    _profile(general_settings, "ebsd")
    with _session(general_settings) as session:
        _require_idle(session)
        if any(settings.enable_eds for settings in step_settings):
            _require_eds_cold(session)
    return True


def preflight_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: List[tbt.EDSSettings],
) -> bool:
    """Check AZtec is idle and the EDS detector is cold."""
    _profile(general_settings, "eds")
    with _session(general_settings) as session:
        _require_idle(session)
        _require_eds_cold(session)
    return True


# ----------------------------------------------------------------------
# State and motion
# ----------------------------------------------------------------------


def get_ebsd_camera_state(
    general_settings: tbt.GeneralSettings,
) -> tbt.RetractableDeviceState:
    with _session(general_settings) as session:
        return device_state(session.ebsd.insertion_state())


def get_eds_detector_state(
    general_settings: tbt.GeneralSettings,
) -> tbt.RetractableDeviceState:
    with _session(general_settings) as session:
        return device_state(session.eds.insertion_state())


def _insert(microscope, general_settings, technique: tbt.ExternalTechnique) -> bool:
    detector_type = (
        tbt.DetectorType.EBSD
        if technique == tbt.ExternalTechnique.EBSD
        else tbt.DetectorType.EDS
    )
    _require_no_collision(microscope, detector_type)
    with _session(general_settings) as session:
        detector = (
            session.ebsd if technique == tbt.ExternalTechnique.EBSD else session.eds
        )
        state = device_state(detector.insertion_state())
        if state == STATE.INSERTED:
            return True
        if state != STATE.RETRACTED:
            raise DetectorError(
                f"The {technique.value} detector is '{state.value}', so it will not "
                "be inserted. Check it in AZtec."
            )
        _require_idle(session)
        with devices.ccd_live_view(microscope=microscope):
            final = device_state(detector.insert())
    if final != STATE.INSERTED:
        raise DetectorError(
            f"The {technique.value} detector did not insert; it is '{final.value}'."
        )
    return True


def _retract(microscope, general_settings, technique: tbt.ExternalTechnique) -> bool:
    """Retraction is the safe direction, so it proceeds from any state."""
    with _session(general_settings) as session:
        detector = (
            session.ebsd if technique == tbt.ExternalTechnique.EBSD else session.eds
        )
        if device_state(detector.insertion_state()) == STATE.RETRACTED:
            return True
        with devices.ccd_live_view(microscope=microscope):
            final = device_state(detector.retract())
    if final != STATE.RETRACTED:
        raise DetectorError(
            f"The {technique.value} detector did not retract; it is '{final.value}'."
        )
    return True


def insert_ebsd_camera(microscope, general_settings) -> bool:
    return _insert(microscope, general_settings, tbt.ExternalTechnique.EBSD)


def insert_eds_detector(microscope, general_settings) -> bool:
    return _insert(microscope, general_settings, tbt.ExternalTechnique.EDS)


def retract_ebsd_camera(microscope, general_settings) -> bool:
    return _retract(microscope, general_settings, tbt.ExternalTechnique.EBSD)


def retract_eds_detector(microscope, general_settings) -> bool:
    return _retract(microscope, general_settings, tbt.ExternalTechnique.EDS)


# ----------------------------------------------------------------------
# Parameters and mapping
# ----------------------------------------------------------------------


def _load_profile(general_settings: tbt.GeneralSettings, technique: str) -> bool:
    name = _profile(general_settings, technique)
    with _session(general_settings) as session:
        available = [profile.name for profile in session.acquisition.profiles()]
        if name not in available:
            raise ConfigurationError(
                f"AZtec has no profile named '{name}' "
                f"(Oxford_settings.{technique}_profile). Available: {available}"
            )
        session.acquisition.load_profile(name)
    return True


def set_ebsd_parameters(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
) -> bool:
    """Load the EBSD profile (which also carries concurrent EDS settings)."""
    return _load_profile(general_settings, "ebsd")


def set_eds_parameters(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
) -> bool:
    """Load the EDS profile."""
    return _load_profile(general_settings, "eds")


def map_name(slice_number: int) -> str:
    """AZtec acquisition name for a slice."""
    return f"slice_{slice_number:04d}"


def _map(general_settings, step_settings, slice_number) -> bool:
    acquisition_type = _acquisition_type(step_settings)
    with _session(general_settings) as session:
        _require_ready(session, acquisition_type)
        session.acquisition.run(
            AcquisitionConfig(acquisition_type=acquisition_type),
            name=map_name(slice_number),
        )
    return True


def map_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
    slice_number: int,
    on_metric: Callable[[str, float], None],
) -> bool:
    """Collect one EBSD map; with concurrent EDS when the step enables it.

    Concurrent EDS also needs "Include EDS" enabled in AZtec (or the profile).
    """
    return _map(general_settings, step_settings, slice_number)


def map_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
    slice_number: int,
    on_metric: Callable[[str, float], None],
) -> bool:
    return _map(general_settings, step_settings, slice_number)
