"""
Hardware validation for the Oxford AZtec adapter.

Two tiers:

- ``oxford_hardware`` only: read-only. Connects to AZtec, reads the detector
  states, runs the preflight checks, and confirms the configured profiles
  exist. Profiles are *not* loaded, because loading replaces AZtec's current
  settings. Runs from any machine that can reach the AZtec plugin service.
- ``hardware`` + ``oxford_hardware``: moves detectors. Inserts and retracts
  the EBSD camera and the EDS detector through the adapter, on the microscope
  PC, with the real collision check and chamber CCD. Needs its own opt-in.

Opt in::

    set PYTRIBEAM_TEST_OEM=oxford
    set PYTRIBEAM_OXFORD_HOST=<AZtec host>          (often 127.0.0.1)
    set PYTRIBEAM_OXFORD_EBSD_PROFILE=<AZtec profile name>
    set PYTRIBEAM_OXFORD_EDS_PROFILE=<AZtec profile name>
    rem optional: PYTRIBEAM_OXFORD_PORT (default 22201), AZTEC_PLUGIN_DIR
    rem motion tier only:
    set PYTRIBEAM_ALLOW_DETECTOR_MOTION=1
    pytest tests/external_oem/test_adapter_oxford_hardware.py -v

Before the motion tier: sample at the EBSD position, nothing else inserted,
and someone watching the chamber CCD.
"""

import os

import pytest

pytest.importorskip("autoscript_sdb_microscope_client")

import pytribeam.types as tbt  # noqa: E402
from pytribeam.external_oem.adapters import oxford as oxford_adapter  # noqa: E402

MOTION_ENV_VAR = "PYTRIBEAM_ALLOW_DETECTOR_MOTION"

pytestmark = pytest.mark.oxford_hardware


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@pytest.fixture(scope="module")
def settings() -> tbt.GeneralSettings:
    host = _env("PYTRIBEAM_OXFORD_HOST")
    if not host:
        pytest.skip("PYTRIBEAM_OXFORD_HOST is not set")
    oxford = tbt.OxfordConfig(
        connection=tbt.MicroscopeConnection(
            host=host, port=int(_env("PYTRIBEAM_OXFORD_PORT", "22201"))
        ),
        ebsd_profile=_env("PYTRIBEAM_OXFORD_EBSD_PROFILE") or None,
        eds_profile=_env("PYTRIBEAM_OXFORD_EDS_PROFILE") or None,
        dll_dir=_env("AZTEC_PLUGIN_DIR") or None,
    )
    return tbt.GeneralSettings(
        yml_version=1.2,
        slice_thickness_um=1.0,
        max_slice_number=1,
        pre_tilt_deg=0.0,
        sectioning_axis=tbt.SectioningAxis.Z,
        stage_tolerance=tbt.StageTolerance(translational_um=1.0, angular_deg=1.0),
        connection=tbt.MicroscopeConnection(host="localhost"),
        EBSD_OEM=tbt.ExternalDeviceOEM.OXFORD,
        EDS_OEM=tbt.ExternalDeviceOEM.OXFORD,
        exp_dir=".",
        h5_log_name="log",
        step_count=1,
        Oxford_settings=oxford,
    )


# ----------------------------------------------------------------------
# Read-only
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "technique", list(tbt.ExternalTechnique), ids=lambda t: t.value.lower()
)
def test_connection(settings, technique):
    assert oxford_adapter.test_connection(settings, technique)


@pytest.mark.parametrize(
    "read",
    [oxford_adapter.get_ebsd_camera_state, oxford_adapter.get_eds_detector_state],
)
def test_states_are_translated(settings, read):
    state = read(settings)

    assert isinstance(state, tbt.RetractableDeviceState)
    print(f"{read.__name__}: {state}")


@pytest.mark.parametrize("technique", ["ebsd", "eds"])
def test_configured_profile_exists(settings, technique):
    """Checked without loading: loading replaces AZtec's current settings."""
    name = getattr(settings.Oxford_settings, f"{technique}_profile")
    if not name:
        pytest.skip(f"PYTRIBEAM_OXFORD_{technique.upper()}_PROFILE is not set")
    with oxford_adapter._session(settings) as session:
        available = [profile.name for profile in session.acquisition.profiles()]

    assert name in available, f"{name!r} not among {available}"


def test_preflight(settings):
    """AZtec idle and EDS cold. Nothing moves and no profile is loaded."""
    if not (
        settings.Oxford_settings.ebsd_profile and settings.Oxford_settings.eds_profile
    ):
        pytest.skip("both profile variables are needed for preflight")
    ebsd_step = tbt.EBSDSettings(image=None, enable_eds=True)

    assert oxford_adapter.preflight_ebsd(settings, [ebsd_step])
    assert oxford_adapter.preflight_eds(settings, [tbt.EDSSettings(image=None)])


# ----------------------------------------------------------------------
# Detector motion (microscope PC, explicit opt-in)
# ----------------------------------------------------------------------


@pytest.mark.hardware
@pytest.mark.skipif(
    os.environ.get(MOTION_ENV_VAR, "").strip().lower() not in {"1", "true", "yes"},
    reason=f"{MOTION_ENV_VAR} is not set; these tests move detectors",
)
@pytest.mark.parametrize(
    "insert, retract, read",
    [
        (
            oxford_adapter.insert_ebsd_camera,
            oxford_adapter.retract_ebsd_camera,
            oxford_adapter.get_ebsd_camera_state,
        ),
        (
            oxford_adapter.insert_eds_detector,
            oxford_adapter.retract_eds_detector,
            oxford_adapter.get_eds_detector_state,
        ),
    ],
    ids=["ebsd", "eds"],
)
def test_insert_and_retract(microscope, settings, insert, retract, read):
    STATE = tbt.RetractableDeviceState
    assert read(settings) == STATE.RETRACTED, "start with the detector retracted"
    try:
        assert insert(microscope, settings)
        assert read(settings) == STATE.INSERTED
    finally:
        assert retract(microscope, settings)
    assert read(settings) == STATE.RETRACTED
