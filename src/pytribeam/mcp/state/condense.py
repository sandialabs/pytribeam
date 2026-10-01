#!/usr/bin/python3
"""
Condensed State
===============

A compact view of a state, sized for an agent.

A full state describes the whole instrument: both beams, the limits and
allowed values of every setting, and accessories that may not be installed.
Most of that does not change between captures. Only one imaging quadrant is
active at a time, and it shows at most one beam, so :func:`condense` keeps
the current settings that matter for that quadrant:

- Only the beam shown in the active quadrant is kept. If the quadrant shows a
  camera rather than a beam, neither beam is kept.
- The other quadrants' devices (``imaging.quadN``) are dropped.
- Instrument bounds (``limits``, ``available_values``, ``is_controllable``)
  are dropped. They describe the hardware, not its state.
- A subtree with ``is_installed: false`` is dropped entirely, and
  ``is_installed: true`` is dropped as implied.
- Paths are nested rather than dotted, and a node whose only remaining child
  is ``value`` is replaced by that value, so
  ``beams.electron_beam.horizontal_field_width.value`` becomes
  ``beams: {electron_beam: {horizontal_field_width: ...}}``.

Values stay in SI units (m, rad, A, V, s). Read errors are omitted.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

_BEAM_FOR_DEVICE = {"ELECTRON_BEAM": "electron_beam", "ION_BEAM": "ion_beam"}

_BOUNDS_KEYS = frozenset({"limits", "available_values", "is_controllable"})

_DROP = object()
"""Sentinel for a pruned node, since None is a legitimate value."""


def active_device(state: Dict[str, Any]) -> Optional[str]:
    """Return the imaging device shown in the active quadrant, if recorded.

    Uses ``imaging.active_device``, falling back to the swept
    ``imaging.quadN.active_device`` entry for the active view.
    """
    values = state["values"]
    if "imaging.active_device" in values:
        return values["imaging.active_device"]
    view = values.get("imaging.active_view")
    return values.get(f"imaging.quad{view}.active_device")


def _keep(parts: List[str], active_beam: Optional[str]) -> bool:
    if _BOUNDS_KEYS.intersection(parts):
        return False
    if parts[0] == "beams" and parts[1] != active_beam:
        return False
    if parts[0] == "imaging" and parts[1].startswith("quad"):
        return False
    return True


def _prune(node: Any) -> Any:
    """Apply the installation and lone-``value`` rules to a nested tree."""
    if not isinstance(node, dict):
        return node
    if node.get("is_installed") is False:
        return _DROP

    out = {}
    for key, child in node.items():
        child = _prune(child)
        if key != "is_installed" and child is not _DROP and child != {}:
            out[key] = child

    if list(out) == ["value"]:
        return out["value"]
    return out


def condense(state: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact, nested view of *state* for the active quadrant.

    Returns
    -------
    dict
        ``recorded_at``, then ``description`` and ``intended_action`` if set,
        then the condensed subsystems, ``imaging`` first.
    """
    device = active_device(state)

    tree: Dict[str, Any] = {}
    for path, value in state["values"].items():
        parts = path.split(".")
        if not _keep(parts, _BEAM_FOR_DEVICE.get(device)):
            continue
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    if device is not None:
        tree.setdefault("imaging", {})["active_device"] = device

    out = {"recorded_at": state["recorded_at"]}
    for key in ("description", "intended_action"):
        if state.get(key):
            out[key] = state[key]

    # Lead with imaging: it says which quadrant and beam the rest describes.
    pruned = _prune(tree)
    if "imaging" in pruned:
        out["imaging"] = pruned.pop("imaging")
    out.update(pruned)
    return out
