#!/usr/bin/python3
"""
Unit tests for the EDAX IPAPI wire protocol.

These cover command formatting and response parsing, which are pure functions
and therefore the cheapest place to pin down the wire format described in the
*EDAX IP / API Reference*.
"""

# Default python modules
from pathlib import Path

# Third-party modules
import pytest

# Local scripts
from pytribeam.external_oem.edax import protocol
from pytribeam.external_oem.edax.errors import EdaxResponseError
from pytribeam.external_oem.edax.types import (
    EdaxAccessType,
    EdaxCommand,
    EdaxEbsdResolution,
    EdaxEvent,
    EdaxGridType,
    EdaxResponse,
)

pytestmark = pytest.mark.detached


# ----------------------------------------------------------------------
# Command formatting
# ----------------------------------------------------------------------
def test_command_without_arguments_is_bare_name():
    """A command with no parameters is sent as its name alone."""
    assert protocol.format_command(EdaxCommand.UNLOCK) == "edax_unlock"


def test_arguments_are_quoted_and_comma_separated():
    """The IPAPI requires every argument in double quotes, comma separated."""
    formatted = protocol.format_command(
        EdaxCommand.EBSD_SET_SYSTEM_PROJECTINFO_EXT, "guid-1", "My Project", 10, 2.5
    )
    assert formatted == (
        'set_system_projectinfo_ext_ebsd "guid-1","My Project","10","2.5"'
    )


def test_booleans_render_as_true_and_false():
    """EDAX expects the literal strings True and False, not 1 and 0."""
    assert protocol.format_command(EdaxCommand.EBSD_SET_SAVEPATTERNS, True) == (
        'set_ebsd_params_savepatterns "True"'
    )
    assert protocol.format_command(EdaxCommand.EBSD_SET_SAVEPATTERNS, False) == (
        'set_ebsd_params_savepatterns "False"'
    )


@pytest.mark.parametrize(
    "value, expected",
    [
        (EdaxAccessType.NO_WAIT, "1"),
        (EdaxGridType.SQUARE, "1"),
        (EdaxGridType.HEXAGONAL, "0"),
        (EdaxEbsdResolution.CUSTOM, "3"),
    ],
)
def test_enums_render_as_their_underlying_value(value, expected):
    """Enum arguments must reach the wire as bare numbers, never as reprs."""
    formatted = protocol.format_command(EdaxCommand.EBSD_SET_GRID, value)
    assert formatted == f'set_ebsd_params_grid "{expected}"'


def test_paths_render_as_plain_strings():
    """Folder paths are sent verbatim, including spaces."""
    formatted = protocol.format_command(
        EdaxCommand.EBSD_SET_FOLDERPATH, Path("C:/EDAX Data/run 1")
    )
    assert 'set_ebsd_params_folderpath "' in formatted
    assert "run 1" in formatted


def test_string_commands_are_accepted_and_normalized():
    """Callers may pass a raw command name instead of the enum member."""
    assert protocol.format_command("GET_MAP_STATUS_EBSD") == "get_map_status_ebsd"


def test_success_response_matches_the_documented_format():
    """The canonical success reply echoes the command and the payload."""
    assert protocol.success_response(EdaxCommand.EBSD_COLLECTION_START) == (
        'do_map_collection_start_ebsd response "execution successful"'
    )


# ----------------------------------------------------------------------
# Response parsing
# ----------------------------------------------------------------------
def test_parse_response_splits_command_from_payload():
    """The command prefix, RESPONSE keyword, and quotes are all removed."""
    response = protocol.parse_message(
        'do_map_collection_start RESPONSE "Execution Successful"'
    )
    assert response.command == "do_map_collection_start"
    assert response.payload == "Execution Successful"
    assert response.is_event is False
    assert response.succeeded is True


def test_payload_preserves_interior_spacing():
    """Folder paths must survive parsing intact, spaces included."""
    response = protocol.parse_message(
        'get_ebsd_params_folderpath response "C:\\EDAX Data\\run 1"'
    )
    assert response.payload == "C:\\EDAX Data\\run 1"


def test_events_are_flagged_and_named():
    """Asynchronous notifications are distinguished from command responses."""
    response = protocol.parse_message(
        'EVENT_MAP_COLLECTION_COMPLETE_EBSD "Mapping Complete"'
    )
    assert response.is_event is True
    assert response.command == EdaxEvent.EBSD_COLLECTION_COMPLETE.value
    assert response.payload == "Mapping Complete"


def test_unlock_acknowledgement_parses_without_a_prefix():
    """The unlock reply does not echo its command, and must still parse."""
    response = protocol.parse_message("Client connection accepted")
    assert response.command == ""
    assert response.payload == "Client connection accepted"
    assert protocol.matches_command(response, EdaxCommand.UNLOCK) is True


def test_matches_command_rejects_a_different_command():
    """A stale response for another command must not satisfy the current one."""
    response = protocol.parse_message('get_map_status response "Ready"')
    assert protocol.matches_command(response, EdaxCommand.EBSD_GET_MAP_STATUS) is False


def test_matches_command_rejects_events():
    """An event is never the answer to a command."""
    response = protocol.parse_message('EVENT_MAP_COLLECTION_COMPLETE "done"')
    assert protocol.matches_command(response, EdaxCommand.EDS_COLLECTION_START) is False


@pytest.mark.parametrize(
    "raw",
    [
        (
            'get_map_status_ebsd RESPONSE "MappingActive"'
            'EVENT_MAP_COLLECTION_COMPLETE_EBSD "Mapping Complete"'
        ),
        (
            'get_map_status_ebsd RESPONSE "MappingActive"\n'
            'EVENT_MAP_COLLECTION_COMPLETE_EBSD "Mapping Complete"'
        ),
        (
            'get_map_status_ebsd RESPONSE "MappingActive"  '
            'EVENT_MAP_COLLECTION_COMPLETE_EBSD "Mapping Complete"'
        ),
    ],
)
def test_concatenated_messages_split_apart(raw):
    """One socket read may carry several messages, with or without separators."""
    responses = protocol.parse_messages(raw)
    assert len(responses) == 2
    assert responses[0].command == "get_map_status_ebsd"
    assert responses[0].payload == "MappingActive"
    assert responses[1].is_event is True
    assert responses[1].payload == "Mapping Complete"


def test_empty_read_yields_no_messages():
    """Blank or missing reads produce nothing rather than an empty message."""
    assert protocol.parse_messages("") == []
    assert protocol.parse_messages("   ") == []
    assert protocol.parse_messages(None) == []


# ----------------------------------------------------------------------
# Payload conversion
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload, expected",
    [("True", True), ("true", True), ("1", True), ("False", False), ("0", False)],
)
def test_to_bool_accepts_the_literals_edax_returns(payload, expected):
    """EDAX is inconsistent about boolean spelling, so accept both forms."""
    response = EdaxResponse(raw="", command="cmd", payload=payload)
    assert protocol.to_bool(response) is expected


def test_to_bool_rejects_non_boolean_payloads():
    """A payload that is not a boolean must raise rather than coerce."""
    response = EdaxResponse(raw="", command="cmd", payload="Ready")
    with pytest.raises(EdaxResponseError):
        protocol.to_bool(response)


def test_to_int_truncates_decimal_payloads():
    """Some IPAPI builds return pixel counts with a decimal point."""
    response = EdaxResponse(raw="", command="cmd", payload="1024.0")
    assert protocol.to_int(response) == 1024


def test_to_int_rejects_non_numeric_payloads():
    """Non-numeric text must raise rather than silently become zero."""
    response = EdaxResponse(raw="", command="cmd", payload="not a number")
    with pytest.raises(EdaxResponseError):
        protocol.to_int(response)


def test_to_float_parses_scientific_notation():
    """Tick counts arrive large enough that exponent form is possible."""
    response = EdaxResponse(raw="", command="cmd", payload="1.2e7")
    assert protocol.to_float(response) == pytest.approx(1.2e7)


def test_to_int_array_parses_a_pixel_list():
    """Camera captures return one comma-delimited integer per pixel."""
    response = EdaxResponse(raw="", command="cmd", payload="10, 20,30 , 40")
    assert protocol.to_int_array(response) == (10, 20, 30, 40)


def test_to_int_array_of_empty_payload_is_empty():
    """An empty capture payload is an empty tuple, not an error."""
    response = EdaxResponse(raw="", command="cmd", payload="")
    assert protocol.to_int_array(response) == ()


def test_to_str_array_parses_binning_names():
    """Binning modes arrive as a comma-delimited list of names."""
    response = EdaxResponse(raw="", command="cmd", payload="1x1, 2x2 ,4x4")
    assert protocol.to_str_array(response) == ("1x1", "2x2", "4x4")
