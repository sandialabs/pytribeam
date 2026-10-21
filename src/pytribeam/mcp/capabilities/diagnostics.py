#!/usr/bin/python3
"""
Diagnostic Capabilities
=======================

Tier 0 tools for checking that the agent, server, configuration, and
microscope connection are wired up correctly. Only ``check_connection`` and
``reconnect`` touch the microscope, and they only read from it.

Every capability module follows the same shape:

* ``TIER``: the tier of every tool in the module.
* ``register(add, config, connection)``: calls ``add(fn, ...)`` once per tool.

Modules never see the server object itself. ``add`` is the only way in, and it
is what applies tier gating and audit logging, so a capability cannot register
a tool that bypasses either. Anything a tool needs from the session (the config
and the shared microscope connection) is captured by closure in ``register``
rather than exposed as a tool argument the agent could set.
"""

from __future__ import annotations

import collections
import datetime
import json
import platform
import sys
import time
from typing import Any, Dict, Optional

from pytribeam import __version__
from pytribeam._package_metadata import get_autoscript_version
from pytribeam.mcp.config import TIERS

TIER = 0

MAX_ACTIVITY_RECORDS = 200


def _probe(microscope) -> Dict[str, Any]:
    """Time one cheap read, and report the vacuum and the active view."""
    from pytribeam import types as tbt

    start = time.perf_counter()
    vacuum = microscope.vacuum.chamber_state
    round_trip_ms = (time.perf_counter() - start) * 1000
    return {
        "round_trip_ms": round(round_trip_ms, 1),
        "vacuum": str(vacuum),
        "active_view": int(microscope.imaging.get_active_view()),
        "active_device": tbt.Device(microscope.imaging.get_active_device()).name,
    }


def _is_simulator() -> Optional[bool]:
    """Whether this machine is a known offline (simulator) PC, or None if unknown."""
    try:
        from pytribeam.constants import Constants
    except ImportError:  # constants imports AutoScript
        return None
    node = platform.uname().node.lower()
    return node in (name.lower() for name in Constants.offline_machines)


def register(add, config, connection) -> None:
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

    def get_server_info() -> dict:
        """Describe this server: versions, tiers, folders, and microscope address.

        ``tiers`` lists every tier and whether this session exposes it; tools
        above ``max_tier`` are not available, and only the operator can raise
        it. ``connected`` says whether a microscope connection is currently
        open. Touches no hardware and never connects; use
        ``check_connection`` to test the microscope.
        """
        return {
            "pytribeam_version": __version__,
            "autoscript_version": get_autoscript_version(),
            "python_version": platform.python_version(),
            "max_tier": config.max_tier,
            "tiers": [
                {"tier": tier, "meaning": meaning, "enabled": tier <= config.max_tier}
                for tier, meaning in TIERS.items()
            ],
            "project_dir": str(config.project_dir),
            "log_dir": str(config.log_dir),
            "states_dir": str(config.states_dir),
            "images_dir": str(config.images_dir),
            "microscope_host": config.microscope_host,
            "microscope_port": config.microscope_port,
            "connected": connection.connected,
        }

    def check_connection() -> dict:
        """Check that the microscope answers, connecting first if needed.

        Makes one cheap read (the chamber vacuum state) and reports its
        round-trip time in ms, the vacuum state, and the active view (quad
        1-4) and its device. ``simulator`` is true on a known offline
        simulator PC, false otherwise, and null if it cannot be determined.

        If the microscope cannot be reached, this does not fail: it returns
        ``connected: false`` and the ``error``. Report that to the user. Only
        reads; changes nothing on the microscope.
        """
        result: Dict[str, Any] = {
            "connected": False,
            "microscope_host": config.microscope_host,
            "microscope_port": config.microscope_port,
            "simulator": _is_simulator(),
        }
        try:
            with connection.use() as microscope:
                result.update(_probe(microscope))
        except Exception as exc:
            # A connection that cannot answer a simple read is not worth
            # keeping; the next call opens a fresh one.
            connection.reset()
            result["error"] = str(exc) or type(exc).__name__
        else:
            result["connected"] = True
        return result

    def reconnect() -> dict:
        """Drop the microscope connection and open a new one.

        Use this after the microscope software (xT or AutoScript) restarts,
        or when tools keep failing with connection errors. Also clears
        cached hardware queries such as the detector lists. Returns the same
        result as ``check_connection``.
        """
        connection.reset()
        return check_connection()

    def get_recent_activity(limit: int = 20) -> dict:
        """Return the most recent tool calls from this project's audit log.

        Includes calls from earlier sessions, so use it to recover what was
        done before. Records are oldest first, newest last; each has the
        tool, its arguments, whether it succeeded, and any error. ``limit``
        is capped at 200; ``total`` is how many records the log holds. This
        call itself is not included. Touches no hardware.
        """
        limit = max(0, min(limit, MAX_ACTIVITY_RECORDS))
        path = config.log_dir / "audit.jsonl"
        total = 0
        recent: collections.deque = collections.deque(maxlen=limit)
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        total += 1
                        recent.append(line)

        records = []
        for line in recent:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append({"unreadable": line.strip()})
        return {"total": total, "records": records}

    add(ping, read_only=True)
    add(get_server_info, read_only=True)
    add(check_connection, read_only=True)
    add(reconnect, read_only=True)
    add(get_recent_activity, read_only=True)
