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
4. The defaults below, which fail closed: tier 0 only, no microscope host,
   stdio transport, HTTP bound to loopback only.

An empty value at any level counts as unset and falls through to the next.

The env file is read into a dict, not into ``os.environ``, so it never leaks
into AutoScript or anything else running in the process.

The HTTP bearer token (``PYTRIBEAM_MCP_HTTP_TOKEN``) can only come from the
environment or the env file, never from a command-line flag, so it does not
show up in process listings or shell history. It is excluded from ``repr()``
and ``summary()``.

Tiers
-----
0. Observe: reads the microscope; never changes what it is doing.
1. Imaging: changes beam, detector, and scan settings and acquires images.
2. Reserved: nothing assigned yet.
3. Stage motion.
4. Material removal and other high-risk operations. Not yet designed.
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

# Tier number -> one-line meaning, reported by get_server_info.
TIERS = {
    0: "Observe: reads the microscope; never changes what it is doing.",
    1: "Imaging: changes beam, detector, and scan settings and acquires images.",
    2: "Reserved: nothing assigned yet.",
    3: "Stage motion.",
    4: "Material removal and other high-risk operations. Not yet designed.",
}
MAX_TIER = 4
ENV_PREFIX = "PYTRIBEAM_MCP_"

# --- Transport ---------------------------------------------------------------
TRANSPORTS = ("stdio", "http")
DEFAULT_HTTP_HOST = "127.0.0.1"  # loopback only unless explicitly widened
DEFAULT_HTTP_PORT = 8765
MIN_TOKEN_LENGTH = 32  # secrets.token_urlsafe(32) yields ~43 characters


def default_project_dir() -> Path:
    """Used when no project directory is configured."""
    base = os.getenv("LOCALAPPDATA", os.path.expanduser("~/.local/share"))
    return Path(base) / "pytribeam" / "mcp"


def default_env_file() -> Path:
    """Used when no env file is named explicitly, and only if it exists."""
    base = os.getenv("LOCALAPPDATA", os.path.expanduser("~/.local/share"))
    return Path(base) / "pytribeam" / "mcp.env"


def read_env_file(path: Path) -> dict:
    """Parse ``KEY=VALUE`` lines. Blank lines, ``#`` comments, an ``export``
    prefix, and surrounding quotes are allowed. Only ``PYTRIBEAM_MCP_*`` keys
    are kept, so a shared .env file can't change anything else.

    Read as ``utf-8-sig`` so a byte-order mark written by some Windows editors
    does not corrupt the first key (which would otherwise fail the prefix
    check and be dropped silently). ``splitlines()`` handles CRLF endings.
    """
    values = {}
    text = Path(path).read_text(encoding="utf-8-sig")
    for n, raw in enumerate(text.splitlines(), 1):
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


def _split_csv(value: Optional[str]) -> list:
    """'a, b,,c' -> ['a', 'b', 'c']; None or '' -> []."""
    return [item.strip() for item in (value or "").split(",") if item.strip()]


@dataclass(frozen=True)
class ServerConfig:
    """Session configuration for the MCP server.

    Everything the server writes goes under ``project_dir``::

        project_dir/
            logs/       server.log, audit.jsonl
            states/     s0001.yml, s0002.yml, ...  (see pytribeam.mcp.state)
            images/     i0001.tif, i0002.tif, ...
    """

    max_tier: int = 0
    microscope_host: Optional[str] = None
    microscope_port: Optional[int] = None
    project_dir: Path = field(default_factory=default_project_dir)
    log_level: str = "INFO"

    # Transport. stdio: launched as a subprocess by the agent host.
    # http: runs standalone; agents connect to http://<http_host>:<http_port>/mcp
    transport: str = "stdio"
    http_host: str = DEFAULT_HTTP_HOST
    http_port: int = DEFAULT_HTTP_PORT
    # Extra Host-header values accepted by the SDK's DNS-rebinding protection,
    # e.g. "host.containers.internal". Loopback names are always accepted.
    http_allowed_hosts: tuple[str, ...] = ()
    # Secret: kept out of repr() and summary(); not used for equality.
    http_token: Optional[str] = field(default=None, repr=False, compare=False)

    @property
    def log_dir(self) -> Path:
        return self.project_dir / "logs"

    @property
    def states_dir(self) -> Path:
        return self.project_dir / "states"

    @property
    def images_dir(self) -> Path:
        return self.project_dir / "images"

    def __post_init__(self) -> None:
        if not 0 <= self.max_tier <= MAX_TIER:
            raise ValueError(f"max_tier must be 0-{MAX_TIER}, got {self.max_tier}")
        if self.microscope_port is not None and not 0 < self.microscope_port < 65536:
            raise ValueError(f"microscope_port out of range: {self.microscope_port}")
        if not isinstance(logging.getLevelName(self.log_level.upper()), int):
            raise ValueError(f"Unknown log level: {self.log_level}")

        # Transport checks. argparse 'choices' does not validate defaults that
        # come from the environment, so the transport is checked here as well.
        if self.transport not in TRANSPORTS:
            raise ValueError(
                f"transport must be one of {TRANSPORTS}, got {self.transport!r}"
            )
        if not 0 < self.http_port < 65536:
            raise ValueError(f"http_port out of range: {self.http_port}")
        if self.transport == "http" and (
            not self.http_token or len(self.http_token) < MIN_TOKEN_LENGTH
        ):
            # Fail closed: never serve microscope control over HTTP without auth
            raise ValueError(
                f"{ENV_PREFIX}HTTP_TOKEN must be set (at least {MIN_TOKEN_LENGTH} "
                "characters) when transport is 'http'. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )

    @classmethod
    def from_args(cls, argv: Optional[Sequence[str]] = None) -> "ServerConfig":
        """Build a config from CLI flags, with environment variables as defaults."""
        pre = argparse.ArgumentParser(add_help=False)
        pre.add_argument("--env-file", type=Path)
        known, _ = pre.parse_known_args(argv)
        file_values = _env_file_values(known.env_file)

        def _env(name: str, default=None):
            key = ENV_PREFIX + name
            # 'or' (not a getenv default) so an empty real env var falls
            # through to the env file, matching "empty means unset".
            value = os.getenv(key) or file_values.get(key)
            return default if value in (None, "") else value

        port = _env("MICROSCOPE_PORT")
        http_port = _env("HTTP_PORT")
        p = argparse.ArgumentParser(
            prog="pytribeam_mcp",
            description="pytribeam MCP server. Exposes microscope capabilities "
            "to an agent, gated by tier, over stdio or Streamable HTTP.",
            epilog=f"HTTP mode requires {ENV_PREFIX}HTTP_TOKEN in the environment "
            "or env file (deliberately not accepted as a flag).",
        )
        p.add_argument(
            "--env-file",
            type=Path,
            help="File of PYTRIBEAM_MCP_* settings (default: "
            f"{default_env_file()}, if it exists).",
        )
        p.add_argument(
            "--max-tier",
            type=int,
            default=int(_env("MAX_TIER", 0)),
            help="Highest capability tier to expose (default: 0).",
        )
        p.add_argument(
            "--microscope-host",
            default=_env("MICROSCOPE_HOST"),
            help="Host name or IP of the microscope PC.",
        )
        p.add_argument(
            "--microscope-port",
            type=int,
            default=int(port) if port else None,
            help="AutoScript port, if not the default.",
        )
        p.add_argument(
            "--project-dir",
            type=Path,
            default=_env("PROJECT_DIR"),
            help="Directory for this project's logs and saved states "
            f"(default: {default_project_dir()}).",
        )
        p.add_argument(
            "--log-level",
            default=_env("LOG_LEVEL", "INFO"),
            help="Level for the server log file (default: INFO).",
        )

        # --- Transport flags ---
        p.add_argument(
            "--transport",
            choices=TRANSPORTS,
            default=_env("TRANSPORT", "stdio"),
            help="stdio: launched by the agent host (default). "
            "http: standalone Streamable HTTP server.",
        )
        p.add_argument(
            "--http-host",
            default=_env("HTTP_HOST", DEFAULT_HTTP_HOST),
            help=f"Address to bind in HTTP mode (default: {DEFAULT_HTTP_HOST}).",
        )
        p.add_argument(
            "--http-port",
            type=int,
            default=int(http_port) if http_port else DEFAULT_HTTP_PORT,
            help=f"Port to bind in HTTP mode (default: {DEFAULT_HTTP_PORT}).",
        )
        # default=None (not a list): with 'append', a non-empty default would be
        # extended by CLI values instead of replaced, breaking "CLI wins".
        p.add_argument(
            "--http-allowed-host",
            action="append",
            default=None,
            metavar="HOST",
            help="Extra Host header to accept, e.g. host.containers.internal. "
            "Repeatable; replaces PYTRIBEAM_MCP_HTTP_ALLOWED_HOSTS (comma-separated).",
        )
        a = p.parse_args(argv)

        allowed = (
            a.http_allowed_host
            if a.http_allowed_host is not None
            else _split_csv(_env("HTTP_ALLOWED_HOSTS"))
        )
        token = _env("HTTP_TOKEN")

        try:
            return cls(
                max_tier=a.max_tier,
                microscope_host=a.microscope_host,
                microscope_port=a.microscope_port,
                project_dir=Path(a.project_dir) if a.project_dir else default_project_dir(),
                log_level=a.log_level.upper(),
                transport=str(a.transport).strip().lower(),
                http_host=a.http_host,
                http_port=a.http_port,
                http_allowed_hosts=tuple(allowed),
                http_token=token.strip() if token else None,
            )
        except ValueError as exc:
            # Clean CLI error on stderr (exit code 2) instead of a traceback.
            # stderr is safe in stdio mode; stdout carries the protocol.
            p.error(str(exc))

    def summary(self) -> dict:
        """JSON-safe view, for logs and diagnostics. Never includes the token."""
        return {
            "max_tier": self.max_tier,
            "microscope_host": self.microscope_host,
            "microscope_port": self.microscope_port,
            "project_dir": str(self.project_dir),
            "log_level": self.log_level,
            "transport": self.transport,
            "http_host": self.http_host,
            "http_port": self.http_port,
            "http_allowed_hosts": list(self.http_allowed_hosts),
            "http_token_set": bool(self.http_token),
        }
