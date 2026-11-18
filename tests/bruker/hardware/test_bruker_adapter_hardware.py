"""
Hardware validation for the Bruker ESPRIT adapter (EDS).

Two tiers:

- ``bruker_hardware`` only: read-only. Connects (reusing one session, as the
  adapter does in an experiment), reads the EDS detector position, and runs EDS
  preflight (spectrometer ready, output folders writable). Runs against ESPRIT
  hardware or the ESPRIT simulator; calls the simulator does not support are
  skipped.
- ``hardware`` + ``bruker_hardware``: moves the EDS detector to acquire and
  back to park through the adapter, on the microscope PC, with the real
  collision check and chamber CCD. Needs the existing Bruker hardware opt-in.

Opt in::

    set PYTRIBEAM_TEST_OEM=bruker            (or PYTRIBEAM_BRUKER_TEST_ENV=...)
    rem optional: PYTRIBEAM_BRUKER_DLL_DIR (default C:\\Program Files\\Bruker\\Esprit API)
    rem motion tier only:
    set PYTRIBEAM_BRUKER_TEST_ENV=hardware
    set PYTRIBEAM_RUN_BRUKER_HARDWARE=1
    pytest tests/bruker/hardware/test_bruker_adapter_hardware.py -v

EBSD is not covered: the EBSD controller is a scaffold, and its camera
positions must be measured on the instrument first.
"""

import os

import pytest

pytest.importorskip("autoscript_sdb_microscope_client")

import pytribeam.types as tbt  # noqa: E402
from pytribeam.external_oem.adapters import bruker as bruker_adapter  # noqa: E402
from pytribeam.external_oem.bruker.config import parse_bruker_settings  # noqa: E402
from pytribeam.external_oem.core.errors import (  # noqa: E402
    APICallError,
    DetectorError,
)
from tests.bruker.helpers import (  # noqa: E402
    BRUKER_HARDWARE_ENV_VAR,
    bruker_hardware_tests_enabled,
    require_declared_bruker_hardware_environment,
    skip_if_runtime_unavailable,
)

pytestmark = pytest.mark.bruker_hardware

DEFAULT_DLL_DIR = r"C:\Program Files\Bruker\Esprit API"


@pytest.fixture(scope="module")
def settings(tmp_path_factory) -> tbt.GeneralSettings:
    root = tmp_path_factory.mktemp("bruker_adapter")
    block = {
        "session": {
            "dll_dir": os.environ.get("PYTRIBEAM_BRUKER_DLL_DIR", DEFAULT_DLL_DIR),
            "mode": "local",
        },
        "eds": {
            "output": {"root_dir": str(root / "esprit"), "run_name": "adapter_hw"},
            "detector": {"detector_index": 1},
            "map": {
                "mode": "simple",
                "width_px": 64,
                "height_px": 48,
                "pixel_time_us": 100,
            },
        },
    }
    general_settings = tbt.GeneralSettings(
        yml_version=1.2,
        slice_thickness_um=1.0,
        max_slice_number=1,
        pre_tilt_deg=0.0,
        sectioning_axis=tbt.SectioningAxis.Z,
        stage_tolerance=tbt.StageTolerance(translational_um=1.0, angular_deg=1.0),
        connection=tbt.MicroscopeConnection(host="localhost"),
        EBSD_OEM=tbt.ExternalDeviceOEM.NONE,
        EDS_OEM=tbt.ExternalDeviceOEM.BRUKER,
        exp_dir=str(root / "exp"),
        h5_log_name="log",
        step_count=1,
        Bruker_settings=parse_bruker_settings(block),
    )
    try:
        bruker_adapter.test_connection(general_settings, tbt.ExternalTechnique.EDS)
    except DetectorError as error:
        pytest.skip(f"ESPRIT not available or not connectable: {error}")
    yield general_settings
    bruker_adapter.close_sessions()


def _call(function, *args):
    """Call the adapter, skipping calls the ESPRIT runtime cannot serve."""
    try:
        return function(*args)
    except APICallError as error:
        skip_if_runtime_unavailable(error, f"{function.__name__} unavailable")


# ----------------------------------------------------------------------
# Read-only
# ----------------------------------------------------------------------


def test_connection_reuses_one_session(settings):
    assert _call(bruker_adapter.test_connection, settings, tbt.ExternalTechnique.EDS)
    assert _call(bruker_adapter.test_connection, settings, tbt.ExternalTechnique.EDS)
    assert len(bruker_adapter._SESSIONS) == 1


def test_eds_state_is_translated(settings):
    state = _call(bruker_adapter.get_eds_detector_state, settings)

    assert isinstance(state, tbt.RetractableDeviceState)
    print(f"EDS detector: {state}")


def test_eds_preflight(settings):
    assert _call(bruker_adapter.preflight_eds, settings, [tbt.EDSSettings(image=None)])


# ----------------------------------------------------------------------
# Detector motion (microscope PC, explicit opt-in)
# ----------------------------------------------------------------------


@pytest.mark.hardware
def test_eds_insert_and_retract(microscope, settings):
    require_declared_bruker_hardware_environment()
    if not bruker_hardware_tests_enabled():
        pytest.skip(f"{BRUKER_HARDWARE_ENV_VAR}=1 is needed to move the detector")
    STATE = tbt.RetractableDeviceState
    assert bruker_adapter.get_eds_detector_state(settings) == STATE.RETRACTED

    try:
        assert bruker_adapter.insert_eds_detector(microscope, settings)
        assert bruker_adapter.get_eds_detector_state(settings) == STATE.INSERTED
    finally:
        assert bruker_adapter.retract_eds_detector(microscope, settings)
    assert bruker_adapter.get_eds_detector_state(settings) == STATE.RETRACTED
