#!/usr/bin/python3
"""
Audit Records
=============

Every tool call is written to ``<log_dir>/audit.jsonl`` by the server's audit
wrapper, one JSON object per line. Each call has an ``op_id``, unique across
sessions: this process's ``SESSION_ID`` and a counter. Calls above tier 0
write two records:

* ``{"event": "started", ...}`` before the tool runs;
* ``{"event": "ended", "ok": ..., ...}`` after it returns or fails.

A ``started`` with no ``ended`` from an earlier session means the process
stopped mid-action: :func:`summarize` reports it as interrupted, since the
microscope may have been left part way through. Tier 0 calls only write the
``ended`` record; they change nothing, so there is nothing to recover.

This module has no MCP or AutoScript imports, so both the server and the
capabilities can use it.
"""

from __future__ import annotations

import datetime
import itertools
import json
import secrets
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SESSION_ID = (
    datetime.datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(2)
)

_counter = itertools.count(1)
_current = threading.local()


def new_op_id() -> str:
    return f"{SESSION_ID}.{next(_counter):04d}"


def current_op_id() -> Optional[str]:
    """The op_id of the tool call running in this thread, if any."""
    return getattr(_current, "op_id", None)


def set_current_op_id(op_id: Optional[str]) -> None:
    _current.op_id = op_id


def read(path: Path) -> List[Dict[str, Any]]:
    """Every record in an audit log, oldest first. Torn lines are kept as
    ``{"unreadable": text}`` so a crash mid-write does not hide the rest."""
    records: List[Dict[str, Any]] = []
    if not Path(path).is_file():
        return records
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append({"unreadable": line.strip()})
    return records


def summarize(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One entry per operation, in the order they started.

    An ``ended`` record replaces its ``started`` one. A ``started`` with no
    ``ended`` gets ``"outcome": "interrupted"`` if it is from an earlier
    session, or ``"outcome": "running"`` if it is from this one. Records
    without an ``op_id`` (written before op ids existed) pass through as they
    are.
    """
    ops: Dict[str, Dict[str, Any]] = {}
    order: List[Any] = []
    for i, record in enumerate(records):
        op_id = record.get("op_id")
        if op_id is None:
            order.append(("legacy", i, record))
            continue
        if op_id not in ops:
            order.append(("op", op_id, None))
        if record.get("event") == "started" and op_id in ops:
            continue  # keep the ended record if both are present
        ops[op_id] = record

    summary = []
    for kind, key, record in order:
        if kind == "legacy":
            summary.append(record)
            continue
        record = dict(ops[key])
        if record.get("event") == "started":
            ours = key.startswith(SESSION_ID + ".")
            record["outcome"] = "running" if ours else "interrupted"
        summary.append(record)
    return summary


def interrupted(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Operations from earlier sessions that started and never ended."""
    return [r for r in summarize(records) if r.get("outcome") == "interrupted"]
