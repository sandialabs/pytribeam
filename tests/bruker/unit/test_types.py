from pytribeam.external_oem.bruker.types import (
    BrukerSessionSettings,
    BrukerEDSMapSettings,
    BrukerDetectorMotionSettings,
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


def test_detector_motion_settings_construct():
    settings = BrukerDetectorMotionSettings(
        detector_index=1,
        target_position="acquire",
        timeout_s=30.0,
        poll_interval_s=0.5,
    )
    assert settings.target_position == "acquire"
