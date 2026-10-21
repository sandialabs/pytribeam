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

It also serializes tool calls. The server's audit wrapper calls :meth:`hold`
around every tool that uses the microscope, so one such call runs at a time.
While it runs, :attr:`busy` says which tool it is and, if the tool called
:meth:`expect`, when it should finish, so a call that has to wait can tell the
agent what it is waiting for.
"""

from __future__ import annotations

import contextlib
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional

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


# A call that finds the microscope busy waits this long at most, and only if
# the running call is expected to finish within it. Otherwise it is refused at
# once, so the agent hears why instead of hanging until the client times out.
BUSY_GRACE_S = 15.0


@dataclass
class Busy:
    """The tool call currently holding the microscope."""

    tool: str
    started: float  # time.monotonic()
    expected_s: Optional[float] = None

    def remaining_s(self) -> Optional[float]:
        if self.expected_s is None:
            return None
        return max(0.0, self.expected_s - (time.monotonic() - self.started))

    def describe(self) -> str:
        elapsed = time.monotonic() - self.started
        text = f"{self.tool} has been running for {elapsed:.0f} s"
        remaining = self.remaining_s()
        if remaining is not None:
            text += f", about {remaining:.0f} s left"
        return text


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
        # One tool call at a time; see hold().
        self._tool_lock = threading.Lock()
        self.busy: Optional[Busy] = None

    @property
    def host(self) -> str:
        return self.config.microscope_host or "the default host"

    @property
    def connected(self) -> bool:
        """Whether a connection is open. Never connects."""
        return self._microscope is not None

    @contextlib.contextmanager
    def hold(self, tool: str, grace_s: float = BUSY_GRACE_S) -> Iterator[float]:
        """Run one tool call with the microscope to itself; yields the wait in s.

        If another call holds it, wait while that call is expected to finish
        within *grace_s*, polling so a call that starts later and is long is
        noticed. Refuse with ``ToolError`` when the wait would be longer or is
        unknown beyond *grace_s*.
        """
        start = time.monotonic()
        while not self._tool_lock.acquire(timeout=0.1):
            busy = self.busy
            waited = time.monotonic() - start
            remaining = busy.remaining_s() if busy else None
            too_long = remaining is not None and remaining > grace_s - waited
            if too_long or waited >= grace_s:
                raise ToolError(
                    "The microscope is busy: "
                    f"{busy.describe() if busy else 'another tool call is running'}. "
                    "Wait and call this tool again; tools that do not use the "
                    "microscope (e.g. list_images, get_server_info) still work."
                )
        self.busy = Busy(tool=tool, started=time.monotonic())
        try:
            yield time.monotonic() - start
        finally:
            self.busy = None
            self._tool_lock.release()

    def expect(self, seconds: float) -> None:
        """Declare how long the running tool call should take from now."""
        busy = self.busy
        if busy is not None:
            busy.expected_s = (time.monotonic() - busy.started) + seconds

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
