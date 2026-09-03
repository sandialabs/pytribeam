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
"""
