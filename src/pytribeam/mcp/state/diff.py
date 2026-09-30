#!/usr/bin/python3
"""
State Diff Engine
=================

Compare two :class:`~pytribeam.mcp.state.schema.StateRecord` objects and
report what changed.

Two recordings of an idle microscope are never byte-identical: encoder and
detector readings jitter. The core job of this module is separating real
changes from that noise, using per-path tolerances from the path metadata
table, and then grouping the surviving changes into the operations that would
explain them.

A diff describes what *differs* between two states. It does not describe what
the operator *did* — a state pair does not determine the path taken between
them. Output that names an operation should be presented as a reconstruction
consistent with the difference, never as a history.

Do not import ``pytribeam.types``, ``pytribeam.utilities``,
``pytribeam.constants``, or AutoScript from this module.

Work package 1. See ``tests/mcp/test_diff.py`` for the acceptance criteria.

Required public API
--------------------
``tests/mcp/test_diff.py`` is written and failing against this contract.
Implement it exactly; the shape below is fixed, the internals are yours.

.. code-block:: python

    def diff_records(
        before: schema.StateRecord,
        after: schema.StateRecord,
        path_metadata: "metadata.PathMetadata",
    ) -> "DiffResult":
        ...

    class DiffResult:
        def to_dict(self) -> dict:
            \"\"\"Return the plain-dict form compared against expected.yml.

            Shape (see any file in ``tests/mcp/expected/`` for real examples)::

                before_id: str
                after_id: str
                before_recorded_at: str
                after_recorded_at: str
                provenance_mismatch: bool
                intended_action: list[str] | None   # copied from `after`,
                                                     # informational only --
                                                     # never compared against.
                differences:
                  - path: str
                    classification: str   # changed | appeared | disappeared |
                                           # read_error_before | read_error_after
                                           # (noise and unchanged are counted,
                                           # not listed here)
                    before: <value> | null
                    after: <value> | null
                    capability: str | null
                    scoped_by: str | null  # set only when this path's scope key
                                            # (see path_metadata.yml) ALSO
                                            # changed in this pair -- flag, don't
                                            # drop
                operations:
                  <capability_id>: [path, ...]   # `changed` paths only, grouped
                observed: [path, ...]            # `changed`, no capability
                read_errors_resolved: [path, ...]    # in before.read_errors,
                                                      # not in after.read_errors
                read_errors_introduced: [path, ...]  # inverse
                unmapped: [path, ...]   # `changed` paths with NO metadata entry
                                        # at all (contrast with
                                        # metadata.report_unmapped(record), which
                                        # audits a whole record, not a diff)
                unchanged_count: int
                noise_count: int

            ``differences`` is sorted by path. Each capability's path list in
            ``operations`` is sorted. Floats are compared by the caller with a
            small epsilon, not exact equality -- don't round for display here,
            that's normalize.py's job.

    def render_text(result: "DiffResult") -> str:
        \"\"\"Plain-text renderer, see mcp/README.md for the target format.\"\"\"
        ...

The ancestor rule (read_error_before / read_error_after)
----------------------------------------------------------
A path P absent from ``after.values`` is ``read_error_after`` if P **or any
ancestor of P** appears in ``after.read_errors``. Otherwise it is
``disappeared``. Symmetrically, a path P absent from ``before.values`` is
``read_error_before`` if P or any ancestor of P appears in
``before.read_errors``; otherwise it is ``appeared``.

This matters because a read error is recorded at the node where the read
threw, which is often an interior node -- see ``tests/mcp/expected/
s0008_s0009.yml``, where ``specimen.compustage.current_position`` erroring as
a whole object makes six child paths (``.x .y .z`` etc.) vanish from
``values`` without any of them appearing in ``read_errors`` by name. An
exact-path lookup against ``read_errors`` gets this fixture wrong silently.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, Iterable, List, Optional


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _paths_for_read_errors(read_errors: Iterable[Any]) -> set[str]:
    return {entry.path for entry in read_errors if getattr(entry, "path", None)}


def _has_ancestor_error(path: str, read_error_paths: set[str]) -> bool:
    if path in read_error_paths:
        return True
    parts = path.split(".")
    for idx in range(1, len(parts)):
        ancestor = ".".join(parts[:idx])
        if ancestor in read_error_paths:
            return True
    return False


def _values_equal(before: Any, after: Any, entry: Optional[Any] = None) -> bool:
    if not _is_numeric(before) or not _is_numeric(after):
        return before == after

    if entry is None:
        return before == after

    abs_diff = abs(float(after) - float(before))
    tol = getattr(entry, "tolerance", None)
    ratio = getattr(entry, "tolerance_ratio", None)

    if tol is not None and abs_diff <= float(tol):
        return True
    if ratio is not None:
        denom = max(abs(float(before)), abs(float(after)))
        if denom == 0:
            denom = 1.0
        if abs_diff <= float(ratio) * denom:
            return True
    return before == after


@dataclasses.dataclass
class DiffResult:
    before_id: str
    after_id: str
    before_recorded_at: str
    after_recorded_at: str
    provenance_mismatch: bool
    intended_action: Optional[List[str]]
    differences: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    operations: Dict[str, List[str]] = dataclasses.field(default_factory=dict)
    observed: List[str] = dataclasses.field(default_factory=list)
    read_errors_resolved: List[str] = dataclasses.field(default_factory=list)
    read_errors_introduced: List[str] = dataclasses.field(default_factory=list)
    unmapped: List[str] = dataclasses.field(default_factory=list)
    unchanged_count: int = 0
    noise_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "before_id": self.before_id,
            "after_id": self.after_id,
            "before_recorded_at": self.before_recorded_at,
            "after_recorded_at": self.after_recorded_at,
            "provenance_mismatch": self.provenance_mismatch,
            "intended_action": self.intended_action,
            "differences": sorted(self.differences, key=lambda item: item["path"]),
            "operations": {k: sorted(v) for k, v in sorted(self.operations.items())},
            "observed": sorted(self.observed),
            "read_errors_resolved": sorted(self.read_errors_resolved),
            "read_errors_introduced": sorted(self.read_errors_introduced),
            "unmapped": sorted(self.unmapped),
            "unchanged_count": int(self.unchanged_count),
            "noise_count": int(self.noise_count),
        }


def diff_records(before, after, path_metadata):
    """Compare two state records and return a structured diff result."""
    before_vals = dict(getattr(before, "values", {}) or {})
    after_vals = dict(getattr(after, "values", {}) or {})
    before_errors = _paths_for_read_errors(getattr(before, "read_errors", []) or [])
    after_errors = _paths_for_read_errors(getattr(after, "read_errors", []) or [])

    all_paths = sorted(set(before_vals) | set(after_vals))

    diff_entries: List[Dict[str, Any]] = []
    operations: Dict[str, set[str]] = {}
    observed: set[str] = set()
    unmapped: set[str] = set()
    unchanged_count = 0
    noise_count = 0
    read_errors_resolved = sorted(path for path in before_errors if path not in after_errors)
    read_errors_introduced = sorted(path for path in after_errors if path not in before_errors)

    diff_by_path: Dict[str, Dict[str, Any]] = {}
    for path in all_paths:
        before_has = path in before_vals
        after_has = path in after_vals
        entry = path_metadata.lookup(path)

        if entry is not None and entry.noise:
            noise_count += 1
            continue

        if before_has and after_has:
            if _values_equal(before_vals[path], after_vals[path], entry):
                unchanged_count += 1
                diff_by_path[path] = {"classification": "unchanged"}
                continue
            classification = "changed"
            before_value = before_vals[path]
            after_value = after_vals[path]
        elif before_has and not after_has:
            classification = "read_error_after" if _has_ancestor_error(path, after_errors) else "disappeared"
            before_value = before_vals[path]
            after_value = None
        elif not before_has and after_has:
            classification = "read_error_before" if _has_ancestor_error(path, before_errors) else "appeared"
            before_value = None
            after_value = after_vals[path]
        else:
            continue

        diff_entry = {
            "path": path,
            "classification": classification,
            "before": before_value,
            "after": after_value,
            "capability": None,
            "scoped_by": None,
        }
        if entry is not None and classification in {"changed", "appeared", "disappeared"}:
            diff_entry["capability"] = entry.capability
        diff_by_path[path] = diff_entry
        diff_entries.append(diff_entry)

        if classification == "changed":
            if entry is not None and entry.capability is not None:
                operations.setdefault(entry.capability, set()).add(path)
            else:
                observed.add(path)
            if entry is None:
                unmapped.add(path)

    for diff_entry in diff_entries:
        path = diff_entry["path"]
        entry = path_metadata.lookup(path)
        if entry is None or entry.scoped_by is None:
            continue
        scope_key = entry.scoped_by
        if scope_key in diff_by_path:
            scope_class = diff_by_path[scope_key].get("classification")
            if scope_class not in {"unchanged", "noise"}:
                diff_entry["scoped_by"] = scope_key

    result = DiffResult(
        before_id=getattr(before, "id", ""),
        after_id=getattr(after, "id", ""),
        before_recorded_at=getattr(before, "recorded_at", ""),
        after_recorded_at=getattr(after, "recorded_at", ""),
        provenance_mismatch=(str(getattr(getattr(before, "provenance", None), "pytribeam_version", "unknown"))
            != str(getattr(getattr(after, "provenance", None), "pytribeam_version", "unknown"))),
        intended_action=getattr(after, "intended_action", None),
        differences=sorted(diff_entries, key=lambda item: item["path"]),
        operations={cap: sorted(paths) for cap, paths in sorted(operations.items())},
        observed=sorted(observed),
        read_errors_resolved=read_errors_resolved,
        read_errors_introduced=read_errors_introduced,
        unmapped=sorted(unmapped),
        unchanged_count=unchanged_count,
        noise_count=noise_count,
    )
    return result


def render_text(result: Any) -> str:
    """Render a DiffResult or dict into a terse textual summary."""
    if hasattr(result, "to_dict"):
        payload = result.to_dict()
    else:
        payload = dict(result)

    before_id = payload.get("before_id", "")
    after_id = payload.get("after_id", "")
    note = payload.get("intended_action")
    lines = [f"{before_id} -> {after_id}"]
    if note:
        lines.append(f"Note: {', '.join(map(str, note))}")
    lines.append(f"Changed: {len(payload.get('differences', []))}")
    for diff_item in sorted(payload.get("differences", []), key=lambda item: item["path"]):
        lines.append(f"  {diff_item['path']}: {diff_item['classification']}")
    lines.append(f"Suppressed: {payload.get('unchanged_count', 0)} unchanged, {payload.get('noise_count', 0)} noise")
    return "\n".join(lines)
