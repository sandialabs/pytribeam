#!/usr/bin/python3
"""
Microscope Connection
=====================

The one microscope connection shared by every capability module.
``build_server`` creates a single :class:`MicroscopeConnection` and hands it
to each module's ``register``, so tools from different modules reuse one
AutoScript client rather than opening their own.

The connection opens on first use, not at startup, so the server starts (and
its tier 0 diagnostics answer) even when the microscope is unreachable.
AutoScript is imported only then.
"""

from __future__ import annotations

import contextlib
import sys
import threading
from typing import Any, Dict, Iterator

from mcp.server.mcpserver.exceptions import ToolError


def _connect(config) -> Any:
    """Return a connected microscope."""
    from pytribeam import types as tbt
    from pytribeam import utilities

    microscope = tbt.Microscope()
    utilities.connect_microscope(
        microscope,
        quiet_output=True,
        connection_host=config.microscope_host,
        connection_port=config.microscope_port,
    )
    return microscope


class MicroscopeConnection:
    """A lazily opened, lock-protected microscope connection.

    ``cache`` holds per-connection results, such as the detector lists, that
    are expensive or intrusive to compute and do not change while connected.
    It is cleared whenever the connection is dropped.
    """

    def __init__(self, config) -> None:
        self.config = config
        self.cache: Dict[Any, Any] = {}
        self._microscope = None
        # Re-entrant: a tool may call a helper that also uses the connection.
        self._lock = threading.RLock()

    @property
    def host(self) -> str:
        return self.config.microscope_host or "the default host"

    @property
    def connected(self) -> bool:
        """Whether a connection is open. Never connects."""
        return self._microscope is not None

    def reset(self) -> None:
        """Drop the connection and the cache; the next use reconnects."""
        with self._lock:
            self._microscope = None
            self.cache.clear()

    @contextlib.contextmanager
    def use(self) -> Iterator[Any]:
        """Yield the connected microscope, connecting first if needed.

        stdout is redirected to stderr for the duration, because stdout
        carries the MCP protocol and AutoScript prints to it. A
        ``ConnectionError`` escaping the block drops the connection, so the
        next call reconnects.
        """
        with self._lock, contextlib.redirect_stdout(sys.stderr):
            if self._microscope is None:
                try:
                    self._microscope = _connect(self.config)
                except Exception as exc:
                    raise ToolError(
                        f"Could not connect to the microscope at {self.host}: {exc}"
                    ) from exc
            try:
                yield self._microscope
            except ConnectionError:
                self.reset()
                raise
