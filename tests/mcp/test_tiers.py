"""The tier scheme as a whole: which tools each tier exposes, and that their
annotations tell the truth. No AutoScript, no hardware.

These tests are the executable form of the Tiers table in the README. If one
fails because a tool was added, update the table and EXPECTED together.
"""

## python standard libraries
import json

# 3rd party libraries
import pytest

pytest.importorskip("mcp")  # the mcp extra needs Python >= 3.10
from mcp import Client  # noqa: E402

# local libraries
from pytribeam.mcp.config import MAX_TIER, TIERS, ServerConfig  # noqa: E402
from pytribeam.mcp.server import build_server  # noqa: E402

pytestmark = [pytest.mark.detached, pytest.mark.anyio]

# The tools each tier adds, matching the README Tiers table.
ADDED = {
    0: {
        "ping",
        "get_server_info",
        "check_connection",
        "reconnect",
        "get_recent_activity",
        "list_states",
        "list_images",
        "view_image",
    },
    1: {
        "get_state",
        "compare_states",
        "get_imaging_limits",
        "set_view",
        "get_available_detector_types",
        "get_available_detector_modes",
        "get_available_insertable_detectors",
        "get_stage_position",
        "get_stage_limits",
        "clear_fault",
    },
    2: {"prepare_imaging", "collect_single_image"},
    3: set(),  # lifts the retractable-detector guardrail
    4: {"move_to_position"},
    5: set(),  # lifts the ion-beam guardrail
}

# Tools that change nothing at all, though they are above tier 0.
READ_ONLY_ABOVE_0 = {"get_state", "compare_states", "get_imaging_limits"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _tools(tmp_path, max_tier):
    config = ServerConfig(max_tier=max_tier, project_dir=tmp_path)
    async with Client(build_server(config)) as client:
        return {t.name: t for t in (await client.list_tools()).tools}


def test_tiers_are_contiguous_and_named():
    assert MAX_TIER == 5
    assert sorted(TIERS) == list(range(MAX_TIER + 1))
    assert sorted(ADDED) == list(range(MAX_TIER + 1))


@pytest.mark.parametrize("max_tier", range(MAX_TIER + 1))
async def test_each_tier_exposes_exactly_its_tools(tmp_path, max_tier):
    expected = set().union(*(ADDED[t] for t in range(max_tier + 1)))
    assert set(await _tools(tmp_path, max_tier)) == expected


async def test_annotations_follow_the_tiers(tmp_path):
    tools = await _tools(tmp_path, MAX_TIER)
    tier_of = {name: tier for tier, names in ADDED.items() for name in names}
    for name, tool in tools.items():
        tier, hints = tier_of[name], tool.annotations
        if tier == 0:
            assert hints.read_only_hint, f"{name}: tier 0 tools are read-only"
            assert not hints.destructive_hint, name
        elif tier >= 2:
            assert hints.destructive_hint, f"{name}: tier 2+ tools are destructive"
            assert not hints.read_only_hint, name
        else:  # tier 1: changes the UI at most
            assert not hints.destructive_hint, f"{name}: tier 1 never moves or exposes"
            assert bool(hints.read_only_hint) == (name in READ_ONLY_ABOVE_0), name


async def test_server_info_reports_six_tiers(tmp_path):
    config = ServerConfig(max_tier=2, project_dir=tmp_path)
    async with Client(build_server(config)) as client:
        result = await client.call_tool("get_server_info", {})
    info = json.loads(result.content[0].text)
    assert [t["tier"] for t in info["tiers"]] == list(range(MAX_TIER + 1))
    assert [t["enabled"] for t in info["tiers"]] == [True, True, True, False, False, False]
