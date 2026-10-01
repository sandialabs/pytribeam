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
def server(tmp_path):
    config = ServerConfig(max_tier=0, log_dir=tmp_path)
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


async def test_get_state_condensed_and_full(server, scope):
    async with Client(server) as client:
        small = await _call(client, "get_state", {"description": "start"})
        full = await _call(client, "get_state", {"full": True})

    assert small["state_id"] == "s1"
    assert small["description"] == "start"
    assert small["imaging"]["active_device"] == "ELECTRON_BEAM"
    assert "values" not in small

    assert full["state_id"] == "s2"
    assert full["values"]["specimen.stage.current_position.x"] == 0.005
    assert "read_errors" in full
    assert scope["connects"] == 1  # the connection is reused


async def test_compare_stored_states_and_against_now(server, scope):
    async with Client(server) as client:
        await _call(client, "get_state")  # s1 <- s0001
        await _call(client, "get_state")  # s2 <- s0002
        stored = await _call(client, "compare_states", {"before": "s1", "after": "s2"})
        now = await _call(client, "compare_states", {"before": "s2"})  # s3 <- s0003
        listing = await _call(client, "list_states")

    assert (stored["before_id"], stored["after_id"]) == ("s1", "s2")
    assert set(stored["changed"]) == {
        "specimen.stage.current_position.r",
        "specimen.stage.current_position.x",
        "specimen.stage.current_position.y",
    }
    assert now["after_id"] == "s3"
    assert set(now["changed"]) == {"beams.electron_beam.scanning.resolution.value"}
    assert [s["state_id"] for s in listing["states"]] == ["s1", "s2", "s3"]


async def test_unknown_state_id_is_refused(server, scope):
    async with Client(server) as client:
        await _call(client, "get_state")
        result = await client.call_tool("compare_states", {"before": "s9"})
    assert result.is_error and "Known ids: s1" in result.content[0].text
    assert len(scope["queue"]) == 8  # refused before reading the microscope


async def test_connection_failure_is_reported(server, monkeypatch):
    def refuse(config):
        raise ConnectionError("no route to host")

    monkeypatch.setattr(state_tools, "_connect", refuse)
    async with Client(server) as client:
        result = await client.call_tool("get_state", {})
    assert result.is_error and "no route to host" in result.content[0].text


async def test_empty_capture_reconnects_next_time(server, scope):
    scope["queue"].insert(0, {"values": {}, "read_errors": {"beams": "gone"}})
    async with Client(server) as client:
        result = await client.call_tool("get_state", {})
        assert result.is_error and "connection" in result.content[0].text
        await _call(client, "get_state")
    assert scope["connects"] == 2


async def test_old_states_are_forgotten(server, scope, monkeypatch):
    monkeypatch.setattr(state_tools, "MAX_STATES", 2)
    async with Client(server) as client:
        for _ in range(3):
            await _call(client, "get_state")
        listing = await _call(client, "list_states")
    assert [s["state_id"] for s in listing["states"]] == ["s2", "s3"]


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
