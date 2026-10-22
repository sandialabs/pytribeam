#!/usr/bin/python3
"""
Project Directory Lock
======================

One server process owns a project directory. Two servers writing the same
``states/`` and ``images/`` would race for the next ``sNNNN``/``iNNNN`` number
and interleave their audit logs, and each would believe it alone controls the
microscope.

:func:`acquire` takes an exclusive lock on ``<project_dir>/.lock`` and keeps the
file open for the life of the process. The operating system releases the lock
when the process exits, however it exits, so a crash never leaves a stale lock
behind.

The lock file is never written. On Windows, ``msvcrt.locking`` locks one byte
at the current position, and the lock is mandatory: no other handle may read
or write that byte. So every process locks byte 0 of an empty file, and the
owner's pid and start time go in a separate ``.lock.owner`` file that a second
server can read for its error message.
"""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path
from typing import IO


class ProjectLocked(RuntimeError):
    """Another server process already owns this project directory."""


def _try_lock(f: IO) -> bool:
    f.seek(0)  # Windows locks the byte at the current position: always byte 0
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    import fcntl

    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def acquire(project_dir: Path) -> IO:
    """Lock *project_dir* for this process, or raise :class:`ProjectLocked`.

    Returns the open lock file; keep a reference to it for as long as the
    server runs. Closing it (or exiting) releases the lock.
    """
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    owner_path = project_dir / ".lock.owner"
    # "a" creates the file without truncating it, and it is never written.
    f = open(project_dir / ".lock", "a", encoding="utf-8")
    if not _try_lock(f):
        f.close()
        try:
            owner = owner_path.read_text(encoding="utf-8").strip()
        except OSError:
            owner = ""
        raise ProjectLocked(
            f"Another pytribeam MCP server is using {project_dir} "
            f"({owner or 'unknown process'}). Stop it, or give this server its "
            "own --project-dir."
        )
    started = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    owner_path.write_text(f"pid {os.getpid()}, started {started}\n", encoding="utf-8")
    return f
