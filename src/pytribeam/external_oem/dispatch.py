"""
# External OEM dispatcher

This script is the high level dispatcher that converts a generic `map_ebsd(...)` (and other functions) into the corresponding external vendor API commands.

### Necessary functionality

external_oem.test_connection(...) - Test whether or not the connection to the vendor is available and functioning
external_oem.insert_ebsd_camera(...) - Insert the EBSD camera.
external_oem.insert_eds_detector(...) - Insert the EDS detector.
external_oem.get_ebsd_camera_state(...) - Get the current state of the EBSD camera.
external_oem.get_eds_detector_state(...) - Get the current state of the EDS detector.
external_oem.retract_ebsd_camera(...) - Retract the EBSD camera.
external_oem.retract_eds_detector(...) - Retract the EDS detector.
external_oem.set_ebsd_parameters(...) - Set the EBSD parameters. Some vendors do not allow this, in which case it checks if the user needs to manually update the parameters in the GUI and raises an error if the current parameters are not equal to the desired parameters.
external_oem.set_eds_parameters(...) - Set the EDS parameters. Some vendors do not allow this, in which case it checks if the user needs to manually update the parameters in the GUI and raises an error if the current parameters are not equal to the desired parameters.
external_oem.map_ebsd(...) - Collect an EBSD map
external_oem.map_eds(...) - Collect an EDS map
external_oem.preflight_eds(...) - This is a test connection call and also a set parameters call. There are often configuration things that need to happen when connecting to the API (setting project, setting parameters, etc.)
external_oem.preflight_ebsd(...) - This is a test connection call and also a set parameters call. There are often configuration things that need to happen when connecting to the API (setting project, setting parameters, etc.)


### External OEMs

There are three external OEMs, with a fallback for two of them: EDAX, Oxford, Bruker. EDAX and Oxford both have a fallback with thermofisher (through their laser module) that provides basic detector insert/retract/status and map EBSD/EDS.


### Notes

- We will need to add some types to src/pytribeam/types.py for the external vendors. This codebase tries to use functional programming and not object oriented, relying heavily on enumerated types. OOP is allowed, but FP is preferred.
- Modifications to the EDAX/Bruker/Oxford submodules are allowed, but should be minimized in order to preserve the known functionality.
- The goal is to keep this lightweight.
- Tests are required. We use a unique marking strategy to ensure that only relevant tests are run on machines (i.e. a simulator does not run hardware tests, a PC with EDAX does not run Oxford tests, etc.). I suspect this will need to be updated for the multi-vendor support we are adding here.
- There are integrations necessary elsewhere in the code (such as src/pytribeam/insertable_devices.py). These are mainly places where we ensure that insertions or stage movements are safe. Those should not be implemented until the external_oem submodule is completed.

"""

# Default python modules
import importlib
from types import ModuleType
from typing import Any, Callable, List, Optional, Sequence

# Local scripts
import pytribeam.log as log
import pytribeam.types as tbt
from pytribeam.constants import Constants
from pytribeam.external_oem.core.errors import ConfigurationError, DetectorError

# ----------------------------------------------------------------------
# Adapter contract
# ----------------------------------------------------------------------
# Each backend has one adapter module under ``external_oem/adapters``. It is a
# plain module (no classes required) that exposes these functions, and it is
# the only code that translates between pyTriBeam types and a vendor API:
#
#   test_connection(general_settings, technique) -> bool
#   preflight_ebsd(general_settings, step_settings: List[EBSDSettings]) -> bool
#   preflight_eds(general_settings, step_settings: List[EDSSettings]) -> bool
#   get_ebsd_camera_state(general_settings) -> RetractableDeviceState
#   get_eds_detector_state(general_settings) -> RetractableDeviceState
#   insert_ebsd_camera(microscope, general_settings) -> bool
#   insert_eds_detector(microscope, general_settings) -> bool
#   retract_ebsd_camera(microscope, general_settings) -> bool
#   retract_eds_detector(microscope, general_settings) -> bool
#   set_ebsd_parameters(general_settings, step_settings) -> bool
#   set_eds_parameters(general_settings, step_settings) -> bool
#   map_ebsd(general_settings, step_settings, slice_number, on_metric) -> bool
#   map_eds(general_settings, step_settings, slice_number, on_metric) -> bool
#
# Rules for adapters:
# - States are returned as ``tbt.RetractableDeviceState``, never vendor enums.
# - Failures raise ``core.errors.DetectorError`` subclasses with the reason.
# - Every insert/retract checks for collisions before inserting and runs under
#   ``insertable_devices.ccd_live_view``. (Phase 6 moves this into the
#   dispatcher, so it is enforced in one place.)
# - Native adapters never call LaserControl.
# - ``preflight_*`` does vendor-specific readiness and session setup only; the
#   dispatcher runs the connection test, the state check, and the per-step
#   ``set_*_parameters`` calls around it.
# - ``map_*`` reports measured values through ``on_metric(name, value)``.

#: Module implementing each backend, imported only when that backend is used,
#: so selecting one vendor never loads another's dependencies.
ADAPTER_MODULES = {
    tbt.ExternalBackend.TFS_LASER: "pytribeam.external_oem.adapters.tfs_laser",
    tbt.ExternalBackend.EDAX_IPAPI: "pytribeam.external_oem.adapters.edax",
    tbt.ExternalBackend.OXFORD_AZTEC: "pytribeam.external_oem.adapters.oxford",
    tbt.ExternalBackend.BRUKER_ESPRIT: "pytribeam.external_oem.adapters.bruker",
}

EBSD = tbt.ExternalTechnique.EBSD
EDS = tbt.ExternalTechnique.EDS

#: Step settings type whose steps each technique collects.
_STEP_SETTINGS_TYPE = {EBSD: tbt.EBSDSettings, EDS: tbt.EDSSettings}

#: Vendor-neutral names for metrics adapters report through ``on_metric``.
CAMERA_SATURATION = "camera_saturation"
AVERAGE_CI = "average_ci"

#: OEMs that can fall back to TFS LaserControl when their native settings
#: block is absent, mapped to the native backend used when it is present.
_NATIVE_WITH_FALLBACK = {
    tbt.ExternalDeviceOEM.EDAX: tbt.ExternalBackend.EDAX_IPAPI,
    tbt.ExternalDeviceOEM.OXFORD: tbt.ExternalBackend.OXFORD_AZTEC,
}


def resolve_backend(
    oem: tbt.ExternalDeviceOEM,
    *,
    edax_settings: Any = None,
    oxford_settings: Any = None,
    bruker_settings: Any = None,
) -> Optional[tbt.ExternalBackend]:
    """
    Return the backend that drives a detector from this OEM.

    The native vendor API is used when that vendor's settings block is present;
    otherwise EDAX and Oxford fall back to TFS LaserControl. Only presence is
    checked, so the settings may be raw YAML dictionaries (during validation)
    or parsed config objects.

    ## Parameters

    - `oem` (`tbt.ExternalDeviceOEM`): The configured EBSD or EDS OEM.
    - `edax_settings`, `oxford_settings`, `bruker_settings`: The vendor
      settings blocks, or None when absent.

    ## Returns

    - `tbt.ExternalBackend`: The backend to use, or None when `oem` is
      `ExternalDeviceOEM.NONE`.

    ## Raises

    - `TypeError`: If `oem` is not an `ExternalDeviceOEM`.
    - `ConfigurationError`: If the OEM is Bruker and no `Bruker_settings`
      block is present; Bruker has no LaserControl fallback.
    """
    if not isinstance(oem, tbt.ExternalDeviceOEM):
        raise TypeError(f"Expected an ExternalDeviceOEM, got {type(oem).__name__}.")
    if oem == tbt.ExternalDeviceOEM.NONE:
        return None
    if oem == tbt.ExternalDeviceOEM.BRUKER:
        if bruker_settings is None:
            raise ConfigurationError(
                "Bruker EBSD/EDS requires a 'Bruker_settings' block (config file "
                "version 1.2 or later); Bruker has no LaserControl fallback."
            )
        return tbt.ExternalBackend.BRUKER_ESPRIT

    native_settings = {
        tbt.ExternalDeviceOEM.EDAX: edax_settings,
        tbt.ExternalDeviceOEM.OXFORD: oxford_settings,
    }[oem]
    if native_settings is not None:
        return _NATIVE_WITH_FALLBACK[oem]
    return tbt.ExternalBackend.TFS_LASER


# ----------------------------------------------------------------------
# Backend lookup
# ----------------------------------------------------------------------


def oem(
    general_settings: tbt.GeneralSettings,
    technique: tbt.ExternalTechnique,
) -> tbt.ExternalDeviceOEM:
    """Return the OEM configured for a technique."""
    if technique == EBSD:
        return general_settings.EBSD_OEM
    if technique == EDS:
        return general_settings.EDS_OEM
    raise TypeError(f"Expected an ExternalTechnique, got {technique!r}.")


def backend(
    general_settings: tbt.GeneralSettings,
    technique: tbt.ExternalTechnique,
) -> Optional[tbt.ExternalBackend]:
    """
    Return the backend that drives a technique for these settings.

    ## Returns

    - `tbt.ExternalBackend`: The backend, or None when no OEM is configured
      for the technique.

    ## Raises

    - `ConfigurationError`: If the configuration names no usable backend
      (see `resolve_backend`).
    """
    return resolve_backend(
        oem(general_settings, technique),
        edax_settings=general_settings.EDAX_settings,
        oxford_settings=general_settings.Oxford_settings,
        bruker_settings=general_settings.Bruker_settings,
    )


def adapter(backend: tbt.ExternalBackend) -> ModuleType:
    """Import and return the adapter module for a backend."""
    return importlib.import_module(ADAPTER_MODULES[backend])


def _required_adapter(
    general_settings: tbt.GeneralSettings,
    technique: tbt.ExternalTechnique,
    action: str,
) -> ModuleType:
    """Return the technique's adapter, or raise if no OEM is configured."""
    found = backend(general_settings, technique)
    if found is None:
        raise ConfigurationError(
            f"{action} was requested, but no {technique.value} OEM is configured "
            f"('{technique.value}_OEM' is null)."
        )
    return adapter(found)


def _checked_state(state: Any, source: str) -> tbt.RetractableDeviceState:
    """Enforce that an adapter translated its vendor state."""
    if not isinstance(state, tbt.RetractableDeviceState):
        raise TypeError(
            f"{source} returned {state!r}; adapters must return a "
            "tbt.RetractableDeviceState."
        )
    return state


def _technique_step_settings(
    steps: Sequence[tbt.Step],
    technique: tbt.ExternalTechnique,
) -> List[Any]:
    """Return the operation settings of every step that maps with a technique.

    Concurrent EDS during an EBSD scan is part of the EBSD step, so it is
    covered by EBSD.
    """
    settings_type = _STEP_SETTINGS_TYPE[technique]
    return [
        step.operation_settings
        for step in steps
        if isinstance(step.operation_settings, settings_type)
    ]


# ----------------------------------------------------------------------
# Metric logging
# ----------------------------------------------------------------------

#: Maps each metric name to the log call that records it. Adding a metric
#: reported by any vendor needs one entry here and a dataset in log.py.
_METRIC_LOGGERS = {
    CAMERA_SATURATION: lambda common, value: log.ebsd_camera_saturation(
        **common,
        dataset_name=Constants.ebsd_camera_saturation_dataset_name,
        cam_sat_p=value,
    ),
    AVERAGE_CI: lambda common, value: log.ebsd_average_ci(
        **common,
        dataset_name=Constants.ebsd_average_ci_dataset_name,
        avg_ci_p=value,
    ),
}


def log_metric(
    general_settings: tbt.GeneralSettings,
    step: tbt.Step,
    slice_number: int,
    name: str,
    value: float,
) -> bool:
    """
    Record one measured metric in the experiment log.

    A metric with no registered dataset is reported and skipped rather than
    raising, so a vendor reporting something new cannot abort a running
    experiment.

    ## Returns

    - `bool`: True when the metric was logged, False when no dataset is defined.
    """
    logger = _METRIC_LOGGERS.get(name)
    if logger is None:
        print(
            f"\tWARNING: no log dataset is defined for metric '{name}'; "
            f"value {value} was not logged."
        )
        return False
    logger(
        {
            "step_number": step.number,
            "step_name": step.name,
            "slice_number": slice_number,
            "log_filepath": general_settings.log_filepath,
        },
        value,
    )
    return True


def _metric_logger(
    general_settings: tbt.GeneralSettings,
    step: tbt.Step,
    slice_number: int,
) -> Callable[[str, float], None]:
    """Return an ``on_metric`` callback that logs each value as it arrives."""

    def on_metric(name: str, value: float) -> None:
        log_metric(general_settings, step, slice_number, name, value)

    return on_metric


# ----------------------------------------------------------------------
# Connection and preflight
# ----------------------------------------------------------------------


def test_connection(
    general_settings: tbt.GeneralSettings,
    technique: tbt.ExternalTechnique,
) -> bool:
    """
    Test that the vendor interface for a technique is reachable and working.

    ## Returns

    - `bool`: True when the connection works.

    ## Raises

    - `ConfigurationError`: If no OEM is configured for the technique.
    - `DetectorError`: If the vendor interface cannot be reached.
    """
    found = _required_adapter(general_settings, technique, "A connection test")
    if not found.test_connection(general_settings, technique):
        raise DetectorError(
            f"{technique.value} connection test failed for "
            f"{oem(general_settings, technique).value}."
        )
    return True


# Not a pytest test, despite the name.
test_connection.__test__ = False


def _preflight(
    general_settings: tbt.GeneralSettings,
    technique: tbt.ExternalTechnique,
    steps: Sequence[tbt.Step],
) -> bool:
    """Check everything a technique will do, short of collecting data."""
    step_settings = _technique_step_settings(steps, technique)
    if backend(general_settings, technique) is None:
        if step_settings:
            raise ConfigurationError(
                f"The experiment has {technique.value} steps, but no "
                f"{technique.value} OEM is configured "
                f"('{technique.value}_OEM' is null)."
            )
        return True

    # Concurrent EDS inserts the EDS detector, which follows EDS_OEM.
    if (
        technique == EBSD
        and any(settings.enable_eds for settings in step_settings)
        and backend(general_settings, EDS) is None
    ):
        raise ConfigurationError(
            "An EBSD step enables concurrent EDS, but no EDS OEM is configured "
            "('EDS_OEM' is null), so the EDS detector cannot be inserted."
        )

    test_connection(general_settings, technique)

    state = _get_state(general_settings, technique)
    if state == tbt.RetractableDeviceState.ERROR:
        raise DetectorError(f"The {technique.value} detector is in an error state.")

    found = _required_adapter(general_settings, technique, "Preflight")
    if technique == EBSD:
        found.preflight_ebsd(general_settings, step_settings)
        set_parameters = found.set_ebsd_parameters
    else:
        found.preflight_eds(general_settings, step_settings)
        set_parameters = found.set_eds_parameters

    # Prove every step's parameters can be applied before the first slice.
    for settings in step_settings:
        set_parameters(general_settings, settings)
    return True


def preflight_ebsd(
    general_settings: tbt.GeneralSettings,
    steps: Sequence[tbt.Step],
) -> bool:
    """
    Verify, before the first slice, that every EBSD step can run.

    Tests the connection, checks the camera is not in an error state, runs the
    vendor's readiness checks and session setup, then applies the parameters of
    every EBSD step (including concurrent EDS). Stops short of collecting data.

    ## Parameters

    - `general_settings` (`tbt.GeneralSettings`): The experiment settings.
    - `steps` (`Sequence[tbt.Step]`): All experiment steps; non-EBSD steps
      are ignored.

    ## Returns

    - `bool`: True when every check passed. With no EBSD OEM and no EBSD
      steps, there is nothing to check.

    ## Raises

    - `ConfigurationError`: If there are EBSD steps but no EBSD OEM.
    - `DetectorError`: If any check fails.
    """
    return _preflight(general_settings, EBSD, steps)


def preflight_eds(
    general_settings: tbt.GeneralSettings,
    steps: Sequence[tbt.Step],
) -> bool:
    """
    Verify, before the first slice, that every EDS step can run.

    The EDS counterpart of `preflight_ebsd`. Concurrent EDS during an EBSD scan
    belongs to the EBSD step and is checked by `preflight_ebsd`.
    """
    return _preflight(general_settings, EDS, steps)


# ----------------------------------------------------------------------
# Detector state and motion
# ----------------------------------------------------------------------


def _get_state(
    general_settings: tbt.GeneralSettings,
    technique: tbt.ExternalTechnique,
) -> tbt.RetractableDeviceState:
    if technique == EBSD:
        found = _required_adapter(general_settings, EBSD, "EBSD camera state")
        return _checked_state(
            found.get_ebsd_camera_state(general_settings),
            f"{found.__name__}.get_ebsd_camera_state",
        )
    found = _required_adapter(general_settings, EDS, "EDS detector state")
    return _checked_state(
        found.get_eds_detector_state(general_settings),
        f"{found.__name__}.get_eds_detector_state",
    )


def get_ebsd_camera_state(
    general_settings: tbt.GeneralSettings,
) -> tbt.RetractableDeviceState:
    """Return the EBSD camera state."""
    return _get_state(general_settings, EBSD)


def get_eds_detector_state(
    general_settings: tbt.GeneralSettings,
) -> tbt.RetractableDeviceState:
    """Return the EDS detector state."""
    return _get_state(general_settings, EDS)


def insert_ebsd_camera(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Insert the EBSD camera."""
    found = _required_adapter(general_settings, EBSD, "EBSD camera insertion")
    return found.insert_ebsd_camera(microscope, general_settings)


def insert_eds_detector(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """
    Insert the EDS detector.

    Also used for concurrent EDS during an EBSD scan: detector motion follows
    the detector's own OEM, while the map follows the step type.
    """
    found = _required_adapter(general_settings, EDS, "EDS detector insertion")
    return found.insert_eds_detector(microscope, general_settings)


def retract_ebsd_camera(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Retract the EBSD camera. With no EBSD OEM there is nothing to retract."""
    found = backend(general_settings, EBSD)
    if found is None:
        return True
    return adapter(found).retract_ebsd_camera(microscope, general_settings)


def retract_eds_detector(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Retract the EDS detector. With no EDS OEM there is nothing to retract."""
    found = backend(general_settings, EDS)
    if found is None:
        return True
    return adapter(found).retract_eds_detector(microscope, general_settings)


def retract_all_external_devices(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """
    Retract every configured external detector.

    Used at the end of an experiment and on abort, so every retraction is
    attempted even if an earlier one fails.

    ## Returns

    - `bool`: True when every retraction succeeded.

    ## Raises

    - `DetectorError`: After attempting all retractions, if any failed.
    """
    failures = []
    for name, retract in (
        ("EBSD camera", retract_ebsd_camera),
        ("EDS detector", retract_eds_detector),
    ):
        try:
            if not retract(microscope, general_settings):
                failures.append(f"{name}: retraction reported failure")
        except Exception as error:
            failures.append(f"{name}: {type(error).__name__}: {error}")
    if failures:
        raise DetectorError("Could not retract: " + "; ".join(failures))
    return True


# ----------------------------------------------------------------------
# Parameters and mapping
# ----------------------------------------------------------------------


def _check_step_settings(step_settings: Any, technique: tbt.ExternalTechnique):
    expected = _STEP_SETTINGS_TYPE[technique]
    if not isinstance(step_settings, expected):
        raise TypeError(
            f"{technique.value} needs {expected.__name__}, got "
            f"{type(step_settings).__name__}."
        )


def set_ebsd_parameters(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
) -> bool:
    """
    Apply an EBSD step's parameters on the vendor side.

    Vendors that cannot set a parameter check it instead, and raise
    `ConfigurationError` telling the operator what to change in the vendor GUI.
    """
    _check_step_settings(step_settings, EBSD)
    found = _required_adapter(general_settings, EBSD, "Setting EBSD parameters")
    return found.set_ebsd_parameters(general_settings, step_settings)


def set_eds_parameters(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
) -> bool:
    """Apply an EDS step's parameters on the vendor side; see `set_ebsd_parameters`."""
    _check_step_settings(step_settings, EDS)
    found = _required_adapter(general_settings, EDS, "Setting EDS parameters")
    return found.set_eds_parameters(general_settings, step_settings)


def map_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
    slice_number: int,
    step: tbt.Step,
) -> bool:
    """
    Collect one EBSD map (with concurrent EDS when the step enables it).

    The step's parameters are applied first, since steps may differ. Metrics
    the vendor reports are logged to the experiment log as they arrive.
    """
    _check_step_settings(step_settings, EBSD)
    found = _required_adapter(general_settings, EBSD, "An EBSD map")
    found.set_ebsd_parameters(general_settings, step_settings)
    return found.map_ebsd(
        general_settings,
        step_settings,
        slice_number,
        _metric_logger(general_settings, step, slice_number),
    )


def map_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings,
    slice_number: int,
    step: tbt.Step,
) -> bool:
    """Collect one EDS map; see `map_ebsd`."""
    _check_step_settings(step_settings, EDS)
    found = _required_adapter(general_settings, EDS, "An EDS map")
    found.set_eds_parameters(general_settings, step_settings)
    return found.map_eds(
        general_settings,
        step_settings,
        slice_number,
        _metric_logger(general_settings, step, slice_number),
    )
