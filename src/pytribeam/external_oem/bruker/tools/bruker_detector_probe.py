"""Probe Bruker EDS detector indices.

This standalone tool helps users determine which ``detector_index`` to use in
Bruker YAML configs. It tries a range of detector indices and reports whether
``EDSGetDetectorPosition`` succeeds.

Usage:
    python bruker_detector_probe.py --dll-dir "C:/Program Files/Bruker/Esprit API"
    python bruker_detector_probe.py --config bruker_eds_workflow_test.yml
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from pytribeam.external_oem.bruker.config import load_bruker_eds_yaml
from pytribeam.external_oem.bruker.detector_motion import BrukerDetectorMotionController
from pytribeam.external_oem.bruker.runtime import validate_bruker_runtime_environment
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.types import BrukerSessionSettings


def _default_session_settings(dll_dir: str) -> BrukerSessionSettings:
    return BrukerSessionSettings(
        dll_dir=dll_dir,
        mode="local",
        server="Lokaler Server",
        user="edx",
        password="edx",
        host=None,
        port=None,
        close_on_exit=False,
        keep_connection_open=True,
    )


def _parse_indices(text: str):
    return [int(part.strip()) for part in text.split(",") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional Bruker EDS workflow YAML to read session settings from.",
    )
    parser.add_argument(
        "--dll-dir",
        default="C:/Program Files/Bruker/Esprit API",
        help="Bruker ESPRIT API DLL directory if --config is not supplied.",
    )
    parser.add_argument(
        "--indices",
        default="0,1,2,3,4",
        help="Comma-separated detector indices to probe (default: 0,1,2,3,4).",
    )
    args = parser.parse_args()

    if args.config is not None:
        settings = load_bruker_eds_yaml(args.config).session
    else:
        settings = _default_session_settings(args.dll_dir)

    print("=== Bruker EDS detector index probe ===")
    print(f"DLL dir: {settings.dll_dir}")
    validate_bruker_runtime_environment(settings)

    session = BrukerSession(settings)
    try:
        info = session.connect()
        print(f"Connected CID={info.cid}")
        print(f"QueryInfo: {info.query_info}")

        motion = BrukerDetectorMotionController(session)
        for detector_index in _parse_indices(args.indices):
            try:
                state = motion.get_eds_detector_position(detector_index)
                print(
                    f"detector_index={detector_index}: OK "
                    f"position_code={state.position_code} "
                    f"position_name={state.position_name}"
                )
            except Exception as exc:
                print(
                    f"detector_index={detector_index}: unavailable/error: "
                    f"{type(exc).__name__}: {exc}"
                )
    finally:
        if settings.close_on_exit:
            session.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
