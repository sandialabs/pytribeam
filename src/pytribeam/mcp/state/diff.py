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
