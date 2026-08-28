#!/usr/bin/python3
"""
Unit tests for the EDAX EBSD controller.

These verify the command sequences the controller emits, the parameter
ordering the IPAPI requires, and the polling loops around camera motion and
map collection.
"""

# Default python modules
from pathlib import Path

# Third-party modules
import pytest

# Local scripts
from pytribeam.external_oem.edax.base import TICKS_PER_SECOND
from pytribeam.external_oem.edax.ebsd import EdaxEbsdController
from pytribeam.external_oem.edax.errors import EdaxStateError, EdaxTimeoutError
from pytribeam.external_oem.edax.types import (
    EdaxAccessType,
    EdaxCameraParams,
    EdaxCameraStatus,
    EdaxCommand,
    EdaxEbsdMapParams,
    EdaxEbsdMode,
    EdaxEbsdResolution,
    EdaxEvent,
    EdaxGridType,
    EdaxMappingStatus,
    EdaxProjectInfo,
)

pytestmark = pytest.mark.detached


# ----------------------------------------------------------------------
# Mapping parameters
# ----------------------------------------------------------------------
def test_apply_map_parameters_sends_only_populated_fields(make_client):
    """Null fields are left alone so partial updates do not clobber settings."""
    client, service = make_client()
    controller = EdaxEbsdController(client)

    controller.apply_map_parameters(
        EdaxEbsdMapParams(x_size_um=25.0, save_patterns=True)
    )

    sent = service.commands()
    assert EdaxCommand.EBSD_SET_XSIZE.value in sent
    assert EdaxCommand.EBSD_SET_SAVEPATTERNS.value in sent
    assert EdaxCommand.EBSD_SET_YSIZE.value not in sent
    assert EdaxCommand.EBSD_SET_GRID.value not in sent


def test_resolution_is_set_before_step_size(make_client):
    """EDAX ignores step size unless the resolution is already custom."""
    client, service = make_client()
    controller = EdaxEbsdController(client)

    controller.apply_map_parameters(
        EdaxEbsdMapParams(
            resolution=EdaxEbsdResolution.CUSTOM,
            step_size_um=0.5,
            custom_step_size_um=0.5,
        )
    )

    sent = service.commands()
    assert sent.index(EdaxCommand.EBSD_SET_RESOLUTION.value) < sent.index(
        EdaxCommand.EBSD_SET_STEPSIZE.value
    )
    assert sent.index(EdaxCommand.EBSD_SET_RESOLUTION.value) < sent.index(
        EdaxCommand.EBSD_SET_CUSTOMSTEPSIZE.value
    )


def test_enum_parameters_reach_the_wire_as_numbers(make_client):
    """A grid or resolution must never be sent as its Python repr."""
    client, service = make_client()
    controller = EdaxEbsdController(client)

    controller.apply_map_parameters(
        EdaxEbsdMapParams(
            grid=EdaxGridType.SQUARE,
            mode=EdaxEbsdMode.NORMAL,
            resolution=EdaxEbsdResolution.CUSTOM,
        )
    )

    assert service.arguments_for(EdaxCommand.EBSD_SET_GRID) == ['"1"']
    assert service.arguments_for(EdaxCommand.EBSD_SET_MODE) == ['"0"']
    assert service.arguments_for(EdaxCommand.EBSD_SET_RESOLUTION) == ['"3"']


def test_folder_path_is_sent_as_text(make_client):
    """Paths reach EDAX as plain strings, spaces intact."""
    client, service = make_client()
    controller = EdaxEbsdController(client)

    controller.apply_map_parameters(
        EdaxEbsdMapParams(folder_path=Path("C:/EDAX Data/run 1"))
    )

    argument = service.arguments_for(EdaxCommand.EBSD_SET_FOLDERPATH)[0]
    assert "run 1" in argument


def test_map_parameters_reads_the_full_set_back(make_client):
    """The read-back path converts every payload into its typed field."""
    client, _ = make_client(
        payloads={
            EdaxCommand.EBSD_GET_FOLDERPATH: r"C:\EDAX Data",
            EdaxCommand.EBSD_GET_MODE: "0",
            EdaxCommand.EBSD_GET_RESOLUTION: "3",
            EdaxCommand.EBSD_GET_GRID: "1",
            EdaxCommand.EBSD_GET_SAVEHOUGHPEAKS: "False",
            EdaxCommand.EBSD_GET_SAVEPATTERNS: "True",
            EdaxCommand.EBSD_GET_SAVESPECTRA: "False",
            EdaxCommand.EBSD_GET_XSTART: "-10.0",
            EdaxCommand.EBSD_GET_YSTART: "-5.0",
            EdaxCommand.EBSD_GET_XSIZE: "25.0",
            EdaxCommand.EBSD_GET_YSIZE: "20.0",
            EdaxCommand.EBSD_GET_STEPSIZE: "0.5",
            EdaxCommand.EBSD_GET_CUSTOMSTEPSIZE: "0.5",
            EdaxCommand.EBSD_GET_EDSNUMCHAN: "1024",
            EdaxCommand.EBSD_GET_BYTESPERCHANNEL: "2",
        }
    )
    params = EdaxEbsdController(client).map_parameters()

    assert params.resolution is EdaxEbsdResolution.CUSTOM
    assert params.grid is EdaxGridType.SQUARE
    assert params.save_patterns is True
    assert params.save_hough_peaks is False
    assert params.x_start_um == -10.0
    assert params.step_size_um == 0.5
    assert params.eds_num_channels == 1024


# ----------------------------------------------------------------------
# Project and access configuration
# ----------------------------------------------------------------------
def test_project_without_slices_uses_the_short_command(make_client):
    """A 2D project has no slice geometry to send."""
    client, service = make_client()
    controller = EdaxEbsdController(client)

    controller.set_project_info(EdaxProjectInfo(guid="guid-1", name="run"))

    assert EdaxCommand.EBSD_SET_SYSTEM_PROJECTINFO.value in service.commands()
    assert EdaxCommand.EBSD_SET_SYSTEM_PROJECTINFO_EXT.value not in service.commands()


def test_project_with_slices_uses_the_extended_command(make_client):
    """3D collection needs the slice count and thickness EDAX stores."""
    client, service = make_client()
    controller = EdaxEbsdController(client)

    controller.set_project_info(
        EdaxProjectInfo(
            guid="guid-1", name="run", num_slices=10, slice_thickness_um=2.5
        )
    )

    assert service.arguments_for(EdaxCommand.EBSD_SET_SYSTEM_PROJECTINFO_EXT) == [
        '"guid-1","run","10","2.5"'
    ]


def test_access_type_is_sent_as_its_integer(make_client):
    """NoWait must arrive as "1", the value EDAX documents."""
    client, service = make_client()
    EdaxEbsdController(client).set_access_type(EdaxAccessType.NO_WAIT)

    assert service.arguments_for(EdaxCommand.EBSD_SET_SYSTEM_REMOTEACCESSTYPE) == [
        '"1"'
    ]


# ----------------------------------------------------------------------
# Status and duration
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload, expected",
    [
        ("Ready", EdaxMappingStatus.READY),
        ("MappingActive", EdaxMappingStatus.MAPPING_ACTIVE),
        ("mappingcomplete", EdaxMappingStatus.MAPPING_COMPLETE),
        ("Mapping_Complete", EdaxMappingStatus.MAPPING_COMPLETE),
        ("Setup Complete", EdaxMappingStatus.SETUP_COMPLETE),
    ],
)
def test_map_status_normalizes_edax_spelling(make_client, payload, expected):
    """EDAX varies case, spaces, and underscores between builds."""
    client, _ = make_client(payloads={EdaxCommand.EBSD_GET_MAP_STATUS: payload})
    assert EdaxEbsdController(client).map_status() is expected


def test_unrecognized_status_becomes_unknown(make_client):
    """An unfamiliar status must not raise mid-collection."""
    client, _ = make_client(payloads={EdaxCommand.EBSD_GET_MAP_STATUS: "SomeNewStatus"})
    assert EdaxEbsdController(client).map_status() is EdaxMappingStatus.UNKNOWN


def test_map_duration_converts_ticks_to_seconds(make_client):
    """The IPAPI reports .NET ticks of 100 ns each."""
    client, _ = make_client(
        payloads={EdaxCommand.EBSD_GET_MAP_DURATION: str(int(90 * TICKS_PER_SECOND))}
    )
    assert EdaxEbsdController(client).map_duration_s() == pytest.approx(90.0)


# ----------------------------------------------------------------------
# Camera slide motion
# ----------------------------------------------------------------------
def test_insert_camera_is_a_no_op_when_already_inserted(make_client, no_sleep):
    """An already-inserted camera must not be commanded to move again."""
    client, service = make_client(
        payloads={EdaxCommand.EBSD_GET_CAMERA_STATUS: "SlideIn"}
    )

    assert EdaxEbsdController(client).insert_camera(quiet=True) is True
    assert EdaxCommand.EBSD_INSERT_CAMERA.value not in service.commands()


def test_insert_camera_polls_until_the_slide_arrives(make_client, no_sleep):
    """The controller waits out the travel rather than returning early."""
    client, service = make_client(
        payloads={
            EdaxCommand.EBSD_GET_CAMERA_STATUS: [
                "SlideOut",
                "SlideMovingIn",
                "SlideMovingIn",
                "SlideIn",
            ]
        }
    )

    assert EdaxEbsdController(client).insert_camera(quiet=True, settle_s=0.0) is True
    assert EdaxCommand.EBSD_INSERT_CAMERA.value in service.commands()


def test_retract_camera_reissues_a_stalled_move(make_client, no_sleep):
    """A slide reporting the move watchdog is re-commanded, as EDAX expects."""
    client, service = make_client(
        payloads={
            EdaxCommand.EBSD_GET_CAMERA_STATUS: [
                "SlideIn",
                "SlideMoveWDog",
                "SlideOut",
            ]
        }
    )

    assert EdaxEbsdController(client).retract_camera(quiet=True, settle_s=0.0) is True
    retracts = [
        command
        for command in service.commands()
        if command == EdaxCommand.EBSD_RETRACT_CAMERA.value
    ]
    assert len(retracts) == 2


def test_camera_error_state_raises_rather_than_spinning(make_client, no_sleep):
    """A watchdog trip needs an operator, so the wait must fail fast."""
    client, _ = make_client(
        payloads={EdaxCommand.EBSD_GET_CAMERA_STATUS: ["SlideIn", "SlideWatchDog"]}
    )

    with pytest.raises(EdaxStateError, match="slidewatchdog"):
        EdaxEbsdController(client).retract_camera(quiet=True, settle_s=0.0)


def test_camera_move_timeout_raises(make_client, no_sleep):
    """A slide that never arrives must not block the workflow forever."""
    client, _ = make_client(
        payloads={EdaxCommand.EBSD_GET_CAMERA_STATUS: "SlideMovingIn"}
    )

    with pytest.raises(EdaxTimeoutError):
        EdaxEbsdController(client).insert_camera(
            quiet=True, settle_s=0.0, timeout_s=0.05, poll_interval_s=0.0
        )


def test_unrecognized_camera_status_becomes_unknown(make_client):
    """An unfamiliar slide status must not raise."""
    client, _ = make_client(
        payloads={EdaxCommand.EBSD_GET_CAMERA_STATUS: "SlideSomethingNew"}
    )
    assert EdaxEbsdController(client).camera_status() is EdaxCameraStatus.UNKNOWN


def test_slide_positions_reads_all_three_values(make_client):
    """Travel limits and the current position come from three commands."""
    client, _ = make_client(
        payloads={
            EdaxCommand.EBSD_GET_SLIDE_POSITION: "12.5",
            EdaxCommand.EBSD_GET_SLIDE_POSITION_INSERTED: "5.0",
            EdaxCommand.EBSD_GET_SLIDE_POSITION_RETRACTED: "80.0",
        }
    )
    positions = EdaxEbsdController(client).slide_positions()

    assert positions.current_mm == 12.5
    assert positions.inserted_mm == 5.0
    assert positions.retracted_mm == 80.0


# ----------------------------------------------------------------------
# Collection
# ----------------------------------------------------------------------
def test_collection_start_passes_the_tag(make_client):
    """Each map needs a unique database tag."""
    client, service = make_client()
    EdaxEbsdController(client).collection_start("Slice_0007")

    assert service.arguments_for(EdaxCommand.EBSD_COLLECTION_START) == ['"Slice_0007"']


def test_wait_for_map_complete_returns_on_terminal_status(make_client, no_sleep):
    """Polling stops as soon as EDAX reports a terminal status."""
    client, _ = make_client(
        payloads={
            EdaxCommand.EBSD_GET_MAP_STATUS: [
                "MappingActive",
                "MappingActive",
                "MappingComplete",
            ]
        }
    )
    status = EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=5.0, poll_interval_s=0.0
    )

    assert status is EdaxMappingStatus.MAPPING_COMPLETE


def test_wait_for_map_complete_honors_the_completion_event(make_client, no_sleep):
    """Completion may be signalled by an event instead of a status change.

    The status query keeps reporting an active map, so the loop can only
    terminate by noticing the event that arrived alongside a status response.
    """
    client, service = make_client(
        payloads={EdaxCommand.EBSD_GET_MAP_STATUS: "MappingActive"}
    )
    service.push_event(EdaxEvent.EBSD_COLLECTION_COMPLETE, "Mapping Complete")

    status = EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=5.0, poll_interval_s=0.0
    )
    assert status is EdaxMappingStatus.MAPPING_COMPLETE


def test_wait_for_map_complete_raises_on_error_status(make_client, no_sleep):
    """A failed map must raise rather than be reported as finished."""
    client, _ = make_client(
        payloads={EdaxCommand.EBSD_GET_MAP_STATUS: ["MappingActive", "MappingError"]}
    )

    with pytest.raises(EdaxStateError, match="mappingerror"):
        EdaxEbsdController(client).wait_for_map_complete(
            timeout_s=5.0, poll_interval_s=0.0
        )


def test_wait_for_map_complete_times_out(make_client, no_sleep):
    """A map that never finishes must not hang the workflow."""
    client, _ = make_client(payloads={EdaxCommand.EBSD_GET_MAP_STATUS: "MappingActive"})

    with pytest.raises(EdaxTimeoutError):
        EdaxEbsdController(client).wait_for_map_complete(
            timeout_s=0.05, poll_interval_s=0.0
        )


def test_progress_callback_receives_status_and_elapsed_time(make_client, no_sleep):
    """Callers log progress through the callback rather than by polling."""
    client, _ = make_client(
        payloads={EdaxCommand.EBSD_GET_MAP_STATUS: ["MappingActive", "MappingComplete"]}
    )
    seen = []

    EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=5.0,
        poll_interval_s=0.0,
        progress_fn=lambda status, elapsed: seen.append((status, elapsed)),
    )

    assert [status for status, _ in seen] == [
        EdaxMappingStatus.MAPPING_ACTIVE,
        EdaxMappingStatus.MAPPING_COMPLETE,
    ]
    assert all(elapsed >= 0.0 for _, elapsed in seen)


# ----------------------------------------------------------------------
# Measurements and capture
# ----------------------------------------------------------------------
def test_camera_saturation_is_returned_as_a_fraction(make_client):
    """Saturation is documented as a value from 0.0 to 1.0."""
    client, _ = make_client(payloads={EdaxCommand.EBSD_GET_CAMERA_SATURATION: "0.62"})
    assert EdaxEbsdController(client).camera_saturation() == pytest.approx(0.62)


def test_average_ci_is_returned_as_a_float(make_client):
    """The average confidence index describes the map just collected."""
    client, _ = make_client(payloads={EdaxCommand.EBSD_GET_MAP_AVG_CI: "0.85"})
    assert EdaxEbsdController(client).average_ci() == pytest.approx(0.85)


def test_snapshot_returns_one_value_per_pixel(make_client):
    """Captures arrive as a comma-delimited list of unsigned integers."""
    client, _ = make_client(
        payloads={EdaxCommand.EBSD_CAMERA_SNAPSHOT: "100,200,300,400"}
    )
    assert EdaxEbsdController(client).snapshot() == (100, 200, 300, 400)


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({}, EdaxCommand.EBSD_CAMERA_CAPTURE_BACKGROUND),
        ({"auto": True}, EdaxCommand.EBSD_CAMERA_CAPTURE_BACKGROUND_AUTO),
        ({"smart": True}, EdaxCommand.EBSD_CAMERA_CAPTURE_BACKGROUND_SMART),
        (
            {"auto": True, "smart": True},
            EdaxCommand.EBSD_CAMERA_CAPTURE_BACKGROUND_SMART,
        ),
    ],
)
def test_background_capture_selects_the_right_command(make_client, kwargs, expected):
    """Smart capture takes precedence over auto, which takes precedence over plain."""
    client, service = make_client(payloads={expected: "1,2,3"})
    EdaxEbsdController(client).capture_background(**kwargs)

    assert expected.value in service.commands()


# ----------------------------------------------------------------------
# Camera parameters
# ----------------------------------------------------------------------
def _capability_payloads(supported: bool):
    """Return payloads answering every capability query with one value."""
    literal = "True" if supported else "False"
    return {
        EdaxCommand.CAMERA_ISSUPPORT_BINNINGCUMULATIVE: literal,
        EdaxCommand.CAMERA_ISSUPPORT_BLACKREFERENCE: literal,
        EdaxCommand.CAMERA_ISSUPPORT_DOUBLESCANRATE: literal,
        EdaxCommand.CAMERA_ISSUPPORT_DUALTAP: literal,
        EdaxCommand.CAMERA_ISSUPPORT_GAIN: literal,
        EdaxCommand.CAMERA_ISSUPPORT_HIGHGAIN: literal,
        EdaxCommand.CAMERA_ISSUPPORT_REDUCEDBITDEPTH: literal,
    }


def test_camera_parameters_skip_unsupported_features(make_client):
    """Sending an unsupported parameter would be rejected by the IPAPI."""
    client, service = make_client(payloads=_capability_payloads(False))
    controller = EdaxEbsdController(client)

    skipped = controller.apply_camera_parameters(
        EdaxCameraParams(exposure_ms=12.0, gain=3.0, dual_tap=True)
    )

    assert set(skipped) == {"gain", "dual_tap"}
    assert EdaxCommand.CAMERA_SET_EXPOSURE.value in service.commands()
    assert EdaxCommand.CAMERA_SET_GAIN.value not in service.commands()
    assert EdaxCommand.CAMERA_SET_DUALTAP.value not in service.commands()


def test_camera_parameters_apply_when_supported(make_client):
    """A supported parameter is sent with its value."""
    client, service = make_client(payloads=_capability_payloads(True))
    controller = EdaxEbsdController(client)

    skipped = controller.apply_camera_parameters(EdaxCameraParams(gain=3.0))

    assert skipped == ()
    assert service.arguments_for(EdaxCommand.CAMERA_SET_GAIN) == ['"3.0"']


def test_capability_check_can_be_disabled(make_client):
    """Skipping the capability query avoids seven extra round trips."""
    client, service = make_client()
    controller = EdaxEbsdController(client)

    controller.apply_camera_parameters(
        EdaxCameraParams(gain=3.0), skip_unsupported=False
    )

    assert EdaxCommand.CAMERA_ISSUPPORT_GAIN.value not in service.commands()
    assert EdaxCommand.CAMERA_SET_GAIN.value in service.commands()


def test_camera_limits_pair_minimum_with_maximum(make_client):
    """Limits come from separate min and max commands per parameter."""
    client, _ = make_client(
        payloads={
            EdaxCommand.CAMERA_GET_EXPOSURE_MIN: "1.0",
            EdaxCommand.CAMERA_GET_EXPOSURE_MAX: "100.0",
            EdaxCommand.CAMERA_GET_GAIN_MIN: "0.0",
            EdaxCommand.CAMERA_GET_GAIN_MAX: "10.0",
            EdaxCommand.CAMERA_GET_FRAMEAVGBACKGROUND_MIN: "1",
            EdaxCommand.CAMERA_GET_FRAMEAVGBACKGROUND_MAX: "64",
            EdaxCommand.CAMERA_GET_FRAMEAVGSCAN_MIN: "1",
            EdaxCommand.CAMERA_GET_FRAMEAVGSCAN_MAX: "16",
            EdaxCommand.CAMERA_GET_FRAMEAVGSNAPSHOT_MIN: "1",
            EdaxCommand.CAMERA_GET_FRAMEAVGSNAPSHOT_MAX: "32",
        }
    )
    limits = EdaxEbsdController(client).camera_limits()

    assert limits.exposure_ms.min == 1.0
    assert limits.exposure_ms.max == 100.0
    assert limits.frame_avg_scan.max == 16
    assert limits.exposure_ms.contains(50.0) is True
    assert limits.exposure_ms.contains(500.0) is False


def test_camera_info_includes_the_binning_modes(make_client):
    """Binning names arrive as a comma-delimited list."""
    client, _ = make_client(
        payloads={
            EdaxCommand.CAMERA_GET_FRAME_WIDTH: "480",
            EdaxCommand.CAMERA_GET_FRAME_HEIGHT: "480",
            EdaxCommand.CAMERA_GET_FRAME_BITDEPTH: "8",
            EdaxCommand.CAMERA_GET_FRAME_RATE: "1400.5",
            EdaxCommand.CAMERA_GET_BINNING_NAMES: "1x1,2x2,4x4",
        }
    )
    info = EdaxEbsdController(client).camera_info()

    assert info.width_px == 480
    assert info.frame_rate_hz == pytest.approx(1400.5)
    assert info.binning_names == ("1x1", "2x2", "4x4")


def test_high_gain_has_no_getter(make_client):
    """The IPAPI exposes no read for high gain, so it reads back as None."""
    client, _ = make_client(
        payloads={
            EdaxCommand.CAMERA_GET_BINNING: "1x1",
            EdaxCommand.CAMERA_GET_BINNINGCUMULATIVE: "False",
            EdaxCommand.CAMERA_GET_DOUBLESCANRATE: "False",
            EdaxCommand.CAMERA_GET_DUALTAP: "True",
            EdaxCommand.CAMERA_GET_EXPOSURE: "12.0",
            EdaxCommand.CAMERA_GET_FRAMEAVGBACKGROUND: "8",
            EdaxCommand.CAMERA_GET_FRAMEAVGSCAN: "1",
            EdaxCommand.CAMERA_GET_FRAMEAVGSNAPSHOT: "4",
            EdaxCommand.CAMERA_GET_GAIN: "2.5",
            EdaxCommand.CAMERA_GET_IMAGEPROCESSINGMODEINT: "3",
            EdaxCommand.CAMERA_GET_REDUCEDBITDEPTH: "False",
        }
    )
    params = EdaxEbsdController(client).camera_parameters()

    assert params.high_gain is None
    assert params.binning == "1x1"
    assert params.exposure_ms == 12.0
    assert params.dual_tap is True
