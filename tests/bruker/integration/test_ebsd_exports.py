import pytest

from pytribeam.external_oem.bruker.ebsd import BrukerEBSDController


@pytest.mark.esprit
def test_ebsd_export_probe(connected_bruker_session):
    controller = BrukerEBSDController(connected_bruker_session)
    status = controller.export_status()

    # This test is mainly an introspection/probe test for now.
    # We only assert that we can build the controller and query export availability.
    assert status is not None

    print("\nEBSD export status:")
    print(f"  has_get_profiles={status.has_get_profiles}")
    print(f"  has_select_profile={status.has_select_profile}")
    print(f"  has_start_acquisition={status.has_start_acquisition}")
    print(f"  has_start_with_profile={status.has_start_with_profile}")
    print(f"  has_stop_acquisition={status.has_stop_acquisition}")
    print(f"  has_get_state={status.has_get_state}")
    print(f"  has_save_to_file={status.has_save_to_file}")
    print(f"  has_export_data={status.has_export_data}")
    print(f"  has_get_detector_position={status.has_get_detector_position}")
    print(f"  has_set_detector_position={status.has_set_detector_position}")
