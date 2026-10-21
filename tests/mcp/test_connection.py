"""Shared microscope connection and capability helpers. No AutoScript."""

## python standard libraries
import json
import types
import warnings

# 3rd party libraries
import pytest

mcp = pytest.importorskip("mcp")  # the mcp extra needs Python >= 3.10
from mcp import Client  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

# local libraries
from pytribeam.mcp import connection as connection_module  # noqa: E402
from pytribeam.mcp.capabilities._helpers import (  # noqa: E402
    agent_errors,
    collect_warnings,
)
from pytribeam.mcp.config import ServerConfig  # noqa: E402
from pytribeam.mcp.connection import MicroscopeConnection  # noqa: E402
from pytribeam.mcp.server import build_server  # noqa: E402

pytestmark = pytest.mark.detached


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def connects(monkeypatch):
    """Count connections; each one returns a fresh fake microscope."""
    calls = []

    def connect(config):
        calls.append(config)
        return object()

    monkeypatch.setattr(connection_module, "_connect", connect)
    return calls


@pytest.fixture
def config(tmp_path):
    return ServerConfig(microscope_host="scope-pc", project_dir=tmp_path)


def test_connects_lazily_and_reuses(config, connects):
    conn = MicroscopeConnection(config)
    assert not conn.connected and not connects
    with conn.use() as first:
        with conn.use() as nested:  # re-entrant from the same tool
            assert nested is first
    with conn.use() as again:
        assert again is first
    assert conn.connected and len(connects) == 1


def test_connection_error_drops_the_connection(config, connects):
    conn = MicroscopeConnection(config)
    conn.cache["detector_types"] = ["ETD"]
    with pytest.raises(ConnectionError):
        with conn.use():
            raise ConnectionError("gone")
    assert not conn.connected and conn.cache == {}
    with conn.use():
        pass
    assert len(connects) == 2


def test_other_errors_keep_the_connection(config, connects):
    conn = MicroscopeConnection(config)
    with pytest.raises(ValueError):
        with conn.use():
            raise ValueError("bad setting")
    assert conn.connected


def test_reset_clears_cache(config, connects):
    conn = MicroscopeConnection(config)
    with conn.use():
        conn.cache["x"] = 1
    conn.reset()
    assert not conn.connected and conn.cache == {}


def test_connect_failure_names_the_host(config, monkeypatch):
    def refuse(config):
        raise ConnectionError("no route to host")

    monkeypatch.setattr(connection_module, "_connect", refuse)
    with pytest.raises(ToolError, match="scope-pc: no route to host"):
        with MicroscopeConnection(config).use():
            pass


def test_stdout_goes_to_stderr(config, connects, capsys):
    with MicroscopeConnection(config).use():
        print("Client connecting to [localhost:7520]...")
    out, err = capsys.readouterr()
    assert "Client connecting" not in out and "Client connecting" in err


def _module(name, calls):
    def register(add, config, connection):
        def touch() -> str:
            """Use the microscope."""
            with connection.use():
                calls.append(name)
            return name

        touch.__name__ = f"touch_{name}"
        add(touch)

    return types.SimpleNamespace(__name__=name, TIER=0, register=register)


@pytest.mark.anyio
async def test_modules_share_one_connection(config, connects):
    calls = []
    server = build_server(config, modules=(_module("a", calls), _module("b", calls)))
    async with Client(server) as client:
        for tool in ("touch_a", "touch_b", "touch_a"):
            result = await client.call_tool(tool, {})
            assert not result.is_error
    assert calls == ["a", "b", "a"]
    assert len(connects) == 1


def test_tier_range():
    assert ServerConfig(max_tier=4).max_tier == 4
    with pytest.raises(ValueError):
        ServerConfig(max_tier=5)


def test_images_dir(tmp_path):
    assert ServerConfig(project_dir=tmp_path).images_dir == tmp_path / "images"


@pytest.mark.parametrize("exc", [ValueError, SystemError, NotImplementedError])
def test_agent_errors_become_tool_errors(exc):
    with pytest.raises(ToolError, match="out of range"):
        with agent_errors():
            raise exc("out of range")


def test_agent_errors_convert_schema_errors():
    class SchemaError(Exception):  # schema.SchemaError is not a ValueError
        pass

    with pytest.raises(ToolError, match="not within limits"):
        with agent_errors():
            raise SchemaError("brightness of '0.0' is not within limits")


def test_agent_errors_pass_others_through():
    with pytest.raises(ToolError, match="refused"):
        with agent_errors():
            raise ToolError("refused")
    with pytest.raises(RuntimeError):
        with agent_errors():
            raise RuntimeError("bug")


def test_collect_warnings_collapses_whitespace():
    with collect_warnings() as found:
        warnings.warn("""Warning. Invalid detector type
                of "ETD" for this device.""")
        warnings.warn("second")
    assert found == ['Warning. Invalid detector type of "ETD" for this device.', "second"]


def test_collect_warnings_survives_an_exception():
    with pytest.raises(ValueError):
        with collect_warnings() as found:
            warnings.warn("before failing")
            raise ValueError
    assert found == ["before failing"]


def test_frame_limits(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        ServerConfig(max_frame_s=100, hard_max_frame_s=50)
    monkeypatch.setenv("PYTRIBEAM_MCP_MAX_FRAME_S", "60")
    cfg = ServerConfig.from_args(["--project-dir", str(tmp_path), "--hard-max-frame-s", "600"])
    assert (cfg.max_frame_s, cfg.hard_max_frame_s) == (60.0, 600.0)
