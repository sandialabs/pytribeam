import pytest

from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.types import BrukerEDSMapSettings


@pytest.mark.esprit
def test_bcf_file_saved_and_nontrivial(connected_bruker_session, tmp_path):
    controller = BrukerEDSController(connected_bruker_session)

    output_bcf = tmp_path / "content_check.bcf"

    settings = BrukerEDSMapSettings(
        name="pytest_bcf_content",
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

    assert outputs.output_bcf_path == str(output_bcf)
    assert output_bcf.exists()

    size = output_bcf.stat().st_size
    assert size > 256
