#!/usr/bin/python3
"""
State Record Schema
===================

Serialization layer for microscope state records.

This module is deliberately free of any AutoScript or ``pytribeam.types``
dependency so that it can be imported, tested, and developed on a machine
with no microscope software installed. It uses ``yaml`` directly rather than
``pytribeam.utilities.dict_to_yml`` because ``pytribeam.utilities`` imports
``pytribeam.types``, which hard-imports the AutoScript client.

Do not add imports from the rest of ``pytribeam`` to this file.

On-disk layout
--------------
A *state directory* holds one file per recorded state plus an index::

    my_session/
        index.yml
        states/
            s0001.yml
            s0002.yml

Writing one file per state (rather than rewriting a single growing journal)
keeps each write O(1), makes an interrupted write survivable, and makes
individual states convenient to use as test fixtures.
"""

from __future__ import annotations

import dataclasses
import datetime
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import yaml

SCHEMA_VERSION = "1.0"
"""Version of the state record format itself.

This is distinct from ``config_file_version`` used by pytribeam experiment
configuration files. Bump the minor version for backward-compatible additions
and the major version for changes that older readers cannot handle.
"""

INDEX_FILENAME = "index.yml"
STATES_DIRNAME = "states"

SUBSYSTEMS = (
    "beams",
    "detector",
    "gas",
    "patterning",
    "specimen",
    "state",
    "vacuum",
    "imaging",
)
"""Top level microscope subsystems walked by the recorder.

The subsystem of any path is its first dot-separated component, so this tuple
is only needed at capture time; readers derive it with :func:`subsystem_of`.
"""


def utc_offset_now() -> str:
    """Return the current local time as an ISO 8601 string with UTC offset.

    Returns
    -------
    str
        e.g. ``"2026-07-15T14:14:03.127-06:00"``.
    """
    return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


def subsystem_of(path: str) -> str:
    """Return the subsystem component of a dotted state path.

    Parameters
    ----------
    path : str
        Dotted path, e.g. ``"specimen.stage.current_position.x"``.

    Returns
    -------
    str
        The leading component, e.g. ``"specimen"``.
    """
    return path.split(".", 1)[0]


@dataclasses.dataclass(frozen=True)
class ReadError:
    """A single attribute that could not be read or represented.

    Recorded explicitly so that a missing key is never ambiguous. Without
    this, "the field vanished between A and B" and "the field failed to read
    in B" look identical to a diff consumer, and they mean very different
    things.

    Attributes
    ----------
    path : str
        Dotted path that failed.
    error : str
        Short description, typically ``"<ExceptionType>: <message>"``.
    kind : str
        ``"access"`` if reading the attribute raised, ``"coerce"`` if the
        value was read but could not be represented as a scalar.
    """

    path: str
    error: str
    kind: str = "access"

    def to_dict(self) -> Dict[str, str]:
        """Return a plain dictionary representation."""
        return {"path": self.path, "error": self.error, "kind": self.kind}

    @classmethod
    def from_dict(cls, db: Dict[str, str]) -> "ReadError":
        """Build a :class:`ReadError` from a plain dictionary."""
        return cls(
            path=db["path"],
            error=db.get("error", ""),
            kind=db.get("kind", "access"),
        )


@dataclasses.dataclass(frozen=True)
class Provenance:
    """Software and connection context for a recording session.

    Diffing two states captured under different pytribeam or AutoScript
    versions is legitimate, but the consumer must be able to notice it.

    Attributes
    ----------
    pytribeam_version : str
        Version of pytribeam that produced the record.
    autoscript_version : str
        Version of the AutoScript client library.
    host : str
        Microscope connection host.
    port : int, optional
        Microscope connection port, or None for the default.
    hostname : str
        Name of the machine that performed the recording.
    recorded_by : str
        Identifier for the producer, e.g. ``"state_recorder"`` or an agent id.
    """

    pytribeam_version: str = "unknown"
    autoscript_version: str = "unknown"
    host: str = "unknown"
    port: Optional[int] = None
    hostname: str = "unknown"
    recorded_by: str = "state_recorder"

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dictionary representation."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, db: Optional[Dict[str, Any]]) -> "Provenance":
        """Build a :class:`Provenance` from a plain dictionary."""
        if not db:
            return cls()
        fields = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in db.items() if k in fields})


@dataclasses.dataclass
class StateRecord:
    """A single captured microscope state.

    Attributes
    ----------
    id : str
        Stable short identifier, e.g. ``"s0003"``. Tools reference states by
        this rather than by timestamp.
    recorded_at : str
        ISO 8601 timestamp with UTC offset.
    values : dict
        Flat mapping of dotted path to scalar value. Paths carry no
        ``scope.`` prefix and are not nested by subsystem; grouping is the
        consumer's job, which keeps a single source of truth for each path
        and makes glob matching against the path metadata table trivial.
    description : str
        Free-text operator note.
    intended_action : str, optional
        Name of the capability the operator believes they used, e.g.
        ``"move_stage"``. Null when the change was uncontrolled or unknown.
        In test fixtures this serves as labelled ground truth for whether a
        diff correctly groups several changed paths into one operation.
    read_errors : list of ReadError
        Attributes that could not be read or represented.
    provenance : Provenance
        Software and connection context.
    """

    id: str
    recorded_at: str
    values: Dict[str, Any] = dataclasses.field(default_factory=dict)
    description: str = ""
    intended_action: Optional[str] = None
    read_errors: List[ReadError] = dataclasses.field(default_factory=list)
    provenance: Provenance = dataclasses.field(default_factory=Provenance)

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain, YAML-safe dictionary representation."""
        return {
            "id": self.id,
            "recorded_at": self.recorded_at,
            "description": self.description,
            "intended_action": self.intended_action,
            "provenance": self.provenance.to_dict(),
            "read_errors": [e.to_dict() for e in self.read_errors],
            "values": dict(self.values),
        }

    @classmethod
    def from_dict(cls, db: Dict[str, Any]) -> "StateRecord":
        """Build a :class:`StateRecord` from a plain dictionary.

        Raises
        ------
        KeyError
            If required keys are absent.
        """
        return cls(
            id=db["id"],
            recorded_at=db["recorded_at"],
            values=dict(db.get("values") or {}),
            description=db.get("description") or "",
            intended_action=db.get("intended_action"),
            read_errors=[
                ReadError.from_dict(e) for e in (db.get("read_errors") or [])
            ],
            provenance=Provenance.from_dict(db.get("provenance")),
        )

    def summary(self) -> Dict[str, Any]:
        """Return the compact form stored in the directory index."""
        return {
            "id": self.id,
            "recorded_at": self.recorded_at,
            "description": self.description,
            "intended_action": self.intended_action,
            "n_values": len(self.values),
            "n_read_errors": len(self.read_errors),
        }


def _atomic_write_yaml(db: Dict[str, Any], file_path: Path) -> Path:
    """Write *db* to *file_path* as YAML via a temporary file and rename.

    A direct write leaves a truncated file if the process dies partway
    through. Writing to a sibling temporary file and renaming makes the
    replacement atomic on POSIX and on Windows via ``os.replace``.

    Parameters
    ----------
    db : dict
        Data to serialize.
    file_path : Path
        Destination path.

    Returns
    -------
    Path
        The destination path.
    """
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    handle, tmp_name = tempfile.mkstemp(
        dir=str(file_path.parent),
        prefix=file_path.name + ".",
        suffix=".tmp",
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out_file:
            yaml.safe_dump(
                db,
                out_file,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
            out_file.flush()
            os.fsync(out_file.fileno())
        os.replace(tmp_name, file_path)
    except BaseException:
        with contextlib_suppress():
            os.unlink(tmp_name)
        raise

    return file_path


class contextlib_suppress:
    """Minimal stand-in for ``contextlib.suppress(OSError)``."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return exc_type is not None and issubclass(exc_type, OSError)


def _read_yaml(file_path: Path) -> Dict[str, Any]:
    """Read a YAML file and return a dictionary.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    ValueError
        If the file does not contain a mapping.
    """
    file_path = Path(file_path)
    if not file_path.is_file():
        raise FileNotFoundError(f"No such file: {file_path}")

    with open(file_path, "r", encoding="utf-8") as in_file:
        db = yaml.safe_load(in_file)

    if not isinstance(db, dict):
        raise ValueError(f"Expected a mapping at the top level of {file_path}")

    return db


def _check_schema_version(db: Dict[str, Any], file_path: Path) -> None:
    """Raise if the file's major schema version is not readable here.

    Raises
    ------
    ValueError
        If the major version differs from :data:`SCHEMA_VERSION`.
    """
    found = str(db.get("schema_version", "0.0"))
    if found.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise ValueError(
            f"{file_path} has schema_version {found}, which this reader "
            f"(schema_version {SCHEMA_VERSION}) cannot interpret."
        )


def states_dir(directory: Path) -> Path:
    """Return the subdirectory holding individual state files."""
    return Path(directory) / STATES_DIRNAME


def index_path(directory: Path) -> Path:
    """Return the path to the index file for a state directory."""
    return Path(directory) / INDEX_FILENAME


def record_path(directory: Path, record_id: str) -> Path:
    """Return the path to a single state record file."""
    return states_dir(directory) / f"{record_id}.yml"


def read_index(directory: Path) -> List[Dict[str, Any]]:
    """Return the list of record summaries for a state directory.

    Returns
    -------
    list of dict
        Summaries in recording order. Empty if no index exists yet.
    """
    path = index_path(directory)
    if not path.is_file():
        return []

    db = _read_yaml(path)
    _check_schema_version(db, path)
    return list(db.get("records") or [])


def next_record_id(directory: Path) -> str:
    """Return the next unused record id for a state directory.

    Ids are zero-padded and monotonically increasing, so they sort correctly
    as strings. Unlike a timestamp key they are stable, locale-independent,
    and safe to use as a filename.
    """
    existing = read_index(directory)
    numbers = []
    for entry in existing:
        try:
            numbers.append(int(str(entry.get("id", "s0"))[1:]))
        except ValueError:
            continue
    nxt = max(numbers) + 1 if numbers else 1
    return f"s{nxt:04d}"


def write_record(record: StateRecord, directory: Path) -> Path:
    """Write a state record into a state directory and update the index.

    The record file is written before the index, so an interruption leaves an
    orphaned state file rather than an index entry pointing at nothing.

    Parameters
    ----------
    record : StateRecord
        The record to write.
    directory : Path
        The state directory. Created if absent.

    Returns
    -------
    Path
        Path to the written record file.
    """
    directory = Path(directory)
    target = record_path(directory, record.id)

    _atomic_write_yaml(
        {"schema_version": SCHEMA_VERSION, **record.to_dict()},
        target,
    )

    summaries = [e for e in read_index(directory) if e.get("id") != record.id]
    summaries.append(record.summary())
    _atomic_write_yaml(
        {
            "schema_version": SCHEMA_VERSION,
            "provenance": record.provenance.to_dict(),
            "records": summaries,
        },
        index_path(directory),
    )

    return target


def read_record(directory: Path, record_id: str) -> StateRecord:
    """Read a single state record by id.

    Raises
    ------
    FileNotFoundError
        If no record with that id exists.
    ValueError
        If the record is malformed or written under an unreadable schema.
    """
    path = record_path(directory, record_id)
    db = _read_yaml(path)
    _check_schema_version(db, path)
    try:
        return StateRecord.from_dict(db)
    except KeyError as error:
        raise ValueError(f"{path} is missing required key {error}") from error


def read_record_file(file_path: Path) -> StateRecord:
    """Read a state record from an explicit file path.

    Convenience for test fixtures laid out as ``before.yml`` / ``after.yml``
    rather than as an indexed state directory.
    """
    file_path = Path(file_path)
    db = _read_yaml(file_path)
    _check_schema_version(db, file_path)
    try:
        return StateRecord.from_dict(db)
    except KeyError as error:
        raise ValueError(f"{file_path} is missing required key {error}") from error


def iter_records(directory: Path) -> Iterator[StateRecord]:
    """Yield every record in a state directory in recording order."""
    for entry in read_index(directory):
        yield read_record(directory, entry["id"])
