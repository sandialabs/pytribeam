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
