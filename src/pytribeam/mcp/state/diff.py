#!/usr/bin/python3
"""
State Diff
==========

Reports what differs between two states.

Two captures of an idle microscope are not identical: stage encoders and
analog readings jitter. Numbers are therefore compared within the absolute
tolerances in :data:`TOLERANCES`, and live readings in :data:`IGNORED` are
not compared at all. Everything else must match exactly.

A diff says what differs, not what the operator did; a pair of states does
not determine the path taken between them.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any, Dict

TOLERANCES = {
    # Stage: general.stage_translational_tol_um and stage_angular_tol_deg
    # from pytribeam experiment configs.
    "specimen.stage.current_position.[xyz]": 5.0e-7,  # 0.5 um
    "specimen.stage.current_position.[tr]": 3.49e-4,  # 0.02 deg
    # Beam: beam.voltage_tol_kv and beam.current_tol_na.
    "beams.*.high_voltage.value": 250.0,  # 0.25 kV
    "beams.*.beam_current.value": 3.2e-10,  # 0.32 nA
    # Constants.contrast_brightness_tolerance.
    "detector.brightness.value": 1.0e-4,
    "detector.contrast.value": 1.0e-4,
}
"""Absolute tolerance, in SI units, for numbers at paths matching each glob."""

IGNORED = (
    "state.specimen_current.value",
    "vacuum.chamber_pressure.value",
)
"""Live readings that change on their own and are never reported."""


def _same(path: str, before: Any, after: Any) -> bool:
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        tol = next((t for p, t in TOLERANCES.items() if fnmatchcase(path, p)), 0.0)
        return abs(after - before) <= tol
    return before == after


def _failed(path: str, read_errors: Dict[str, str]) -> bool:
    """Return True if *path* or any ancestor of it failed to read.

    A read error is recorded where the read threw, often at an interior node:
    when ``specimen.stage.current_position`` fails, its ``.x``, ``.y``, ...
    vanish from ``values`` without being named in ``read_errors``.
    """
    parts = path.split(".")
    return any(".".join(parts[:i]) in read_errors for i in range(1, len(parts) + 1))


def diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two states.

    Returns
    -------
    dict
        ``before`` and ``after``: the two ``recorded_at`` timestamps.
        ``changed``: path to ``[before, after]`` for values outside tolerance.
        ``appeared`` / ``disappeared``: path to value for paths present in
        only one state, excluding those explained by a read error.
        ``read_errors_introduced``: path to message for new read errors.
        ``read_errors_resolved``: paths that no longer fail to read.
    """
    old, new = before["values"], after["values"]
    old_errors, new_errors = before["read_errors"], after["read_errors"]

    changed, appeared, disappeared = {}, {}, {}
    for path in sorted(set(old) | set(new)):
        if path in IGNORED:
            continue
        if path in old and path in new:
            if not _same(path, old[path], new[path]):
                changed[path] = [old[path], new[path]]
        elif path in old:
            if not _failed(path, new_errors):
                disappeared[path] = old[path]
        elif not _failed(path, old_errors):
            appeared[path] = new[path]

    return {
        "before": before["recorded_at"],
        "after": after["recorded_at"],
        "changed": changed,
        "appeared": appeared,
        "disappeared": disappeared,
        "read_errors_introduced": {
            p: new_errors[p] for p in sorted(new_errors) if p not in old_errors
        },
        "read_errors_resolved": sorted(p for p in old_errors if p not in new_errors),
    }
