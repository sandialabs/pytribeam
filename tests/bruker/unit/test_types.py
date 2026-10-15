from pytribeam.external_oem.bruker.types import (
    BrukerDetectorMotionSettings,
    BrukerDetectorRanges,
    BrukerEDSElementMapSetting,
    BrukerEDSMapSettings,
    BrukerEDSOutputSettings,
    BrukerEDSProfileMapSettings,
    BrukerEDSWorkflowResult,
    BrukerElementReadbackResult,
    BrukerRectROI,
    BrukerSessionSettings,
)


def test_session_settings_construct():
    settings = BrukerSessionSettings(
        dll_dir="C:/dll",
        mode="local",
        server="Lokaler Server",
        user="edx",
        password="edx",
        host=None,
        port=None,
        close_on_exit=False,
        keep_connection_open=True,
    )
    assert settings.mode == "local"
    assert settings.keep_connection_open is True


def test_eds_map_settings_construct():
    settings = BrukerEDSMapSettings(
        name="map1",
        width_px=32,
        height_px=24,
        pixel_time_us=1024,
        real_time_s=0,
        output_bcf_path="C:/tmp/map.bcf",
        output_image_path="C:/tmp/map.bmp",
        output_image_format="bmp",
        spu_device=1,
    )
    assert settings.width_px == 32
    assert settings.output_image_format == "bmp"
    assert settings.roi is None


def test_eds_map_settings_with_roi():
    roi = BrukerRectROI(x_start_px=10, y_start_px=5, width_px=20, height_px=15)
    settings = BrukerEDSMapSettings(
        name="map_roi",
        width_px=64,
        height_px=48,
        pixel_time_us=512,
        real_time_s=0,
        output_bcf_path="C:/tmp/map.bcf",
        output_image_path=None,
        output_image_format=None,
        spu_device=1,
        roi=roi,
    )
    assert settings.roi is not None
    assert settings.roi.x_start_px == 10
    assert settings.roi.width_px == 20


def test_detector_motion_settings_construct():
    settings = BrukerDetectorMotionSettings(
        detector_index=1,
        target_position="acquire",
        timeout_s=30.0,
        poll_interval_s=0.5,
    )
    assert settings.target_position == "acquire"


def test_rect_roi_construct():
    roi = BrukerRectROI(
        x_start_px=0,
        y_start_px=0,
        width_px=100,
        height_px=50,
    )
    assert roi.x_start_px == 0
    assert roi.width_px == 100
    assert roi.height_px == 50


def test_element_readback_result_success():
    result = BrukerElementReadbackResult(
        element_index=0,
        atomic_number=14,
        line="KA",
        path="/tmp/element_0.npy",
        shape=(48, 64),
        dtype="uint16",
        min_val=0,
        max_val=255,
        sum_val=10000,
        nonzero=500,
    )
    assert result.error is None
    assert result.shape == (48, 64)


def test_element_readback_result_failure():
    result = BrukerElementReadbackResult(
        element_index=2,
        atomic_number=26,
        line="KA",
        error="OSError: buffer failure",
    )
    assert result.error == "OSError: buffer failure"
    assert result.path is None
    assert result.shape is None


def test_output_settings_standalone():
    settings = BrukerEDSOutputSettings(
        output_dir="C:/output",
        run_name="eds_test",
    )
    assert settings.slice_number is None
    assert settings.repeat_index is None
    assert settings.save_bcf is True


def test_output_settings_with_slice():
    settings = BrukerEDSOutputSettings(
        output_dir="C:/output",
        run_name="eds_map",
        slice_number=42,
        repeat_index=0,
    )
    assert settings.slice_number == 42
    assert settings.repeat_index == 0


def test_output_settings_with_repeat():
    settings = BrukerEDSOutputSettings(
        output_dir="C:/output",
        run_name="eds_map",
        slice_number=1,
        repeat_index=2,
    )
    assert settings.repeat_index == 2


def test_detector_ranges_construct():
    ranges = BrukerDetectorRanges(
        max_energy=(10, 20, 30),
        pulse_throughput=(1, 2, 3),
        energy_index_count=3,
        pulse_index_count=3,
    )
    assert ranges.energy_index_count == 3
    assert ranges.pulse_index_count == 3


def test_workflow_result_success():
    result = BrukerEDSWorkflowResult(
        success=True,
        bcf_path="/tmp/map.bcf",
        elapsed_s=5.2,
    )
    assert result.success is True
    assert result.errors == ()
    assert result.element_readback_results is None


def test_workflow_result_with_errors():
    result = BrukerEDSWorkflowResult(
        success=False,
        errors=("BCF missing", "Element 0 failed"),
        elapsed_s=3.1,
    )
    assert result.success is False
    assert len(result.errors) == 2


def test_profile_map_settings_roi_default_none():
    settings = BrukerEDSProfileMapSettings(
        name="profile_test",
        width_px=64,
        height_px=48,
        pixel_time_us=1024,
        output_bcf_path="/tmp/test.bcf",
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
    )
    assert settings.roi is None
    assert len(settings.elements) == 1
