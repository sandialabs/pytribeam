#!/usr/bin/python3
"""
Unit tests for the EDAX SEM controller.

These commands act on the microscope through EDAX rather than on a detector,
and matter mainly when EDAX takes external beam control.
"""

# Third-party modules
import pytest

# Local scripts
from pytribeam.external_oem.edax.sem import EdaxSemController
from pytribeam.external_oem.edax.types import EdaxCommand

pytestmark = pytest.mark.detached


def test_magnification_round_trip(make_client):
    """Magnification reads back as an integer and writes as a bare number."""
    client, service = make_client(payloads={EdaxCommand.SEM_GET_MAGNIFICATION: "1500"})
    controller = EdaxSemController(client)

    assert controller.magnification() == 1500
    controller.set_magnification(2000)
    assert service.arguments_for(EdaxCommand.SEM_SET_MAGNIFICATION) == ['"2000"']


def test_external_beam_control_uses_boolean_literals(make_client):
    """Beam handover is a boolean, spelled the way EDAX expects."""
    client, service = make_client(
        payloads={EdaxCommand.SEM_GET_EXTERNAL_BEAM_CONTROL: "False"}
    )
    controller = EdaxSemController(client)

    assert controller.external_beam_control() is False
    controller.set_external_beam_control(True)
    assert service.arguments_for(EdaxCommand.SEM_SET_EXTERNAL_BEAM_CONTROL) == [
        '"True"'
    ]


def test_beam_location_sends_two_integer_arguments(make_client):
    """Beam parking takes an x and y pixel pair."""
    client, service = make_client()
    EdaxSemController(client).set_beam_location_px(128, 256)

    assert service.arguments_for(EdaxCommand.SEM_SET_BEAM_LOCATION) == ['"128","256"']


def test_pretilt_round_trip(make_client):
    """The pretilt holder angle reads and writes as a float in degrees."""
    client, service = make_client(payloads={EdaxCommand.SEM_GET_PRETILT_ANGLE: "70.0"})
    controller = EdaxSemController(client)

    assert controller.pretilt_deg() == pytest.approx(70.0)
    controller.set_pretilt_deg(36.0)
    assert service.arguments_for(EdaxCommand.SEM_SET_PRETILT_ANGLE) == ['"36.0"']


def test_state_reads_every_sem_value(make_client):
    """The aggregate read exists so callers snapshot the SEM in one call."""
    client, _ = make_client(
        payloads={
            EdaxCommand.SEM_GET_MAGNIFICATION: "1500",
            EdaxCommand.SEM_GET_EXTERNAL_BEAM_CONTROL: "True",
            EdaxCommand.SEM_GET_IMAGE_WIDTH: "1024",
            EdaxCommand.SEM_GET_IMAGE_HEIGHT: "884",
            EdaxCommand.SEM_GET_PRETILT_ANGLE: "70.0",
        }
    )
    state = EdaxSemController(client).state()

    assert state.magnification == 1500
    assert state.external_beam_control is True
    assert state.image_width_px == 1024
    assert state.image_height_px == 884
    assert state.pretilt_deg == pytest.approx(70.0)
