"""State tools, driven through an in-process MCP client with the microscope
replaced by recorded fixture states. No AutoScript, no hardware."""

## python standard libraries
import json
from pathlib import Path

# 3rd party libraries
import pytest

mcp = pytest.importorskip("mcp")  # the mcp extra needs Python >= 3.10
from mcp import Client  # noqa: E402

# local libraries
from pytribeam.mcp import state  # noqa: E402
from pytribeam.mcp.capabilities import state as state_tools  # noqa: E402
from pytribeam.mcp.config import ServerConfig  # noqa: E402
from pytribeam.mcp.server import build_server  # noqa: E402

pytestmark = [pytest.mark.detached, pytest.mark.anyio]

STATE_DIR = Path(__file__).parent / "state_records"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def scope(monkeypatch):
    """Serve fixture states s0001, s0002, ... in order, one per capture."""
    fake = {
        "connects": 0,
        "queue": [state.load(p) for p in sorted(STATE_DIR.glob("s0*.yml"))],
    }

    def connect(config):
        fake["connects"] += 1
        return object()

    def capture(microscope, description):
        captured = fake["queue"].pop(0)
        captured["description"] = description
        return captured

    monkeypatch.setattr(state_tools, "_connect", connect)
    monkeypatch.setattr(state_tools, "_capture", capture)
    return fake


@pytest.fixture
def config(tmp_path):
    return ServerConfig(max_tier=0, project_dir=tmp_path)


@pytest.fixture
def server(config):
    return build_server(config, modules=(state_tools,))


async def _call(client, tool, args=None):
    result = await client.call_tool(tool, args or {})
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


async def test_tools_are_read_only(server):
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"get_state", "compare_states", "list_states"}
    assert all(t.annotations.read_only_hint for t in tools.values())


async def test_get_state_saves_full_state_and_returns_condensed(server, scope, config):
    async with Client(server) as client:
        small = await _call(client, "get_state", {"description": "start"})
        full = await _call(client, "get_state", {"full": True})

    assert small["state_id"] == "s0001"
    assert small["description"] == "start"
    assert small["imaging"]["active_device"] == "ELECTRON_BEAM"
    assert "values" not in small

    assert full["state_id"] == "s0002"
    assert full["values"]["specimen.stage.current_position.x"] == 0.005

    saved = state.load(config.states_dir / "s0001.yml")
    assert saved["description"] == "start"
    assert saved["values"] == state.load(STATE_DIR / "s0001.yml")["values"]
    assert scope["connects"] == 1  # the connection is reused


async def test_compare_saved_states_and_against_now(server, scope):
    async with Client(server) as client:
        await _call(client, "get_state")  # s0001
        await _call(client, "get_state")  # s0002
        saved = await _call(
            client, "compare_states", {"before": "s0001", "after": "s0002"}
        )
        now = await _call(client, "compare_states", {"before": "s0002"})  # s0003
        listing = await _call(client, "list_states")

    assert (saved["before_id"], saved["after_id"]) == ("s0001", "s0002")
    assert set(saved["changed"]) == {
        "specimen.stage.current_position.r",
        "specimen.stage.current_position.x",
        "specimen.stage.current_position.y",
    }
    assert now["after_id"] == "s0003"
    assert set(now["changed"]) == {"beams.electron_beam.scanning.resolution.value"}
    assert listing["total"] == 3
    assert [s["state_id"] for s in listing["states"]] == ["s0001", "s0002", "s0003"]


async def test_states_from_earlier_sessions_are_available(server, scope, config):
    """Ids continue from what is already in the project, and old states compare."""
    config.states_dir.mkdir()
    state.save(state.load(STATE_DIR / "s0009.yml"), config.states_dir / "s0041.yml")

    async with Client(server) as client:
        result = await _call(client, "compare_states", {"before": "s0041"})

    assert result["after_id"] == "s0042"
    assert "specimen.stage.current_position" in result["read_errors_resolved"]


async def test_list_states_limit(server, scope):
    async with Client(server) as client:
        for _ in range(3):
            await _call(client, "get_state")
        listing = await _call(client, "list_states", {"limit": 2})
    assert listing["total"] == 3
    assert [s["state_id"] for s in listing["states"]] == ["s0002", "s0003"]


@pytest.mark.parametrize("bad_id", ["s0009", "../logs/audit", "s0001.yml"])
async def test_unknown_or_malformed_state_id_is_refused(server, scope, bad_id):
    async with Client(server) as client:
        await _call(client, "get_state")
        result = await client.call_tool("compare_states", {"before": bad_id})
    assert result.is_error and "No state with id" in result.content[0].text
    assert len(scope["queue"]) == 8  # refused before reading the microscope


async def test_connection_failure_is_reported(server, monkeypatch):
    def refuse(config):
        raise ConnectionError("no route to host")

    monkeypatch.setattr(state_tools, "_connect", refuse)
    async with Client(server) as client:
        result = await client.call_tool("get_state", {})
    assert result.is_error and "no route to host" in result.content[0].text


async def test_empty_capture_is_not_saved_and_reconnects(server, scope, config):
    scope["queue"].insert(0, {"values": {}, "read_errors": {"beams": "gone"}})
    async with Client(server) as client:
        result = await client.call_tool("get_state", {})
        assert result.is_error and "connection" in result.content[0].text
        assert (await _call(client, "get_state"))["state_id"] == "s0001"
    assert scope["connects"] == 2


async def test_autoscript_output_is_kept_off_stdout(server, scope, monkeypatch, capsys):
    """stdout carries the MCP protocol; anything AutoScript prints must not."""

    def chatty_connect(config):
        print("Client connecting to [localhost:7520]...")
        return object()

    monkeypatch.setattr(state_tools, "_connect", chatty_connect)
    async with Client(server) as client:
        await _call(client, "get_state")
    out, err = capsys.readouterr()
    assert "Client connecting" not in out
    assert "Client connecting" in err
