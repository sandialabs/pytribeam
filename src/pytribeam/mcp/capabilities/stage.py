#!/usr/bin/python3
"""
Stage Capabilities
==================

Tier 4 tools that move the stage.

This module only wraps pytribeam. ``move_to_position`` does what the
experiment workflow does before each slice: retract the insertable devices
with ``insertable_devices.retract_all_devices``, then move with
``stage.move_to_position``, which checks the target against the stage limits,
moves the axes in its safety order, and verifies the result. Nothing about the
position is checked here; pytribeam's own checks and messages are what the
agent sees.

Each pytribeam call sits in a small module-level function that imports
pytribeam itself, so the server starts without AutoScript and tests can
replace the hardware.
"""

from __future__ import annotations

import time
from typing import Dict, Optional

from mcp.server.mcpserver.exceptions import ToolError

from pytribeam.mcp.capabilities._helpers import (
    acted,
    agent_errors,
    collect_warnings,
    snapshot,
)
from pytribeam.mcp.capabilities.hardware import _stage_errors, _stage_position

TIER = 4

AXES = ("x_mm", "y_mm", "z_mm", "r_deg", "t_deg")


# ---------------------------------------------------------------------------
# pytribeam calls. Tests replace these.
# ---------------------------------------------------------------------------
def _retract_all(microscope) -> None:
    """Retract every insertable microscope detector, as the workflow does
    before a stage move. EBSD and EDS (Laser API devices) are not included."""
    from pytribeam import insertable_devices as devices

    devices.retract_all_devices(microscope, enable_EBSD=False, enable_EDS=False)


def _move(microscope, target: Dict[str, float]) -> None:
    """``stage.move_to_position`` to a RAW target in mm and degrees."""
    from pytribeam import stage
    from pytribeam import types as tbt

    stage.move_to_position(
        microscope,
        tbt.StagePositionUser(**target, coordinate_system=tbt.StageCoordinateSystem.RAW),
    )


def register(add, config, connection) -> None:
    """Register this module's tools."""
    states_dir = config.states_dir

    def move_to_position(
        x_mm: Optional[float] = None,
        y_mm: Optional[float] = None,
        z_mm: Optional[float] = None,
        r_deg: Optional[float] = None,
        t_deg: Optional[float] = None,
    ) -> dict:
        """Move the stage to a position in the RAW coordinate system.

        Values are in mm and degrees, in the RAW coordinate system that
        ``get_stage_position`` reports; pass its values, never the meters and
        radians in ``get_state``. An axis left out stays where it is; give at
        least one.

        First retracts every insertable detector (as pytribeam's experiment
        workflow does before each move), then moves with pytribeam's
        ``stage.move_to_position``, which:

        * refuses a target outside the stage limits, and says what they are;
        * switches quad 4 to the CCD camera during the move;
        * sets the default coordinate system to RAW;
        * moves one axis at a time in the order R, X, Y, Z, T, returning the
          tilt to 0 first if the rotation changes, to reduce collision risk;
        * checks the final position and retries once.

        If the stage still misses the target, the move is reported as failed
        and the server stops accepting state-changing tools until the operator
        has checked the stage and ``clear_fault`` is called. Do not retry a
        failed move. Refused while the bulk stage is not active (for example,
        while the compustage is in).

        Returns the position before and after, how long the move took,
        warnings, and what changed (state ids and diff).
        """
        requested = {
            "x_mm": x_mm,
            "y_mm": y_mm,
            "z_mm": z_mm,
            "r_deg": r_deg,
            "t_deg": t_deg,
        }
        if all(value is None for value in requested.values()):
            raise ToolError(
                "Give at least one axis to move (x_mm, y_mm, z_mm, r_deg, t_deg)."
            )

        before = snapshot(connection, states_dir, "before move_to_position")
        with connection.use() as microscope, collect_warnings() as found:
            with agent_errors():
                try:
                    start = _stage_position(microscope)
                except Exception as exc:
                    _stage_errors(exc)
                    raise
                target = {
                    axis: float(requested[axis]) if requested[axis] is not None else start[axis]
                    for axis in AXES
                }
                t0 = time.monotonic()
                _retract_all(microscope)
                try:
                    _move(microscope, target)
                except SystemError as exc:
                    connection.set_fault(f"a stage move did not reach its target: {exc}")
                    raise ToolError(
                        f"The stage did not reach the target after a retry: {exc} "
                        "Stop and tell the user; do not retry. The operator should "
                        "check the stage, then call clear_fault."
                    ) from exc
                elapsed_s = time.monotonic() - t0
                end = _stage_position(microscope)
        after = snapshot(connection, states_dir, "after move_to_position")
        return {
            "target": target,
            "position_before": start,
            "position_after": end,
            "move_s": round(elapsed_s, 1),
            "warnings": found,
            **acted(before, after),
        }

    add(move_to_position, destructive=True)
