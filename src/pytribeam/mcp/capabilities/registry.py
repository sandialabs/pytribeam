#!/usr/bin/python3
"""
Capability Registry
===================

Maps capability ids to the functions that implement them.

This mapping is written by hand and reviewed. It is the only place where a
capability id becomes an executable call. ``path_metadata.yml`` names ids and
nothing else, so that editing a configuration file can never extend what the
server is able to do.

An id that appears in the metadata table but not here resolves to nothing, and
the associated paths remain read-only. Fail closed.

Work package 4. Do not start before the state layer is complete.
"""
