#!/usr/bin/python3
"""
View Capabilities
=================

Tier 1 tools that change what the microscope UI shows, without moving
hardware or exposing the sample, and ``clear_fault``, which lets tools run
again after the operator has checked the microscope.

Each pytribeam call sits in a small module-level function that imports
pytribeam itself, so the server starts without AutoScript and tests can
replace the hardware.
"""

from __future__ import annotations

from typing import Any, Dict, Literal

from mcp.server.mcpserver.exceptions import ToolError

from pytribeam.mcp.capabilities._helpers import acted, agent_errors, snapshot

TIER = 1


def _read_view(microscope) -> Dict[str, Any]:
    from pytribeam import types as tbt

    return {
        "active_view": int(microscope.imaging.get_active_view()),
        "active_device": tbt.Device(microscope.imaging.get_active_device()).name,
    }


def _set_view(microscope, quad: int) -> None:
    from pytribeam import image
    from pytribeam import types as tbt

    image.set_view(microscope, tbt.ViewQuad(quad))


def register(add, config, connection) -> None:
    """Register this module's tools."""
    states_dir = config.states_dir

    def set_view(quad: Literal[1, 2, 3, 4]) -> dict:
        """Make one of the four imaging quadrants in the microscope UI active.

        Quads are 1 = upper left, 2 = upper right, 3 = lower left, 4 = lower
        right. By pytribeam convention the electron beam is in quad 1 and the
        ion beam in quad 2. Detector settings in ``get_state`` belong to the
        active quad, so they change when the view changes. Returns the new
        ``active_view`` and ``active_device`` and what changed. Changes the
        UI only; moves nothing and scans nothing.
        """
        before = snapshot(connection, states_dir, f"before set_view({quad})")
        with connection.use() as microscope, agent_errors():
            _set_view(microscope, quad)
            view = _read_view(microscope)
        after = snapshot(connection, states_dir, f"after set_view({quad})")
        return {**view, **acted(before, after)}

    def clear_fault() -> dict:
        """Allow state-changing tools again after a fault.

        A fault means the server could not leave the microscope the way it
        found it: a UI change could not be undone, or an acquisition did not
        finish. While it is set, every tool above tier 0 is refused.

        Only call this after the operator has checked the microscope and told
        you it is safe. Ask the user first; never call it just to get past a
        refusal. Returns the fault that was cleared, which is also written to
        the audit log. Changes nothing on the microscope.
        """
        busy = connection.busy  # e.g. an abandoned acquisition still running
        if busy is not None:
            raise ToolError(
                f"Cannot clear the fault while {busy.describe()}. Wait for it to "
                "finish, or ask the operator to restart the server."
            )
        cleared = connection.clear_fault()
        return {"cleared": cleared is not None, "fault": cleared}

    add(set_view)
    # Not read-only (it changes what the server allows); touches nothing on
    # the microscope, so it does not take the hardware lock.
    add(clear_fault, uses_microscope=False)
