## python standard libraries
from pathlib import Path

# 3rd party libraries
import pytest
import yaml

# Local
from pytribeam.mcp import state
from pytribeam.mcp.state.condense import condense

STATE_DIR = Path(__file__).parent / "state_records"

pytestmark = pytest.mark.detached


def _load(record_id: str) -> dict:
    return state.load(STATE_DIR / f"{record_id}.yml")


# ---------------------------------------------------------------------------
# save / load
# ---------------------------------------------------------------------------
def test_state_round_trips_through_a_file(tmp_path):
    original = _load("s0004")
    path = state.save(original, tmp_path / "copy.yml")
    assert state.load(path) == original
    assert list(tmp_path.iterdir()) == [path]  # no temporary file left behind


def test_schema_1_state_still_loads(tmp_path):
    path = tmp_path / "old.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "id": "s0001",
                "recorded_at": "2026-01-01T00:00:00.000-00:00",
                "provenance": {"pytribeam_version": "0.1.4"},
                "read_errors": [{"path": "a.b", "error": "boom", "kind": "access"}],
                "values": {"vacuum.chamber_state": "Pumped"},
            }
        )
    )
    loaded = state.load(path)
    assert loaded["read_errors"] == {"a.b": "boom"}
    assert loaded["values"] == {"vacuum.chamber_state": "Pumped"}


def test_next_path(tmp_path):
    session = tmp_path / "session"
    assert state.next_path(session) == session / "s0001.yml"

    session.mkdir()
    for name in ("s0001.yml", "s0007.yml", "steps.yml", "s0009.yml.tmp"):
        (session / name).touch()
    assert state.next_path(session) == session / "s0008.yml"


# ---------------------------------------------------------------------------
# condense
# ---------------------------------------------------------------------------
def test_condense_keeps_only_the_active_beam():
    electron = condense(_load("s0005"))
    assert electron["imaging"]["active_view"] == 1
    assert electron["imaging"]["active_device"] == "ELECTRON_BEAM"
    assert list(electron["beams"]) == ["electron_beam"]

    ion = condense(_load("s0006"))
    assert ion["imaging"]["active_view"] == 2
    assert ion["imaging"]["active_device"] == "ION_BEAM"
    assert list(ion["beams"]) == ["ion_beam"]
    assert ion["beams"]["ion_beam"]["horizontal_field_width"] == 0.0001
    assert ion["beams"]["ion_beam"]["scanning"]["resolution"] == "1536x1024"


def test_condense_drops_bounds_and_uninstalled_hardware():
    condensed = condense(_load("s0001"))
    text = yaml.safe_dump(condensed)
    for dropped in (
        "limits",
        "available_values",
        "is_controllable",
        "is_installed",
        "quad",
    ):
        assert dropped not in text

    specimen = condensed["specimen"]
    assert "cap_probe" not in specimen
    assert "loadlock" not in specimen
    assert specimen["stage"]["current_position"]["x"] == 0.0


def test_condense_collapses_lone_value_but_not_siblings():
    condensed = condense(_load("s0001"))
    assert condensed["detector"]["type"] == "TLD2"
    assert condensed["beams"]["electron_beam"]["beam_shift"] == {"x": 0.0, "y": 0.0}
    # `value` has a `target_value` sibling here, so it stays nested.
    assert condensed["specimen"]["temperature_stage"]["temperature"] == {
        "target_value": 313.15,
        "value": 293.15,
    }


def test_condense_with_a_camera_active_keeps_no_beam():
    condensed = condense(
        {
            "recorded_at": "t",
            "values": {
                "imaging.active_view": 3,
                "imaging.active_device": "NAV_CAM",
                "beams.electron_beam.is_on": True,
                "beams.ion_beam.is_on": True,
            },
        }
    )
    assert condensed["imaging"] == {"active_view": 3, "active_device": "NAV_CAM"}
    assert "beams" not in condensed


def test_condense_is_much_smaller():
    full = _load("s0001")
    assert len(yaml.safe_dump(condense(full))) < len(yaml.safe_dump(full)) / 5
