import pytest

from pytribeam.external_oem.bruker.detector_motion import BrukerDetectorMotionController
from pytribeam.external_oem.bruker.types import BrukerDetectorMotionSettings


@pytest.mark.esprit
@pytest.mark.hardware
@pytest.mark.bruker_hardware
def test_eds_detector_move_acquire_and_park(connected_bruker_hardware_session):
    controller = BrukerDetectorMotionController(connected_bruker_hardware_session)

    acquire_settings = BrukerDetectorMotionSettings(
        detector_index=1,
        target_position="acquire",
        timeout_s=60.0,
        poll_interval_s=0.5,
    )
    park_settings = BrukerDetectorMotionSettings(
        detector_index=1,
        target_position="park",
        timeout_s=60.0,
        poll_interval_s=0.5,
    )

    try:
        initial_state = controller.get_eds_detector_position(detector_index=1)
        assert initial_state.detector_index == 1

        state1 = controller.move_eds_detector(acquire_settings)
        assert state1.position_name == "acquire"
    finally:
        state2 = controller.move_eds_detector(park_settings)
        assert state2.position_name == "park"
