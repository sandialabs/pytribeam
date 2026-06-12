import pytest
import time

from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.detector_motion import BrukerDetectorMotionController
from pytribeam.external_oem.core.errors import APICallError


def require_esprit(session_settings):
    try:
        session = BrukerSession(session_settings)
        session.connect()
        return session
    except Exception as exc:
        pytest.skip(f"Esprit not available or not connectable: {exc}")


def require_hardware(session_settings, detector_index: int = 1):
    """
    Require a real Esprit session plus accessible EDS detector hardware.
    Returns a connected session if available, otherwise skips the test.
    """
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
