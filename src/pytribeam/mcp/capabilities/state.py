#!/usr/bin/python3
"""
State Capabilities
==================

Tier 1 tools for reading the microscope state and comparing states over
time. They read the microscope but never change it: they do not sweep the
imaging quadrants, which would switch the operator's view, so they are
annotated read-only. They are tier 1 rather than tier 0 because tier 0 never
talks to the microscope. Listing saved states is in ``records``.

Every capture is saved in full to ``<project_dir>/states`` as ``s0001.yml``,
``s0002.yml``, ..., and the file name is the id the agent sees. The files are
the only record: states from earlier sessions, or from the GUI state
recorder pointed at the same folder, can be compared like any other. States
are plain dictionaries; see :mod:`pytribeam.mcp.state`.

The microscope connection is the shared one from
:mod:`pytribeam.mcp.connection`, opened on first use.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Tuple

from mcp.server.mcpserver.exceptions import ToolError

from pytribeam.mcp import state
from pytribeam.mcp.capabilities._helpers import snapshot
from pytribeam.mcp.state.condense import condense
from pytribeam.mcp.state.diff import diff

TIER = 1

_STATE_ID = re.compile(r"^s\d+$")


def register(add, config, connection) -> None:
    """Register this module's tools."""
    states_dir = config.states_dir

    def read_state(description: str) -> Tuple[str, Dict[str, Any]]:
        """Capture and save a state, returning its id and contents."""
        return snapshot(connection, states_dir, description)

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

    add(get_state, read_only=True)
    add(compare_states, read_only=True)
