#!/usr/bin/python3
"""
Microscope State Capture
========================

Reads the full microscope state by walking the AutoScript object tree.

This is the only module in the package that touches the hardware and
imports AutoScript. It takes an already-connected microscope, so a caller
polling state holds one connection. Capture never raises on an unreadable
attribute: the failure is recorded in ``read_errors`` and the walk continues.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import autoscript_sdb_microscope_client.structures as as_structs

from pytribeam import types as tbt
from pytribeam.mcp.state import SCHEMA_VERSION

SUBSYSTEMS = (
    "beams",
    "detector",
    "gas",
    "patterning",
    "specimen",
    "state",
    "vacuum",
    "imaging",
)
"""Top level microscope attributes walked by the recorder."""

MAX_DEPTH = 8
"""Maximum recursion depth when walking the attribute tree.

The AutoScript object graph is deep and proxy-backed. Cycle detection alone
is not enough to bound the walk, because distinct proxy objects can be minted
on each access.
"""

SIGNIFICANT_FIGURES = 12
"""Floats are rounded to this many significant figures.

This strips binary representation noise (``6.399999999999999e-09`` becomes
``6.4e-09``) while keeping far more precision than any reading carries.
"""

QUADS = (1, 2, 3, 4)

_LEAF_TYPES = (Enum, bool, int, float, str, bytes, list, tuple, dict)


def _describe(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"


def _is_leaf(value: Any) -> bool:
    """Return True for a value to record, False for an object to walk into."""
    return value is None or isinstance(value, _LEAF_TYPES) or _is_numpy_scalar(value)


def _is_numpy_scalar(value: Any) -> bool:
    return callable(getattr(value, "item", None))


def _coerce(value: Any) -> Any:
    """Return a leaf value as YAML-safe data, or raise TypeError.

    Enums are stored by name, since an integer alone is meaningless to a
    reader. Tuples become lists so that ``yaml.safe_load`` can read them back.
    """
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, float):
        return float(f"{value:.{SIGNIFICANT_FIGURES}g}")
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_coerce(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _coerce(item) for key, item in value.items()}
    if _is_numpy_scalar(value):
        return _coerce(value.item())
    raise TypeError(type(value).__name__)


def _collect(
    obj: Any,
    prefix: str,
    values: Dict[str, Any],
    errors: Dict[str, str],
    visited: Dict[int, Any],
    depth: int = 0,
) -> None:
    """Recursively walk the public attributes of *obj* into *values*.

    *visited* maps ``id`` to object for everything already walked, breaking
    reference cycles; holding the objects stops their ids being reused.
    """
    if depth > MAX_DEPTH:
        errors[prefix] = f"max depth {MAX_DEPTH} exceeded"
        return
    if id(obj) in visited:
        return
    visited[id(obj)] = obj

    for name in dir(obj):
        if name.startswith("_"):
            continue
        path = f"{prefix}.{name}"

        try:
            attr = getattr(obj, name)
        except Exception as error:
            errors[path] = _describe(error)
            continue

        if callable(attr):
            continue

        if isinstance(attr, as_structs.StagePosition):
            # Record only the axes; walking it would also pick up helpers.
            for axis in ("coordinate_system", "x", "y", "z", "t", "r"):
                _store(f"{path}.{axis}", getattr(attr, axis, None), values, errors)
        elif _is_leaf(attr):
            _store(path, attr, values, errors)
        else:
            _collect(attr, path, values, errors, visited, depth + 1)


def _store(path: str, value: Any, values: Dict[str, Any], errors: Dict[str, str]):
    """Store a leaf value, or a read error if it cannot be represented."""
    try:
        values[path] = _coerce(value)
    except Exception as error:
        errors[path] = f"unrepresentable value, {_describe(error)}"


def _capture_imaging(
    microscope: tbt.Microscope,
    values: Dict[str, Any],
    errors: Dict[str, str],
    include_quads: bool,
) -> None:
    """Record the active view and its device, optionally sweeping all quads.

    Reading the active view and device does not disturb the microscope UI.
    The quadrant sweep does: it switches the view through each quad and
    restores the original in a ``finally`` block, so a failure partway
    through never leaves the operator on a different quadrant. The sweep is
    skipped if the original view cannot be read, since it could not then be
    restored.
    """
    imaging = microscope.imaging
    try:
        original_view = imaging.get_active_view()
        values["imaging.active_view"] = original_view
    except Exception as error:
        errors["imaging.active_view"] = _describe(error)
        return

    try:
        values["imaging.active_device"] = tbt.Device(imaging.get_active_device()).name
    except Exception as error:
        errors["imaging.active_device"] = _describe(error)

    if not include_quads:
        return

    try:
        for quad in QUADS:
            path = f"imaging.quad{quad}.active_device"
            try:
                imaging.set_active_view(quad)
                values[path] = tbt.Device(imaging.get_active_device()).name
            except Exception as error:
                errors[path] = _describe(error)
    finally:
        try:
            imaging.set_active_view(original_view)
        except Exception as error:
            errors["imaging.restore_active_view"] = _describe(error)


def capture(
    microscope: tbt.Microscope,
    description: str = "",
    intended_action: Optional[List[str]] = None,
    include_quads: bool = False,
) -> Dict[str, Any]:
    """Capture the current microscope state.

    A subsystem that fails entirely is absent from ``values`` and present in
    ``read_errors``, so a consumer can decide whether the gap matters.

    Parameters
    ----------
    microscope : tbt.Microscope
        A connected microscope.
    description : str
        Free-text operator note.
    intended_action : list of str, optional
        What the operator believes they did since the previous capture, e.g.
        ``["move_stage"]``. Recorded as ground truth for testing diffs.
    include_quads : bool
        If True, also cycle through the four imaging quadrants to record
        ``imaging.quadN.active_device`` for each. This perturbs the microscope
        UI and may close open drop-down menus, so it is off by default. The
        active view and its device are recorded either way.

    Returns
    -------
    dict
        A state, in the format described in :mod:`pytribeam.mcp.state`.
    """
    recorded_at = (
        datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")
    )
    values: Dict[str, Any] = {}
    errors: Dict[str, str] = {}

    for subsystem in SUBSYSTEMS:
        try:
            root = getattr(microscope, subsystem)
        except Exception as error:
            errors[subsystem] = _describe(error)
            continue
        _collect(root, subsystem, values, errors, {})

    _capture_imaging(microscope, values, errors, include_quads)

    return {
        "schema_version": SCHEMA_VERSION,
        "recorded_at": recorded_at,
        "description": description,
        "intended_action": intended_action,
        "values": values,
        "read_errors": errors,
    }
