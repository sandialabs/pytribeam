import pytest

from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.types import (
    BrukerEDSElementMapSetting,
    BrukerEDSMapSettings,
    BrukerEDSProfileMapSettings,
    BrukerRectROI,
)


class DummyFunc:
    def __init__(self, return_value=0):
        self.return_value = return_value
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        return self.return_value


class DummyDLL:
    def __init__(self):
        self.ImageSetConfiguration = DummyFunc()
        self.HyMapCreateProfile = DummyFunc()
        self.HyMapStart = DummyFunc()
        self.HyMapStartEx = DummyFunc()
        self.HyMapStartWithProfile = DummyFunc()
        self.HyMapGetStateEx = DummyFunc()
        self.HyMapStop = DummyFunc()
        self.HyMapSaveToFile = DummyFunc()
        self.HyMapGetImage = DummyFunc()
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
        if rc != 0:
            raise RuntimeError(f"{name} failed rc={rc}")


def _make_simple_settings(roi):
    return BrukerEDSMapSettings(
        name="invalid_roi_simple",
        width_px=64,
        height_px=48,
        pixel_time_us=1024,
        real_time_s=0,
        output_bcf_path="C:/temp/invalid_roi_simple.bcf",
        output_image_path=None,
        output_image_format=None,
        spu_device=1,
        roi=roi,
    )


def _make_profile_settings(roi):
    return BrukerEDSProfileMapSettings(
        name="invalid_roi_profile",
        width_px=64,
        height_px=48,
        pixel_time_us=1024,
        output_bcf_path="C:/temp/invalid_roi_profile.bcf",
        output_image_path=None,
        output_image_format=None,
        spu_device=1,
        elements=(BrukerEDSElementMapSetting(atomic_number=14, line="KA"),),
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


def _assert_no_acquisition_dll_calls(dll):
    assert dll.ImageSetConfiguration.calls == []
    assert dll.HyMapCreateProfile.calls == []
    assert dll.HyMapStart.calls == []
    assert dll.HyMapStartEx.calls == []
    assert dll.HyMapStartWithProfile.calls == []


@pytest.mark.parametrize(
    "roi",
    [
        BrukerRectROI(x_start_px=-1, y_start_px=0, width_px=8, height_px=8),
        BrukerRectROI(x_start_px=0, y_start_px=-1, width_px=8, height_px=8),
        BrukerRectROI(x_start_px=0, y_start_px=0, width_px=0, height_px=8),
        BrukerRectROI(x_start_px=0, y_start_px=0, width_px=8, height_px=0),
        BrukerRectROI(x_start_px=60, y_start_px=0, width_px=8, height_px=8),
        BrukerRectROI(x_start_px=0, y_start_px=44, width_px=8, height_px=8),
    ],
)
def test_invalid_simple_roi_rejected_before_any_dll_call(monkeypatch, roi):
    dll = DummyDLL()
    monkeypatch.setattr("pytribeam.external_oem.bruker.eds.bind_eds", lambda _: None)

    controller = BrukerEDSController(DummySession(dll))

    with pytest.raises(ValueError, match="ROI"):
        controller.acquire_map(
            _make_simple_settings(roi),
            poll_interval_s=0.0,
            max_wait_s=0.01,
        )

    _assert_no_acquisition_dll_calls(dll)


@pytest.mark.parametrize(
    "roi",
    [
        BrukerRectROI(x_start_px=-1, y_start_px=0, width_px=8, height_px=8),
        BrukerRectROI(x_start_px=0, y_start_px=-1, width_px=8, height_px=8),
        BrukerRectROI(x_start_px=0, y_start_px=0, width_px=0, height_px=8),
        BrukerRectROI(x_start_px=0, y_start_px=0, width_px=8, height_px=0),
        BrukerRectROI(x_start_px=60, y_start_px=0, width_px=8, height_px=8),
        BrukerRectROI(x_start_px=0, y_start_px=44, width_px=8, height_px=8),
    ],
)
def test_invalid_profile_roi_rejected_before_any_dll_call(monkeypatch, roi):
    dll = DummyDLL()
    monkeypatch.setattr("pytribeam.external_oem.bruker.eds.bind_eds", lambda _: None)

    controller = BrukerEDSController(DummySession(dll))

    with pytest.raises(ValueError, match="ROI"):
        controller.acquire_map_with_profile(
            _make_profile_settings(roi),
            poll_interval_s=0.0,
            max_wait_s=0.01,
        )

    _assert_no_acquisition_dll_calls(dll)
