#!/usr/bin/python3
"""
MCP Server Configuration
========================

Everything that varies between sessions lives here, in one frozen object that
is built once at startup and never changes while the server runs.

Each setting is resolved in this order, first match wins:

1. Command-line flag (``--max-tier``)
2. Environment variable (``PYTRIBEAM_MCP_MAX_TIER``)
3. Env file (same variable names), from ``--env-file``,
   ``PYTRIBEAM_MCP_ENV_FILE``, or ``default_env_file()`` if it exists
4. The defaults below, which fail closed: tier 0 only, no microscope host.

The env file is read into a dict, not into ``os.environ``, so it never leaks
into AutoScript or anything else running in the process.

Tiers
-----
0. Observe: read state, compare states. Issues no commands.
1. Reversible parameters (contrast/brightness, HFW, view quad, ...).
2. Image acquisition, motion, device insertion/retraction.
3. Material removal.
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

MAX_TIER = 3
ENV_PREFIX = "PYTRIBEAM_MCP_"


def default_log_dir() -> Path:
    """Same location the GUI uses, so all pytribeam logs live together."""
    base = os.getenv("LOCALAPPDATA", os.path.expanduser("~/.local/share"))
    return Path(base) / "pytribeam" / "logs" / "mcp"


def default_env_file() -> Path:
    """Used when no env file is named explicitly, and only if it exists."""
    base = os.getenv("LOCALAPPDATA", os.path.expanduser("~/.local/share"))
    return Path(base) / "pytribeam" / "mcp.env"


def read_env_file(path: Path) -> dict:
    """Parse ``KEY=VALUE`` lines. Blank lines, ``#`` comments, an ``export``
    prefix, and surrounding quotes are allowed. Only ``PYTRIBEAM_MCP_*`` keys
    are kept, so a shared .env file can't change anything else."""
    values = {}
    for n, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.removeprefix("export ").partition("=")
        if not sep:
            raise ValueError(f"{path}:{n}: expected KEY=VALUE, got {raw!r}")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key.startswith(ENV_PREFIX):
            values[key] = value
    return values


def _env_file_values(explicit: Optional[Path]) -> dict:
    path = explicit or os.getenv(ENV_PREFIX + "ENV_FILE")
    if path:
        return read_env_file(Path(path))  # named explicitly: must exist
    if default_env_file().is_file():
        return read_env_file(default_env_file())
    return {}


@dataclass(frozen=True)
class ServerConfig:
    """Session configuration for the MCP server."""

    max_tier: int = 0
    microscope_host: Optional[str] = None
    microscope_port: Optional[int] = None
    log_dir: Path = field(default_factory=default_log_dir)
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if not 0 <= self.max_tier <= MAX_TIER:
            raise ValueError(f"max_tier must be 0-{MAX_TIER}, got {self.max_tier}")
        if self.microscope_port is not None and not 0 < self.microscope_port < 65536:
            raise ValueError(f"microscope_port out of range: {self.microscope_port}")
        if not isinstance(logging.getLevelName(self.log_level.upper()), int):
            raise ValueError(f"Unknown log level: {self.log_level}")

    @classmethod
    def from_args(cls, argv: Optional[Sequence[str]] = None) -> "ServerConfig":
        """Build a config from CLI flags, with environment variables as defaults."""
        pre = argparse.ArgumentParser(add_help=False)
        pre.add_argument("--env-file", type=Path)
        known, _ = pre.parse_known_args(argv)
        file_values = _env_file_values(known.env_file)

        def _env(name: str, default=None):
            key = ENV_PREFIX + name
            return os.getenv(key, file_values.get(key, default))

        port = _env("MICROSCOPE_PORT")
        p = argparse.ArgumentParser(
            prog="pytribeam_mcp",
            description="pytribeam MCP server (stdio). Exposes microscope "
            "capabilities to an agent, gated by tier.",
        )
        p.add_argument("--env-file", type=Path,
                       help="File of PYTRIBEAM_MCP_* settings (default: "
                       f"{default_env_file()}, if it exists).")
        p.add_argument("--max-tier", type=int, default=int(_env("MAX_TIER", 0)),
                       help="Highest capability tier to expose (default: 0).")
        p.add_argument("--microscope-host", default=_env("MICROSCOPE_HOST"),
                       help="Host name or IP of the microscope PC.")
        p.add_argument("--microscope-port", type=int,
                       default=int(port) if port else None,
                       help="AutoScript port, if not the default.")
        p.add_argument("--log-dir", type=Path, default=_env("LOG_DIR"),
                       help="Directory for server and audit logs.")
        p.add_argument("--log-level", default=_env("LOG_LEVEL", "INFO"),
                       help="Level for the server log file (default: INFO).")
        a = p.parse_args(argv)
        return cls(
            max_tier=a.max_tier,
            microscope_host=a.microscope_host,
            microscope_port=a.microscope_port,
            log_dir=Path(a.log_dir) if a.log_dir else default_log_dir(),
            log_level=a.log_level.upper(),
        )

    def summary(self) -> dict:
        """JSON-safe view, for logs and diagnostics."""
        return {
            "max_tier": self.max_tier,
            "microscope_host": self.microscope_host,
            "microscope_port": self.microscope_port,
            "log_dir": str(self.log_dir),
            "log_level": self.log_level,
        }
