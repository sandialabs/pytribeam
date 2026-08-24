from pathlib import Path

import numpy as np
import pytest

from pytribeam.external_oem.bruker.readback import BrukerEDSReadbackController
from pytribeam.external_oem.bruker.types import (
    BrukerEDSElementMapSetting,
    BrukerEDSProfileMapSettings,
    BrukerRectROI,
)


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
        self.HyMapGetElementData = DummyFunc()
        # Required by bind_eds but not used in readback
        self.ImageSetConfiguration = DummyFunc()
        self.HyMapStart = DummyFunc()
        self.HyMapStartEx = DummyFunc()
        self.HyMapGetStateEx = DummyFunc()
        self.HyMapStop = DummyFunc()
        self.HyMapSaveToFile = DummyFunc()
        self.HyMapGetImage = DummyFunc()
        self.EDSSetDetectorPosition = DummyFunc()
        self.EDSGetDetectorPosition = DummyFunc()
        self.HyMapCreateProfile = DummyFunc()
        self.HyMapStartWithProfile = DummyFunc()
        self.HyMapGetElementImage = DummyFunc()
        self.HyMapGetMixedMapImage = DummyFunc()


class DummySession:
    def __init__(self, dll):
        self._dll = dll
        self._cid = 1234

    @property
    def dll(self):
        return self._dll

    @property
    def cid(self):
        return self._cid

    def _check(self, rc, name):
        if rc not in (0, 1, -201):
            raise RuntimeError(f"{name} failed rc={rc}")


def _make_profile_settings(width=32, height=24, roi=None):
    """Helper to create a minimal BrukerEDSProfileMapSettings."""
    return BrukerEDSProfileMapSettings(
        name="test",
        width_px=width,
        height_px=height,
        pixel_time_us=1024,
        output_bcf_path="/tmp/test.bcf",
        output_image_path=None,
        output_image_format=None,
        spu_device=1,
        elements=(
            BrukerEDSElementMapSetting(atomic_number=14, line="KA"),
            BrukerEDSElementMapSetting(atomic_number=26, line="KA"),
        ),
        image_filter=0,
        map_filter=0,
        map_filter_width=3,
        color_mix_method=0,
        brightness=0.0,
        gamma=1.0,
        color_saturation=1.0,
        absolute_scaling=False,
        normalization=True,
        deconvolution=False,
        roi=roi,
    )


def test_get_element_data_bytes_success(monkeypatch):
    dll = DummyDLL()
    expected_data = b"\x01\x00\x02\x00" * 100  # 400 bytes

    def side_effect(cid, element_index, buf_ptr, size_ptr):
        import ctypes as ct

        data_len = len(expected_data)
        ct.memmove(buf_ptr, expected_data, data_len)
        size_ptr._obj.value = data_len
        return 0

    dll.HyMapGetElementData.side_effect = side_effect

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.readback.bind_eds",
        lambda esprit: None,
    )

    controller = BrukerEDSReadbackController(DummySession(dll))
    data = controller.get_element_data_bytes(element_index=0, expected_size=400)

    assert len(data) == 400
    assert data[:4] == b"\x01\x00\x02\x00"


def test_get_element_data_array_correct_shape(monkeypatch):
    dll = DummyDLL()
    width, height = 8, 4
    pixel_data = np.arange(width * height, dtype=np.uint16).tobytes()

    def side_effect(cid, element_index, buf_ptr, size_ptr):
        import ctypes as ct

        ct.memmove(buf_ptr, pixel_data, len(pixel_data))
        size_ptr._obj.value = len(pixel_data)
        return 0

    dll.HyMapGetElementData.side_effect = side_effect

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.readback.bind_eds",
        lambda esprit: None,
    )

    controller = BrukerEDSReadbackController(DummySession(dll))
    arr = controller.get_element_data_array(
        element_index=0, width_px=width, height_px=height
    )

    assert arr.shape == (height, width)
    assert arr.dtype == np.uint16


def test_get_element_data_array_size_mismatch(monkeypatch):
    dll = DummyDLL()
    # Return 100 bytes but expect 64 bytes (8*4*2)
    wrong_data = b"\x00" * 100

    def side_effect(cid, element_index, buf_ptr, size_ptr):
        import ctypes as ct

        ct.memmove(buf_ptr, wrong_data, len(wrong_data))
        size_ptr._obj.value = len(wrong_data)
        return 0

    dll.HyMapGetElementData.side_effect = side_effect

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.readback.bind_eds",
        lambda esprit: None,
    )

    controller = BrukerEDSReadbackController(DummySession(dll))

    with pytest.raises(ValueError, match="size mismatch"):
        controller.get_element_data_array(element_index=0, width_px=8, height_px=4)


def test_read_all_element_maps_per_element_error(monkeypatch):
    """One element fails, others succeed — non-strict mode."""
    dll = DummyDLL()
    width, height = 4, 3
    good_data = np.ones(width * height, dtype=np.uint16).tobytes()
    call_count = [0]

    def side_effect(cid, element_index, buf_ptr, size_ptr):
        import ctypes as ct

        call_count[0] += 1
        # Fail on element index 1
        if element_index == 1:
            return -1  # IFC_ERROR_IN_EXECUTION

        ct.memmove(buf_ptr, good_data, len(good_data))
        size_ptr._obj.value = len(good_data)
        return 0

    dll.HyMapGetElementData.side_effect = side_effect

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.readback.bind_eds",
        lambda esprit: None,
    )

    controller = BrukerEDSReadbackController(DummySession(dll))
    settings = _make_profile_settings(width=width, height=height)

    results = controller.read_all_element_maps(settings, strict=False)

    assert len(results) == 2
    assert results[0].error is None
    assert results[0].shape == (height, width)
    assert results[1].error is not None
    assert "failed" in results[1].error.lower() or "rc=" in results[1].error.lower()


def test_read_all_element_maps_strict_raises(monkeypatch):
    """In strict mode, first failure raises immediately."""
    dll = DummyDLL()

    def side_effect(cid, element_index, buf_ptr, size_ptr):
        return -1  # Always fail

    dll.HyMapGetElementData.side_effect = side_effect

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.readback.bind_eds",
        lambda esprit: None,
    )

    controller = BrukerEDSReadbackController(DummySession(dll))
    settings = _make_profile_settings(width=4, height=3)

    with pytest.raises(RuntimeError):
        controller.read_all_element_maps(settings, strict=True)


def test_effective_readback_dimensions_no_roi():
    settings = _make_profile_settings(width=64, height=48, roi=None)
    w, h = BrukerEDSReadbackController._effective_readback_dimensions(settings)
    assert w == 64
    assert h == 48


def test_effective_readback_dimensions_with_roi():
    roi = BrukerRectROI(x_start_px=5, y_start_px=5, width_px=20, height_px=30)
    settings = _make_profile_settings(width=64, height=48, roi=roi)
    w, h = BrukerEDSReadbackController._effective_readback_dimensions(settings)
    assert w == 20
    assert h == 30


def test_save_element_maps_npy_writes_files(monkeypatch, tmp_path):
    """Verify .npy files and summary JSON are written."""
    dll = DummyDLL()
    width, height = 4, 3
    pixel_data = np.ones(width * height, dtype=np.uint16).tobytes()

    def side_effect(cid, element_index, buf_ptr, size_ptr):
        import ctypes as ct

        ct.memmove(buf_ptr, pixel_data, len(pixel_data))
        size_ptr._obj.value = len(pixel_data)
        return 0

    dll.HyMapGetElementData.side_effect = side_effect

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.readback.bind_eds",
        lambda esprit: None,
    )

    controller = BrukerEDSReadbackController(DummySession(dll))
    settings = _make_profile_settings(width=width, height=height)

    results = controller.save_element_maps_npy(
        settings=settings,
        output_dir=str(tmp_path),
        prefix="test_map",
    )

    assert len(results) == 2
    assert all(r.error is None for r in results)
    assert all(r.path is not None for r in results)

    # Check files exist
    for r in results:
        assert Path(r.path).exists()
        arr = np.load(r.path)
        assert arr.shape == (height, width)

    # Check summary JSON
    summary_path = tmp_path / "test_map_readback_summary.json"
    assert summary_path.exists()


def test_save_element_maps_npy_can_also_write_tiff(monkeypatch, tmp_path):
    """Verify optional 16-bit TIFF files are written from successful readback."""
    dll = DummyDLL()
    width, height = 4, 3
    pixel_data = np.arange(width * height, dtype=np.uint16).tobytes()

    def side_effect(cid, element_index, buf_ptr, size_ptr):
        import ctypes as ct

        ct.memmove(buf_ptr, pixel_data, len(pixel_data))
        size_ptr._obj.value = len(pixel_data)
        return 0

    dll.HyMapGetElementData.side_effect = side_effect

    monkeypatch.setattr(
        "pytribeam.external_oem.bruker.readback.bind_eds",
        lambda esprit: None,
    )

    controller = BrukerEDSReadbackController(DummySession(dll))
    settings = _make_profile_settings(width=width, height=height)

    results = controller.save_element_maps_npy(
        settings=settings,
        output_dir=str(tmp_path),
        prefix="test_map_tiff",
        save_element_tiff=True,
    )

    assert len(results) == 2
    assert all(r.error is None for r in results)
    assert all(r.tiff_path is not None for r in results)

    for result in results:
        tiff_path = Path(result.tiff_path)
        assert tiff_path.exists()
        assert tiff_path.suffix == ".tiff"
        with open(tiff_path, "rb") as f:
            assert f.read(4) in (b"II*\x00", b"MM\x00*")
