#!/usr/bin/python3
"""
Path Metadata
=============

Loader and lookup for ``path_metadata.yml``.

One declarative table supplies everything the rest of the package needs to
know about a state path: its units, its display units, its comparison
tolerance, whether it is noise, and which capability (if any) can change it.

Pattern matching must be deterministic. When several patterns match one path
the winner is decided by fewest wildcards, then longest literal character
count, then first occurrence in the file. Implement and test that resolution
on its own before anything depends on it.

Two invariants this module enforces:

1. A path with no entry, or an entry with no ``capability``, is read-only.
   Absence never means "probably fine".
2. Entries name capability *ids*, never Python attributes. Resolution from id
   to callable happens in a hand-written registry, so that a configuration
   file can never widen what the server is able to do.

Do not import ``pytribeam.types``, ``pytribeam.utilities``,
``pytribeam.constants``, or AutoScript from this module.

Work package 2.

Required public API
--------------------
``diff.py`` and ``tests/mcp/test_diff.py`` call this surface. Implement it
exactly; the internals (how you store/index the table) are yours.

.. code-block:: python

    def load(path: Optional[Path] = None) -> "PathMetadata":
        \"\"\"Load and validate path_metadata.yml (default: the file next to
        this module). Raises on the three invalid-table cases below.\"\"\"

    class PathMetadata:
        def lookup(self, path: str) -> Optional["PathEntry"]:
            \"\"\"Return the winning entry for *path*, or None if unmapped.

            Winner among multiple matching patterns: fewest wildcards, then
            longest literal character count, then first occurrence in the
            file. Implement and test glob resolution as its own function
            before anything depends on it.
            \"\"\"

        def capability(self, capability_id: str) -> Optional[dict]:
            \"\"\"Return the `capabilities:` entry for *capability_id*, or None.\"\"\"

    class PathEntry:
        units: Optional[str]
        display: Optional[str]
        tolerance: Optional[float]
        tolerance_ratio: Optional[float]
        noise: bool
        capability: Optional[str]
        scoped_by: Optional[str]

    def report_unmapped(record: "schema.StateRecord", path_metadata: "PathMetadata") -> list[str]:
        \"\"\"List every path in *record* with no entry in *path_metadata*.

        A whole-record audit, not a diff. Distinct from diff.py's own
        ``unmapped`` field, which is scoped to paths that came out `changed`
        with no entry at all -- see diff.py's docstring.
        \"\"\"

Validation (``load`` must raise on all three)
------------------------------------------------
1. A ``capability`` naming an id not defined under ``capabilities``.
2. A malformed pattern.
3. An entry with both ``noise: true`` and a ``capability`` set.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

_DEFAULT_PATH = Path(__file__).with_name("path_metadata.yml")


def _validate_pattern(pattern: str) -> None:
    """Raise ValueError if a metadata pattern is malformed."""
    if not isinstance(pattern, str):
        raise ValueError("Metadata pattern must be a string")
    if not pattern:
        raise ValueError("Metadata pattern must not be empty")
    if pattern.strip() != pattern:
        raise ValueError(f"Malformed pattern {pattern!r}: leading/trailing whitespace is not allowed")
    if pattern.startswith(".") or pattern.endswith("."):
        raise ValueError(f"Malformed pattern {pattern!r}: cannot start or end with a dot")
    if " " in pattern:
        raise ValueError(f"Malformed pattern {pattern!r}: spaces are not allowed")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.*-")
    for char in pattern:
        if char not in allowed:
            raise ValueError(f"Malformed pattern {pattern!r}: unsupported character {char!r}")
    for part in pattern.split("."):
        if part == "":
            raise ValueError(f"Malformed pattern {pattern!r}: empty path segment")


def glob_match(pattern: str, path: str) -> bool:
    """Return whether *path* matches a wildcard path pattern."""
    _validate_pattern(pattern)
    regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    return re.fullmatch(regex, path) is not None


@dataclasses.dataclass(frozen=True)
class PathEntry:
    """Metadata for a single path pattern."""

    pattern: str
    units: Optional[str] = None
    display: Optional[str] = None
    tolerance: Optional[float] = None
    tolerance_ratio: Optional[float] = None
    noise: bool = False
    capability: Optional[str] = None
    scoped_by: Optional[str] = None


class PathMetadata:
    """Load and resolve path metadata entries."""

    def __init__(self, entries: List[Tuple[str, PathEntry]], capabilities: Dict[str, Dict[str, Any]]):
        self._entries = list(entries)
        self._capabilities = dict(capabilities)

    def lookup(self, path: str) -> Optional[PathEntry]:
        """Return the winning metadata entry for *path* or None if unmapped."""
        matches: List[Tuple[int, int, int, PathEntry]] = []
        for idx, (pattern, entry) in enumerate(self._entries):
            if glob_match(pattern, path):
                wildcard_count = pattern.count("*")
                literal_count = len(pattern.replace("*", ""))
                matches.append((wildcard_count, -literal_count, idx, entry))
        if not matches:
            return None
        _, _, _, winner = min(matches, key=lambda item: (item[0], item[1], item[2]))
        return winner

    def capability(self, capability_id: str) -> Optional[Dict[str, Any]]:
        """Return the raw `capabilities:` entry for *capability_id* or None."""
        return self._capabilities.get(capability_id)


def _coerce_scalar(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def load(path: Optional[Path] = None) -> PathMetadata:
    """Load and validate the default path metadata file."""
    file_path = Path(path) if path is not None else _DEFAULT_PATH
    with open(file_path, "r", encoding="utf-8") as handle:
        doc = yaml.safe_load(handle) or {}

    if not isinstance(doc, dict):
        raise ValueError(f"Path metadata root in {file_path} must be a mapping")
    paths = doc.get("paths") or {}
    capabilities = doc.get("capabilities") or {}
    if not isinstance(paths, dict):
        raise ValueError(f"Metadata 'paths' must be a mapping in {file_path}")
    if not isinstance(capabilities, dict):
        raise ValueError(f"Metadata 'capabilities' must be a mapping in {file_path}")

    entries: List[Tuple[str, PathEntry]] = []
    for pattern, raw in paths.items():
        pattern_str = str(pattern)
        _validate_pattern(pattern_str)
        if not isinstance(raw, dict):
            raise ValueError(f"Metadata entry for {pattern_str!r} must be a mapping")

        capability = raw.get("capability")
        if capability is not None:
            capability = str(capability)
            if capability not in capabilities:
                raise ValueError(f"Capability {capability!r} is not defined in the metadata table")
        if raw.get("noise") is True and capability is not None:
            raise ValueError(f"Entry {pattern_str!r} cannot be both noise and capability-backed")

        entry = PathEntry(
            pattern=pattern_str,
            units=raw.get("units"),
            display=raw.get("display"),
            tolerance=_coerce_scalar(raw.get("tolerance")),
            tolerance_ratio=_coerce_scalar(raw.get("tolerance_ratio")),
            noise=bool(raw.get("noise", False)),
            capability=capability,
            scoped_by=raw.get("scoped_by"),
        )
        entries.append((pattern_str, entry))

    return PathMetadata(entries=entries, capabilities=capabilities)


def report_unmapped(record: "schema.StateRecord", path_metadata: PathMetadata) -> List[str]:
    """List all paths in *record* with no metadata entry."""
    values = getattr(record, "values", {}) or {}
    missing = []
    for path in sorted(values):
        if path_metadata.lookup(path) is None:
            missing.append(path)
    return missing
