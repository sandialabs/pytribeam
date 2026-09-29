#!/usr/bin/python3
"""
External OEM Dispatcher
=======================

Routes external EBSD/EDS operations to the right backend for the configured
OEM. The workflow calls only this module; it never reaches into a vendor
package or the TFS LaserControl interface directly.

Routing
-------
EBSD and EDS are separate threads. Concurrent EDS during an EBSD scan is still
an EBSD scan: it is a flag on the EBSD step, routed with ``EBSD_OEM``.

============  =============================================  ===================
OEM           EBSD                                           EDS
============  =============================================  ===================
EDAX          native IPAPI when ``EDAX_settings`` is set,    LaserControl
              otherwise LaserControl
Oxford        LaserControl                                   LaserControl
Bruker        not supported                                  Bruker custom step
============  =============================================  ===================

Whether the native EDAX path applies depends on the configuration, not only the
OEM: a configuration without an ``EDAX_settings`` block names no IPAPI host, so
LaserControl is the only option. That reproduces the ``yml_version >= 1.1``
rule this dispatcher replaced.

Detector insertion and retraction stay on LaserControl for EDAX and Oxford in
both modes, matching the behavior proven on hardware. The native EDAX map also
retracts the camera over the IPAPI when it finishes.

Native EDAX EDS mapping is available in the wrapper but not routed here yet:
the experiment configuration has no EDS scan parameters to send, and the path
has not been validated on hardware.

Vendor packages are imported lazily, so selecting one OEM never imports
another's dependencies.
"""

# Local scripts
import pytribeam.insertable_devices as devices
import pytribeam.log as log
import pytribeam.types as tbt
from pytribeam.constants import Constants
from pytribeam.external_oem.edax.mapping import AVERAGE_CI, CAMERA_SATURATION

BRUKER_EDS_MESSAGE = (
    "Bruker EDS device control is handled by the Bruker workflow configuration; "
    "skipping TFS EDS control."
)
BRUKER_EBSD_MESSAGE = (
    "Bruker EBSD device control is not implemented in Phase 1; "
    "skipping TFS EBSD control."
)
BRUKER_EBSD_MAP_MESSAGE = (
    "EBSD mapping with Bruker requires the Bruker EBSD wrapper, which is not "
    "available yet. The TFS LaserControl interface does not support Bruker."
)
BRUKER_EDS_MAP_MESSAGE = (
    "EDS mapping with Bruker runs through the Bruker workflow as a 'custom' "
    "step, not an 'eds' step. The TFS LaserControl interface does not support "
    "Bruker."
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _ensure_oem(oem: tbt.ExternalDeviceOEM) -> tbt.ExternalDeviceOEM:
    """Validate and return an ExternalDeviceOEM value."""
    if not isinstance(oem, tbt.ExternalDeviceOEM):
        raise NotImplementedError(
            f"Unsupported type of {type(oem)}, only 'ExternalDeviceOEM' types are supported."
        )
    return oem


def _is_tfs_laser_oem(oem: tbt.ExternalDeviceOEM) -> bool:
    """Return True for OEMs the TFS LaserControl interface can drive."""
    return oem in (tbt.ExternalDeviceOEM.OXFORD, tbt.ExternalDeviceOEM.EDAX)


def _neutral_status() -> tbt.RetractableDeviceState:
    """Return a neutral non-error device status for no-op dispatcher branches."""
    return tbt.RetractableDeviceState.CONNECTED


def _laser():
    """Import the LaserControl module on first use."""
    import pytribeam.laser as laser

    return laser


def _edax_workflow():
    """Import the EDAX workflow glue on first use."""
    import pytribeam.external_oem.edax.workflow as edax_workflow

    return edax_workflow


def uses_native_edax_ebsd(general_settings: tbt.GeneralSettings) -> bool:
    """
    Return True when EBSD runs over the native EDAX IPAPI.

    Parameters
    ----------
    general_settings : tbt.GeneralSettings
        Experiment settings.

    Returns
    -------
    bool
        True when the EBSD OEM is EDAX and an ``EDAX_settings`` block names the
        IPAPI host. Configurations without one fall back to LaserControl.
    """
    oem = _ensure_oem(general_settings.EBSD_OEM)
    return (
        oem == tbt.ExternalDeviceOEM.EDAX
        and getattr(general_settings, "EDAX_settings", None) is not None
    )


# ----------------------------------------------------------------------
# Metric logging
# ----------------------------------------------------------------------
#: Maps each EBSD metric name to the log call that records it. Adding a metric
#: reported by any vendor needs one entry here and a dataset in log.py.
_EBSD_METRIC_LOGGERS = {
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


def log_ebsd_metric(
    general_settings: tbt.GeneralSettings,
    step: tbt.Step,
    slice_number: int,
    name: str,
    value: float,
) -> bool:
    """
    Record one EBSD metric in the experiment log.

    A metric with no registered dataset is reported and skipped rather than
    raising, so a vendor reporting something new cannot abort a running
    experiment.

    Parameters
    ----------
    general_settings : tbt.GeneralSettings
        Experiment settings, for the log file path.
    step : tbt.Step
        The step being run, for the dataset location.
    slice_number : int
        The slice being collected.
    name : str
        Metric name, such as ``camera_saturation`` or ``average_ci``.
    value : float
        The measured value.

    Returns
    -------
    bool
        True when the metric was logged, False when no dataset is defined.
    """
    logger = _EBSD_METRIC_LOGGERS.get(name)
    if logger is None:
        print(
            f"\tWARNING: no log dataset is defined for EBSD metric '{name}'; "
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


# ----------------------------------------------------------------------
# Connection and preflight
# ----------------------------------------------------------------------
def connect_eds(general_settings: tbt.GeneralSettings) -> tbt.RetractableDeviceState:
    """
    Connect to the configured external EDS device control interface.

    Bruker is a Phase 1 no-op placeholder and does not call TFS Laser API.
    """
    oem = _ensure_oem(general_settings.EDS_OEM)
    if oem == tbt.ExternalDeviceOEM.NONE:
        return _neutral_status()
    if _is_tfs_laser_oem(oem):
        return devices.connect_EDS()
    if oem == tbt.ExternalDeviceOEM.BRUKER:
        print(BRUKER_EDS_MESSAGE)
        return _neutral_status()
    raise NotImplementedError(f"Unsupported EDS OEM device control for '{oem.value}'.")


def connect_ebsd(general_settings: tbt.GeneralSettings) -> tbt.RetractableDeviceState:
    """
    Connect to the configured external EBSD device control interface.

    Detector control stays on LaserControl for EDAX even when mapping runs over
    the native IPAPI; the IPAPI connection is established by
    :func:`preflight_ebsd`. Bruker is a Phase 1 no-op placeholder and does not
    call TFS Laser API.
    """
    oem = _ensure_oem(general_settings.EBSD_OEM)
    if oem == tbt.ExternalDeviceOEM.NONE:
        return _neutral_status()
    if _is_tfs_laser_oem(oem):
        return devices.connect_EBSD()
    if oem == tbt.ExternalDeviceOEM.BRUKER:
        print(BRUKER_EBSD_MESSAGE)
        return _neutral_status()
    raise NotImplementedError(f"Unsupported EBSD OEM device control for '{oem.value}'.")


def check_edax_connection(host: str, port: int) -> bool:
    """
    Validate that an EDAX IPAPI service accepts connections.

    Used while validating an experiment configuration, before anything runs.

    Parameters
    ----------
    host : str
        Host running the IPAPI service.
    port : int
        IPAPI service port.

    Returns
    -------
    bool
        True when the service accepted the connection and unlock.

    Raises
    ------
    EdaxConnectionError
        If the service is unreachable or refuses the unlock.
    """
    return _edax_workflow().check_connection(host=host, port=port)


def preflight_ebsd(general_settings: tbt.GeneralSettings) -> bool:
    """
    Prepare the EBSD software before the first slice.

    For native EDAX this points the application at the experiment folder and
    project over the IPAPI. LaserControl needs no preflight, so the other OEMs
    return immediately.

    Parameters
    ----------
    general_settings : tbt.GeneralSettings
        Experiment settings.

    Returns
    -------
    bool
        True on success.
    """
    if uses_native_edax_ebsd(general_settings):
        return _edax_workflow().preflight(general_settings)
    return True


# ----------------------------------------------------------------------
# Detector motion
# ----------------------------------------------------------------------
def insert_eds(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """
    Insert the configured external EDS detector.

    Bruker is a Phase 1 no-op placeholder and does not call TFS Laser API.
    """
    oem = _ensure_oem(general_settings.EDS_OEM)
    if oem == tbt.ExternalDeviceOEM.NONE:
        return True
    if _is_tfs_laser_oem(oem):
        return devices.insert_EDS(microscope=microscope)
    if oem == tbt.ExternalDeviceOEM.BRUKER:
        print(BRUKER_EDS_MESSAGE)
        return True
    raise NotImplementedError(f"Unsupported EDS OEM device control for '{oem.value}'.")


def insert_ebsd(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """
    Insert the configured external EBSD detector.

    Bruker is a Phase 1 no-op placeholder and does not call TFS Laser API.
    """
    oem = _ensure_oem(general_settings.EBSD_OEM)
    if oem == tbt.ExternalDeviceOEM.NONE:
        return True
    if _is_tfs_laser_oem(oem):
        return devices.insert_EBSD(microscope=microscope)
    if oem == tbt.ExternalDeviceOEM.BRUKER:
        print(BRUKER_EBSD_MESSAGE)
        return True
    raise NotImplementedError(f"Unsupported EBSD OEM device control for '{oem.value}'.")


def retract_eds(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """
    Retract the configured external EDS detector.

    Bruker is a Phase 1 no-op placeholder and does not call TFS Laser API.
    """
    oem = _ensure_oem(general_settings.EDS_OEM)
    if oem == tbt.ExternalDeviceOEM.NONE:
        return True
    if _is_tfs_laser_oem(oem):
        return devices.retract_EDS(microscope=microscope)
    if oem == tbt.ExternalDeviceOEM.BRUKER:
        print(BRUKER_EDS_MESSAGE)
        return True
    raise NotImplementedError(f"Unsupported EDS OEM device control for '{oem.value}'.")


def retract_ebsd(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """
    Retract the configured external EBSD detector.

    Bruker is a Phase 1 no-op placeholder and does not call TFS Laser API.
    """
    oem = _ensure_oem(general_settings.EBSD_OEM)
    if oem == tbt.ExternalDeviceOEM.NONE:
        return True
    if _is_tfs_laser_oem(oem):
        return devices.retract_EBSD(microscope=microscope)
    if oem == tbt.ExternalDeviceOEM.BRUKER:
        print(BRUKER_EBSD_MESSAGE)
        return True
    raise NotImplementedError(f"Unsupported EBSD OEM device control for '{oem.value}'.")


def retract_all_external_devices(
    microscope: tbt.Microscope,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Retract all configured external OEM EBSD/EDS detectors."""
    if general_settings.EBSD_OEM != tbt.ExternalDeviceOEM.NONE:
        retract_ebsd(microscope=microscope, general_settings=general_settings)
    if general_settings.EDS_OEM != tbt.ExternalDeviceOEM.NONE:
        retract_eds(microscope=microscope, general_settings=general_settings)
    return True


# ----------------------------------------------------------------------
# Mapping
# ----------------------------------------------------------------------
def map_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
    slice_number: int,
    step: tbt.Step,
) -> bool:
    """
    Collect one EBSD map with the configured OEM.

    Native EDAX collection logs each metric as soon as it is measured, so the
    camera saturation is recorded even when the map that follows fails.

    Parameters
    ----------
    general_settings : tbt.GeneralSettings
        Experiment settings.
    step_settings : tbt.EBSDSettings
        The EBSD step's scan and concurrent-EDS settings.
    slice_number : int
        The slice being collected.
    step : tbt.Step
        The step being run, for logging.

    Returns
    -------
    bool
        True once the map is complete.

    Raises
    ------
    NotImplementedError
        For Bruker, which LaserControl cannot drive and whose EBSD wrapper is
        not available yet, or when no EBSD OEM is configured.
    """
    oem = _ensure_oem(general_settings.EBSD_OEM)

    if uses_native_edax_ebsd(general_settings):

        def record(name: str, value: float) -> None:
            log_ebsd_metric(general_settings, step, slice_number, name, value)

        _edax_workflow().map_ebsd(
            general_settings=general_settings,
            step_settings=step_settings,
            slice_number=slice_number,
            on_metric=record,
        )
        return True

    if _is_tfs_laser_oem(oem):
        return _laser().map_ebsd()
    if oem == tbt.ExternalDeviceOEM.BRUKER:
        raise NotImplementedError(BRUKER_EBSD_MAP_MESSAGE)
    raise NotImplementedError(
        f"An EBSD step was requested, but the EBSD OEM is '{oem.value}'."
    )


def map_eds(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EDSSettings = None,
    slice_number: int = None,
    step: tbt.Step = None,
) -> bool:
    """
    Collect one EDS map with the configured OEM.

    The step arguments are accepted for symmetry with :func:`map_ebsd`, and so
    native EDAX EDS can be routed here later without changing callers.

    Parameters
    ----------
    general_settings : tbt.GeneralSettings
        Experiment settings.
    step_settings : tbt.EDSSettings, optional
        The EDS step's settings.
    slice_number : int, optional
        The slice being collected.
    step : tbt.Step, optional
        The step being run.

    Returns
    -------
    bool
        True once the map is complete.

    Raises
    ------
    NotImplementedError
        For Bruker, whose EDS maps run as a custom step, or when no EDS OEM is
        configured.
    """
    oem = _ensure_oem(general_settings.EDS_OEM)
    if _is_tfs_laser_oem(oem):
        return _laser().map_eds()
    if oem == tbt.ExternalDeviceOEM.BRUKER:
        raise NotImplementedError(BRUKER_EDS_MAP_MESSAGE)
    raise NotImplementedError(
        f"An EDS step was requested, but the EDS OEM is '{oem.value}'."
    )
