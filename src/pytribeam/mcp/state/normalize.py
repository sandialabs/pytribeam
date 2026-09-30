#!/usr/bin/python3
"""
Value Normalization
===================

Unit conversion and display formatting for recorded state values.

The microscope reports SI base units: meters and radians. Nobody reads
``0.001234`` as 1.234 mm reliably, and an agent reasoning about it will get it
wrong. Everything user-facing or agent-facing passes through here first.

Conversions are driven by the ``units`` and ``display`` fields of the path
metadata table; this module should contain the conversion arithmetic and
formatting, not a second copy of the table.

Do not import ``pytribeam.types``, ``pytribeam.utilities``,
``pytribeam.constants``, or AutoScript from this module. Everything under
``state/`` must import and run on a machine with no microscope software
installed. Tolerance constants that exist in ``pytribeam.constants`` should be
copied into ``path_metadata.yml`` rather than imported.

Work package 1.
"""

from __future__ import annotations

import math
from typing import Any, Optional


_UNIT_FACTORS = {
    "m": 1.0,
    "mm": 1e-3,
    "um": 1e-6,
    "nm": 1e-9,
    "cm": 1e-2,
    "A": 1.0,
    "nA": 1e-9,
    "uA": 1e-6,
    "V": 1.0,
    "kV": 1e3,
    "s": 1.0,
    "ms": 1e-3,
    "us": 1e-6,
    "rad": 1.0,
    "deg": math.pi / 180.0,
}


def _convert_factor(from_unit: Optional[str], to_unit: Optional[str]) -> float:
    if from_unit is None or to_unit is None:
        return 1.0
    if from_unit == to_unit:
        return 1.0
    base_from = _UNIT_FACTORS.get(from_unit)
    base_to = _UNIT_FACTORS.get(to_unit)
    if base_from is None or base_to is None:
        return 1.0
    # Convert to base SI unit first, then to the display unit.
    value_in_base = 1.0 / base_from
    return value_in_base * base_to


def convert_to_display(value: Any, units: Optional[str], display: Optional[str]) -> Any:
    """Convert a scalar value from *units* into *display* units."""
    if value is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return value
    if units is None or display is None or units == display:
        return value
    factor = _convert_factor(units, display)
    return value * factor


def format_value(value: Any, units: Optional[str] = None, display: Optional[str] = None) -> Any:
    """Return a display-friendly scalar or keep non-numeric values unchanged."""
    if value is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return value
    if units is None and display is None:
        return value
    return convert_to_display(value, units, display)


def normalize_value(path: str, value: Any, path_metadata: Any) -> Any:
    """Normalize a path value using the matching path metadata entry."""
    if value is None or path_metadata is None:
        return value
    entry = path_metadata.lookup(path)
    if entry is None:
        return value
    return format_value(value, entry.units, entry.display)
