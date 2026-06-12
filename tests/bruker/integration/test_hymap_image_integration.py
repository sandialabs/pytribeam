import pytest

from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.types import BrukerEDSMapSettings


@pytest.mark.esprit
def test_hymap_get_image_writes_valid_bmp(connected_bruker_session, tmp_path):
    controller = BrukerEDSController(connected_bruker_session)

    output_bcf = tmp_path / "image_only_map.bcf"
    output_bmp = tmp_path / "image_only_map.bmp"

    settings = BrukerEDSMapSettings(
        name="pytest_hymap_image",
        width_px=16,
        height_px=12,
        pixel_time_us=1024,
        real_time_s=0,
        output_bcf_path=str(output_bcf),
        output_image_path=None,
        output_image_format=None,
        spu_device=1,
    )

    controller.acquire_map(settings, poll_interval_s=0.2, max_wait_s=60.0)

    image_path = controller.save_map_image(
        output_path=str(output_bmp),
        fmt="bmp",
        image_channel=0,
    )

    assert image_path == str(output_bmp)
    assert output_bmp.exists()
    assert output_bmp.stat().st_size > 0

    with open(output_bmp, "rb") as f:
        assert f.read(2) == b"BM"
