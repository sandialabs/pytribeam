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
"""
