import pytest

from pytribeam.external_oem.bruker.detector_motion import BrukerDetectorMotionController
from pytribeam.external_oem.bruker.types import BrukerDetectorMotionSettings


class DummyFunc:
    def __init__(self, return_value=0, side_effect=None):
        self.return_value = return_value
        self.side_effect = side_effect
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        if self.side_effect is not None:
            return self.side_effect(*args)
        return self.return_value


class DummyDLL:
    def __init__(self):
        self.EDSSetDetectorPosition = DummyFunc()
        self.EDSGetDetectorPosition = DummyFunc()


class DummySession:
    def __init__(self, dll):
        self._dll = dll
        self._cid = 777

    @property
    def dll(self):
        return self._dll

    @property
    def cid(self):
        return self._cid

    def _check(self, rc, name):
        if rc not in (0, 1, -201):
            raise RuntimeError(f"{name} failed rc={rc}")


def test_get_detector_position(monkeypatch):
    dll = DummyDLL()

    def get_pos_side_effect(cid, detector_index, pos_ptr):
        pos_ptr._obj.value = 2
        return 0

    dll.EDSGetDetectorPosition.side_effect = get_pos_side_effect

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.detector_motion.bind_eds",
        lambda esprit: None,
    )

    controller = BrukerDetectorMotionController(DummySession(dll))
    state = controller.get_eds_detector_position(1)

    assert state.detector_index == 1
    assert state.position_code == 2
    assert state.position_name == "acquire"


def test_move_detector_success(monkeypatch):
    dll = DummyDLL()
    poll_results = [1, 1, 2]

    def set_pos_side_effect(cid, detector_index, target_code):
        return 0

    def get_pos_side_effect(cid, detector_index, pos_ptr):
        pos_ptr._obj.value = poll_results.pop(0)
        return 0

    dll.EDSSetDetectorPosition.side_effect = set_pos_side_effect
    dll.EDSGetDetectorPosition.side_effect = get_pos_side_effect

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.detector_motion.bind_eds",
        lambda esprit: None,
    )

    controller = BrukerDetectorMotionController(DummySession(dll))
    settings = BrukerDetectorMotionSettings(
        detector_index=1,
        target_position="acquire",
        timeout_s=2.0,
        poll_interval_s=0.0,
    )

    state = controller.move_eds_detector(settings)

    assert state.position_code == 2
    assert state.position_name == "acquire"


def test_move_detector_timeout(monkeypatch):
    dll = DummyDLL()

    def set_pos_side_effect(cid, detector_index, target_code):
        return 0

    def get_pos_side_effect(cid, detector_index, pos_ptr):
        pos_ptr._obj.value = 1
        return 0

    dll.EDSSetDetectorPosition.side_effect = set_pos_side_effect
    dll.EDSGetDetectorPosition.side_effect = get_pos_side_effect

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.detector_motion.bind_eds",
        lambda esprit: None,
    )

    controller = BrukerDetectorMotionController(DummySession(dll))
    settings = BrukerDetectorMotionSettings(
        detector_index=1,
        target_position="acquire",
        timeout_s=0.01,
        poll_interval_s=0.0,
    )

    with pytest.raises(TimeoutError):
        controller.move_eds_detector(settings)
