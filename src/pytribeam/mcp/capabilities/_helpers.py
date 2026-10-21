#!/usr/bin/python3
"""
Capability Helpers
==================

Small pieces shared by the capability modules.

* :func:`agent_errors` turns the exceptions pytribeam raises for bad input or
  a refused operation into ``ToolError``, so their messages reach the agent.
* :func:`collect_warnings` records the ``warnings.warn`` messages pytribeam
  uses to report useful information, so a tool can return them.
* :func:`snapshot` captures and saves a microscope state, as ``get_state``
  does, and :func:`acted` turns two of them into the record every action
  returns (convention 10).
"""

from __future__ import annotations

import contextlib
import warnings
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

from mcp.server.mcpserver.exceptions import ToolError

from pytribeam.mcp import state
from pytribeam.mcp.state.diff import diff

# pytribeam raises these for invalid settings and refused operations. Their
# messages are written for a person and are safe to show the agent.
AGENT_ERRORS = (ValueError, SystemError, NotImplementedError)


@contextlib.contextmanager
def agent_errors() -> Iterator[None]:
    """Re-raise :data:`AGENT_ERRORS` as ``ToolError`` with the same message.

    ``ToolError`` passes through unchanged, and anything else propagates as a
    bug or hardware fault.
    """
    try:
        yield
    except ToolError:
        raise
    except AGENT_ERRORS as exc:
        raise ToolError(str(exc) or type(exc).__name__) from exc


@contextlib.contextmanager
def collect_warnings() -> Iterator[List[str]]:
    """Yield a list that fills with the messages of warnings raised inside.

    pytribeam writes warnings as multi-line f-strings, so each message has its
    whitespace collapsed to single spaces.
    """
    messages: List[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            yield messages
        finally:
            messages.extend(" ".join(str(w.message).split()) for w in caught)


def _capture(microscope, description: str) -> Dict[str, Any]:
    """Read the current state from a connected microscope."""
    from pytribeam.mcp.state.capture import capture

    return capture(microscope, description=description)


def snapshot(connection, states_dir: Path, description: str) -> Tuple[str, Dict]:
    """Capture the current state, save it as the next ``sNNNN.yml``, and return
    ``(state_id, state)``. Takes about 0.2 s on the simulator.

    A capture in which every read failed means the connection has dropped: it
    is not saved, the connection is reset, and ``ToolError`` is raised.
    """
    with connection.use() as microscope:
        captured = _capture(microscope, description)

    if not captured["values"]:
        connection.reset()
        raise ToolError(
            "Could not read anything from the microscope; the connection "
            "may have dropped and will be reopened on the next call."
        )

    path = state.save(captured, state.next_path(states_dir))
    return path.stem, captured


def acted(before: Tuple[str, Dict], after: Tuple[str, Dict]) -> Dict[str, Any]:
    """The record of an action: both state ids and what changed between them.

    *before* and *after* are :func:`snapshot` results. ``changes`` maps each
    changed path to ``[before, after]``, with the same jitter filtering as
    ``compare_states``.
    """
    (before_id, old), (after_id, new) = before, after
    return {
        "before_state_id": before_id,
        "after_state_id": after_id,
        "changes": diff(old, new)["changed"],
    }
