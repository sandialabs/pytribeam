"""MCP server wiring tests. In-process: no subprocess, no AutoScript, no LLM."""

## python standard libraries
import json
import types

# 3rd party libraries
import pytest
from mcp import Client

# local libraries
from pytribeam.mcp.config import ServerConfig
from pytribeam.mcp.server import build_server

pytestmark = [pytest.mark.detached, pytest.mark.anyio]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def config(tmp_path):
    return ServerConfig(max_tier=0, microscope_host="scope-pc", project_dir=tmp_path)


def _fake_module(tier):
    """A stand-in capability module at an arbitrary tier."""

    def register(add, config):
        def poke() -> str:
            """Pretend to touch hardware."""
            return "poked"

        add(poke)

    return types.SimpleNamespace(
        __name__=f"fake_tier{tier}", TIER=tier, register=register
    )


async def test_ping_round_trip(config):
    async with Client(build_server(config)) as client:
        result = await client.call_tool("ping", {"message": "hi"})
    payload = json.loads(result.content[0].text)
    assert payload["echo"] == "hi"
    assert payload["microscope_host"] == "scope-pc"


async def test_ping_is_annotated_read_only(config):
    async with Client(build_server(config)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert tools["ping"].annotations.read_only_hint is True


async def test_modules_above_max_tier_are_not_exposed(config):
    server = build_server(config, modules=(_fake_module(0), _fake_module(1)))
    async with Client(server) as client:
        names = [t.name for t in (await client.list_tools()).tools]
    assert names == ["poke"]  # only the tier-0 copy registered


def test_config_fails_closed():
    assert ServerConfig().max_tier == 0
    with pytest.raises(ValueError):
        ServerConfig(max_tier=7)


def test_config_from_args(tmp_path):
    cfg = ServerConfig.from_args(
        [
            "--max-tier",
            "1",
            "--microscope-host",
            "10.0.0.5",
            "--project-dir",
            str(tmp_path),
        ]
    )
    assert (cfg.max_tier, cfg.microscope_host, cfg.project_dir) == (
        1,
        "10.0.0.5",
        tmp_path,
    )


def _failing_module(exc):
    def register(add, config):
        def fail() -> str:
            """Always fails."""
            raise exc

        add(fail)

    return types.SimpleNamespace(__name__="failing", TIER=0, register=register)


async def test_tool_error_message_reaches_the_agent(config):
    from mcp.server.mcpserver.exceptions import ToolError

    server = build_server(
        config, modules=(_failing_module(ToolError("stage is locked")),)
    )
    async with Client(server) as client:
        result = await client.call_tool("fail", {})
    assert result.is_error and "stage is locked" in result.content[0].text


async def test_unexpected_errors_are_not_leaked(config):
    server = build_server(
        config, modules=(_failing_module(RuntimeError("secret detail")),)
    )
    async with Client(server) as client:
        result = await client.call_tool("fail", {})
    assert result.is_error and "secret detail" not in result.content[0].text


def test_env_file_precedence(tmp_path, monkeypatch):
    env_file = tmp_path / "mcp.env"
    env_file.write_text(
        "# microscope settings\n"
        "PYTRIBEAM_MCP_MICROSCOPE_HOST='10.0.0.5'\n"
        "export PYTRIBEAM_MCP_MAX_TIER=1\n"
        "OTHER_TOOL_SECRET=ignored\n"
    )
    monkeypatch.setenv("PYTRIBEAM_MCP_MAX_TIER", "0")  # real env beats the file
    cfg = ServerConfig.from_args(
        ["--env-file", str(env_file), "--project-dir", str(tmp_path)]
    )
    assert (cfg.microscope_host, cfg.max_tier) == ("10.0.0.5", 0)
    cfg = ServerConfig.from_args(
        [
            "--env-file",
            str(env_file),
            "--microscope-host",
            "cli-host",
            "--project-dir",
            str(tmp_path),
        ]
    )
    assert cfg.microscope_host == "cli-host"  # flag beats everything
