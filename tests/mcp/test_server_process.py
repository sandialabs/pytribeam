"""The server as a separate process, over its real transports. No microscope.

The other MCP tests run the server inside the test process. These start
``python -m pytribeam.mcp`` the way an agent host does, so they cover what
those cannot: the entry point, logging setup, that nothing but protocol
reaches stdout, and the HTTP transport with its bearer-token gate.

There is no microscope here, so the stdout check covers the server's own
start-up and tool calls, not AutoScript's output while connecting; that is
redirected by ``MicroscopeConnection.use`` and covered by ``test_connection``.
"""

## python standard libraries
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# 3rd party libraries
import pytest

pytest.importorskip("mcp")  # the mcp extra needs Python >= 3.10
import httpx2  # noqa: E402
from mcp import Client, StdioServerParameters  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

pytestmark = [pytest.mark.detached, pytest.mark.anyio]

SRC = str(Path(__file__).resolve().parents[2] / "src")
TOKEN = "t" * 40


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def env(tmp_path):
    """The server's environment: no PYTRIBEAM_MCP_* settings from the
    developer, and no default env file (it lives under LOCALAPPDATA)."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith("PYTRIBEAM_MCP_")}
    clean["LOCALAPPDATA"] = str(tmp_path / "localappdata")
    clean["PYTHONPATH"] = os.pathsep.join(filter(None, [SRC, clean.get("PYTHONPATH")]))
    return clean


async def test_stdio_entry_point(tmp_path, env, monkeypatch):
    # The SDK client logs and skips a stdout line that is not JSON-RPC, so a
    # stray print would pass unnoticed here but can break stricter clients.
    # Record every such line instead.
    import mcp.client.stdio as stdio

    bad_lines = []
    real_parse = stdio._parse_line

    def parse(line):
        message = real_parse(line)
        if isinstance(message, Exception):
            bad_lines.append(line)
        return message

    monkeypatch.setattr(stdio, "_parse_line", parse)
    project = tmp_path / "project"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "pytribeam.mcp", "--project-dir", str(project), "--max-tier", "2"],
        env=env,
    )
    async with Client(params) as client:
        instructions = client.instructions
        tools = {t.name for t in (await client.list_tools()).tools}
        result = await client.call_tool("ping", {"message": "over stdio"})

    assert bad_lines == []  # stdout carried only the protocol
    # The agent is told how to recover from a call it never saw finish.
    assert "get_recent_activity" in instructions and "interrupted" in instructions
    assert {"ping", "get_server_info", "collect_single_image"} <= tools
    assert "move_to_position" not in tools  # tier 4, above --max-tier
    assert json.loads(result.content[0].text)["echo"] == "over stdio"
    # The real entry point sets up logging and the project lock.
    audit = (project / "logs" / "audit.jsonl").read_text().splitlines()
    assert any(json.loads(line)["tool"] == "ping" for line in audit)
    assert (project / ".lock").exists()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def http_server(tmp_path, env):
    """The server over HTTP on a free loopback port; yields its base URL."""
    port = _free_port()
    env = {**env, "PYTRIBEAM_MCP_HTTP_TOKEN": TOKEN}
    log = open(tmp_path / "server.stderr", "w")
    process = subprocess.Popen(
        [
            sys.executable, "-m", "pytribeam.mcp",
            "--transport", "http",
            "--http-port", str(port),
            "--project-dir", str(tmp_path / "project"),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=log,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):  # wait for it to come up
            if process.poll() is not None:
                raise RuntimeError((tmp_path / "server.stderr").read_text())
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        log.close()


async def test_http_transport_and_token_gate(http_server):
    async with httpx2.AsyncClient() as raw:
        health = await raw.get(f"{http_server}/healthz")
        no_token = await raw.post(f"{http_server}/mcp", json={})
        wrong_token = await raw.post(
            f"{http_server}/mcp", json={}, headers={"Authorization": "Bearer nope"}
        )
    assert health.status_code == 200 and health.json() == {"status": "ok"}
    assert no_token.status_code == 401 and wrong_token.status_code == 401

    authed = httpx2.AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"})
    async with authed, Client(streamable_http_client(f"{http_server}/mcp", http_client=authed)) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        result = await client.call_tool("ping", {"message": "over http"})
    assert tools == {
        "ping", "get_server_info", "check_connection", "reconnect",
        "get_recent_activity", "list_states", "list_images", "view_image",
    }  # tier 0 by default
    assert json.loads(result.content[0].text)["echo"] == "over http"
