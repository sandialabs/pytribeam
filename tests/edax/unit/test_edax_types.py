#!/usr/bin/python3
"""
Unit tests for the EDAX type definitions.

These pin the enum values against the *EDAX IP / API Reference* tables, since a
wrong integer here would be silently accepted by the IPAPI and produce a
mis-configured scan rather than an error.
"""

# Third-party modules
import pytest

# Local scripts
from pytribeam.external_oem.edax import types as et

pytestmark = pytest.mark.detached


# ----------------------------------------------------------------------
# Enum values against the reference tables
# ----------------------------------------------------------------------
def test_access_type_values_match_section_3_3():
    """RemoteAccessSourceType: Normal 0, NoWait 1, None 2."""
    assert et.EdaxAccessType.NORMAL == 0
    assert et.EdaxAccessType.NO_WAIT == 1
    assert et.EdaxAccessType.NONE == 2


def test_resolution_values_match_section_2_5_5():
    """Fine 0, Medium 1, Coarse 2, Custom 3."""
    assert et.EdaxEbsdResolution.FINE == 0
    assert et.EdaxEbsdResolution.MEDIUM == 1
    assert et.EdaxEbsdResolution.COARSE == 2
    assert et.EdaxEbsdResolution.CUSTOM == 3


def test_grid_values_match_section_2_5_7():
    """Hexagonal 0, Square 1."""
    assert et.EdaxGridType.HEXAGONAL == 0
    assert et.EdaxGridType.SQUARE == 1


def test_detector_slide_status_covers_section_3_6():
    """SlideOut, SlideIn, and Unknown are the documented members."""
    assert {status.value for status in et.EdaxDetectorSlideStatus} == {
        "slideout",
        "slidein",
        "unknown",
    }


def test_mapping_status_covers_all_seventeen_members():
    """Sections 3.2 and 3.5 list seventeen mapping states."""
    assert len(list(et.EdaxMappingStatus)) == 17


def test_camera_status_covers_all_eighteen_members():
    """Section 3.4 lists seventeen slide states plus Unknown."""
    assert len(list(et.EdaxCameraStatus)) == 18


def test_command_names_are_lower_case_and_unique():
    """Command values are compared against response prefixes directly."""
    values = [command.value for command in et.EdaxCommand]
    assert all(value == value.lower() for value in values)
    assert len(values) == len(set(values))


def test_event_names_are_lower_case_and_prefixed():
    """Events are recognized by their EVENT_ prefix when parsing."""
    for event in et.EdaxEvent:
        assert event.value == event.value.lower()
        assert event.value.startswith("event_")


# ----------------------------------------------------------------------
# Status classification
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "status, terminal",
    [
        (et.EdaxMappingStatus.MAPPING_ACTIVE, False),
        (et.EdaxMappingStatus.SETUP_ACTIVE, False),
        (et.EdaxMappingStatus.MAPPING_PAUSED, False),
        (et.EdaxMappingStatus.READY, True),
        (et.EdaxMappingStatus.MAPPING_COMPLETE, True),
        (et.EdaxMappingStatus.MAPPING_ABORTED, True),
        (et.EdaxMappingStatus.MAPPING_STOPPED, True),
        (et.EdaxMappingStatus.MAPPING_ERROR, True),
    ],
)
def test_terminal_statuses_end_a_collection_wait(status, terminal):
    """The polling loop stops only on a status that ends the collection."""
    assert status.is_terminal is terminal


@pytest.mark.parametrize(
    "status, is_error",
    [
        (et.EdaxMappingStatus.MAPPING_ERROR, True),
        (et.EdaxMappingStatus.SETUP_ERROR, True),
        (et.EdaxMappingStatus.UNKNOWN, True),
        (et.EdaxMappingStatus.MAPPING_COMPLETE, False),
        (et.EdaxMappingStatus.MAPPING_ABORTED, False),
    ],
)
def test_error_statuses_are_distinguished_from_completion(status, is_error):
    """A failed map must raise; a stopped or aborted one merely ends."""
    assert status.is_error is is_error


@pytest.mark.parametrize(
    "status, moving",
    [
        (et.EdaxCameraStatus.SLIDE_MOVING_IN, True),
        (et.EdaxCameraStatus.SLIDE_MOVING_OUT, True),
        (et.EdaxCameraStatus.SLIDE_MOVE_MID_IN, True),
        (et.EdaxCameraStatus.SLIDE_IN, False),
        (et.EdaxCameraStatus.SLIDE_OUT, False),
    ],
)
def test_moving_camera_states_are_recognized(status, moving):
    """In-transit states must not be mistaken for arrival."""
    assert status.is_moving is moving


@pytest.mark.parametrize(
    "status, is_error",
    [
        (et.EdaxCameraStatus.SLIDE_ERROR, True),
        (et.EdaxCameraStatus.SLIDE_WATCHDOG, True),
        (et.EdaxCameraStatus.SLIDE_NO_POWER, True),
        (et.EdaxCameraStatus.SLIDE_DISABLED, True),
        (et.EdaxCameraStatus.SLIDE_MOVE_WDOG, False),
        (et.EdaxCameraStatus.SLIDE_MID, False),
    ],
)
def test_camera_error_states_require_intervention(status, is_error):
    """A stalled move is recoverable; a watchdog trip is not."""
    assert status.is_error is is_error


# ----------------------------------------------------------------------
# Named tuples
# ----------------------------------------------------------------------
def test_response_reports_execution_success():
    """The success check tolerates the case EDAX actually sends."""
    assert et.EdaxResponse("", "cmd", "Execution Successful").succeeded is True
    assert et.EdaxResponse("", "cmd", "execution successful").succeeded is True
    assert et.EdaxResponse("", "cmd", "Ready").succeeded is False


def test_limit_contains_is_inclusive():
    """Camera limits are documented as inclusive minimum and maximum."""
    limit = et.EdaxLimit(min=1.0, max=100.0)
    assert limit.contains(1.0) is True
    assert limit.contains(100.0) is True
    assert limit.contains(0.999) is False


def test_map_parameter_defaults_are_all_null():
    """A default parameter set changes nothing when applied."""
    assert all(value is None for value in et.EdaxEbsdMapParams())
    assert all(value is None for value in et.EdaxEdsMapParams())
    assert all(value is None for value in et.EdaxCameraParams())


def test_connection_defaults_match_the_documented_service():
    """The IPAPI service listens on port 8301 unless reconfigured."""
    settings = et.EdaxConnectionSettings(host="edax-pc")
    assert settings.port == 8301
