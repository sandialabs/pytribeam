from pathlib import Path

import numpy as np
import pytest

from pytribeam.external_oem.bruker.config import load_bruker_eds_yaml
from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.readback import BrukerEDSReadbackController
from pytribeam.external_oem.bruker.types import (
    BrukerEDSElementMapSetting,
    BrukerEDSProfileMapSettings,
)

WORKFLOW_TEST_YAML = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "pytribeam"
    / "external_oem"
    / "bruker"
    / "tools"
    / "validation"
    / "bruker_eds_workflow_test.yml"
)


def _make_profile_settings(tmp_path, *, name="pytest_profile_smoke", save_image=True):
    return BrukerEDSProfileMapSettings(
        name=name,
        width_px=16,
        height_px=12,
        pixel_time_us=1024,
        output_bcf_path=str(tmp_path / f"{name}.bcf"),
        output_image_path=str(tmp_path / f"{name}.bmp") if save_image else None,
        output_image_format="bmp" if save_image else None,
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
        roi=None,
    )


def test_packaged_workflow_yaml_loads_and_roi_is_valid():

    settings = load_bruker_eds_yaml(WORKFLOW_TEST_YAML)

    assert settings.map.width_px == 64
    assert settings.map.height_px == 48
    assert settings.map.roi is not None
    assert (
        settings.map.roi.x_start_px + settings.map.roi.width_px <= settings.map.width_px
    )
    assert (
        settings.map.roi.y_start_px + settings.map.roi.height_px
        <= settings.map.height_px
    )
    assert len(settings.map.elements) >= 1


@pytest.mark.esprit
def test_small_profile_map_saves_bcf_and_bmp(connected_bruker_session, tmp_path):
    controller = BrukerEDSController(connected_bruker_session)
    settings = _make_profile_settings(tmp_path)

    outputs = controller.acquire_map_with_profile(
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


@pytest.mark.esprit
def test_small_profile_numeric_readback_npy_if_supported(
    connected_bruker_session,
    tmp_path,
):
    eds = BrukerEDSController(connected_bruker_session)
    settings = _make_profile_settings(
        tmp_path,
        name="pytest_profile_readback_smoke",
        save_image=False,
    )

    eds.acquire_map_with_profile(
        settings,
        poll_interval_s=0.2,
        max_wait_s=60.0,
    )

    readback = BrukerEDSReadbackController(connected_bruker_session)
    results = readback.save_element_maps_npy(
        settings=settings,
        output_dir=str(tmp_path / "readback"),
        prefix=settings.name,
        strict=False,
    )

    successful = [r for r in results if r.error is None]
    if not successful:
        pytest.skip(
            "HyMapGetElementData did not return numeric element data in this "
            "ESPRIT/simulator configuration"
        )

    for result in successful:
        assert result.path is not None
        arr = np.load(result.path)
        assert arr.shape == (settings.height_px, settings.width_px)
        assert arr.dtype == np.uint16
