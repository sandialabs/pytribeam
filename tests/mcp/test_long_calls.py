"""Long tool calls: the microscope lock, busy refusals, and progress. No AutoScript."""

## python standard libraries
import json
import threading
import time
import types

# 3rd party libraries
import anyio
import pytest

mcp = pytest.importorskip("mcp")  # the mcp extra needs Python >= 3.10
from mcp import Client  # noqa: E402
from mcp.server.mcpserver import Context  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

# local libraries
from pytribeam.mcp.capabilities import diagnostics  # noqa: E402
from pytribeam.mcp.config import ServerConfig  # noqa: E402
from pytribeam.mcp.connection import MicroscopeConnection  # noqa: E402
from pytribeam.mcp.server import build_server  # noqa: E402

pytestmark = pytest.mark.detached


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def config(tmp_path):
    return ServerConfig(project_dir=tmp_path)


def _slow_module(release: threading.Event, started: threading.Event):
    """A hardware tool that runs until *release* is set, declaring 120 s."""

    def register(add, config, connection):
        def acquire() -> str:
            """Pretend to take a long image."""
            connection.expect(120)
            started.set()
            release.wait(10)
            return "done"

        def quick() -> str:
            """Pretend to read the microscope."""
            return "read"

        add(acquire)
        add(quick)

    return types.SimpleNamespace(__name__="slow", TIER=0, register=register)


@pytest.mark.anyio
async def test_long_call_does_not_block_file_tools(config):
    release, started = threading.Event(), threading.Event()
    server = build_server(config, modules=(diagnostics, _slow_module(release, started)))
    results = {}

    async with Client(server) as client:

        async def run_acquire():
            results["acquire"] = await client.call_tool("acquire", {})

        async with anyio.create_task_group() as tg:
            tg.start_soon(run_acquire)
            await anyio.to_thread.run_sync(started.wait, 5)

            t0 = time.monotonic()
            info = await client.call_tool("get_server_info", {})
            results["info_s"] = time.monotonic() - t0

            t0 = time.monotonic()
            busy = await client.call_tool("quick", {})
            results["busy_s"] = time.monotonic() - t0
            release.set()

    assert not info.is_error
    assert results["info_s"] < 1.0  # answered while acquire held the microscope
    assert busy.is_error and results["busy_s"] < 1.0  # refused at once, not after 60 s
    message = busy.content[0].text
    assert "acquire has been running" in message and "s left" in message
    assert not results["acquire"].is_error


def test_short_waits_queue_instead_of_failing(config):
    """Parallel quick calls wait for each other within the grace period."""
    conn = MicroscopeConnection(config)
    order = []

    def call(name, hold_s):
        with conn.hold(name):
            order.append(name)
            time.sleep(hold_s)

    first = threading.Thread(target=call, args=("first", 0.3))
    first.start()
    time.sleep(0.05)
    call("second", 0)  # waits ~0.25 s, does not raise
    first.join()
    assert order == ["first", "second"]


def test_unknown_duration_is_refused_after_the_grace_period(config):
    conn = MicroscopeConnection(config)
    release = threading.Event()

    def hold():
        with conn.hold("mystery"):
            release.wait(5)

    thread = threading.Thread(target=hold)
    thread.start()
    time.sleep(0.05)
    t0 = time.monotonic()
    with pytest.raises(ToolError, match="mystery has been running"):
        with conn.hold("second", grace_s=0.3):
            pass
    assert 0.25 < time.monotonic() - t0 < 1.0
    release.set()
    thread.join()


def test_lock_is_released_after_an_error(config):
    conn = MicroscopeConnection(config)
    with pytest.raises(ValueError):
        with conn.hold("first"):
            raise ValueError
    with conn.hold("second"):
        assert conn.busy.tool == "second"
    assert conn.busy is None


def _progress_module():
    def register(add, config, connection):
        def stepped(ctx: Context) -> str:
            """Report three steps of progress."""
            for i in range(3):
                anyio.from_thread.run(ctx.report_progress, i + 1, 3, f"step {i + 1}")
            return "done"

        add(stepped)

    return types.SimpleNamespace(__name__="progress", TIER=0, register=register)


@pytest.mark.anyio
async def test_context_reaches_tools_through_the_audit_wrapper(config):
    seen = []

    async def on_progress(progress, total, message):
        seen.append((progress, total, message))

    async with Client(build_server(config, modules=(_progress_module(),))) as client:
        tool = (await client.list_tools()).tools[0]
        result = await client.call_tool("stepped", {}, progress_callback=on_progress)

    assert "ctx" not in tool.input_schema.get("properties", {})
    assert not result.is_error
    assert seen == [(1, 3, "step 1"), (2, 3, "step 2"), (3, 3, "step 3")]


@pytest.mark.anyio
async def test_audit_record_omits_the_context(config, caplog):
    caplog.set_level("INFO", logger="pytribeam.mcp.audit")
    async with Client(build_server(config, modules=(_progress_module(),))) as client:
        await client.call_tool("stepped", {})
    record = json.loads(caplog.records[-1].getMessage())
    assert record["tool"] == "stepped" and record["args"] == {}
