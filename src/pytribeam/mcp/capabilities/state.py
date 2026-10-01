#!/usr/bin/python3
"""
State Capabilities
==================

Tier 0 tools for reading the microscope state and comparing states over
time. They read the microscope but never change it; in particular they do
not sweep the imaging quadrants, which would switch the operator's view.

Each capture is kept in memory for the session under a short id (``s1``,
``s2``, ...) so the agent can compare any two without reading them again.
States are plain dictionaries; see :mod:`pytribeam.mcp.state`.

The microscope connection is opened on first use and reused. AutoScript is
imported only then, so the server still starts on a machine without it.
"""

from __future__ import annotations

import contextlib
import itertools
import sys
import threading
from typing import Any, Dict

from mcp.server.mcpserver.exceptions import ToolError

from pytribeam.mcp.state.condense import condense
from pytribeam.mcp.state.diff import diff

TIER = 0

MAX_STATES = 100
"""States kept in memory per session; the oldest are forgotten first."""


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


def _capture(microscope, description: str) -> Dict[str, Any]:
    """Read the current state from a connected microscope."""
    from pytribeam.mcp.state.capture import capture

    return capture(microscope, description=description)


def register(add, config) -> None:
    """Register this module's tools."""
    lock = threading.Lock()
    session: Dict[str, Any] = {"microscope": None}
    states: Dict[str, Dict[str, Any]] = {}
    ids = (f"s{n}" for n in itertools.count(1))

    def read_state(description: str) -> str:
        """Capture and store a state, returning its id."""
        with lock:
            # stdout carries the MCP protocol, and AutoScript prints to it.
            with contextlib.redirect_stdout(sys.stderr):
                if session["microscope"] is None:
                    try:
                        session["microscope"] = _connect(config)
                    except Exception as exc:
                        raise ToolError(
                            f"Could not connect to the microscope at "
                            f"{config.microscope_host or 'the default host'}: {exc}"
                        ) from exc
                state = _capture(session["microscope"], description)

            if not state["values"]:
                # Every read failed, so the connection is likely gone.
                session["microscope"] = None
                raise ToolError(
                    "Could not read anything from the microscope; the connection "
                    "may have dropped and will be reopened on the next call."
                )

            state_id = next(ids)
            states[state_id] = state
            while len(states) > MAX_STATES:
                del states[next(iter(states))]
            return state_id

    def stored(state_id: str) -> Dict[str, Any]:
        if state_id not in states:
            raise ToolError(
                f"No state with id {state_id!r}. Known ids: {', '.join(states) or 'none'}."
            )
        return states[state_id]

    def get_state(description: str = "", full: bool = False) -> dict:
        """Read the current microscope state and store it for later comparison.

        By default returns a condensed view of the active imaging quadrant:
        only the beam it shows, current settings without their limits or
        allowed values, and no hardware that is not installed. Set ``full``
        to get every recorded value, keyed by dotted path, plus any
        attributes that failed to read.

        All values are SI units: m, rad, A, V, s, K. The returned
        ``state_id`` can be passed to ``compare_states``. ``description`` is
        an optional note stored with the state, e.g. "before milling".
        """
        state_id = read_state(description)
        state = states[state_id]
        return {"state_id": state_id, **(state if full else condense(state))}

    def compare_states(before: str, after: str = "") -> dict:
        """Report what differs between two stored states.

        ``before`` and ``after`` are ids from ``get_state`` or
        ``list_states``. If ``after`` is omitted, the current state is read
        and stored first, so this answers "what has changed since
        ``before``?" in one call.

        Returns ``changed`` (path to [before, after]), ``appeared`` and
        ``disappeared`` (path to value), and read errors introduced or
        resolved. Small jitter in stage position, beam voltage and current,
        and detector levels is ignored, as are live pressure and specimen
        current readings. A diff shows what differs, not the steps that led
        there.
        """
        old = stored(before)
        after = after or read_state("")
        return {"before_id": before, "after_id": after, **diff(old, stored(after))}

    def list_states() -> dict:
        """List the states stored this session, oldest first."""
        return {
            "states": [
                {
                    "state_id": state_id,
                    "recorded_at": state["recorded_at"],
                    "description": state["description"],
                }
                for state_id, state in states.items()
            ]
        }

    add(get_state, read_only=True)
    add(compare_states, read_only=True)
    add(list_states, read_only=True)
