#!/usr/bin/python3
"""
Unit tests for the EDAX preflight and per-slice EBSD map sequences.

These pin down the behavior carried over from the proven hardware
implementation that lived in ``laser.py``: the order of operations, which
settings reach the wire, the duration and timeout arithmetic, and the checks
that catch a map EDAX did not actually collect.
"""

# Default python modules
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
