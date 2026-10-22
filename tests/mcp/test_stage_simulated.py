"""Stage motion against the AutoScript simulator, through ``build_server``.

Runs only on machines listed in ``Constants.offline_machines``. Moves the
simulated stage a little and back.
"""

## python standard libraries
import json

# 3rd party libraries
import pytest

mcp = pytest.importorskip("mcp")  # the mcp extra needs Python >= 3.10
from mcp import Client  # noqa: E402

# local libraries
from pytribeam.mcp.config import ServerConfig  # noqa: E402
from pytribeam.mcp.server import build_server  # noqa: E402

pytestmark = [pytest.mark.simulated, pytest.mark.anyio]

STEP_MM = 0.5


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def server(tmp_path):
    config = ServerConfig(max_tier=4, microscope_host="localhost", project_dir=tmp_path)
    return build_server(config)


async def _call(client, tool, args=None):
    result = await client.call_tool(tool, args or {})
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


def _within(limit, value):
    return limit["min"] <= value <= limit["max"]


async def test_move_x_and_y_and_back(server):
    async with Client(server) as client:
        start = await _call(client, "get_stage_position")
        limits = await _call(client, "get_stage_limits")
        # Step towards the middle of the range, so the move stays in limits.
        target = {
            axis: start[axis] + (STEP_MM if start[axis] < (limits[axis]["min"] + limits[axis]["max"]) / 2 else -STEP_MM)
            for axis in ("x_mm", "y_mm")
        }
        assert all(_within(limits[a], v) for a, v in target.items())

        out = await _call(client, "move_to_position", target)
        back = await _call(client, "move_to_position", {a: start[a] for a in target})
        diff = await _call(
            client, "compare_states", {"before": out["before_state_id"], "after": out["after_state_id"]}
        )

    for axis in ("x_mm", "y_mm"):
        assert out["position_after"][axis] == pytest.approx(target[axis], abs=0.01)
        assert back["position_after"][axis] == pytest.approx(start[axis], abs=0.01)
    for axis in ("z_mm", "r_deg", "t_deg"):
        assert out["position_after"][axis] == pytest.approx(start[axis], abs=0.01)

    changed = set(diff["changed"])
    assert {"specimen.stage.current_position.x", "specimen.stage.current_position.y"} <= changed
    # Besides the stage, only what the retract and the CCD view touch may change.
    allowed = ("specimen.stage.", "detector.", "imaging.")
    unexpected = sorted(p for p in changed if not p.startswith(allowed))
    assert not unexpected, unexpected


async def test_target_outside_the_limits_is_refused(server):
    async with Client(server) as client:
        limits = await _call(client, "get_stage_limits")
        result = await client.call_tool("move_to_position", {"x_mm": limits["x_mm"]["max"] + 10})
        after = await _call(client, "get_stage_position")
    assert result.is_error and "unsafe" in result.content[0].text.lower()
    assert _within(limits["x_mm"], after["x_mm"])
