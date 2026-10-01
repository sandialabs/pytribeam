#!/usr/bin/python3
"""
Diagnostic Capabilities
=======================

Tier 0 tools for checking that the agent, server, and configuration are
wired up correctly. Touches no hardware.

Every capability module follows the same shape:

* ``TIER``: the tier of every tool in the module.
* ``register(add, config)``: calls ``add(fn, ...)`` once per tool.

Modules never see the server object itself. ``add`` is the only way in, and it
is what applies tier gating and audit logging, so a capability cannot register
a tool that bypasses either. Anything a tool needs from the session (config
now, the microscope connection later) is captured by closure in ``register``
rather than exposed as a tool argument the agent could set.
"""

from __future__ import annotations

import datetime

from pytribeam import __version__

TIER = 0


def register(add, config) -> None:
    """Register this module's tools."""

    def ping(message: str = "hello") -> dict:
        """Echo a message back along with basic server details.

        Use this to confirm the connection to the pytribeam server works.
        Touches no hardware and has no side effects.
        """
        return {
            "echo": message,
            "server_time": datetime.datetime.now().astimezone().isoformat(),
            "pytribeam_version": __version__,
            "max_tier": config.max_tier,
            "microscope_host": config.microscope_host,
        }

    add(ping, read_only=True)
