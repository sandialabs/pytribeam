#!/usr/bin/python3
"""
pytribeam MCP Server
====================

Builds the MCP server from a :class:`~pytribeam.mcp.config.ServerConfig` and
runs it over one of two transports:

* ``stdio`` (default). The agent host (Claude Code, the Inspector, a
  local-model harness) launches this as a subprocess::

      python -m pytribeam.mcp --max-tier 0 --microscope-host 192.168.0.10

  stdout carries the MCP protocol. Nothing in this process may print to it;
  logs go to stderr and to files under ``config.log_dir``.

* ``http`` (Streamable HTTP). The server runs on its own, next to AutoScript,
  and agents connect to it over the network, e.g. Claude Code in a WSL/Podman
  container on the same PC::

      pytribeam_mcp --transport http --env-file C:\\path\\to\\.env

  Every request except ``/healthz`` must carry
  ``Authorization: Bearer <PYTRIBEAM_MCP_HTTP_TOKEN>``. The tier limit is set
  here, on the microscope PC, and cannot be changed by the client.

Do not import ``pytribeam.types``, ``pytribeam.utilities``, or AutoScript at
module level here. The server must start, and be testable, on a machine with no
microscope software installed; capabilities that need the hardware import it
themselves.
"""

from __future__ import annotations

import datetime
import functools
import hmac
import inspect
import json
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from typing import Callable, Optional, Sequence

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse  # starlette ships with the mcp SDK

from pytribeam import __version__
from pytribeam.mcp import audit as audit_log
from pytribeam.mcp import project_lock
from pytribeam.mcp.capabilities import (
    diagnostics,
    hardware,
    imaging,
    records,
    stage,
    state,
    views,
)
from pytribeam.mcp.config import LOOPBACK_HOSTS, ServerConfig
from pytribeam.mcp.connection import MicroscopeConnection

# Hand-written and reviewed. A capability module that is not listed here is
# never loaded, whatever the configuration says. Fail closed.
CAPABILITY_MODULES = (diagnostics, records, state, hardware, views, imaging, stage)

INSTRUCTIONS = (
    "You are connected to a FIB-SEM (TriBeam) through pytribeam. Only the "
    "tools you can see are permitted in this session. When a tool refuses a "
    "request, report the reason to the user; do not try to reach the same "
    "result another way. Tools are grouped into tiers: 0 diagnostics, 1 UI "
    "changes, 2 electron-beam exposure, 3 insertable detectors, 4 stage "
    "movement, 5 ion beam and material removal. The operator sets the highest "
    "tier this server exposes; if a task needs a higher tier, ask the user to "
    "raise it rather than working around the limit."
)

# --- HTTP transport constants ----------------------------------------------
MCP_PATH = "/mcp"  # SDK default Streamable HTTP endpoint path
HEALTH_PATH = "/healthz"  # unauthenticated liveness check, returns no data

log = logging.getLogger("pytribeam.mcp")
audit = logging.getLogger("pytribeam.mcp.audit")



# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging(config: ServerConfig) -> None:
    """Server log (rotating, human-readable), audit log (JSON lines), stderr."""
    config.log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    server_file = RotatingFileHandler(
        config.log_dir / "server.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    server_file.setLevel(config.log_level)
    server_file.setFormatter(fmt)

    # One JSON object per line, never rotated away: this is the record of what
    # the agent did. Archive it deliberately rather than letting it roll over.
    audit_file = logging.FileHandler(config.log_dir / "audit.jsonl", encoding="utf-8")
    audit_file.setFormatter(logging.Formatter("%(message)s"))
    audit.addHandler(audit_file)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    console.setFormatter(fmt)

    root = logging.getLogger("pytribeam")
    root.setLevel(logging.DEBUG)
    root.addHandler(server_file)
    root.addHandler(console)
    root.propagate = False  # keep our records out of any handlers the SDK installs


# Tools that run even while the connection has a fault: they are how the
# operator clears it. Everything else above tier 0 is refused.
FAULT_EXEMPT = ("clear_fault",)


def _audited(
    fn: Callable,
    tier: int,
    connection: Optional[MicroscopeConnection] = None,
    serialize: bool = True,
) -> Callable:
    """Wrap a tool so every call writes one audit record, success or failure.

    Error contract for capabilities:

    * Raise ``ToolError`` for anything the agent should read and act on: a
      refusal, an out-of-range value, an interlock. Its message is returned to
      the agent verbatim, so write it for the agent.
    * Any other exception is a bug or a hardware fault. The SDK reports it to
      the agent only as a generic failure; the traceback goes to server.log.

    Tools that use the microscope are serialized with ``connection.hold``,
    one call at a time across every transport and client. The SDK runs sync
    tools in worker threads, so a tool registered with ``serialize=False`` (one
    that reads only files or config) runs alongside them, even during a
    minutes-long acquisition.

    While ``connection.fault`` is set, every tool above tier 0 except those in
    :data:`FAULT_EXEMPT` is refused before it runs. The check is here, not in
    each tool, so no tool can forget it.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        op_id = audit_log.new_op_id()
        record = {
            "time": datetime.datetime.now().astimezone().isoformat(),
            "op_id": op_id,
            "tool": fn.__name__,
            "tier": tier,
        }
        # The SDK passes the request Context in by keyword; it is not an
        # argument the agent chose, and does not serialize.
        record["args"] = {
            k: v for k, v in kwargs.items() if not isinstance(v, Context)
        }
        if tier > 0:
            # Written before the tool runs: if the process dies mid-action,
            # this is the record that it started.
            audit.info(json.dumps({**record, "event": "started"}, default=str))
        audit_log.set_current_op_id(op_id)
        start = time.perf_counter()
        try:
            fault = connection.fault if connection is not None else None
            if fault and tier > 0 and fn.__name__ not in FAULT_EXEMPT:
                raise ToolError(
                    f"Refused: the microscope may not be in the state this server "
                    f"left it in ({fault}). Ask the operator to check the "
                    "microscope, then call clear_fault. Tier 0 tools still work."
                )
            if connection is None or not serialize:
                result = fn(*args, **kwargs)
            else:
                with connection.hold(fn.__name__) as waited_s:
                    record["wait_ms"] = round(waited_s * 1000, 1)
                    result = fn(*args, **kwargs)
        except ToolError as exc:
            record.update(ok=False, refused=True, error=str(exc))
            raise
        except Exception as exc:
            record.update(ok=False, refused=False, error=f"{type(exc).__name__}: {exc}")
            log.exception("tool %s failed unexpectedly", fn.__name__)
            raise
        else:
            record["ok"] = True
            if fn.__name__ == "clear_fault" and isinstance(result, dict):
                # The operator's decision to resume is part of the record.
                record["cleared_fault"] = result.get("fault")
            return result
        finally:
            audit_log.set_current_op_id(None)
            record["event"] = "ended"
            record["ms"] = round((time.perf_counter() - start) * 1000, 1)
            level = logging.INFO if record.get("ok") else logging.WARNING
            audit.log(level, json.dumps(record, default=str))

    return wrapper


# ---------------------------------------------------------------------------
# Server construction
# ---------------------------------------------------------------------------
def _adder(
    server: MCPServer, tier: int, connection: MicroscopeConnection
) -> Callable:
    """The ``add`` function handed to one capability module's ``register``.

    Pass ``uses_microscope=False`` for a tool that never touches the hardware,
    so it does not wait behind (or block) tools that do.
    """

    def add(
        fn: Callable,
        *,
        read_only: bool = False,
        destructive: bool = False,
        uses_microscope: bool = True,
    ) -> None:
        server.add_tool(
            _audited(fn, tier, connection, serialize=uses_microscope),
            description=inspect.cleandoc(fn.__doc__ or ""),
            annotations=ToolAnnotations(
                read_only_hint=read_only, destructive_hint=destructive
            ),
        )
        log.info("registered tool %s (tier %d)", fn.__name__, tier)

    return add


def build_server(config: ServerConfig, modules=CAPABILITY_MODULES) -> MCPServer:
    """Create the server and register every module at or below ``config.max_tier``.

    Every module receives the same :class:`MicroscopeConnection`, so all tools
    share one microscope connection.
    """
    server = MCPServer(name="pytribeam", version=__version__, instructions=INSTRUCTIONS)
    connection = MicroscopeConnection(config)
    for module in modules:
        if module.TIER > config.max_tier:
            log.info(
                "skipping %s (tier %d > max %d)",
                module.__name__,
                module.TIER,
                config.max_tier,
            )
            continue
        module.register(_adder(server, module.TIER, connection), config, connection)
    return server


# ---------------------------------------------------------------------------
# HTTP transport
# ---------------------------------------------------------------------------
class BearerTokenASGI:
    """Pure-ASGI bearer-token gate (safe for SSE streaming, unlike BaseHTTPMiddleware).

    * Non-HTTP scopes (notably ``lifespan``) pass straight through so the SDK's
      session manager starts and stops correctly.
    * ``/healthz`` answers without auth and reveals nothing but liveness.
    * Everything else needs ``Authorization: Bearer <token>``.
    """

    def __init__(self, app, token: str):
        self._app = app
        self._expected = f"Bearer {token}".encode("utf-8")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        if scope.get("path") == HEALTH_PATH:
            await JSONResponse({"status": "ok"})(scope, receive, send)
            return

        supplied = b""
        for name, value in scope.get("headers", []):
            if name == b"authorization":  # ASGI header names are lower-case bytes
                supplied = value
                break

        # Constant-time comparison so response timing does not leak the token
        if not hmac.compare_digest(supplied, self._expected):
            client = scope.get("client") or ("?", 0)
            log.warning(
                "rejected unauthenticated %s %s from %s",
                scope.get("method"), scope.get("path"), client[0],
            )
            # No WWW-Authenticate header on purpose: some MCP clients treat it
            # as a cue to start an OAuth flow, which this server does not offer.
            await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
            return

        await self._app(scope, receive, send)


def _allowed_host_patterns(config: ServerConfig) -> list[str]:
    """Host-header patterns accepted by the SDK's DNS-rebinding protection."""
    patterns = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    if config.http_host not in LOOPBACK_HOSTS:  # wildcards are refused by ServerConfig
        patterns.append(f"{config.http_host}:*")  # e.g. the vEthernet (WSL) adapter IP
    for host in config.http_allowed_hosts:
        patterns.append(host if ":" in host else f"{host}:*")  # add any-port wildcard
    return patterns


def _build_http_app(server: MCPServer, config: ServerConfig):
    """Get the SDK's Streamable HTTP ASGI app, passing Host security if supported."""
    factory = getattr(server, "streamable_http_app", None)
    if factory is None:
        raise SystemExit(
            "This version of the mcp SDK has no MCPServer.streamable_http_app(); "
            "upgrade the 'mcp' package to use --transport http."
        )

    kwargs = {}
    if "transport_security" in inspect.signature(factory).parameters:
        from mcp.server.transport_security import TransportSecuritySettings

        hosts = _allowed_host_patterns(config)
        kwargs["transport_security"] = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
            allowed_origins=[f"http://{h}" for h in hosts],  # browsers only (e.g. Inspector)
        )
        log.info("HTTP Host allowlist: %s", hosts)
    elif config.http_allowed_hosts:
        log.warning(
            "This SDK's streamable_http_app() does not accept transport_security; "
            "http_allowed_hosts is ignored. Connect to the server via localhost."
        )
    return factory(**kwargs)


def serve_http(server: MCPServer, config: ServerConfig) -> None:
    """Run the server over Streamable HTTP behind the bearer-token gate."""
    import uvicorn  # lazy: only needed for HTTP mode

    # ServerConfig already enforces this; checked again here as defense in
    # depth in case serve_http is ever called with a hand-built config.
    if not config.http_token:
        raise SystemExit("refusing to serve HTTP without PYTRIBEAM_MCP_HTTP_TOKEN")

    # ServerConfig refuses wildcard binds, and non-loopback ones without the
    # operator's host-only opt-in; record that opt-in when it was given.
    if config.http_host not in LOOPBACK_HOSTS:
        log.warning(
            "binding to non-loopback address %s on the operator's statement "
            "(--allow-host-only-http) that it is a host-only adapter; the bearer "
            "token is sent in plain text",
            config.http_host,
        )

    app = BearerTokenASGI(_build_http_app(server, config), config.http_token)
    url = f"http://{config.http_host}:{config.http_port}{MCP_PATH}"
    log.info("serving MCP over Streamable HTTP at %s", url)
    print(f"pytribeam MCP listening on {url} (health: {HEALTH_PATH})", file=sys.stderr)

    # A single process means one microscope connection and one safety state.
    # lifespan="on" makes startup fail loudly if the SDK session manager cannot start.
    uvicorn.run(
        app, host=config.http_host, port=config.http_port, lifespan="on", log_level="info"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> None:
    """Console entry point: parse config, set up logging, serve over stdio or HTTP."""
    config = ServerConfig.from_args(argv)  # all settings, incl. transport, in one place
    try:
        # One server per project directory. Keep this reference for the life
        # of the process: if the file object is dropped, it closes and the
        # lock is released.
        lock = project_lock.acquire(config.project_dir)  # noqa: F841 (held, not read)
    except project_lock.ProjectLocked as exc:
        raise SystemExit(str(exc)) from exc
    setup_logging(config)
    log.info("starting pytribeam MCP server %s with %s", __version__, config.summary())
    log.info("session %s; any fault from an earlier session is cleared by this restart",
             audit_log.SESSION_ID)
    for op in audit_log.interrupted(audit_log.read(config.log_dir / "audit.jsonl")):
        log.warning(
            "an earlier session stopped during %s (op %s, %s); the microscope may "
            "be part way through it",
            op.get("tool"), op.get("op_id"), op.get("time"),
        )
    server = build_server(config)
    try:
        if config.transport == "http":
            serve_http(server, config)
        else:
            server.run("stdio")
    finally:
        log.info("server stopped")


if __name__ == "__main__":
    main()
