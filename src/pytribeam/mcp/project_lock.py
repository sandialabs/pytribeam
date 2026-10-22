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
behind. The file holds the owner's pid and start time, for the error message
a second server shows.
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
    path = project_dir / ".lock"
    # "a+" so opening never truncates the owner's details before we hold it.
    f = open(path, "a+", encoding="utf-8")
    if not _try_lock(f):
        f.seek(0)
        owner = f.read().strip() or "unknown process"
        f.close()
        raise ProjectLocked(
            f"Another pytribeam MCP server is using {project_dir} ({owner}). "
            "Stop it, or give this server its own --project-dir."
        )
    f.seek(0)
    f.truncate()
    started = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    f.write(f"pid {os.getpid()}, started {started}\n")
    f.flush()
    return f
