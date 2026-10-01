#!/usr/bin/python3
"""
pytribeam MCP Server
====================

Builds the MCP server from a :class:`~pytribeam.mcp.config.ServerConfig` and
runs it over stdio. The agent host (Claude Code, the Inspector, a local-model
harness) launches this as a subprocess::

    python -m pytribeam.mcp --max-tier 0 --microscope-host 192.168.0.10

stdout carries the MCP protocol. Nothing in this process may print to it;
logs go to stderr and to files under ``config.log_dir``
(``<project_dir>/logs``).

Do not import ``pytribeam.types``, ``pytribeam.utilities``, or AutoScript at
module level here. The server must start, and be testable, on a machine with no
microscope software installed; capabilities that need the hardware import it
themselves.
"""

from __future__ import annotations

import datetime
import functools
import inspect
import json
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from typing import Callable, Optional, Sequence

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from pytribeam import __version__
from pytribeam.mcp.capabilities import diagnostics, state
from pytribeam.mcp.config import ServerConfig

# Hand-written and reviewed. A capability module that is not listed here is
# never loaded, whatever the configuration says. Fail closed.
CAPABILITY_MODULES = (diagnostics, state)

INSTRUCTIONS = (
    "You are connected to a FIB-SEM (TriBeam) through pytribeam. Only the "
    "tools you can see are permitted in this session. When a tool refuses a "
    "request, report the reason to the user; do not try to reach the same "
    "result another way."
)

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
        config.log_dir / "server.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
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


def _audited(fn: Callable, tier: int) -> Callable:
    """Wrap a tool so every call writes one audit record, success or failure.

    Error contract for capabilities:

    * Raise ``ToolError`` for anything the agent should read and act on: a
      refusal, an out-of-range value, an interlock. Its message is returned to
      the agent verbatim, so write it for the agent.
    * Any other exception is a bug or a hardware fault. The SDK reports it to
      the agent only as a generic failure; the traceback goes to server.log.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        record = {
            "time": datetime.datetime.now().astimezone().isoformat(),
            "tool": fn.__name__,
            "tier": tier,
            "args": kwargs,
        }
        start = time.perf_counter()
        try:
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
            return result
        finally:
            record["ms"] = round((time.perf_counter() - start) * 1000, 1)
            level = logging.INFO if record["ok"] else logging.WARNING
            audit.log(level, json.dumps(record, default=str))

    return wrapper


# ---------------------------------------------------------------------------
# Server construction
# ---------------------------------------------------------------------------
def _adder(server: MCPServer, tier: int) -> Callable:
    """The ``add`` function handed to one capability module's ``register``."""

    def add(fn: Callable, *, read_only: bool = False, destructive: bool = False) -> None:
        server.add_tool(
            _audited(fn, tier),
            description=inspect.cleandoc(fn.__doc__ or ""),
            annotations=ToolAnnotations(
                read_only_hint=read_only, destructive_hint=destructive
            ),
        )
        log.info("registered tool %s (tier %d)", fn.__name__, tier)

    return add


def build_server(config: ServerConfig, modules=CAPABILITY_MODULES) -> MCPServer:
    """Create the server and register every module at or below ``config.max_tier``."""
    server = MCPServer(name="pytribeam", version=__version__, instructions=INSTRUCTIONS)
    for module in modules:
        if module.TIER > config.max_tier:
            log.info("skipping %s (tier %d > max %d)",
                     module.__name__, module.TIER, config.max_tier)
            continue
        module.register(_adder(server, module.TIER), config)
    return server


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Console entry point: parse config, set up logging, serve over stdio."""
    config = ServerConfig.from_args(argv)
    setup_logging(config)
    log.info("starting pytribeam MCP server %s with %s", __version__, config.summary())
    server = build_server(config)
    try:
        server.run("stdio")
    finally:
        log.info("server stopped")


if __name__ == "__main__":
    main()
