## python standard libraries
import math
from pathlib import Path

# 3rd party libraries
import pytest
import yaml

# Local
from pytribeam.mcp.state import diff, metadata, schema

STATE_DIR = Path(__file__).parent / "state_records"
EXPECTED_DIR = Path(__file__).parent / "expected"

PAIRS = [
    ("s0001", "s0002"),
    ("s0002", "s0003"),
    ("s0003", "s0004"),
    ("s0004", "s0005"),
    ("s0005", "s0006"),
    ("s0006", "s0007"),
    ("s0007", "s0008"),
    ("s0008", "s0009"),
    ("s0001", "s0007"),
]
PAIR_IDS = [f"{a}_{b}" for a, b in PAIRS]

FLOAT_EPS = 1e-12


def _load_expected(before_id: str, after_id: str) -> dict:
    path = EXPECTED_DIR / f"{before_id}_{after_id}.yml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _compute(before_id: str, after_id: str) -> dict:
    before = schema.read_record(STATE_DIR, before_id)
    after = schema.read_record(STATE_DIR, after_id)
    path_metadata = metadata.load()
    result = diff.diff_records(before, after, path_metadata)
    return result.to_dict()


def _values_close(a, b) -> bool:
    if (
        isinstance(a, (int, float))
        and isinstance(b, (int, float))
        and not isinstance(a, bool)
        and not isinstance(b, bool)
    ):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=FLOAT_EPS)
    return a == b


def _differences_by_path(differences: list) -> dict:
    return {d["path"]: d for d in differences}


@pytest.fixture(params=PAIRS, ids=PAIR_IDS)
def pair(request):
    return request.param


@pytest.fixture
def expected(pair):
    return _load_expected(*pair)


@pytest.fixture
def actual(pair):
    return _compute(*pair)


# ---------------------------------------------------------------------------
# Full data-driven comparison, one fixture pair at a time.
# ---------------------------------------------------------------------------
@pytest.mark.detached
def test_diff_matches_expected(pair, expected, actual):
    before_id, after_id = pair

    assert actual["before_id"] == expected["before_id"]
    assert actual["after_id"] == expected["after_id"]
    assert actual["provenance_mismatch"] == expected["provenance_mismatch"]

    exp_by_path = _differences_by_path(expected["differences"])
    act_by_path = _differences_by_path(actual["differences"])
    assert set(act_by_path) == set(exp_by_path), (
        f"{before_id}->{after_id}: path set mismatch.\n"
        f"missing: {set(exp_by_path) - set(act_by_path)}\n"
        f"extra:   {set(act_by_path) - set(exp_by_path)}"
    )
    for path, exp_d in exp_by_path.items():
        act_d = act_by_path[path]
        assert act_d["classification"] == exp_d["classification"], path
        assert act_d["capability"] == exp_d["capability"], path
        assert act_d.get("scoped_by") == exp_d.get("scoped_by"), path
        assert _values_close(act_d["before"], exp_d["before"]), path
        assert _values_close(act_d["after"], exp_d["after"]), path

    assert actual["operations"] == expected["operations"]
    assert sorted(actual["observed"]) == sorted(expected["observed"])
    assert sorted(actual["read_errors_resolved"]) == sorted(
        expected["read_errors_resolved"]
    )
    assert sorted(actual["read_errors_introduced"]) == sorted(
        expected["read_errors_introduced"]
    )
    assert sorted(actual["unmapped"]) == sorted(expected["unmapped"])
    assert actual["unchanged_count"] == expected["unchanged_count"]
    assert actual["noise_count"] == expected["noise_count"]


# ---------------------------------------------------------------------------
# Named acceptance criteria (mcp_context_transfer.md WP1 spec, task list #3).
# Each of these is checkable from the same fixtures above; they are broken
# out individually so a failure names the exact behavior that's missing
# rather than a generic dict-mismatch.
# ---------------------------------------------------------------------------
@pytest.mark.detached
def test_pure_jitter_pair_reports_zero_changes():
    """Criterion 1: a pair with only jitter reports zero changes.

    s0001 vs s0007 is a non-adjacent pair with exactly zero real
    differences (this is simulator data with no float jitter at all, so
    'jitter' here just means 'nothing that should surface').
    """
    expected = _load_expected("s0001", "s0007")
    assert expected["differences"] == []

    actual = _compute("s0001", "s0007")
    assert actual["differences"] == []


@pytest.mark.detached
def test_stage_move_grouped_as_one_capability():
    """Criterion 2: 1->2 reports exactly the stage axes, grouped as one
    ``move_stage`` operation."""
    expected = _load_expected("s0001", "s0002")
    assert set(expected["operations"]) == {"move_stage"}
    assert set(expected["operations"]["move_stage"]) == {
        "specimen.stage.current_position.r",
        "specimen.stage.current_position.x",
        "specimen.stage.current_position.y",
    }

    actual = _compute("s0001", "s0002")
    assert actual["operations"] == expected["operations"]


@pytest.mark.detached
def test_hfw_and_stage_reported_as_separate_capabilities():
    """Criterion 3: 4->5 reports HFW and stage separately, as two
    capabilities (the stage move here is tilt-only -- see mcp/README.md)."""
    expected = _load_expected("s0004", "s0005")
    assert set(expected["operations"]) == {"set_hfw", "move_stage"}
    assert expected["operations"]["move_stage"] == ["specimen.stage.current_position.t"]

    actual = _compute("s0004", "s0005")
    assert actual["operations"] == expected["operations"]


@pytest.mark.detached
def test_ancestor_rule_both_directions():
    """Criterion 4: a path whose *ancestor* errors in `after` is
    `read_error_after`, not `disappeared` -- and symmetrically for
    `before` -- exercised by fixture 8->9 in both directions.

    `specimen.stage.current_position` (the parent object) starts erroring
    as a whole in s0009, which is why `specimen.stage.current_position.x`
    (never itself named in read_errors) must still classify as
    read_error_after. Symmetrically, `specimen.compustage.current_position`
    stops erroring, so its children are read_error_before in the same pair.
    """
    actual = _compute("s0008", "s0009")
    by_path = _differences_by_path(actual["differences"])

    assert (
        by_path["specimen.stage.current_position.x"]["classification"]
        == "read_error_after"
    )
    assert (
        by_path["specimen.stage.current_position.y"]["classification"]
        == "read_error_after"
    )
    assert (
        by_path["specimen.compustage.current_position.x"]["classification"]
        == "read_error_before"
    )
    assert (
        by_path["specimen.compustage.current_position.y"]["classification"]
        == "read_error_before"
    )

    # None of these six children ever appear by name in either record's
    # read_errors list -- only their parent object does. A lookup that
    # doesn't walk ancestors would misclassify them as disappeared/appeared.
    before = schema.read_record(STATE_DIR, "s0008")
    after = schema.read_record(STATE_DIR, "s0009")
    before_err_paths = {e.path for e in before.read_errors}
    after_err_paths = {e.path for e in after.read_errors}
    assert "specimen.stage.current_position.x" not in after_err_paths
    assert "specimen.stage.current_position" in after_err_paths
    assert "specimen.compustage.current_position.x" not in before_err_paths
    assert "specimen.compustage.current_position" in before_err_paths


@pytest.mark.detached
def test_provenance_mismatch_flagged():
    """Criterion 5: records with differing provenance.pytribeam_version
    still diff, with the mismatch flag set.

    None of the 9 session fixtures were recorded under different pytribeam
    versions (they're all one session), so this is exercised with two
    minimal synthetic records rather than the session fixtures.
    """
    before = schema.StateRecord(
        id="synthetic_before",
        recorded_at="2026-01-01T00:00:00.000-00:00",
        values={"specimen.stage.current_position.x": 0.0},
        provenance=schema.Provenance(pytribeam_version="0.1.3"),
    )
    after = schema.StateRecord(
        id="synthetic_after",
        recorded_at="2026-01-01T00:01:00.000-00:00",
        values={"specimen.stage.current_position.x": 0.005},
        provenance=schema.Provenance(pytribeam_version="0.1.4"),
    )
    path_metadata = metadata.load()
    result = diff.diff_records(before, after, path_metadata).to_dict()

    assert result["provenance_mismatch"] is True
    assert len(result["differences"]) == 1


@pytest.mark.detached
def test_unmapped_path_reported():
    """Criterion 6: a path in neither the metadata table nor the noise
    list appears in `unmapped`.

    `beams.electron_beam.is_on` (7->8) is deliberately left out of
    path_metadata.yml -- see the file's "deliberately left unmapped"
    section -- specifically so this case has something real to catch.
    """
    expected = _load_expected("s0007", "s0008")
    assert "beams.electron_beam.is_on" in expected["unmapped"]

    actual = _compute("s0007", "s0008")
    assert "beams.electron_beam.is_on" in actual["unmapped"]
