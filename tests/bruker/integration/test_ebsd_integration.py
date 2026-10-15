import pytest

from pytribeam.external_oem.bruker.ebsd import BrukerEBSDController
from pytribeam.external_oem.core.errors import APICallError
from tests.bruker.helpers import skip_if_runtime_unavailable


@pytest.mark.esprit
def test_ebsd_get_profiles_raw(connected_bruker_session):
    controller = BrukerEBSDController(connected_bruker_session)
    status = controller.export_status()

    if not status.has_get_profiles:
        pytest.skip("EBSDGetAcquisitionProfiles not exported")

    try:
        profiles = controller.get_profiles_raw()
    except APICallError as exc:
        skip_if_runtime_unavailable(
            exc,
            "EBSD profiles not available in current simulator/runtime state",
        )

    assert isinstance(profiles, str)
    assert len(profiles) > 0


@pytest.mark.esprit
def test_ebsd_get_detector_position_mm(connected_bruker_session):
    controller = BrukerEBSDController(connected_bruker_session)
    status = controller.export_status()

    if not status.has_get_detector_position:
        pytest.skip("EBSDGetDetectorPosition not exported")

    try:
        position_mm = controller.get_detector_position_mm()
    except APICallError as exc:
        skip_if_runtime_unavailable(
            exc,
            "EBSD detector position query not available in current simulator/runtime state",
        )

    assert isinstance(position_mm, float)


@pytest.mark.esprit
def test_ebsd_get_acquisition_state_smoke(connected_bruker_session):
    controller = BrukerEBSDController(connected_bruker_session)
    status = controller.export_status()

    if not status.has_get_state:
        pytest.skip("EBSDGetAcquisitionState not exported")

    try:
        state = controller.get_acquisition_state()
    except APICallError as exc:
        skip_if_runtime_unavailable(
            exc,
            "EBSD acquisition state not available in current simulator/runtime state",
        )

    assert isinstance(state.current_line, int)
    assert isinstance(state.acquisition_percent, int)
    assert isinstance(state.indexing_percent, int)
    assert isinstance(state.acquisition_running, bool)
    assert isinstance(state.indexing_running, bool)
