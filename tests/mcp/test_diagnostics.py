"""Diagnostic tools, driven through an in-process MCP client with a fake
microscope connection. No AutoScript, no hardware."""

## python standard libraries
import json

# 3rd party libraries
import pytest

mcp = pytest.importorskip("mcp")  # the mcp extra needs Python >= 3.10
from mcp import Client  # noqa: E402

# local libraries
from pytribeam.mcp import connection  # noqa: E402
from pytribeam.mcp.capabilities import diagnostics  # noqa: E402
from pytribeam.mcp.config import ServerConfig  # noqa: E402
from pytribeam.mcp.server import build_server  # noqa: E402

pytestmark = [pytest.mark.detached, pytest.mark.anyio]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def config(tmp_path):
    return ServerConfig(
        max_tier=1, microscope_host="scope-pc", microscope_port=7520, project_dir=tmp_path
    )


@pytest.fixture
def scope(monkeypatch):
    """A fake connection and probe. Set ``scope["fail"]`` to make reads raise."""
    fake = {"connects": 0, "probes": 0, "fail": None}

    def connect(config):
        fake["connects"] += 1
        return object()

    def probe(microscope):
        fake["probes"] += 1
        if fake["fail"]:
            raise fake["fail"]
        return {
            "round_trip_ms": 1.5,
            "vacuum": "Pumped",
            "active_view": 1,
            "active_device": "ELECTRON_BEAM",
        }

    monkeypatch.setattr(connection, "_connect", connect)
    monkeypatch.setattr(diagnostics, "_probe", probe)
    monkeypatch.setattr(diagnostics, "_is_simulator", lambda: True)
    return fake


@pytest.fixture
def server(config):
    return build_server(config, modules=(diagnostics,))


async def _call(client, tool, args=None):
    result = await client.call_tool(tool, args or {})
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


async def test_tools_are_read_only(server):
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {
        "ping",
        "get_server_info",
        "check_connection",
        "reconnect",
        "get_recent_activity",
    }
    assert all(t.annotations.read_only_hint for t in tools.values())


async def test_server_info_does_not_connect(server, scope, config):
    async with Client(server) as client:
        info = await _call(client, "get_server_info")
        await _call(client, "check_connection")
        after = await _call(client, "get_server_info")

    assert info["connected"] is False and after["connected"] is True
    assert scope["connects"] == 1  # only check_connection connected
    assert info["max_tier"] == 1
    assert [(t["tier"], t["enabled"]) for t in info["tiers"]] == [
        (0, True),
        (1, True),
        (2, False),
        (3, False),
        (4, False),
    ]
    assert info["images_dir"] == str(config.images_dir)
    assert info["states_dir"] == str(config.states_dir)
    assert (info["microscope_host"], info["microscope_port"]) == ("scope-pc", 7520)
    assert "autoscript_version" in info and info["python_version"]


async def test_check_connection_reports_the_microscope(server, scope):
    async with Client(server) as client:
        result = await _call(client, "check_connection")
    assert result == {
        "connected": True,
        "microscope_host": "scope-pc",
        "microscope_port": 7520,
        "simulator": True,
        "round_trip_ms": 1.5,
        "vacuum": "Pumped",
        "active_view": 1,
        "active_device": "ELECTRON_BEAM",
    }


async def test_check_connection_returns_failure_instead_of_raising(
    server, scope, monkeypatch
):
    def refuse(config):
        raise ConnectionError("no route to host")

    monkeypatch.setattr(connection, "_connect", refuse)
    async with Client(server) as client:
        result = await _call(client, "check_connection")
    assert result["connected"] is False
    assert "scope-pc" in result["error"] and "no route to host" in result["error"]


async def test_failed_read_drops_the_connection(server, scope):
    scope["fail"] = RuntimeError("ApplicationServerException: server restarted")
    async with Client(server) as client:
        failed = await _call(client, "check_connection")
        scope["fail"] = None
        ok = await _call(client, "check_connection")
    assert failed["connected"] is False and "server restarted" in failed["error"]
    assert ok["connected"] is True
    assert scope["connects"] == 2


async def test_reconnect_opens_a_new_connection(server, scope):
    async with Client(server) as client:
        await _call(client, "check_connection")
        result = await _call(client, "reconnect")
        await _call(client, "check_connection")
    assert result["connected"] is True
    assert scope["connects"] == 2


def _write_audit(config, n):
    config.log_dir.mkdir(parents=True, exist_ok=True)
    with open(config.log_dir / "audit.jsonl", "w", encoding="utf-8") as f:
        for i in range(n):
            f.write(json.dumps({"tool": "ping", "args": {"message": str(i)}}) + "\n")


async def test_recent_activity_newest_last(server, config):
    _write_audit(config, 30)
    async with Client(server) as client:
        result = await _call(client, "get_recent_activity", {"limit": 3})
    assert result["total"] == 30
    assert [r["args"]["message"] for r in result["records"]] == ["27", "28", "29"]


async def test_recent_activity_limit_is_capped(server, config):
    _write_audit(config, 250)
    async with Client(server) as client:
        capped = await _call(client, "get_recent_activity", {"limit": 10_000})
        none = await _call(client, "get_recent_activity", {"limit": -1})
    assert len(capped["records"]) == diagnostics.MAX_ACTIVITY_RECORDS
    assert capped["records"][-1]["args"]["message"] == "249"
    assert none["records"] == []


async def test_recent_activity_without_a_log(server):
    async with Client(server) as client:
        result = await _call(client, "get_recent_activity")
    assert result == {"total": 0, "records": []}


async def test_recent_activity_survives_a_torn_line(server, config):
    _write_audit(config, 2)
    with open(config.log_dir / "audit.jsonl", "a", encoding="utf-8") as f:
        f.write('{"tool": "get_st')  # e.g. the server was killed mid-write
    async with Client(server) as client:
        result = await _call(client, "get_recent_activity")
    assert result["total"] == 3
    assert result["records"][-1] == {"unreadable": '{"tool": "get_st'}
