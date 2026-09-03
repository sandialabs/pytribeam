#!/usr/bin/python3
"""
Stage Capabilities
==================

Capabilities that move the sample stage.

Thin wrappers only. Anything that amounts to a sequence of pytribeam calls in
a particular order belongs in ``pytribeam.workflow``, where the existing
safety envelope and test coverage already live. If a function in this file
grows past a few dozen lines, that is the signal to move the logic upstream
rather than reimplement it here.

Every entry point checks the configured envelope in ``mcp/config.py`` before
acting. The instrument's own limits are a floor, not the whole story — the
operator sets a narrower envelope for a given session.

Work package 4.
"""
