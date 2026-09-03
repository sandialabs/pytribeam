#!/usr/bin/python3
"""
Microscope State Capture
========================

Reflective capture of the full microscope state tree into a
:class:`~schema.StateRecord`.

This module touches the hardware and therefore imports AutoScript. Everything
that reads, writes, or compares records lives in ``schema.py`` and stays
importable without it.

Two deliberate differences from ``GUI/state_recorder_background.py``:

1. :func:`capture_state` takes an already-connected microscope rather than
   connecting on every call. A GUI button pressed occasionally can afford a
   reconnect; an agent polling state cannot, and the open question in
   ``state_recorder_dev.md`` about reconnection cost disappears if there is
   only one connection.
2. Attributes that raise, and values that cannot be represented as scalars,
   are recorded in ``read_errors`` instead of being silently skipped.
"""

from __future__ import annotations

import platform
import socket
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import autoscript_sdb_microscope_client.structures as as_structs

from pytribeam import types as tbt
from pytribeam import utilities as ut
from pytribeam._version import __version__ as PYTRIBEAM_VERSION

from pytribeam.mcp.state.schema import (
    Provenance,
    ReadError,
    StateRecord,
    SUBSYSTEMS,
    next_record_id,
    utc_offset_now,
)

MAX_DEPTH = 8
"""Maximum recursion depth when walking the attribute tree.

The AutoScript object graph is deep and proxy-backed. Cycle detection alone
is not enough to bound the walk, because distinct proxy objects can be minted
on each access.
"""

QUADS = (1, 2, 3, 4)


def _is_public(name: str) -> bool:
    """Return True if *name* is not private or dunder."""
    return not name.startswith("_")


def _coerce(value: Any) -> Tuple[bool, Any]:
    """Convert a read value into something YAML-safe and diffable.

    Returns
    -------
    tuple of (bool, Any)
        ``(True, coerced)`` on success, ``(False, type_name)`` if the value
        cannot be represented as a scalar or flat sequence of scalars.

    Notes
    -----
    Enums are stored by name rather than by integer value. An integer alone
    is meaningless to a diff consumer and to anyone reading the file, which
    is why the original recorder had to special-case ``active_device``.
    Tuples become lists so that pyyaml does not emit ``!!python/tuple`` tags,
    which ``yaml.safe_load`` refuses to read back.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return True, value

    if isinstance(value, Enum):
        return True, value.name

    if isinstance(value, bytes):
        return False, "bytes"

    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            ok, coerced = _coerce(item)
            if not ok:
                return False, f"{type(value).__name__}[{coerced}]"
            out.append(coerced)
        return True, out

    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if not isinstance(key, str):
                return False, f"dict[{type(key).__name__}]"
            ok, coerced = _coerce(item)
            if not ok:
                return False, f"dict[{coerced}]"
            out[key] = coerced
        return True, out

    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _coerce(item_method())
        except Exception:
            return False, type(value).__name__

    return False, type(value).__name__


def _collect(
    obj: Any,
    prefix: str,
    visited: Dict[int],
    values: Dict[str, Any],
    errors: List[ReadError],
    depth: int = 0,
) -> None:
    """Recursively walk *obj*, filling *values* and *errors* in place.

    Parameters
    ----------
    obj : Any
        Object currently being inspected.
    prefix : str
        Dotted path to *obj*. No ``scope.`` prefix is added; the subsystem is
        simply the first component.
    visited : set of int
        ``id`` values already seen, to break reference cycles.
    values : dict
        Accumulator for successfully read paths.
    errors : list of ReadError
        Accumulator for paths that could not be read or represented.
    depth : int
        Current recursion depth.
    """
    if depth > MAX_DEPTH:
        errors.append(
            ReadError(
                path=prefix, error=f"max depth {MAX_DEPTH} exceeded", kind="depth"
            )
        )
        return

    obj_id = id(obj)
    if obj_id in visited:
        return
    visited[obj_id] = obj

    for name in dir(obj):
        if not _is_public(name):
            continue

        full_path = f"{prefix}.{name}" if prefix else name

        try:
            attr = getattr(obj, name)
        except Exception as error:
            errors.append(
                ReadError(
                    path=full_path,
                    error=f"{type(error).__name__}: {error}",
                    kind="access",
                )
            )
            continue

        if callable(attr):
            continue

        if isinstance(attr, as_structs.StagePosition):
            for axis in ("coordinate_system", "x", "y", "z", "t", "r"):
                ok, coerced = _coerce(getattr(attr, axis, None))
                if ok:
                    values[f"{full_path}.{axis}"] = coerced
                else:
                    errors.append(
                        ReadError(
                            path=f"{full_path}.{axis}",
                            error=f"unrepresentable type {coerced}",
                            kind="coerce",
                        )
                    )
            continue

        ok, coerced = _coerce(attr)
        if ok:
            values[full_path] = coerced
        elif isinstance(attr, (int, float, str, bool, bytes)) or attr is None:
            errors.append(
                ReadError(
                    path=full_path,
                    error=f"unrepresentable type {coerced}",
                    kind="coerce",
                )
            )
        else:
            _collect(attr, full_path, visited, values, errors, depth + 1)


def capture_values(
    microscope: tbt.Microscope,
    include_quads: bool = True,
) -> Tuple[Dict[str, Any], List[ReadError]]:
    """Read the microscope state tree into a flat path/value mapping.

    Parameters
    ----------
    microscope : tbt.Microscope
        A connected microscope.
    include_quads : bool
        If True, additionally cycle through the four imaging quadrants to
        record the active device in each, restoring the operator's original
        view afterwards. This perturbs the microscope UI and may close open
        drop-down menus, so it is worth skipping for frequent polling. The
        cost of skipping it is that ``imaging.quadN.active_device`` will be
        absent from the record.

    Returns
    -------
    tuple of (dict, list of ReadError)
        The flat values mapping and any paths that failed.
    """
    values: Dict[str, Any] = {}
    errors: List[ReadError] = []

    for subsystem in SUBSYSTEMS:
        try:
            root = getattr(microscope, subsystem)
        except Exception as error:
            errors.append(
                ReadError(
                    path=subsystem,
                    error=f"{type(error).__name__}: {error}",
                    kind="access",
                )
            )
            continue
        _collect(root, subsystem, {}, values, errors)

    if include_quads:
        _capture_quads(microscope, values, errors)

    return values, errors


def _capture_quads(
    microscope: tbt.Microscope,
    values: Dict[str, Any],
    errors: List[ReadError],
) -> None:
    """Record the active device in each imaging quadrant, restoring the view.

    The operator's original active view is restored in a ``finally`` block so
    that a failure partway through the sweep does not leave them looking at a
    different quadrant than they started on.
    """
    try:
        original_view = microscope.imaging.get_active_view()
        values["imaging.active_view"] = original_view
    except Exception as error:
        original_view = None
        errors.append(
            ReadError(
                path="imaging.active_view",
                error=f"{type(error).__name__}: {error}",
                kind="access",
            )
        )

    try:
        for quad in QUADS:
            path = f"imaging.quad{quad}.active_device"
            try:
                microscope.imaging.set_active_view(quad)
                values[path] = tbt.Device(microscope.imaging.get_active_device()).name
            except Exception as error:
                errors.append(
                    ReadError(
                        path=path,
                        error=f"{type(error).__name__}: {error}",
                        kind="access",
                    )
                )
    finally:
        if original_view is not None:
            try:
                microscope.imaging.set_active_view(original_view)
            except Exception as error:
                errors.append(
                    ReadError(
                        path="imaging.active_view",
                        error=f"restore failed, {type(error).__name__}: {error}",
                        kind="restore",
                    )
                )


def build_provenance(
    host: str = "unknown",
    port: Optional[int] = None,
    recorded_by: str = "state_recorder",
) -> Provenance:
    """Collect software and connection context for a recording.

    Parameters
    ----------
    host : str
        Microscope connection host.
    port : int, optional
        Microscope connection port.
    recorded_by : str
        Identifier for whatever produced the record.

    Returns
    -------
    Provenance
        Populated provenance block. Version lookups that fail fall back to
        ``"unknown"`` rather than raising, since provenance should never be
        the reason a capture is lost.
    """
    try:
        autoscript_version = ut.get_autoscript_version()
    except Exception:
        autoscript_version = "unknown"

    try:
        hostname = socket.gethostname() or platform.node()
    except Exception:
        hostname = "unknown"

    return Provenance(
        pytribeam_version=PYTRIBEAM_VERSION,
        autoscript_version=str(autoscript_version),
        host=host,
        port=port,
        hostname=hostname,
        recorded_by=recorded_by,
    )


def capture_state(
    microscope: tbt.Microscope,
    record_id: str,
    description: str = "",
    intended_action: Optional[List[str]] = None,
    include_quads: bool = True,
    provenance: Optional[Provenance] = None,
) -> StateRecord:
    """Capture the current microscope state as a :class:`StateRecord`.

    This function is total: it does not raise on unreadable attributes, and a
    subsystem that fails entirely yields a record with that subsystem absent
    from ``values`` and present in ``read_errors``. A consumer can then decide
    whether the gap matters, which it cannot do if capture throws.

    Parameters
    ----------
    microscope : tbt.Microscope
        A connected microscope.
    record_id : str
        Identifier for this record, typically from
        :func:`schema.next_record_id`.
    description : str
        Free-text operator note.
    intended_action : str, optional
        Capability the operator believes they used since the previous record.
    include_quads : bool
        Whether to sweep the imaging quadrants. See :func:`capture_values`.
    provenance : Provenance, optional
        Precomputed provenance. Built fresh if omitted.

    Returns
    -------
    StateRecord
        The captured state.
    """
    recorded_at = utc_offset_now()
    values, errors = capture_values(microscope, include_quads=include_quads)

    return StateRecord(
        id=record_id,
        recorded_at=recorded_at,
        values=values,
        description=description,
        intended_action=intended_action,
        read_errors=errors,
        provenance=provenance or build_provenance(),
    )


def capture_to_directory(
    microscope: tbt.Microscope,
    directory,
    description: str = "",
    intended_action: Optional[List[str]] = None,
    include_quads: bool = True,
    provenance: Optional[Provenance] = None,
) -> StateRecord:
    """Capture the current state and write it into a state directory.

    Convenience wrapper that allocates the next record id, captures, and
    writes. Returns the record so the caller can report its id.
    """
    from pytribeam.mcp.state.schema import write_record

    record = capture_state(
        microscope,
        record_id=next_record_id(directory),
        description=description,
        intended_action=intended_action,
        include_quads=include_quads,
        provenance=provenance,
    )
    write_record(record, directory)
    return record
