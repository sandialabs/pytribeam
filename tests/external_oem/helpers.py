"""Shared helpers for the external OEM adapter tests."""

import pytribeam.types as tbt

OEM = tbt.ExternalDeviceOEM
STATE = tbt.RetractableDeviceState
EBSD = tbt.ExternalTechnique.EBSD
EDS = tbt.ExternalTechnique.EDS

#: Stand-in microscope; the chamber fixture intercepts everything that uses it.
MICROSCOPE = object()


def general_settings(ebsd_oem=OEM.NONE, eds_oem=OEM.NONE, exp_dir=".", **blocks):
    """Build minimal GeneralSettings for adapter tests."""
    return tbt.GeneralSettings(
        yml_version=1.2,
        slice_thickness_um=1.0,
        max_slice_number=10,
        pre_tilt_deg=0.0,
        sectioning_axis=tbt.SectioningAxis.Z,
        stage_tolerance=tbt.StageTolerance(translational_um=1.0, angular_deg=1.0),
        connection=tbt.MicroscopeConnection(host="localhost"),
        EBSD_OEM=ebsd_oem,
        EDS_OEM=eds_oem,
        exp_dir=exp_dir,
        h5_log_name="log",
        step_count=1,
        **blocks,
    )


def ebsd_settings(enable_eds=False, scan_box=None) -> tbt.EBSDSettings:
    return tbt.EBSDSettings(image=None, enable_eds=enable_eds, scan_box=scan_box)


def eds_settings() -> tbt.EDSSettings:
    return tbt.EDSSettings(image=None)
