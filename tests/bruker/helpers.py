import os
import time

import pytest

from pytribeam.external_oem.bruker.detector_motion import BrukerDetectorMotionController
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.core.errors import APICallError

BRUKER_HARDWARE_ENV_VAR = "PYTRIBEAM_RUN_BRUKER_HARDWARE"
BRUKER_TEST_ENV_VAR = "PYTRIBEAM_BRUKER_TEST_ENV"


def bruker_hardware_tests_enabled() -> bool:
    """Return True when Bruker hardware tests were explicitly enabled."""
    return os.environ.get(BRUKER_HARDWARE_ENV_VAR, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def bruker_test_environment() -> str:
    """Return operator-declared Bruker test environment.

    Expected values are "simulator" or "hardware". An empty value means the
    environment was not declared explicitly.
    """
    return os.environ.get(BRUKER_TEST_ENV_VAR, "").strip().lower()


def require_declared_bruker_hardware_environment():
    """Require the operator to declare this run as true Bruker hardware."""
    env = bruker_test_environment()
    if env != "hardware":
        pytest.skip(
            f"Bruker true-hardware tests require {BRUKER_TEST_ENV_VAR}=hardware. "
            f"Current value: {env or '<unset>'}. Use {BRUKER_TEST_ENV_VAR}=simulator "
            "for ESPRIT simulator runs."
        )


def require_esprit(session_settings):
    try:
        session = BrukerSession(session_settings)
        session.connect()
        return session
    except Exception as exc:
        pytest.skip(f"Esprit not available or not connectable: {exc}")


def require_hardware(session_settings, detector_index: int = 1):
    """
    Require an explicit operator opt-in plus accessible EDS detector hardware.

    Bruker hardware tests may move the detector. They are therefore gated by
    both PYTRIBEAM_BRUKER_TEST_ENV=hardware and
    PYTRIBEAM_RUN_BRUKER_HARDWARE=1 even on machines that pytest recognizes as
    hardware hosts. This avoids treating ESPRIT simulator detector stubs as true
    hardware.
    """
    require_declared_bruker_hardware_environment()

    if not bruker_hardware_tests_enabled():
        pytest.skip(
            f"Bruker hardware tests are disabled. Set {BRUKER_HARDWARE_ENV_VAR}=1 "
            "to enable detector-hardware tests."
        )

    session = require_esprit(session_settings)

    try:
        motion = BrukerDetectorMotionController(session)
        state = motion.get_eds_detector_position(detector_index)
        # If this succeeds at all, we assume the detector path is accessible enough
        # for hardware smoke tests.
        _ = state
        return session
    except Exception as exc:
        if session_settings.close_on_exit:
            session.close()
        pytest.skip(f"Bruker hardware not available or detector query failed: {exc}")


def wait_until_readable(path, timeout_s: float = 10.0, poll_interval_s: float = 0.2):
    deadline = time.time() + timeout_s
    last_exc = None

    while time.time() < deadline:
        try:
            data = path.read_bytes()
            return data
        except Exception as exc:
            last_exc = exc
            time.sleep(poll_interval_s)

    if last_exc is not None:
        raise last_exc
    raise TimeoutError(f"Timed out waiting for readable file: {path}")


def skip_if_runtime_unavailable(exc: APICallError, reason: str):
    if exc.rc in (-1, 232):
        pytest.skip(f"{reason} (rc={exc.rc})")
    raise exc
