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
