import os
from pathlib import Path

import numpy as np
import pytest

from pytribeam.external_oem.bruker.detector_motion import BrukerDetectorMotionController
from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.readback import BrukerEDSReadbackController
from pytribeam.external_oem.bruker.types import (
    BrukerDetectorMotionSettings,
    BrukerEDSElementMapSetting,
    BrukerEDSProfileMapSettings,
)


def _move_settings(target_position):
    return BrukerDetectorMotionSettings(
        detector_index=1,
        target_position=target_position,
        timeout_s=60.0,
        poll_interval_s=0.5,
    )


def _small_profile_settings(tmp_path):
    return BrukerEDSProfileMapSettings(
        name="pytest_hardware_profile_smoke",
        width_px=64,
        height_px=48,
        pixel_time_us=1024,
        output_bcf_path=str(tmp_path / "pytest_hardware_profile_smoke.bcf"),
        output_image_path=str(tmp_path / "pytest_hardware_profile_smoke.bmp"),
        output_image_format="bmp",
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
        roi=None,
    )


@pytest.mark.esprit
@pytest.mark.hardware
def test_known_small_profile_map_bcf_bmp_and_numeric_readback_hardware(
    connected_bruker_hardware_session,
    tmp_path,
):
    """Short real-hardware smoke test.

    This test moves the EDS detector to acquire and always attempts to park it
    again in a finally block. It intentionally uses a small map to keep the
    hardware test short and safe.
    """
    motion = BrukerDetectorMotionController(connected_bruker_hardware_session)
    eds = BrukerEDSController(connected_bruker_hardware_session)
    settings = _small_profile_settings(tmp_path)

    try:
        acquire_state = motion.move_eds_detector(_move_settings("acquire"))
        assert acquire_state.position_name == "acquire"

        outputs = eds.acquire_map_with_profile(
            settings,
            poll_interval_s=0.5,
            max_wait_s=120.0,
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

        readback = BrukerEDSReadbackController(connected_bruker_hardware_session)
        results = readback.save_element_maps_npy(
            settings=settings,
            output_dir=str(tmp_path / "readback"),
            prefix=settings.name,
            strict=False,
        )
        successful = [r for r in results if r.error is None]
        assert successful, [r.error for r in results]

        for result in successful:
            assert result.path is not None
            arr = np.load(result.path)
            assert arr.shape == (settings.height_px, settings.width_px)
            assert arr.dtype == np.uint16

        if os.environ.get("PYTRIBEAM_BRUKER_HARDWARE_EXPECT_NONZERO") == "1":
            assert any((r.nonzero or 0) > 0 for r in successful)
    finally:
        park_state = motion.move_eds_detector(_move_settings("park"))
        assert park_state.position_name == "park"
