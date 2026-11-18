"""
Oxford AZtec adapter
====================

Native Oxford backend, through the AZtec plugin API
(`pytribeam.external_oem.oxford`). LaserControl is never used.

AZtec's plugin API cannot set technique parameters (step size, dwell,
resolution...). Parameters are applied by loading the AZtec profile named in
each step's `oxford_settings.profile`, so steps can differ. Loading a profile
replaces AZtec's current settings, including unsaved GUI changes.

Data: each experiment has one AZtec project, `<project_folder>/<experiment>/`
(`Oxford_settings.project_folder`, on the AZtec computer), created or reopened
by preflight. Every map is acquired into it and exported to `.h5oina` in the
project's `data` folder, next to the `.ebsp` pattern file AZtec saves for EBSD
maps (when pattern saving is on in the profile), so AZtecCrystal pairs them.
Without the export, AZtec keeps a map only in its internal `.dat` files.

AZtec only reports a technique "ready" once its detector is inserted (and, for
EDS, cold), so preflight checks what does not depend on insertion, and each map
checks AZtec's readiness just before collecting.

Each call opens its own session and disconnects afterwards. `session_factory`
builds that session; tests replace it to run against the in-process simulator.

See the adapter contract in `pytribeam.external_oem.dispatch`.
"""

# Default python modules
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, List

# Local scripts
import pytribeam.types as tbt
from pytribeam.external_oem.core.errors import ConfigurationError, DetectorError
from pytribeam.external_oem.oxford.enums import (
    AcquisitionType,
    InsertionActivity,
    InsertionPositionState,
    OperatingState,
    StatusImageTypes,
)
from pytribeam.external_oem.oxford.data import windows_safe
from pytribeam.external_oem.oxford.errors import DataError, ScanExportError
from pytribeam.external_oem.oxford.models import AcquisitionConfig, ProjectInfo
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


def _step(step_settings, technique: str) -> tbt.OxfordStepSettings:
    """The step's Oxford settings, or a clear error if it has none."""
    if step_settings.oxford is None:
        raise ConfigurationError(
            f"Oxford {technique} parameters are applied by loading an AZtec "
            f"profile, but this {technique} step has no 'oxford_settings' "
            "(profile)."
        )
    return step_settings.oxford


def _profile(step_settings, technique: str) -> str:
    return _step(step_settings, technique).profile


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


def _project_location(general_settings: tbt.GeneralSettings):
    """(folder, name, project file) of the experiment's AZtec project.

    Named after the experiment directory; the file layout is AZtec's own
    (`<folder>/<name>/<name>.oipx`, observed on AZtec 6.1).
    """
    folder = general_settings.Oxford_settings.project_folder
    if folder is None:
        raise ConfigurationError(
            "Oxford needs Oxford_settings 'project_folder' (a folder on the AZtec "
            "computer) for the experiment's AZtec project and exports."
        )
    folder = str(folder)
    name = windows_safe(Path(str(general_settings.exp_dir)).name) or "pytribeam"
    sep = "\\" if ("\\" in folder or ":" in folder[:3]) else "/"
    file_name = sep.join([folder.rstrip("\\/"), name, name + ".oipx"])
    return folder, name, file_name


def _same_path(first: str, second: str) -> bool:
    return first.replace("\\", "/").lower() == second.replace("\\", "/").lower()


def ensure_project(
    session: AztecSession, general_settings: tbt.GeneralSettings
) -> ProjectInfo:
    """The experiment's AZtec project: already open, reopened, or created.

    Reusing it means validating then starting, or resuming, never creates a
    second project for the same experiment.
    """
    folder, name, file_name = _project_location(general_settings)
    for project in session.data.projects():
        if project.file_name and _same_path(project.file_name, file_name):
            return project
    try:
        return session.data.open_project(file_name)
    except DataError:
        pass  # not created yet
    if session.aztec_is_local:
        Path(folder).mkdir(parents=True, exist_ok=True)
    project = session.data.create_project(name, folder)
    print(f"\tCreated AZtec project {file_name}")
    return project


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
    """Check every step has its Oxford settings, AZtec is idle, and the EDS
    detector is cold for concurrent EDS; create or reopen the experiment's
    AZtec project. The profiles are loaded by set_ebsd_parameters."""
    for settings in step_settings:
        _step(settings, "EBSD")
    with _session(general_settings) as session:
        _require_idle(session)
        if any(settings.enable_eds for settings in step_settings):
            _require_eds_cold(session)
        ensure_project(session, general_settings)
    return True


def preflight_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: List[tbt.EDSSettings],
) -> bool:
    """Check every step has its Oxford settings, AZtec is idle, and the EDS
    detector is cold; create or reopen the experiment's AZtec project. The
    profiles are loaded by set_eds_parameters."""
    for settings in step_settings:
        _step(settings, "EDS")
    with _session(general_settings) as session:
        _require_idle(session)
        _require_eds_cold(session)
        ensure_project(session, general_settings)
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
    """Move a detector in. The dispatcher has checked for collisions and shows
    the chamber CCD around this call."""
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


def _load_profile(general_settings, step_settings, technique: str) -> bool:
    name = _profile(step_settings, technique)
    with _session(general_settings) as session:
        available = [profile.name for profile in session.acquisition.profiles()]
        if name not in available:
            raise ConfigurationError(
                f"AZtec has no profile named '{name}' (the {technique} step's "
                f"oxford_settings.profile). Available: {available}"
            )
        session.acquisition.load_profile(name)
    return True


def set_ebsd_parameters(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
) -> bool:
    """Load the step's profile (which also carries concurrent EDS settings)."""
    return _load_profile(general_settings, step_settings, "EBSD")


def set_eds_parameters(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
) -> bool:
    """Load the step's profile."""
    return _load_profile(general_settings, step_settings, "EDS")


def map_name(run_name: str, slice_number: int) -> str:
    """AZtec acquisition (and exported file) name for a step's slice."""
    return f"{run_name}_slice_{slice_number:04d}"


#: Status images to request per technique. AZtec can leave an acquisition's
#: map ids empty unless its status image was requested, and the export needs
#: those ids.
_STATUS_IMAGES = {
    AcquisitionType.EBSD_MAP: StatusImageTypes.EBSD_MAP,
    AcquisitionType.EDS_MAP: StatusImageTypes.EDS_MAP,
}


def _status_images(acquisition_type: AcquisitionType) -> StatusImageTypes:
    images = StatusImageTypes.NONE
    for technique, image in _STATUS_IMAGES.items():
        if acquisition_type & technique:
            images |= image
    return images


def _map(general_settings, step_settings, slice_number, technique: str) -> bool:
    step = _step(step_settings, technique)
    acquisition_type = _acquisition_type(step_settings)
    name = map_name(step.run_name, slice_number)
    with _session(general_settings) as session:
        _require_ready(session, acquisition_type)
        project = ensure_project(session, general_settings)
        specimens = session.data.specimens(project)
        config = AcquisitionConfig(
            acquisition_type=acquisition_type,
            status_images=_status_images(acquisition_type),
            project_id=project.id,
            specimen_id=specimens[0].id if specimens else None,
        )
        try:
            # Acquire, then have AZtec export each map to <project>/data, next
            # to the .ebsp. Pattern saving is an AZtec profile setting, so a
            # missing .ebsp is a warning, not an error.
            result = session.scan(name, config, item_name=name, require_patterns=False)
        except ScanExportError as error:
            raise DetectorError(
                f"The {technique} map '{name}' was collected but AZtec could not "
                f"export it: {error}. It is still in the AZtec project "
                f"{project.file_name}."
            ) from error
    for files in result.files:
        print(f"\tAZtec exported {files.scan}")
        if files.patterns:
            print(f"\t\tpatterns: {files.patterns}")
    return True


def map_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
    slice_number: int,
    on_metric: Callable[[str, float], None],
) -> bool:
    """Collect one EBSD map, with concurrent EDS when the step enables it, and
    export it to .h5oina (EDS included).

    Concurrent EDS also needs "Include EDS" enabled in AZtec (or the profile).
    """
    return _map(general_settings, step_settings, slice_number, "EBSD")


def map_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
    slice_number: int,
    on_metric: Callable[[str, float], None],
) -> bool:
    """Collect one EDS map and export it to .h5oina."""
    return _map(general_settings, step_settings, slice_number, "EDS")
