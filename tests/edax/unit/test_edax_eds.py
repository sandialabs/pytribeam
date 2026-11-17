#!/usr/bin/python3
"""
Unit tests for the EDAX EDS controller.

The EDS and EBSD controllers share a base class, so these tests concentrate on
what is specific to EDS: the unsuffixed command names, the mapping parameter
set, and detector slide and cooling control.
"""

# Third-party modules
import pytest

# Local scripts
from pytribeam.external_oem.edax.eds import EdaxEdsController
from pytribeam.external_oem.edax.errors import EdaxResponseError, EdaxTimeoutError
from pytribeam.external_oem.edax.types import (
    EdaxCommand,
    EdaxDetectorSlideStatus,
    EdaxDetectorStatus,
    EdaxEdsMapParams,
    EdaxEdsResolution,
    EdaxMappingStatus,
)

pytestmark = pytest.mark.detached


# ----------------------------------------------------------------------
# Command binding
# ----------------------------------------------------------------------
def test_eds_uses_the_unsuffixed_command_names(make_client):
    """The EDS half of the API has no _EBSD suffix on shared commands."""
    client, service = make_client()
    EdaxEdsController(client).collection_start("map1")

    assert EdaxCommand.EDS_COLLECTION_START.value in service.commands()
    assert EdaxCommand.EBSD_COLLECTION_START.value not in service.commands()


def test_eds_map_status_uses_the_eds_command(make_client):
    """Status must be read from get_map_status, not get_map_status_ebsd."""
    client, service = make_client(
        payloads={EdaxCommand.EDS_GET_MAP_STATUS: "MappingActive"}
    )

    assert EdaxEdsController(client).map_status() is EdaxMappingStatus.MAPPING_ACTIVE
    assert EdaxCommand.EDS_GET_MAP_STATUS.value in service.commands()


# ----------------------------------------------------------------------
# Mapping parameters
# ----------------------------------------------------------------------
def test_apply_map_parameters_sends_only_populated_fields(make_client):
    """Null fields are left alone so partial updates do not clobber settings."""
    client, service = make_client()

    EdaxEdsController(client).apply_map_parameters(
        EdaxEdsMapParams(
            resolution=EdaxEdsResolution.PRESET_512X400, preset_dwell_us=200.0
        )
    )

    sent = service.commands()
    assert EdaxCommand.EDS_SET_NUMPOINTS.value in sent
    assert EdaxCommand.EDS_SET_PRESETDWELL.value in sent
    assert EdaxCommand.EDS_SET_NUMFRAMES.value not in sent


@pytest.mark.parametrize("preset", list(EdaxEdsResolution))
def test_resolution_is_sent_as_its_exact_point_count_only(make_client, preset):
    """Seen on hardware: APEX picks its preset from numpoints (rounding down)
    and ignores numlines. Exact widths make the rounding irrelevant."""
    client, service = make_client()

    EdaxEdsController(client).apply_map_parameters(EdaxEdsMapParams(resolution=preset))

    assert service.arguments_for(EdaxCommand.EDS_SET_NUMPOINTS) == [
        f'"{preset.points}"'
    ]
    assert EdaxCommand.EDS_SET_NUMLINES.value not in service.commands()


READBACK = {
    EdaxCommand.EDS_GET_FOLDERPATH: r"C:\EDAX Data",
    EdaxCommand.EDS_GET_EDSCHANNEL: "1",
    EdaxCommand.EDS_GET_NUMFRAMES: "10",
    EdaxCommand.EDS_GET_NUMPOINTS: "512",
    EdaxCommand.EDS_GET_PRESETDWELL: "200.0",
    EdaxCommand.EDS_GET_EDSNUMCHAN: "1024",
    EdaxCommand.EDS_GET_BYTESPERCHANNEL: "2",
    EdaxCommand.EDS_GET_IPD: "5",
    EdaxCommand.EDS_GET_NUMREADS: "1",
}


def test_map_parameters_reads_the_full_set_back(make_client):
    """The read-back path converts every payload into its typed field."""
    client, _ = make_client(payloads=READBACK)
    params = EdaxEdsController(client).map_parameters()

    assert params.resolution is EdaxEdsResolution.PRESET_512X400
    assert params.preset_dwell_us == pytest.approx(200.0)
    assert params.inter_pixel_delay == 5


def test_dwell_duration_takes_the_lines_from_the_preset(make_client):
    """APEX's stored line count goes stale; the preset's own is used."""
    client, _ = make_client(
        payloads={
            EdaxCommand.EDS_GET_NUMPOINTS: "256",
            EdaxCommand.EDS_GET_NUMLINES: "101",
            EdaxCommand.EDS_GET_NUMFRAMES: "3",
            EdaxCommand.EDS_GET_PRESETDWELL: "50",
        }
    )

    duration = EdaxEdsController(client).dwell_duration_s()

    assert duration == pytest.approx(256 * 200 * 3 * 50e-6)


def test_dwell_duration_is_unknown_off_the_presets(make_client):
    """A stored point count that is no preset leaves the size unknown."""
    client, _ = make_client(payloads={EdaxCommand.EDS_GET_NUMPOINTS: "100"})

    assert EdaxEdsController(client).dwell_duration_s() is None


def test_stored_point_count_off_the_presets_reads_back_as_none(make_client):
    """A value APEX rounded (e.g. 100, sent before) names no preset."""
    client, _ = make_client(payloads={**READBACK, EdaxCommand.EDS_GET_NUMPOINTS: "100"})

    assert EdaxEdsController(client).map_parameters().resolution is None


# ----------------------------------------------------------------------
# Detector status
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload, expected",
    [
        ("Ready", EdaxDetectorStatus.READY),
        ("NotReady", EdaxDetectorStatus.NOT_READY),
        ("Not_Ready", EdaxDetectorStatus.NOT_READY),
    ],
)
def test_detector_status_normalizes_edax_spelling(make_client, payload, expected):
    """EDAX varies case and underscores between builds."""
    client, _ = make_client(
        payloads={EdaxCommand.EDS_GET_SYSTEM_DETECTOR_STATUS: payload}
    )
    assert EdaxEdsController(client).detector_status() is expected


def test_unrecognized_detector_status_raises_with_the_text(make_client):
    """An unexpected payload must surface as-is, not as a false "not ready"."""
    client, _ = make_client(
        payloads={EdaxCommand.EDS_GET_SYSTEM_DETECTOR_STATUS: "Warming"}
    )

    with pytest.raises(EdaxResponseError, match="Warming"):
        EdaxEdsController(client).detector_status()


@pytest.mark.parametrize(
    "payload, expected",
    [
        ("SlideIn", EdaxDetectorSlideStatus.SLIDE_IN),
        ("SlideOut", EdaxDetectorSlideStatus.SLIDE_OUT),
        ("1", EdaxDetectorSlideStatus.SLIDE_IN),
        ("0", EdaxDetectorSlideStatus.SLIDE_OUT),
        ("100", EdaxDetectorSlideStatus.UNKNOWN),
        ("something else", EdaxDetectorSlideStatus.UNKNOWN),
    ],
)
def test_slide_status_accepts_names_and_enum_values(make_client, payload, expected):
    """The IPAPI documents this command as returning an enum value, not a name."""
    client, _ = make_client(payloads={EdaxCommand.EDS_GET_DETECTOR_STATUS: payload})
    assert EdaxEdsController(client).slide_status() is expected


# ----------------------------------------------------------------------
# Detector motion
# ----------------------------------------------------------------------
def test_insert_detector_is_a_no_op_when_already_inserted(make_client, no_sleep):
    """An already-inserted detector must not be commanded to move again."""
    client, service = make_client(
        payloads={EdaxCommand.EDS_GET_DETECTOR_STATUS: "SlideIn"}
    )

    assert EdaxEdsController(client).insert_detector(quiet=True) is True
    assert EdaxCommand.EDS_INSERT_DETECTOR.value not in service.commands()


def test_insert_detector_polls_until_the_slide_arrives(make_client, no_sleep):
    """The controller waits out the travel rather than returning early."""
    client, service = make_client(
        payloads={EdaxCommand.EDS_GET_DETECTOR_STATUS: ["SlideOut", "0", "SlideIn"]}
    )

    assert EdaxEdsController(client).insert_detector(quiet=True) is True
    assert EdaxCommand.EDS_INSERT_DETECTOR.value in service.commands()


def test_retract_detector_polls_until_the_slide_arrives(make_client, no_sleep):
    """Retraction mirrors insertion, waiting for the opposite state."""
    client, service = make_client(
        payloads={EdaxCommand.EDS_GET_DETECTOR_STATUS: ["SlideIn", "SlideOut"]}
    )

    assert EdaxEdsController(client).retract_detector(quiet=True) is True
    assert EdaxCommand.EDS_RETRACT_DETECTOR.value in service.commands()


@pytest.mark.parametrize("command", ["insert_detector", "retract_detector"])
def test_detector_moves_accept_the_true_acknowledgement(make_client, no_sleep, command):
    """The hardware answers do_retract_eds_detector with 'True', not the
    documented 'Execution Successful'; the move must still wait and succeed."""
    start, end = ["SlideOut", "SlideIn"]
    if command == "retract_detector":
        start, end = end, start
    client, _ = make_client(
        payloads={
            EdaxCommand.EDS_GET_DETECTOR_STATUS: [start, end],
            EdaxCommand.EDS_INSERT_DETECTOR: "True",
            EdaxCommand.EDS_RETRACT_DETECTOR: "True",
        }
    )

    assert getattr(EdaxEdsController(client), command)(quiet=True) is True


def test_detector_move_timeout_raises(make_client, no_sleep):
    """A detector that never arrives must not block the workflow forever."""
    client, _ = make_client(payloads={EdaxCommand.EDS_GET_DETECTOR_STATUS: "SlideOut"})

    with pytest.raises(EdaxTimeoutError):
        EdaxEdsController(client).insert_detector(
            quiet=True, timeout_s=0.05, poll_interval_s=0.0
        )


# ----------------------------------------------------------------------
# Cooling
# ----------------------------------------------------------------------
def test_cooling_is_set_with_a_boolean_literal(make_client):
    """EDAX expects the literal True, not 1."""
    client, service = make_client()
    EdaxEdsController(client).set_cooling(True)

    assert service.arguments_for(EdaxCommand.EDS_SET_DETECTOR_COOLING) == ['"True"']


def test_cooling_status_is_returned_as_a_boolean(make_client):
    """The cooling query answers with a boolean payload."""
    client, _ = make_client(
        payloads={EdaxCommand.EDS_GET_DETECTOR_COOLING_STATUS: "True"}
    )
    assert EdaxEdsController(client).cooling_enabled() is True
