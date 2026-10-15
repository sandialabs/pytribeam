import tempfile
from pathlib import Path

from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.types import BrukerEDSMapSettings


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
        self.ImageSetConfiguration = DummyFunc()
        self.HyMapStart = DummyFunc()
        self.HyMapGetStateEx = DummyFunc()
        self.HyMapStop = DummyFunc()
        self.HyMapSaveToFile = DummyFunc()
        self.HyMapGetImage = DummyFunc()


class DummySession:
    def __init__(self, dll):
        self._dll = dll
        self._cid = 4242

    @property
    def dll(self):
        return self._dll

    @property
    def cid(self):
        return self._cid

    def _check(self, rc, name):
        if rc not in (0, 1, -201):
            raise RuntimeError(f"{name} failed rc={rc}")


def test_get_map_progress(monkeypatch):
    dll = DummyDLL()

    def state_side_effect(cid, running_ptr, state_ptr, line_ptr):
        running_ptr._obj.value = True
        state_ptr._obj.value = 42.5
        line_ptr._obj.value = 7
        return 0

    dll.HyMapGetStateEx.side_effect = state_side_effect

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.eds.bind_eds",
        lambda esprit: None,
    )

    controller = BrukerEDSController(DummySession(dll))
    progress = controller.get_map_progress()

    assert progress.running is True
    assert progress.percent_complete == 42.5
    assert progress.current_line == 7


def test_acquire_map_success(monkeypatch):
    dll = DummyDLL()
    poll_states = [
        (True, 10.0, 0),
        (True, 80.0, 10),
        (False, 100.0, 20),
    ]

    def state_side_effect(cid, running_ptr, state_ptr, line_ptr):
        running, state, line = poll_states.pop(0)
        running_ptr._obj.value = running
        state_ptr._obj.value = state
        line_ptr._obj.value = line
        return 0

    dll.HyMapGetStateEx.side_effect = state_side_effect

    def get_image_side_effect(cid, fmt, image_channel, buf, size_ptr):
        payload = b"BMFAKEBMPDATA"
        size_ptr._obj.value = len(payload)
        # ct_buf = (
        #     (type(buf)._type_ * len(payload)).from_address(buf.value)
        #     if hasattr(buf, "value")
        #     else None
        # )
        return 0

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.eds.bind_eds",
        lambda esprit: None,
    )

    controller = BrukerEDSController(DummySession(dll))

    with tempfile.TemporaryDirectory() as tmpdir:
        bcf_path = str(Path(tmpdir) / "map.bcf")
        # bmp_path = str(Path(tmpdir) / "map.bmp")

        settings = BrukerEDSMapSettings(
            name="test_map",
            width_px=32,
            height_px=24,
            pixel_time_us=1024,
            real_time_s=0,
            output_bcf_path=bcf_path,
            output_image_path=None,
            output_image_format=None,
            spu_device=1,
        )

        outputs = controller.acquire_map(settings, poll_interval_s=0.0, max_wait_s=5.0)

        assert outputs.output_bcf_path == bcf_path
        assert outputs.output_image_path is None
        assert len(dll.ImageSetConfiguration.calls) == 1
        assert len(dll.HyMapStart.calls) == 1
        assert len(dll.HyMapStop.calls) == 1
        assert len(dll.HyMapSaveToFile.calls) == 1


def test_acquire_map_timeout(monkeypatch):
    dll = DummyDLL()

    def state_side_effect(cid, running_ptr, state_ptr, line_ptr):
        running_ptr._obj.value = True
        state_ptr._obj.value = 1.0
        line_ptr._obj.value = 0
        return 0

    dll.HyMapGetStateEx.side_effect = state_side_effect

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.eds.bind_eds",
        lambda esprit: None,
    )

    controller = BrukerEDSController(DummySession(dll))

    settings = BrukerEDSMapSettings(
        name="test_map",
        width_px=32,
        height_px=24,
        pixel_time_us=1024,
        real_time_s=0,
        output_bcf_path=r"C:\temp\map.bcf",
        output_image_path=None,
        output_image_format=None,
        spu_device=1,
    )

    try:
        controller.acquire_map(settings, poll_interval_s=0.0, max_wait_s=0.01)
        assert False, "Expected TimeoutError"
    except TimeoutError:
        pass
