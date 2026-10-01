"""
Microscope State
================

A microscope state is a plain dictionary, saved as one self-contained YAML
file::

    schema_version: 2
    recorded_at: '2026-09-03T10:09:14.553-07:00'
    description: Free-text operator note
    intended_action: [move_stage]          # or null
    values:                                # dotted path -> value, SI units
      specimen.stage.current_position.x: 0.005
      beams.electron_beam.horizontal_field_width.value: 0.0009
    read_errors:                           # dotted path -> error message
      detector.state: "ApplicationServerException: ..."

A recording session is a directory of these files, named ``s0001.yml``,
``s0002.yml``, ... in capture order.

- :func:`capture.capture` reads a state from the microscope.
- :func:`condense.condense` reduces a state to the active quadrant.
- :func:`diff.diff` reports what changed between two states.

Everything except ``capture.py`` imports without AutoScript, so states can be
inspected and compared on a machine with no microscope software.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml

SCHEMA_VERSION = 2

_RECORD_NAME = re.compile(r"^s(\d+)\.yml$")


def save(state: Dict[str, Any], path: Path) -> Path:
    """Write *state* to *path* as YAML, replacing any existing file atomically.

    Writing to a sibling temporary file and renaming means an interrupted
    write never leaves a truncated record behind.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(state, f, sort_keys=False, allow_unicode=True)
    os.replace(tmp, path)
    return path


def load(path: Path) -> Dict[str, Any]:
    """Read a state from a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        state = yaml.safe_load(f)

    errors = state.get("read_errors") or {}
    if isinstance(errors, list):  # schema 1 stored a list of {path, error, kind}
        errors = {e["path"]: e["error"] for e in errors}
    state["read_errors"] = errors
    state["values"] = state.get("values") or {}
    return state


def next_path(directory: Path) -> Path:
    """Return the path for the next ``sNNNN.yml`` record in *directory*.

    The number is one past the highest already present. Other files are
    ignored, and the directory need not exist yet.
    """
    directory = Path(directory)
    numbers = [0]
    if directory.is_dir():
        for path in directory.iterdir():
            match = _RECORD_NAME.match(path.name)
            if match:
                numbers.append(int(match.group(1)))
    return directory / f"s{max(numbers) + 1:04d}.yml"
