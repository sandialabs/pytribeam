import pytest

from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.types import BrukerEDSMapSettings


@pytest.mark.esprit
def test_eds_map_save_bcf_to_tmp(connected_bruker_session, tmp_path):
    controller = BrukerEDSController(connected_bruker_session)

    output_bcf = tmp_path / "test_map.bcf"

    settings = BrukerEDSMapSettings(
        name="pytest_map",
        width_px=16,
        height_px=12,
        pixel_time_us=1024,
        real_time_s=0,
        output_bcf_path=str(output_bcf),
        output_image_path=None,
        output_image_format=None,
        spu_device=1,
    )

    outputs = controller.acquire_map(settings, poll_interval_s=0.2, max_wait_s=60.0)

    assert output_bcf.exists()
    assert output_bcf.stat().st_size > 0
    assert outputs.output_bcf_path == str(output_bcf)
    assert outputs.output_image_path is None


@pytest.mark.esprit
def test_eds_map_save_bcf_and_image_to_tmp(connected_bruker_session, tmp_path):
    controller = BrukerEDSController(connected_bruker_session)

    output_bcf = tmp_path / "test_map.bcf"
    output_bmp = tmp_path / "test_map.bmp"

    settings = BrukerEDSMapSettings(
        name="pytest_map_image",
        width_px=16,
        height_px=12,
        pixel_time_us=1024,
        real_time_s=0,
        output_bcf_path=str(output_bcf),
        output_image_path=str(output_bmp),
        output_image_format="bmp",
        spu_device=1,
    )

    outputs = controller.acquire_map(settings, poll_interval_s=0.2, max_wait_s=60.0)

    assert output_bcf.exists()
    assert output_bcf.stat().st_size > 0

    assert output_bmp.exists()
    assert output_bmp.stat().st_size > 0
    with open(output_bmp, "rb") as f:
        assert f.read(2) == b"BM"

    assert outputs.output_bcf_path == str(output_bcf)
    assert outputs.output_image_path == str(output_bmp)
