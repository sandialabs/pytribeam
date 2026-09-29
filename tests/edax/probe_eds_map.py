#!/usr/bin/python3
"""
Record what APEX reports, second by second, while one small EDS map runs.

pyTriBeam decides an EDS map is finished from ``get_map_status`` and the
``EVENT_MAP_COLLECTION_COMPLETE`` event. On hardware, a 32 s map reported
``Ready`` 12 s after starting, which is also what APEX reports before a map
has begun, so the status alone cannot say whether the map ran. This probe
collects the evidence needed to choose the completion rule:

- the payload APEX acknowledged ``do_map_collection_start`` with;
- every EDS (and, for comparison, EBSD) map status, once a second, with time;
- every event, with the time it arrived;
- the files that appeared in the map folder, when it is on this machine.

It starts a map, which scans the beam, so it will not run without ``--yes``.
It never moves a detector: insert the EDS detector from APEX yourself, with
the chamber CCD on, before running it. It sets the same headless state as the
workflow (NoWait access, folder, project), applies a small map size, and puts
APEX's own map size back afterwards.

From the repository root, in the same environment as pytest::

    python tests/edax/probe_eds_map.py --folder "D:\\EDAX Data\\probe" --yes

Watch APEX while it runs, and note whether and when it shows the map
collecting. Output is plain ASCII, so it can be pasted as-is.
"""

# Default python modules
import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import conftest  # noqa: E402  (loads .env, as pytest does)
from pytribeam.external_oem.edax import mapping  # noqa: E402
from pytribeam.external_oem.edax.client import EdaxClient  # noqa: E402
from pytribeam.external_oem.edax.eds import EdaxEdsController  # noqa: E402
from pytribeam.external_oem.edax.errors import EdaxError, EdaxTimeoutError  # noqa: E402
from pytribeam.external_oem.edax.types import (  # noqa: E402
    EdaxCommand,
    EdaxConnectionSettings,
    EdaxDetectorSlideStatus,
    EdaxEdsMapParams,
    EdaxEvent,
    EdaxProjectInfo,
)

# Same as Constants.EDAX_GUID; not imported, so this runs without AutoScript.
PROJECT = EdaxProjectInfo(
    guid="7b093500-6e8e-4657-bf45-03bc05ce8a32", name="pytribeam_eds_probe"
)

# Answers that mean a map is under way, as opposed to idle or finished.
IN_PROGRESS = {
    "setupactive",
    "setuppaused",
    "setupresumed",
    "mappingactive",
    "mappingpaused",
    "mappingresumed",
}


def _arguments():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--folder",
        default=os.environ.get("PYTRIBEAM_EDAX_MAP_FOLDER", ""),
        help="existing folder on the EDAX PC for the map "
        "(default: PYTRIBEAM_EDAX_MAP_FOLDER)",
    )
    parser.add_argument("--points", type=int, default=128)
    parser.add_argument("--lines", type=int, default=100)
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--dwell-us", type=float, default=200.0)
    parser.add_argument(
        "--after-s",
        type=float,
        default=20.0,
        help="keep recording this long after the completion event",
    )
    parser.add_argument(
        "--yes", action="store_true", help="actually start the map (scans the beam)"
    )
    return parser.parse_args()


class Recorder:
    """Print lines stamped with seconds since the map was started."""

    def __init__(self):
        self.start = None

    def __call__(self, message: str) -> None:
        stamp = "  --  " if self.start is None else f"{time.time() - self.start:6.1f}"
        print(f"[{stamp}] {message}", flush=True)


def _poll_statuses(client, pending, timeout_s=5.0):
    """
    Query the EDS then the EBSD map status, one request at a time.

    ``pending`` is a command still awaiting its reply from the last round. It
    is waited on rather than re-sent, and nothing else is sent until it
    answers; see ``EdaxMappingController.wait_for_map_complete`` for why.
    Returns ({command: payload, or None if unanswered}, pending).
    """
    answers = {}
    for command in (EdaxCommand.EDS_GET_MAP_STATUS, EdaxCommand.EBSD_GET_MAP_STATUS):
        if pending is not None and pending is not command:
            continue
        try:
            if pending is command:
                response = client.await_response(command, timeout_s=timeout_s)
            else:
                response = client.send(command, timeout_s=timeout_s)
        except EdaxTimeoutError:
            answers[command] = None
            return answers, command
        answers[command] = response.payload
        pending = None
    return answers, None


def _snapshot(folder: Path):
    """Return {relative path: size} under a local folder, or None if not local."""
    if not folder.is_dir():
        return None
    return {
        str(path.relative_to(folder)): path.stat().st_size
        for path in folder.rglob("*")
        if path.is_file()
    }


def main() -> int:
    args = _arguments()
    host = os.environ.get(conftest.EDAX_HOST_ENV_VAR, "").strip() or "localhost"
    port = int(os.environ.get("PYTRIBEAM_EDAX_PORT", "8301"))
    params = EdaxEdsMapParams(
        num_points=args.points,
        num_lines=args.lines,
        num_frames=args.frames,
        preset_dwell_us=args.dwell_us,
    )
    if not args.folder:
        print("No map folder: pass --folder or set PYTRIBEAM_EDAX_MAP_FOLDER.")
        return 2
    folder = Path(args.folder)
    tag = time.strftime("probe_%Y%m%d_%H%M%S")
    nominal_s = args.points * args.lines * args.frames * args.dwell_us * 1e-6

    print(f"EDS map probe at {host}:{port}")
    print(f"  folder {folder}, tag {tag}")
    print(f"  {params}")
    print(f"  points x lines x frames x dwell = {nominal_s:.1f} s")
    if not args.yes:
        print("\nDry run. Add --yes to start the map; it scans the beam.")
        return 0

    log = Recorder()
    settings = EdaxConnectionSettings(host=host, port=port, timeout_s=15.0)
    with EdaxClient(settings, quiet=True) as client:
        eds = EdaxEdsController(client)

        position = eds.slide_status()
        log(f"EDS detector position: {position.value}")
        if position is not EdaxDetectorSlideStatus.SLIDE_IN:
            print(
                "\nThe EDS detector is not inserted. Insert it from APEX with the "
                "chamber CCD on, then run this again. The probe never moves it."
            )
            return 2
        status = client.query(EdaxCommand.EDS_GET_MAP_STATUS)
        log(f"EDS map status before anything: {status!r}")
        if status.strip().lower() in IN_PROGRESS:
            print("\nAn EDS map is already running in APEX; stop it first.")
            return 2

        original = eds.map_parameters()
        files_before = _snapshot(folder)
        try:
            mapping.run_eds_preflight(eds, folder, PROJECT)
            log("preflight done: NoWait access, folder, project, detector ready")
            eds.apply_map_parameters(params)
            log(f"applied; APEX reads back {eds.map_parameters()}")
            predicted_s = eds.map_duration_s()
            log(f"APEX predicts {predicted_s:.1f} s")
            log(f"events so far: {[e.raw for e in client.drain_events()] or 'none'}")

            deadline_s = max(3 * predicted_s, predicted_s + 120.0)
            log.start = time.time()
            reply = client.send(EdaxCommand.EDS_COLLECTION_START, tag)
            log(f"do_map_collection_start acknowledged with {reply.payload!r}")

            first_busy = completed_at = pending = None
            while True:
                elapsed = time.time() - log.start
                for event in client.drain_events():
                    log(f"EVENT {event.raw!r}")
                    if event.command == EdaxEvent.EDS_COLLECTION_COMPLETE.value:
                        completed_at = completed_at or elapsed
                answers, pending = _poll_statuses(client, pending)
                eds_status = answers.get(EdaxCommand.EDS_GET_MAP_STATUS)
                ebsd_status = answers.get(EdaxCommand.EBSD_GET_MAP_STATUS)
                log(
                    f"get_map_status {eds_status!r:<18} "
                    f"get_map_status_ebsd {ebsd_status!r}"
                    + ("" if pending is None else "  (no answer yet; APEX busy)")
                )
                if (
                    first_busy is None
                    and eds_status
                    and eds_status.strip().lower() in IN_PROGRESS
                ):
                    first_busy = elapsed
                if completed_at is not None and elapsed >= completed_at + args.after_s:
                    break
                if elapsed >= deadline_s:
                    log(f"no completion event after {deadline_s:.0f} s; stopping")
                    break
                time.sleep(1.0)
            # Leave nothing outstanding before the connection closes.
            client.quiesce()
        finally:
            eds.apply_map_parameters(
                EdaxEdsMapParams(
                    num_points=original.num_points,
                    num_lines=original.num_lines,
                    num_frames=original.num_frames,
                    preset_dwell_us=original.preset_dwell_us,
                )
            )
            print("\nAPEX's own EDS map size restored.")

    print("\nSummary")
    print(f"  predicted duration        {predicted_s:.1f} s")
    print(
        "  first in-progress status  "
        + ("never" if first_busy is None else f"{first_busy:.1f} s")
    )
    print(
        "  completion event          "
        + ("never" if completed_at is None else f"{completed_at:.1f} s")
    )
    files_after = _snapshot(folder)
    if files_before is None:
        print("  new files                 folder is not on this machine; check it")
    else:
        new = sorted(set(files_after) - set(files_before))
        print(f"  new files                 {new or 'none'}")
    print("\nThe EDS detector is still inserted; retract it from APEX.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EdaxError as error:
        print(f"\nIPAPI error: {type(error).__name__}: {error}")
        raise SystemExit(1)
