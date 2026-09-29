#!/usr/bin/python3
"""
Unit tests for the EDAX preflight and per-slice EBSD map sequences.

These pin down the behavior carried over from the proven hardware
implementation that lived in ``laser.py``: the order of operations, which
settings reach the wire, the duration and timeout arithmetic, and the checks
that catch a map EDAX did not actually collect.
"""

# Default python modules
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import NamedTuple

# Third-party modules
import pytest

# Local scripts
from pytribeam.external_oem.edax import mapping
from pytribeam.external_oem.edax.base import TICKS_PER_SECOND
from pytribeam.external_oem.edax.ebsd import EdaxEbsdController
from pytribeam.external_oem.edax.errors import EdaxStateError
from pytribeam.external_oem.edax.types import (
    EdaxCommand,
    EdaxEbsdMapParams,
    EdaxEbsdResolution,
    EdaxGridType,
    EdaxMappingStatus,
    EdaxProjectInfo,
)

pytestmark = pytest.mark.detached


class ScanBox(NamedTuple):
    """Stand-in for pytribeam.types.EBSDScanBox, which needs AutoScript."""

    x_start_um: float
    y_start_um: float
    x_size_um: float
    y_size_um: float
    step_size_um: float


SCAN_BOX = ScanBox(
    x_start_um=-10.0, y_start_um=-5.0, x_size_um=25.0, y_size_um=20.0, step_size_um=0.5
)


def _plan(**overrides) -> mapping.EbsdMapPlan:
    """Return a plan with timing short enough for tests."""
    values = dict(
        tag="Slice_0007",
        params=mapping.ebsd_map_params(scan_box=SCAN_BOX, grid_type=1),
        start_delay_s=0.0,
        poll_interval_s=0.0,
        status_timeout_s=0.5,
        timeout_scalar=3.0,
        min_timeout_s=5.0,
        settle_s=0.0,
    )
    values.update(overrides)
    return mapping.EbsdMapPlan(**values)


def _service_payloads(**overrides):
    """Payloads for a map that completes, with the camera already retracted."""
    payloads = {
        EdaxCommand.EBSD_GET_MAP_DURATION: "0",
        EdaxCommand.EBSD_GET_MAP_STATUS: ["MappingActive", "MappingComplete"],
        EdaxCommand.EBSD_GET_MAP_AVG_CI: "0.85",
        EdaxCommand.EBSD_GET_CAMERA_STATUS: "SlideOut",
    }
    payloads.update(overrides)
    return payloads


# ----------------------------------------------------------------------
# Parameter translation
# ----------------------------------------------------------------------
def test_slice_tag_is_zero_padded():
    """Tags sort correctly in the EDAX database up to 9999 slices."""
    assert mapping.slice_tag(7) == "Slice_0007"
    assert mapping.slice_tag(1234) == "Slice_1234"


def test_scan_box_forces_custom_resolution():
    """EDAX ignores step size unless the resolution is custom."""
    params = mapping.ebsd_map_params(scan_box=SCAN_BOX)

    assert params.resolution is EdaxEbsdResolution.CUSTOM
    assert params.step_size_um == 0.5
    assert params.custom_step_size_um == 0.5
    assert (params.x_start_um, params.y_start_um) == (-10.0, -5.0)
    assert (params.x_size_um, params.y_size_um) == (25.0, 20.0)


def test_without_scan_box_geometry_is_left_alone():
    """A step with no scan box must not overwrite the application's area."""
    params = mapping.ebsd_map_params(grid_type=0, save_patterns=True)

    assert params.resolution is None
    assert params.x_size_um is None
    assert params.grid is EdaxGridType.HEXAGONAL
    assert params.save_patterns is True


def test_concurrent_eds_is_stated_in_both_directions():
    """The setting persists in EDAX, so an EBSD-only step must clear it.

    Otherwise an EBSD-only step following an EBSD+EDS step would collect
    spectra with the EDS detector retracted.
    """
    assert mapping.ebsd_map_params(enable_eds=True).save_spectra is True
    assert mapping.ebsd_map_params(enable_eds=False).save_spectra is False


def test_grid_accepts_the_pytribeam_int_enum_value():
    """tbt.EBSDGridType is an IntEnum with the same values as EDAX's grid."""
    assert mapping.ebsd_map_params(grid_type=1).grid is EdaxGridType.SQUARE
    assert mapping.ebsd_map_params(grid_type=None).grid is None


# ----------------------------------------------------------------------
# Preflight
# ----------------------------------------------------------------------
def test_preflight_runs_access_folder_then_project(make_client):
    """NoWait access requires the folder to be set over the IPAPI, in order."""
    client, service = make_client()

    mapping.run_ebsd_preflight(
        EdaxEbsdController(client),
        folder=Path("D:/EDAX Data/exp1"),
        project=EdaxProjectInfo(
            guid="guid-1", name="exp1", num_slices=200, slice_thickness_um=1.5
        ),
    )

    sent = service.commands()[1:]  # skip the unlock
    assert sent == [
        EdaxCommand.EBSD_SET_SYSTEM_REMOTEACCESSTYPE.value,
        EdaxCommand.EBSD_SET_FOLDERPATH.value,
        EdaxCommand.EBSD_SET_SYSTEM_PROJECTINFO_EXT.value,
    ]
    assert service.arguments_for(EdaxCommand.EBSD_SET_SYSTEM_REMOTEACCESSTYPE) == [
        '"1"'
    ]
    assert "exp1" in service.arguments_for(EdaxCommand.EBSD_SET_FOLDERPATH)[0]
    assert service.arguments_for(EdaxCommand.EBSD_SET_SYSTEM_PROJECTINFO_EXT) == [
        '"guid-1","exp1","200","1.5"'
    ]


# ----------------------------------------------------------------------
# Map sequence
# ----------------------------------------------------------------------
def test_map_sequence_order(make_client, no_sleep):
    """Configure, measure, predict, start, wait, then read the CI.

    Saturation must be measured after the scan parameters are applied and
    before collection starts, while the camera is idle.
    """
    client, service = make_client(payloads=_service_payloads())
    events = []
    original_send = service.sendall

    def spy(data):
        events.append(data.decode("ascii").split(" ", 1)[0])
        original_send(data)

    service.sendall = spy

    mapping.run_ebsd_map(
        EdaxEbsdController(client),
        _plan(),
        measure_saturation=lambda: events.append("<measure saturation>") or 0.6,
        motion_guard=nullcontext,
        quiet=True,
    )

    first_start = events.index(EdaxCommand.EBSD_COLLECTION_START.value)
    assert events.index(EdaxCommand.EBSD_SET_XSIZE.value) < events.index(
        "<measure saturation>"
    )
    assert events.index("<measure saturation>") < first_start
    assert events.index(EdaxCommand.EBSD_GET_MAP_DURATION.value) < first_start
    assert events.index(EdaxCommand.EBSD_GET_MAP_STATUS.value) > first_start
    assert events.index(EdaxCommand.EBSD_GET_MAP_AVG_CI.value) > events.index(
        EdaxCommand.EBSD_GET_MAP_STATUS.value
    )


def test_map_starts_under_the_plan_tag(make_client, no_sleep):
    """The tag identifies the slice's map in the EDAX database."""
    client, service = make_client(payloads=_service_payloads())

    mapping.run_ebsd_map(
        EdaxEbsdController(client), _plan(), motion_guard=nullcontext, quiet=True
    )

    assert service.arguments_for(EdaxCommand.EBSD_COLLECTION_START) == ['"Slice_0007"']


def test_metrics_reported_as_measured_and_returned(make_client, no_sleep):
    """Each metric reaches the callback in order and lands in the result."""
    client, _ = make_client(payloads=_service_payloads())
    seen = []

    result = mapping.run_ebsd_map(
        EdaxEbsdController(client),
        _plan(),
        measure_saturation=lambda: 0.6,
        on_metric=lambda name, value: seen.append((name, value)),
        motion_guard=nullcontext,
        quiet=True,
    )

    assert seen == [(mapping.CAMERA_SATURATION, 0.6), (mapping.AVERAGE_CI, 0.85)]
    assert result.metrics == {mapping.CAMERA_SATURATION: 0.6, mapping.AVERAGE_CI: 0.85}
    assert result.status is EdaxMappingStatus.MAPPING_COMPLETE
    assert result.tag == "Slice_0007"


def test_saturation_is_reported_even_when_the_map_fails(make_client, no_sleep):
    """The saturation reading is the first clue when a collection fails."""
    client, _ = make_client(
        payloads=_service_payloads(
            **{EdaxCommand.EBSD_GET_MAP_STATUS: ["MappingActive", "MappingError"]}
        )
    )
    seen = []

    with pytest.raises(EdaxStateError):
        mapping.run_ebsd_map(
            EdaxEbsdController(client),
            _plan(),
            measure_saturation=lambda: 0.97,
            on_metric=lambda name, value: seen.append((name, value)),
            motion_guard=nullcontext,
            quiet=True,
        )

    assert seen == [(mapping.CAMERA_SATURATION, 0.97)]


def test_saturation_is_optional(make_client, no_sleep):
    """Without a microscope callable, only the CI is measured."""
    client, _ = make_client(payloads=_service_payloads())

    result = mapping.run_ebsd_map(
        EdaxEbsdController(client), _plan(), motion_guard=nullcontext, quiet=True
    )

    assert mapping.CAMERA_SATURATION not in result.metrics


def test_camera_is_retracted_after_the_map(make_client, no_sleep):
    """The native path retracts over the IPAPI once collection finishes."""
    client, service = make_client(
        payloads=_service_payloads(
            **{EdaxCommand.EBSD_GET_CAMERA_STATUS: ["SlideIn", "SlideOut"]}
        )
    )

    mapping.run_ebsd_map(
        EdaxEbsdController(client), _plan(), motion_guard=nullcontext, quiet=True
    )

    assert EdaxCommand.EBSD_RETRACT_CAMERA.value in service.commands()


def test_retraction_can_be_skipped(make_client, no_sleep):
    """Callers that manage the camera themselves can opt out."""
    client, service = make_client(
        payloads=_service_payloads(**{EdaxCommand.EBSD_GET_CAMERA_STATUS: "SlideIn"})
    )

    mapping.run_ebsd_map(
        EdaxEbsdController(client),
        _plan(retract_after=False),
        motion_guard=nullcontext,
        quiet=True,
    )

    assert EdaxCommand.EBSD_GET_CAMERA_STATUS.value not in service.commands()


# ----------------------------------------------------------------------
# Failure detection
# ----------------------------------------------------------------------
def test_a_map_finishing_early_is_rejected(make_client, no_sleep):
    """A map shorter than EDAX predicted was not really collected."""
    client, _ = make_client(
        payloads=_service_payloads(
            **{EdaxCommand.EBSD_GET_MAP_DURATION: str(int(60 * TICKS_PER_SECOND))}
        )
    )

    with pytest.raises(EdaxStateError, match="unexpectedly quickly"):
        mapping.run_ebsd_map(
            EdaxEbsdController(client), _plan(), motion_guard=nullcontext, quiet=True
        )


@pytest.mark.parametrize("status", ["MappingAborted", "MappingStopped"])
def test_an_interrupted_map_is_rejected(make_client, no_sleep, status):
    """Aborted and stopped maps end the wait but leave partial data."""
    client, _ = make_client(
        payloads=_service_payloads(
            **{EdaxCommand.EBSD_GET_MAP_STATUS: ["MappingActive", status]}
        )
    )

    with pytest.raises(EdaxStateError, match=status.lower()):
        mapping.run_ebsd_map(
            EdaxEbsdController(client), _plan(), motion_guard=nullcontext, quiet=True
        )


def test_interrupted_map_does_not_read_the_ci(make_client, no_sleep):
    """A CI from a partial map would be misleading in the log."""
    client, service = make_client(
        payloads=_service_payloads(
            **{EdaxCommand.EBSD_GET_MAP_STATUS: ["MappingActive", "MappingAborted"]}
        )
    )

    with pytest.raises(EdaxStateError):
        mapping.run_ebsd_map(
            EdaxEbsdController(client), _plan(), motion_guard=nullcontext, quiet=True
        )

    assert EdaxCommand.EBSD_GET_MAP_AVG_CI.value not in service.commands()


def test_result_reports_the_edax_prediction(make_client, no_sleep):
    """The result carries EDAX's own prediction, without the start delay."""
    client, _ = make_client(payloads=_service_payloads())

    result = mapping.run_ebsd_map(
        EdaxEbsdController(client),
        _plan(start_delay_s=0.0),
        motion_guard=nullcontext,
        quiet=True,
    )

    assert result.predicted_duration_s == pytest.approx(0.0)


def test_map_finishing_within_the_start_delay_is_accepted(make_client):
    """A short map that completes during the start delay is not "too quick".

    Completion can only be observed after the delay, so the observed duration
    is the delay itself. The check used to compare that against the prediction
    *plus* the delay, rejecting every map shorter than the delay, which is
    every small test map. Real sleeps here, since the timing is the point.
    """
    client, _ = make_client(
        payloads=_service_payloads(
            **{EdaxCommand.EBSD_GET_MAP_DURATION: str(int(0.1 * TICKS_PER_SECOND))}
        )
    )

    result = mapping.run_ebsd_map(
        EdaxEbsdController(client),
        _plan(start_delay_s=0.2),
        motion_guard=nullcontext,
        quiet=True,
    )

    assert result.predicted_duration_s == pytest.approx(0.1)
    assert result.duration_s >= 0.2


def test_a_map_that_never_started_is_still_rejected(make_client):
    """The guard still catches the failure it exists for.

    EDAX reporting Ready straight after the start command means the map never
    ran. The start delay is far shorter than a real prediction, so the
    observed duration falls short of it.
    """
    client, _ = make_client(
        payloads=_service_payloads(
            **{
                EdaxCommand.EBSD_GET_MAP_DURATION: str(int(30 * TICKS_PER_SECOND)),
                EdaxCommand.EBSD_GET_MAP_STATUS: "Ready",
            }
        )
    )

    with pytest.raises(EdaxStateError, match="predicted 30.0 seconds"):
        mapping.run_ebsd_map(
            EdaxEbsdController(client),
            _plan(start_delay_s=0.2),
            motion_guard=nullcontext,
            quiet=True,
        )


def test_timeout_budget_scales_with_the_expected_duration(make_client, no_sleep):
    """The wait is bounded by timeout_scalar times the expected duration."""
    client, _ = make_client(payloads=_service_payloads())
    controller = EdaxEbsdController(client)
    budgets = []
    original = controller.wait_for_map_complete

    def spy(timeout_s, **kwargs):
        budgets.append(timeout_s)
        return original(timeout_s=5.0, **kwargs)

    controller.wait_for_map_complete = spy
    client_payload = str(int(20 * TICKS_PER_SECOND))
    client._socket.payloads[EdaxCommand.EBSD_GET_MAP_DURATION.value] = client_payload

    with pytest.raises(EdaxStateError):  # finishes early; the budget is the point
        mapping.run_ebsd_map(
            controller, _plan(timeout_scalar=3.0), motion_guard=nullcontext, quiet=True
        )

    # (predicted 20 s + start delay 0 s) x 3
    assert budgets[0] == pytest.approx(60.0, abs=0.5)


def test_default_params_leave_every_setting_alone(make_client, no_sleep):
    """An empty parameter set sends no configuration commands at all."""
    client, service = make_client(payloads=_service_payloads())

    mapping.run_ebsd_map(
        EdaxEbsdController(client),
        _plan(params=EdaxEbsdMapParams()),
        motion_guard=nullcontext,
        quiet=True,
    )

    assert not [
        name for name in service.commands() if name.startswith("set_ebsd_params")
    ]


# ----------------------------------------------------------------------
# Observing camera motion
# ----------------------------------------------------------------------
# Every detector insertion and retraction must be visible on the live chamber
# CCD, so the operator can stop a collision. This module cannot reach the
# microscope, so the caller supplies the view as a motion guard.
class GuardRecorder:
    """A motion guard that records when it opens and closes."""

    def __init__(self, service):
        self.service = service
        self.opened_after = None  # commands sent before the guard opened
        self.closed_after = None  # commands sent before the guard closed

    @contextmanager
    def __call__(self):
        self.opened_after = len(self.service.commands())
        try:
            yield
        finally:
            self.closed_after = len(self.service.commands())

    def commands_inside(self):
        return self.service.commands()[self.opened_after : self.closed_after]


def test_camera_motion_refused_without_a_guard(make_client):
    """Forgetting the CCD view must fail loudly, not move the camera blind."""
    client, service = make_client(payloads=_service_payloads())
    sent_before = len(service.commands())

    with pytest.raises(ValueError, match="motion guard"):
        mapping.run_ebsd_map(EdaxEbsdController(client), _plan(), quiet=True)

    assert len(service.commands()) == sent_before, "nothing may be sent"


def test_no_guard_needed_when_the_camera_stays_put(make_client, no_sleep):
    """A plan that does not retract moves nothing, so needs no guard."""
    client, _ = make_client(payloads=_service_payloads())

    mapping.run_ebsd_map(
        EdaxEbsdController(client), _plan(retract_after=False), quiet=True
    )


def test_guard_wraps_the_retraction_and_nothing_else(make_client, no_sleep):
    """The CCD is live for the motion only, not during the map.

    Chamber CCD illumination reaches the EBSD detector, so it must be off while
    patterns are collected.
    """
    client, service = make_client(
        payloads=_service_payloads(
            **{EdaxCommand.EBSD_GET_CAMERA_STATUS: ["SlideIn", "SlideOut"]}
        )
    )
    guard = GuardRecorder(service)

    mapping.run_ebsd_map(
        EdaxEbsdController(client), _plan(), motion_guard=guard, quiet=True
    )

    inside = guard.commands_inside()
    assert EdaxCommand.EBSD_RETRACT_CAMERA.value in inside
    assert EdaxCommand.EBSD_COLLECTION_START.value not in inside
    assert EdaxCommand.EBSD_GET_MAP_STATUS.value not in inside
    before_guard = service.commands()[: guard.opened_after]
    assert EdaxCommand.EBSD_RETRACT_CAMERA.value not in before_guard


def test_guard_closes_when_the_retraction_fails(make_client, no_sleep):
    """A failed retraction still pauses the CCD before the error propagates."""
    client, service = make_client(
        payloads=_service_payloads(
            **{EdaxCommand.EBSD_GET_CAMERA_STATUS: ["SlideIn", "SlideWatchDog"]}
        )
    )
    guard = GuardRecorder(service)

    with pytest.raises(EdaxStateError, match="slidewatchdog"):
        mapping.run_ebsd_map(
            EdaxEbsdController(client), _plan(), motion_guard=guard, quiet=True
        )

    assert guard.opened_after is not None
    assert guard.closed_after is not None


def test_guard_is_not_opened_when_the_map_fails(make_client, no_sleep):
    """No retraction is attempted after a failed map, so no view is shown."""
    client, service = make_client(
        payloads=_service_payloads(
            **{EdaxCommand.EBSD_GET_MAP_STATUS: ["MappingActive", "MappingError"]}
        )
    )
    guard = GuardRecorder(service)

    with pytest.raises(EdaxStateError):
        mapping.run_ebsd_map(
            EdaxEbsdController(client), _plan(), motion_guard=guard, quiet=True
        )

    assert guard.opened_after is None


# ----------------------------------------------------------------------
# EDS
# ----------------------------------------------------------------------
from pytribeam.external_oem.edax.eds import EdaxEdsController  # noqa: E402
from pytribeam.external_oem.edax.errors import (  # noqa: E402
    EdaxResponseError,
    EdaxTimeoutError,
)
from pytribeam.external_oem.edax.types import (  # noqa: E402
    EdaxEdsMapParams,
    EdaxEdsResolution,
    EdaxEvent,
)


def _eds_payloads(**overrides):
    """Payloads for an EDS map that completes, with the detector ready."""
    payloads = {
        EdaxCommand.EDS_GET_SYSTEM_ISAPPSTARTED: "True",
        EdaxCommand.EDS_GET_SYSTEM_DETECTOR_STATUS: "Ready",
        EdaxCommand.EDS_GET_MAP_DURATION: "0",
        EdaxCommand.EDS_GET_MAP_STATUS: ["MappingActive", "MappingComplete"],
        # The map pyTriBeam predicts from: 64 x 50, one frame, no dwell.
        EdaxCommand.EDS_GET_NUMPOINTS: "64",
        EdaxCommand.EDS_GET_NUMFRAMES: "1",
        EdaxCommand.EDS_GET_PRESETDWELL: "0",
    }
    payloads.update(overrides)
    return payloads


def _eds_plan(**overrides) -> mapping.EdsMapPlan:
    values = dict(
        tag="Slice_0007_EDS",
        start_delay_s=0.0,
        poll_interval_s=0.0,
        status_timeout_s=0.5,
        min_timeout_s=5.0,
        max_duration_s=5.0,
        start_timeout_s=0.3,
    )
    values.update(overrides)
    return mapping.EdsMapPlan(**values)


PROJECT = EdaxProjectInfo(
    guid="guid-1", name="exp1", num_slices=200, slice_thickness_um=1.5
)


def test_eds_tag_differs_from_the_ebsd_tag():
    """EBSD and EDS maps of one slice share a folder, where tags must differ."""
    assert mapping.eds_slice_tag(7) == "Slice_0007_EDS"
    assert mapping.eds_slice_tag(7) != mapping.slice_tag(7)


def test_eds_preflight_sets_headless_access_then_folder_then_project(make_client):
    """NoWait needs the EDS folder sent before mapping, or the path isn't set.

    This is the setup LaserControl never performed, which left EDS maps saving
    wherever APEX pointed, or nowhere once EBSD had set NoWait.
    """
    client, service = make_client(payloads=_eds_payloads())

    mapping.run_eds_preflight(
        EdaxEdsController(client), folder=Path("D:/EDAX Data/exp1"), project=PROJECT
    )

    sets = [name for name in service.commands() if name.startswith("set_")]
    assert sets == [
        EdaxCommand.EDS_SET_SYSTEM_REMOTEACCESSTYPE.value,
        EdaxCommand.EDS_SET_FOLDERPATH.value,
        EdaxCommand.EDS_SET_SYSTEM_PROJECTINFO_EXT.value,
    ]
    assert service.arguments_for(EdaxCommand.EDS_SET_SYSTEM_REMOTEACCESSTYPE) == ['"1"']
    assert "exp1" in service.arguments_for(EdaxCommand.EDS_SET_FOLDERPATH)[0]
    assert service.arguments_for(EdaxCommand.EDS_SET_SYSTEM_PROJECTINFO_EXT) == [
        '"guid-1","exp1","200","1.5"'
    ]


def test_eds_preflight_uses_the_eds_commands_not_the_ebsd_ones(make_client):
    """EDAX keeps EDS and EBSD settings apart; the EBSD folder is not enough."""
    client, service = make_client(payloads=_eds_payloads())

    mapping.run_eds_preflight(
        EdaxEdsController(client), folder=Path("D:/x"), project=PROJECT
    )

    assert not [name for name in service.commands() if name.endswith("_ebsd")]
    assert EdaxCommand.EBSD_SET_FOLDERPATH.value not in service.commands()


def test_eds_preflight_refuses_when_apex_is_not_running(make_client):
    """Nothing is configured against an application that is not there."""
    client, service = make_client(
        payloads=_eds_payloads(**{EdaxCommand.EDS_GET_SYSTEM_ISAPPSTARTED: "False"})
    )

    with pytest.raises(EdaxStateError, match="not running"):
        mapping.run_eds_preflight(
            EdaxEdsController(client), folder=Path("D:/x"), project=PROJECT
        )
    assert not [name for name in service.commands() if name.startswith("set_")]


def test_eds_preflight_reports_a_detector_that_is_not_ready(make_client):
    """Fail at the start of an experiment, not hours in at the first EDS step."""
    client, _ = make_client(
        payloads=_eds_payloads(
            **{EdaxCommand.EDS_GET_SYSTEM_DETECTOR_STATUS: "NotReady"}
        )
    )

    with pytest.raises(EdaxStateError, match="cooled"):
        mapping.run_eds_preflight(
            EdaxEdsController(client), folder=Path("D:/x"), project=PROJECT
        )


def test_eds_map_collects_under_its_tag(make_client, no_sleep):
    """A completed map reports its tag, status, and timing; no metrics."""
    client, service = make_client(payloads=_eds_payloads())

    result = mapping.run_eds_map(EdaxEdsController(client), _eds_plan(), quiet=True)

    assert service.arguments_for(EdaxCommand.EDS_COLLECTION_START) == [
        '"Slice_0007_EDS"'
    ]
    assert result.status is EdaxMappingStatus.MAPPING_COMPLETE
    assert result.tag == "Slice_0007_EDS"
    assert result.metrics == {}


def test_eds_map_leaves_apex_settings_alone_by_default(make_client, no_sleep):
    """With no parameters given, APEX's own EDS map settings are used, as
    LaserControl collection did."""
    client, service = make_client(payloads=_eds_payloads())

    mapping.run_eds_map(EdaxEdsController(client), _eds_plan(), quiet=True)

    assert not [n for n in service.commands() if n.startswith("set_map_params")]


def test_eds_map_applies_the_parameters_it_is_given(make_client, no_sleep):
    """Parameters set on the plan reach APEX before collection starts."""
    client, service = make_client(payloads=_eds_payloads())

    mapping.run_eds_map(
        EdaxEdsController(client),
        _eds_plan(
            params=EdaxEdsMapParams(
                resolution=EdaxEdsResolution.PRESET_512X400, num_frames=4
            )
        ),
        quiet=True,
    )

    sent = service.commands()
    assert service.arguments_for(EdaxCommand.EDS_SET_NUMPOINTS) == ['"512"']
    assert sent.index(EdaxCommand.EDS_SET_NUMFRAMES.value) < sent.index(
        EdaxCommand.EDS_COLLECTION_START.value
    )


def test_eds_map_refuses_a_detector_that_is_not_ready(make_client, no_sleep):
    """Readiness is rechecked per map: cooling can be lost mid-experiment."""
    client, service = make_client(
        payloads=_eds_payloads(
            **{EdaxCommand.EDS_GET_SYSTEM_DETECTOR_STATUS: "NotReady"}
        )
    )

    with pytest.raises(EdaxStateError, match="notready"):
        mapping.run_eds_map(EdaxEdsController(client), _eds_plan(), quiet=True)
    assert EdaxCommand.EDS_COLLECTION_START.value not in service.commands()


def test_eds_map_surfaces_an_unexpected_detector_status(make_client, no_sleep):
    """An unrecognized status shows its real text, not a false 'not ready'."""
    client, _ = make_client(
        payloads=_eds_payloads(
            **{EdaxCommand.EDS_GET_SYSTEM_DETECTOR_STATUS: "Warming"}
        )
    )

    with pytest.raises(EdaxResponseError, match="Warming"):
        mapping.run_eds_map(EdaxEdsController(client), _eds_plan(), quiet=True)


# EDS duration is predicted from the preset, frames, and dwell, because APEX's
# get_map_duration multiplies by a stale line count. Every EDS map must also be
# seen running: on hardware a running map reports MappingActive, then the
# event, then Ready. A stored point count that is no preset leaves the size
# unknown, and only then is APEX's figure used, unchecked and open-ended.
PREDICTED_60_S = str(int(60 * TICKS_PER_SECOND))
UNKNOWN_SIZE = {EdaxCommand.EDS_GET_NUMPOINTS: "100"}


def test_eds_prediction_comes_from_the_map_size_not_apex(make_client, no_sleep):
    """256 x 200, 3 frames, 50 us is 7.68 s, whatever APEX's own figure."""
    client, _ = make_client(
        payloads=_eds_payloads(
            **{
                EdaxCommand.EDS_GET_MAP_DURATION: PREDICTED_60_S,
                EdaxCommand.EDS_GET_NUMPOINTS: "256",
                EdaxCommand.EDS_GET_NUMFRAMES: "3",
                EdaxCommand.EDS_GET_PRESETDWELL: "50",
            }
        )
    )

    with pytest.raises(EdaxStateError, match=r"predicted 7\.7 seconds"):
        mapping.run_eds_map(EdaxEdsController(client), _eds_plan(), quiet=True)


def test_eds_map_finishing_before_its_dwell_is_rejected(make_client, no_sleep):
    """With the size known, a map shorter than its dwell was not collected."""
    client, _ = make_client(
        payloads=_eds_payloads(
            **{
                EdaxCommand.EDS_GET_NUMPOINTS: "512",
                EdaxCommand.EDS_GET_NUMFRAMES: "10",
                EdaxCommand.EDS_GET_PRESETDWELL: "100",
            }
        )
    )

    with pytest.raises(EdaxStateError, match="EDS map .* unexpectedly quickly"):
        mapping.run_eds_map(EdaxEdsController(client), _eds_plan(), quiet=True)


def test_eds_map_of_unknown_size_uses_apex_prediction_unchecked(make_client, no_sleep):
    """APEX's 60 s figure sizes the budget, but a quick map seen running is
    accepted: that figure is not trusted as a lower bound."""
    client, _ = make_client(
        payloads=_eds_payloads(
            **{EdaxCommand.EDS_GET_MAP_DURATION: PREDICTED_60_S, **UNKNOWN_SIZE}
        )
    )

    result = mapping.run_eds_map(EdaxEdsController(client), _eds_plan(), quiet=True)

    assert result.predicted_duration_s == pytest.approx(60.0)
    assert result.duration_s < result.predicted_duration_s


def test_eds_map_seen_active_then_ready_is_accepted(make_client, no_sleep):
    """The observed hardware sequence, with no event: active, then Ready."""
    client, _ = make_client(
        payloads=_eds_payloads(
            **{EdaxCommand.EDS_GET_MAP_STATUS: ["MappingActive", "Ready"]}
        )
    )

    result = mapping.run_eds_map(EdaxEdsController(client), _eds_plan(), quiet=True)

    assert result.status is EdaxMappingStatus.READY


def test_eds_map_ended_by_the_event_alone_is_accepted(make_client, no_sleep):
    """A map shorter than the start delay is over before the first poll; its
    event proves it ran."""
    client, service = make_client(
        payloads=_eds_payloads(**{EdaxCommand.EDS_GET_MAP_STATUS: "Ready"})
    )
    service.push_event(EdaxEvent.EDS_COLLECTION_COMPLETE, "Mapping complete")

    result = mapping.run_eds_map(EdaxEdsController(client), _eds_plan(), quiet=True)

    assert result.status is EdaxMappingStatus.MAPPING_COMPLETE


def test_eds_map_event_trailing_ready_is_accepted(make_client, no_sleep):
    """The event may land just after the status reads Ready."""
    client, service = make_client(
        payloads=_eds_payloads(**{EdaxCommand.EDS_GET_MAP_STATUS: "Ready"})
    )
    service.push_event(
        EdaxEvent.EDS_COLLECTION_COMPLETE, "Mapping complete", delay_s=0.1
    )

    mapping.run_eds_map(
        EdaxEdsController(client), _eds_plan(start_timeout_s=2.0), quiet=True
    )


def test_eds_map_never_seen_starting_is_rejected(make_client, no_sleep):
    """Ready throughout, with no event, is a map that never started; the
    error says so, and why APEX may simply be slow."""
    client, _ = make_client(
        payloads=_eds_payloads(**{EdaxCommand.EDS_GET_MAP_STATUS: "Ready"})
    )

    with pytest.raises(EdaxStateError) as error:
        mapping.run_eds_map(EdaxEdsController(client), _eds_plan(), quiet=True)

    message = str(error.value)
    assert "not seen starting" in message
    assert "last status 'ready'" in message
    assert "identifying elements" in message


def test_eds_element_identification_is_waited_out(make_client, no_sleep):
    """Seen on hardware: APEX reports Ready for minutes while it identifies
    elements, then maps. That Ready must not end the wait, and the duration
    budget, far shorter than the identification here, runs from the start of
    mapping, not of collection."""
    client, _ = make_client(
        payloads=_eds_payloads(
            **{
                EdaxCommand.EDS_GET_MAP_STATUS: ["Ready"] * 5
                + ["MappingActive", "Ready"]
            }
        ),
        delays={EdaxCommand.EDS_GET_MAP_STATUS: [0.1] * 5 + [0.0, 0.0]},
    )

    result = mapping.run_eds_map(
        EdaxEdsController(client),
        _eds_plan(min_timeout_s=0.2, start_timeout_s=5.0, status_timeout_s=1.0),
        quiet=True,
    )

    assert result.status is EdaxMappingStatus.READY
    assert result.duration_s > 0.4  # the identification was waited out


def test_eds_map_outlasting_its_prediction_is_waited_for(make_client, no_sleep):
    """With the size unknown, a map larger than APEX predicted must not be
    abandoned mid-collection while APEX says it is running. Budget: zero."""
    client, _ = make_client(
        payloads=_eds_payloads(
            **{
                EdaxCommand.EDS_GET_MAP_STATUS: ["MappingActive"] * 5
                + ["MappingComplete"],
                **UNKNOWN_SIZE,
            }
        )
    )

    result = mapping.run_eds_map(
        EdaxEdsController(client), _eds_plan(min_timeout_s=0.0), quiet=True
    )

    assert result.status is EdaxMappingStatus.MAPPING_COMPLETE


def test_eds_map_running_past_the_hard_limit_times_out(make_client, no_sleep):
    """The extension is bounded: a map stuck 'active' still ends the wait."""
    client, _ = make_client(
        payloads=_eds_payloads(
            **{EdaxCommand.EDS_GET_MAP_STATUS: "MappingActive", **UNKNOWN_SIZE}
        )
    )

    with pytest.raises(EdaxTimeoutError):
        mapping.run_eds_map(
            EdaxEdsController(client),
            _eds_plan(min_timeout_s=0.0, max_duration_s=0.3),
            quiet=True,
        )


def test_eds_map_of_known_size_keeps_a_hard_budget(make_client, no_sleep):
    """A predictable map is not waited on past its budget, so a hung APEX
    that keeps answering 'active' still ends the wait promptly."""
    client, _ = make_client(
        payloads=_eds_payloads(**{EdaxCommand.EDS_GET_MAP_STATUS: "MappingActive"})
    )

    started = time.monotonic()
    with pytest.raises(EdaxTimeoutError):
        mapping.run_eds_map(
            EdaxEdsController(client),
            _eds_plan(min_timeout_s=0.0, max_duration_s=60.0),
            quiet=True,
        )

    # Well short of max_duration_s, which applies only to an unknown size.
    assert time.monotonic() - started < 5.0


def test_interrupted_eds_map_is_rejected(make_client, no_sleep):
    """An aborted EDS map leaves partial data, so it is a failure."""
    client, _ = make_client(
        payloads=_eds_payloads(
            **{EdaxCommand.EDS_GET_MAP_STATUS: ["MappingActive", "MappingAborted"]}
        )
    )

    with pytest.raises(EdaxStateError, match="mappingaborted"):
        mapping.run_eds_map(EdaxEdsController(client), _eds_plan(), quiet=True)


def test_eds_map_survives_the_finalization_stall(make_client, no_sleep):
    """EDS shares the stall handling: one query, waited on, never re-sent."""
    client, service = make_client(
        payloads=_eds_payloads(**{EdaxCommand.EDS_GET_MAP_STATUS: "MappingComplete"}),
        delays={EdaxCommand.EDS_GET_MAP_STATUS: 0.3},
    )

    result = mapping.run_eds_map(
        EdaxEdsController(client),
        _eds_plan(status_timeout_s=0.02, min_timeout_s=5.0),
        quiet=True,
    )

    assert result.status is EdaxMappingStatus.MAPPING_COMPLETE
    assert service.commands().count(EdaxCommand.EDS_GET_MAP_STATUS.value) == 1


def test_eds_stall_past_an_unknown_size_budget_is_waited_for(make_client, no_sleep):
    """The production case: the map ran longer than predicted, the budget is
    spent, and APEX then goes quiet to finalize. It said the map was running,
    so the quiet is waited out, with one query and no re-send."""
    client, service = make_client(
        payloads=_eds_payloads(
            **{
                EdaxCommand.EDS_GET_MAP_STATUS: ["MappingActive", "MappingComplete"],
                **UNKNOWN_SIZE,
            }
        ),
        delays={EdaxCommand.EDS_GET_MAP_STATUS: [0.0, 0.3]},
    )

    result = mapping.run_eds_map(
        EdaxEdsController(client),
        _eds_plan(status_timeout_s=0.02, min_timeout_s=0.0),
        quiet=True,
    )

    assert result.status is EdaxMappingStatus.MAPPING_COMPLETE
    assert service.commands().count(EdaxCommand.EDS_GET_MAP_STATUS.value) == 2
