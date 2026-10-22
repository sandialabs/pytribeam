"""Stage motion, driven through an in-process MCP client with a fake microscope.
No AutoScript, no hardware.

The tool wraps pytribeam (retract_all_devices, then stage.move_to_position),
so these tests replace those two calls and check what the tool adds around
them: filling in axes, ordering, error messages, and failing closed.
"""

## python standard libraries
import json

# 3rd party libraries
import pytest

mcp = pytest.importorskip("mcp")  # the mcp extra needs Python >= 3.10
from mcp import Client  # noqa: E402

# local libraries
from pytribeam.mcp import connection  # noqa: E402
from pytribeam.mcp.capabilities import _helpers, stage, views  # noqa: E402
from pytribeam.mcp.config import ServerConfig  # noqa: E402
from pytribeam.mcp.server import build_server  # noqa: E402

pytestmark = [pytest.mark.detached, pytest.mark.anyio]

HOME = {"x_mm": 1.0, "y_mm": 2.0, "z_mm": 4.0, "r_deg": 10.0, "t_deg": 0.0}


class ApplicationServerException(Exception):
    """Same name as the AutoScript exception the tool matches."""


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def scope(monkeypatch):
    """A stage that remembers its position and every call made to it."""
    fake = {"position": dict(HOME), "calls": [], "move_error": None, "read_error": None}

    def capture(microscope, description):
        return {
            "recorded_at": "t",
            "description": description,
            "values": {f"stage.{k}": v for k, v in fake["position"].items()},
            "read_errors": {},
        }

    def position(microscope):
        if fake["read_error"]:
            raise fake["read_error"]
        return {**fake["position"], "coordinate_system": "Raw"}

    def retract(microscope):
        fake["calls"].append("retract")

    def move(microscope, target):
        fake["calls"].append(("move", dict(target)))
        if fake["move_error"]:
            raise fake["move_error"]
        fake["position"].update(target)

    monkeypatch.setattr(connection, "_connect", lambda config: object())
    monkeypatch.setattr(_helpers, "_capture", capture)
    monkeypatch.setattr(stage, "_stage_position", position)
    monkeypatch.setattr(stage, "_retract_all", retract)
    monkeypatch.setattr(stage, "_move", move)
    return fake


@pytest.fixture
def server(tmp_path):
    config = ServerConfig(max_tier=4, project_dir=tmp_path)
    return build_server(config, modules=(stage, views))


async def _call(client, tool, args=None):
    result = await client.call_tool(tool, args or {})
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


async def _refused(client, tool, args=None):
    result = await client.call_tool(tool, args or {})
    assert result.is_error, result.content[0].text
    return result.content[0].text


async def test_registration(server):
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert tools["move_to_position"].annotations.destructive_hint is True


@pytest.mark.parametrize("max_tier", [0, 1, 2, 3])
async def test_needs_tier_4(tmp_path, max_tier):
    config = ServerConfig(max_tier=max_tier, project_dir=tmp_path)
    async with Client(build_server(config, modules=(stage,))) as client:
        assert (await client.list_tools()).tools == []


async def test_partial_target_keeps_other_axes(server, scope):
    async with Client(server) as client:
        result = await _call(client, "move_to_position", {"x_mm": 5, "t_deg": 12.5})
    target = {**HOME, "x_mm": 5.0, "t_deg": 12.5}
    assert result["target"] == target
    assert scope["calls"] == ["retract", ("move", target)]  # retract first, then move
    assert result["position_before"]["x_mm"] == 1.0
    assert result["position_after"]["x_mm"] == 5.0
    assert set(result["changes"]) == {"stage.x_mm", "stage.t_deg"}
    assert result["before_state_id"] == "s0001" and result["after_state_id"] == "s0002"


async def test_no_axes_is_refused_before_anything(server, scope, tmp_path):
    async with Client(server) as client:
        message = await _refused(client, "move_to_position", {})
    assert "at least one axis" in message
    assert scope["calls"] == [] and not list(tmp_path.glob("states/*.yml"))


async def test_unsafe_target_reaches_the_agent_unchanged(server, scope):
    """pytribeam checks the limits; its message, with the limits, is passed on."""
    limits = "Destination position of ... is unsafe. Stage limits are: x_mm=Limit(min=-55, max=55)"
    scope["move_error"] = ValueError(limits)
    async with Client(server) as client:
        message = await _refused(client, "move_to_position", {"x_mm": 500})
    assert limits in message


async def test_unsafe_target_does_not_set_the_fault(server, scope):
    scope["move_error"] = ValueError("Destination position is unsafe.")
    async with Client(server) as client:
        await _refused(client, "move_to_position", {"x_mm": 500})
        scope["move_error"] = None
        result = await _call(client, "move_to_position", {"x_mm": 2})
    assert result["position_after"]["x_mm"] == 2.0


async def test_missed_move_fails_closed(server, scope):
    scope["move_error"] = SystemError(
        "Error: Stage move did not execute correctly.\n\t X axis error: 12.0 micron"
    )
    async with Client(server) as client:
        failed = await _refused(client, "move_to_position", {"x_mm": 3})
        scope["move_error"] = None
        blocked = await _refused(client, "move_to_position", {"x_mm": 3})
        cleared = await _call(client, "clear_fault")
        moved = await _call(client, "move_to_position", {"x_mm": 3})
    assert "did not reach the target" in failed and "X axis error: 12.0 micron" in failed
    assert "do not retry" in failed and "clear_fault" in failed
    assert "may not be in the state" in blocked and "stage move did not reach" in blocked
    assert cleared["cleared"] is True
    assert moved["position_after"]["x_mm"] == 3.0


async def test_inactive_bulk_stage_is_reported(server, scope):
    scope["read_error"] = ApplicationServerException("Bulk stage is not an active stage.")
    async with Client(server) as client:
        message = await _refused(client, "move_to_position", {"x_mm": 3})
    assert "Bulk stage is not an active stage" in message
    assert scope["calls"] == []  # nothing retracted or moved


# --- the pytribeam wrappers, against stand-in modules -------------------------
def test_move_wrapper_builds_a_raw_user_position(monkeypatch):
    """_move must hand stage.move_to_position a RAW StagePositionUser built from
    the agent's mm/deg values, with nothing checked or changed on the way."""
    import sys
    import types
    from enum import Enum
    from typing import NamedTuple

    import pytribeam

    class StageCoordinateSystem(Enum):
        RAW = "Raw"

    class StagePositionUser(NamedTuple):
        x_mm: float
        y_mm: float
        z_mm: float
        r_deg: float
        t_deg: float
        coordinate_system: StageCoordinateSystem = StageCoordinateSystem.RAW

    seen = {}
    tbt = types.ModuleType("pytribeam.types")
    tbt.StageCoordinateSystem, tbt.StagePositionUser = StageCoordinateSystem, StagePositionUser
    stage_mod = types.ModuleType("pytribeam.stage")
    stage_mod.move_to_position = lambda microscope, target: seen.update(target=target)
    devices = types.ModuleType("pytribeam.insertable_devices")
    devices.retract_all_devices = lambda microscope, **kw: seen.update(retract=kw)
    for name, module in (("types", tbt), ("stage", stage_mod), ("insertable_devices", devices)):
        monkeypatch.setitem(sys.modules, f"pytribeam.{name}", module)
        monkeypatch.setattr(pytribeam, name, module, raising=False)

    stage._move(None, {"x_mm": 5.0, "y_mm": 2.0, "z_mm": 4.0, "r_deg": 10.0, "t_deg": 0.0})
    stage._retract_all(None)
    assert seen["target"] == StagePositionUser(5.0, 2.0, 4.0, 10.0, 0.0, StageCoordinateSystem.RAW)
    assert seen["retract"] == {"enable_EBSD": False, "enable_EDS": False}
