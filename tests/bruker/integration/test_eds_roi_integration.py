from pathlib import Path

import numpy as np
import pytest

from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.readback import BrukerEDSReadbackController
from pytribeam.external_oem.bruker.types import (
    BrukerEDSElementMapSetting,
    BrukerEDSProfileMapSettings,
    BrukerRectROI,
)


def _make_roi_profile_settings(tmp_path, roi, *, name):
    return BrukerEDSProfileMapSettings(
        name=name,
        width_px=16,
        height_px=12,
        pixel_time_us=1024,
        output_bcf_path=str(tmp_path / f"{name}.bcf"),
        output_image_path=str(tmp_path / f"{name}.bmp"),
        output_image_format="bmp",
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


@pytest.mark.esprit
@pytest.mark.bruker_simulator
@pytest.mark.parametrize(
    "name,roi",
    [
        (
            "roi_origin",
            BrukerRectROI(x_start_px=0, y_start_px=0, width_px=8, height_px=6),
        ),
        (
            "roi_non_origin",
            BrukerRectROI(x_start_px=3, y_start_px=2, width_px=8, height_px=6),
        ),
        (
            "roi_boundary_adjacent",
            BrukerRectROI(x_start_px=12, y_start_px=8, width_px=4, height_px=4),
        ),
    ],
)
def test_profile_roi_acquisition_outputs_and_readback_shape_if_supported(
    connected_bruker_session,
    tmp_path,
    name,
    roi,
):
    settings = _make_roi_profile_settings(tmp_path, roi, name=f"pytest_{name}")
    eds = BrukerEDSController(connected_bruker_session)

    outputs = eds.acquire_map_with_profile(
        settings,
        poll_interval_s=0.2,
        max_wait_s=60.0,
    )

    bcf_path = Path(outputs.output_bcf_path)
    assert bcf_path.exists()
    assert bcf_path.stat().st_size > 256

    assert outputs.output_image_path is not None
    bmp_path = Path(outputs.output_image_path)
    assert bmp_path.exists()
    assert bmp_path.stat().st_size > 0
    with open(bmp_path, "rb") as f:
        assert f.read(2) == b"BM"

    readback = BrukerEDSReadbackController(connected_bruker_session)
    results = readback.save_element_maps_npy(
        settings=settings,
        output_dir=str(tmp_path / f"readback_{name}"),
        prefix=settings.name,
        strict=False,
    )

    successful = [r for r in results if r.error is None]
    if not successful:
        pytest.skip(
            "HyMapGetElementData did not return numeric ROI data in this "
            "ESPRIT/simulator configuration"
        )

    for result in successful:
        assert result.shape == (roi.height_px, roi.width_px)
        assert result.path is not None
        arr = np.load(result.path)
        assert arr.shape == (roi.height_px, roi.width_px)
        assert arr.dtype == np.uint16


@pytest.mark.esprit
@pytest.mark.bruker_simulator
def test_invalid_roi_rejected_locally_before_esprit_acquisition(
    connected_bruker_session,
    tmp_path,
):
    settings = _make_roi_profile_settings(
        tmp_path,
        BrukerRectROI(x_start_px=14, y_start_px=0, width_px=4, height_px=4),
        name="pytest_invalid_roi_reject",
    )
    eds = BrukerEDSController(connected_bruker_session)

    with pytest.raises(ValueError, match="ROI exceeds map width"):
        eds.acquire_map_with_profile(settings, poll_interval_s=0.2, max_wait_s=60.0)

    assert not Path(settings.output_bcf_path).exists()
    assert not Path(settings.output_image_path).exists()
