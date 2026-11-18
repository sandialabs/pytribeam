#!/usr/bin/python3
"""
Hardware validation for the EDAX adapter of the external OEM dispatcher.

Read-only, like ``test_edax_ipapi_hardware.py``: it connects and reads the EBSD
camera and EDS detector states, translated to pyTriBeam's device states.
Nothing moves and no map starts. Opt in as for the IPAPI tier::

    set PYTRIBEAM_EDAX_HOST=<ipapi host>
    set PYTRIBEAM_TEST_OEM=edax
    pytest tests/edax/hardware/test_edax_adapter_hardware.py -v

The adapter is built on ``pytribeam.types``, so this also needs AutoScript.
"""

import os

import pytest

pytest.importorskip("autoscript_sdb_microscope_client")

import pytribeam.types as tbt  # noqa: E402
from pytribeam.external_oem.adapters import edax as edax_adapter  # noqa: E402

# Needs only the IPAPI service, not the TriBeam.
pytestmark = pytest.mark.edax_hardware


@pytest.fixture(scope="module")
def settings():
    host = os.environ.get("PYTRIBEAM_EDAX_HOST", "").strip()
    if not host:
        pytest.skip("PYTRIBEAM_EDAX_HOST is not set")
    port = int(os.environ.get("PYTRIBEAM_EDAX_PORT", "8301"))
    edax = tbt.EDAXConfig(
        save_directory="unused",
        project_name="unused",
        connection=tbt.MicroscopeConnection(host=host, port=port),
    )
    return tbt.GeneralSettings(
        yml_version=1.2,
        slice_thickness_um=1.0,
        max_slice_number=1,
        pre_tilt_deg=0.0,
        sectioning_axis=tbt.SectioningAxis.Z,
        stage_tolerance=tbt.StageTolerance(translational_um=1.0, angular_deg=1.0),
        connection=tbt.MicroscopeConnection(host="localhost"),
        EBSD_OEM=tbt.ExternalDeviceOEM.EDAX,
        EDS_OEM=tbt.ExternalDeviceOEM.EDAX,
        exp_dir=".",
        h5_log_name="log",
        step_count=1,
        EDAX_settings=edax,
    )


@pytest.mark.parametrize(
    "technique", list(tbt.ExternalTechnique), ids=lambda t: t.value.lower()
)
def test_connection(settings, technique):
    assert edax_adapter.test_connection(settings, technique)


@pytest.mark.parametrize(
    "read", [edax_adapter.get_ebsd_camera_state, edax_adapter.get_eds_detector_state]
)
def test_states_are_translated(settings, read):
    state = read(settings)

    assert isinstance(state, tbt.RetractableDeviceState)
    print(f"{read.__name__}: {state}")
