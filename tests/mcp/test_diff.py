## python standard libraries
from pathlib import Path

# 3rd party libraries
import pytest
import yaml

# Local
from pytribeam.mcp import state
from pytribeam.mcp.state.diff import diff

STATE_DIR = Path(__file__).parent / "state_records"
EXPECTED_DIR = Path(__file__).parent / "expected"

pytestmark = pytest.mark.detached


def _diff(before_id: str, after_id: str) -> dict:
    return diff(
        state.load(STATE_DIR / f"{before_id}.yml"),
        state.load(STATE_DIR / f"{after_id}.yml"),
    )


def _state(values: dict, read_errors: dict = None) -> dict:
    return {"recorded_at": "t", "values": values, "read_errors": read_errors or {}}


@pytest.mark.parametrize(
    "expected_file", sorted(EXPECTED_DIR.glob("*.yml")), ids=lambda p: p.stem
)
def test_diff_matches_expected(expected_file):
    with open(expected_file, "r", encoding="utf-8") as f:
        expected = yaml.safe_load(f)
    assert _diff(*expected_file.stem.split("_")) == expected


def test_returning_to_start_reports_no_changes():
    """s0007 undoes everything since s0001."""
    result = _diff("s0001", "s0007")
    assert (
        not result["changed"] and not result["appeared"] and not result["disappeared"]
    )


def test_stage_move_changes_only_stage_axes():
    assert set(_diff("s0001", "s0002")["changed"]) == {
        "specimen.stage.current_position.r",
        "specimen.stage.current_position.x",
        "specimen.stage.current_position.y",
    }


def test_values_lost_to_a_parent_read_error_are_not_reported():
    """In s0009 ``specimen.stage.current_position`` fails as a whole, so its
    axes vanish without being named in ``read_errors``. They are explained by
    the parent's read error, not reported as disappeared; symmetrically for
    the compustage axes, which start reading."""
    result = _diff("s0008", "s0009")
    assert "specimen.stage.current_position" in result["read_errors_introduced"]
    assert "specimen.compustage.current_position" in result["read_errors_resolved"]
    assert result["appeared"] == {}
    assert result["disappeared"] == {}


def test_tolerance_and_ignored_paths():
    before = _state(
        {
            "specimen.stage.current_position.x": 0.0,
            "specimen.stage.current_position.t": 0.0,
            "beams.electron_beam.horizontal_field_width.value": 1.0e-4,
            "vacuum.chamber_pressure.value": 1.0e-4,
        }
    )
    after = _state(
        {
            "specimen.stage.current_position.x": 4.0e-7,  # within 0.5 um
            "specimen.stage.current_position.t": 1.0e-3,  # beyond 0.02 deg
            "beams.electron_beam.horizontal_field_width.value": 1.0000001e-4,
            "vacuum.chamber_pressure.value": 2.0e-4,
        }
    )
    assert set(diff(before, after)["changed"]) == {
        "specimen.stage.current_position.t",
        "beams.electron_beam.horizontal_field_width.value",
    }


def test_unexplained_paths_appear_and_disappear():
    result = diff(_state({"a.b": 1}), _state({"a.c": 2}))
    assert result["disappeared"] == {"a.b": 1}
    assert result["appeared"] == {"a.c": 2}
