#!/usr/bin/python3
"""
MCP Server Configuration
========================

Everything that varies between sessions lives here, in one frozen object that
is built once at startup and never changes while the server runs.

Values come from command-line flags, falling back to ``PYTRIBEAM_MCP_*``
environment variables, falling back to the defaults below. Defaults fail
closed: tier 0 only, and no microscope host.

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


def _env(name: str, default=None):
    return os.getenv(ENV_PREFIX + name, default)


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
        port = _env("MICROSCOPE_PORT")
        p = argparse.ArgumentParser(
            prog="pytribeam_mcp",
            description="pytribeam MCP server (stdio). Exposes microscope "
            "capabilities to an agent, gated by tier.",
        )
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
