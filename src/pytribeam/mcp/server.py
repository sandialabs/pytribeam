"""Read-only MCP-style state access tools.

This module exposes the small, safe surface area the MCP server needs for
recorded states: listing available records, reading one state, and diffs
between two states. It intentionally avoids any hardware access and any
AutoScript / vendor imports.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Union

from pytribeam.mcp.state import diff, metadata, schema

StateDir = Union[str, Path]


def _default_state_dir() -> Path:
    """Return the best-known state fixture directory if one exists."""
    candidates = [
        Path.cwd() / "tests" / "mcp" / "state_records",
        Path.cwd() / "state_records",
        Path(__file__).resolve().parents[3] / "tests" / "mcp" / "state_records",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "No state directory found. Pass directory=... explicitly or create a "
        "state_records directory in the project."
    )


def _resolve_state_dir(directory: Optional[StateDir] = None) -> Path:
    if directory is None:
        return _default_state_dir()
    return Path(directory)


def list_states(directory: Optional[StateDir] = None) -> list[dict]:
    """Return the index summaries for every state record in a directory."""
    state_dir = _resolve_state_dir(directory)
    return list(schema.read_index(state_dir))


def get_state(record_id: str, directory: Optional[StateDir] = None) -> dict:
    """Return the full serialized state for *record_id*."""
    state_dir = _resolve_state_dir(directory)
    return schema.read_record(state_dir, record_id).to_dict()


def diff_states(
    before_id: str,
    after_id: str,
    directory: Optional[StateDir] = None,
    path_metadata: Optional[metadata.PathMetadata] = None,
) -> dict:
    """Return the diff between two state records from *directory*."""
    state_dir = _resolve_state_dir(directory)
    before = schema.read_record(state_dir, before_id)
    after = schema.read_record(state_dir, after_id)
    pm = path_metadata or metadata.load()
    return diff.diff_records(before, after, pm).to_dict()


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Read-only pytribeam state inspection tools")
    parser.add_argument("command", choices=["list", "get", "diff"], help="Action to perform")
    parser.add_argument("--directory", default=None, help="State record directory to inspect")
    parser.add_argument("--before", default=None, help="Before record id for a diff")
    parser.add_argument("--after", default=None, help="After record id for a diff")
    parser.add_argument("--record", default=None, help="Single record id for get")
    args = parser.parse_args()

    if args.command == "list":
        records = list_states(args.directory)
        print(records)
        return

    if args.command == "get":
        if not args.record:
            raise SystemExit("--record is required for get")
        print(get_state(args.record, args.directory))
        return

    if args.command == "diff":
        if not args.before or not args.after:
            raise SystemExit("--before and --after are required for diff")
        print(diff_states(args.before, args.after, args.directory))
        return


__all__ = ["list_states", "get_state", "diff_states"]


if __name__ == "__main__":
    _cli()
