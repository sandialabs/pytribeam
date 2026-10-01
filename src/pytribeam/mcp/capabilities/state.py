#!/usr/bin/python3
"""
State Capabilities
==================

Tier 0 tools for reading the microscope state and comparing states over
time. They read the microscope but never change it; in particular they do
not sweep the imaging quadrants, which would switch the operator's view.

Every capture is saved in full to ``<project_dir>/states`` as ``s0001.yml``,
``s0002.yml``, ..., and the file name is the id the agent sees. The files are
the only record: states from earlier sessions, or from the GUI state
recorder pointed at the same folder, can be compared like any other. States
are plain dictionaries; see :mod:`pytribeam.mcp.state`.

The microscope connection is opened on first use and reused. AutoScript is
imported only then, so the server still starts on a machine without it.
"""

from __future__ import annotations

import contextlib
import re
import sys
import threading
from typing import Any, Dict, Tuple

from mcp.server.mcpserver.exceptions import ToolError

from pytribeam.mcp import state
from pytribeam.mcp.state.condense import condense
from pytribeam.mcp.state.diff import diff

TIER = 0

_STATE_ID = re.compile(r"^s\d+$")


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
    states_dir = config.states_dir

    def read_state(description: str) -> Tuple[str, Dict[str, Any]]:
        """Capture and save a state, returning its id and contents."""
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
                captured = _capture(session["microscope"], description)

            if not captured["values"]:
                # Every read failed, so the connection is likely gone.
                session["microscope"] = None
                raise ToolError(
                    "Could not read anything from the microscope; the connection "
                    "may have dropped and will be reopened on the next call."
                )

            path = state.save(captured, state.next_path(states_dir))
            return path.stem, captured

    def load(state_id: str) -> Dict[str, Any]:
        path = states_dir / f"{state_id}.yml"
        if not _STATE_ID.match(state_id) or not path.is_file():
            raise ToolError(
                f"No state with id {state_id!r}; list_states shows the saved ids."
            )
        return state.load(path)

    def get_state(description: str = "", full: bool = False) -> dict:
        """Read the current microscope state and save it for later comparison.

        By default returns a condensed view of the active imaging quadrant:
        only the beam it shows, current settings without their limits or
        allowed values, and no hardware that is not installed. Set ``full``
        to get every recorded value, keyed by dotted path, plus any
        attributes that failed to read. The full state is saved either way.

        All values are SI units: m, rad, A, V, s, K. The returned
        ``state_id`` can be passed to ``compare_states``. ``description`` is
        an optional note saved with the state, e.g. "before milling".
        """
        state_id, captured = read_state(description)
        return {"state_id": state_id, **(captured if full else condense(captured))}

    def compare_states(before: str, after: str = "") -> dict:
        """Report what differs between two saved states.

        ``before`` and ``after`` are ids from ``get_state`` or
        ``list_states``. If ``after`` is omitted, the current state is read
        and saved first, so this answers "what has changed since
        ``before``?" in one call.

        Returns ``changed`` (path to [before, after]), ``appeared`` and
        ``disappeared`` (path to value), and read errors introduced or
        resolved. Small jitter in stage position, beam voltage and current,
        and detector levels is ignored, as are live pressure and specimen
        current readings. A diff shows what differs, not the steps that led
        there.
        """
        old = load(before)
        if after:
            new = load(after)
        else:
            after, new = read_state("")
        return {"before_id": before, "after_id": after, **diff(old, new)}

    def list_states(limit: int = 20) -> dict:
        """List the most recent saved states, oldest first.

        Includes states from earlier sessions in this project. ``limit`` caps
        how many are returned; ``total`` is how many exist.
        """
        ids = sorted(
            (p.stem for p in states_dir.glob("s*.yml") if _STATE_ID.match(p.stem)),
            key=lambda state_id: int(state_id[1:]),
        )
        recent = []
        for state_id in ids[-limit:] if limit > 0 else []:
            saved = state.load(states_dir / f"{state_id}.yml")
            recent.append(
                {
                    "state_id": state_id,
                    "recorded_at": saved["recorded_at"],
                    "description": saved.get("description") or "",
                }
            )
        return {"total": len(ids), "states": recent}

    add(get_state, read_only=True)
    add(compare_states, read_only=True)
    add(list_states, read_only=True)
