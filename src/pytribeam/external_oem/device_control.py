#!/usr/bin/python3
"""
External OEM Device Control Dispatcher
======================================

This module dispatches external OEM EBSD/EDS device-control operations.

For Phase 1, Oxford and EDAX preserve existing behavior by delegating to the
current TFS Laser-style functions in :mod:`pytribeam.insertable_devices`.
Bruker branches are safe placeholders and must not call the TFS Laser API.
"""

# Local scripts
import pytribeam.insertable_devices as devices
import pytribeam.types as tbt

BRUKER_EDS_MESSAGE = (
    "Bruker EDS device control is handled by the Bruker workflow configuration; "
    "skipping TFS EDS control."
)
BRUKER_EBSD_MESSAGE = (
    "Bruker EBSD device control is not implemented in Phase 1; "
    "skipping TFS EBSD control."
)


def _ensure_oem(oem: tbt.ExternalDeviceOEM) -> tbt.ExternalDeviceOEM:
    """Validate and return an ExternalDeviceOEM value."""
    if not isinstance(oem, tbt.ExternalDeviceOEM):
        raise NotImplementedError(
            f"Unsupported type of {type(oem)}, only 'ExternalDeviceOEM' types are supported."
        )
    return oem


def _is_tfs_laser_oem(oem: tbt.ExternalDeviceOEM) -> bool:
    """Return True for OEMs still routed through TFS Laser-style device control."""
    return oem in (tbt.ExternalDeviceOEM.OXFORD, tbt.ExternalDeviceOEM.EDAX)


def _neutral_status() -> tbt.RetractableDeviceState:
    """Return a neutral non-error device status for no-op dispatcher branches."""
    return tbt.RetractableDeviceState.CONNECTED


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

    Bruker is a Phase 1 no-op placeholder and does not call TFS Laser API.
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
