import pytest

from pytribeam.external_oem.bruker.spectrometer import BrukerSpectrometerController


@pytest.mark.esprit
@pytest.mark.bruker_simulator
def test_spectrometer_status_configuration_and_ranges_if_available(
    connected_bruker_session,
):
    controller = BrukerSpectrometerController(connected_bruker_session)

    try:
        status = controller.get_spectrometer_status(spu=1)
        config = controller.get_spectrometer_configuration(spu=1)
        ranges = controller.get_spectrometer_ranges(spu=1, det=1)
    except Exception as exc:
        pytest.skip(f"Spectrometer status/config/ranges unavailable: {exc}")

    assert isinstance(status.ready, bool)
    assert len(status.detector_statuses) == 4

    assert len(config) == 2
    assert all(isinstance(value, int) for value in config)

    assert len(ranges.max_energy) == 8
    assert len(ranges.pulse_throughput) == 8
    assert isinstance(ranges.energy_index_count, int)
    assert isinstance(ranges.pulse_index_count, int)
