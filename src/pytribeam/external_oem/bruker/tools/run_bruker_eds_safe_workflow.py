"""Run a standalone Bruker EDS YAML workflow with operator-safe defaults.

This tool is a small command-line wrapper around the standalone Bruker EDS
workflow modules. The Bruker YAML remains the source of truth for session,
detector motion, acquisition, and output settings. This wrapper adds:

* local Bruker DLL runtime preflight before connecting to ESPRIT,
* an owned BrukerSession so the CLI can attempt detector recovery on failure,
* BCF-only acquisition policy by disabling API readback for this CLI run,
* strict final detector-position confirmation when detector motion is enabled,
* clear operator-facing log and traceback output.

No TFS Laser API, AutoScript, main pytribeam workflow dispatch, or GUI code is
used by this script.

Usage:
    python run_bruker_eds_safe_workflow.py --config C:/path/bruker_config.yml
    python run_bruker_eds_safe_workflow.py --config C:/path/bruker_config.yml \
        --log-path C:/path/bruker_safe_workflow.log
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

# If pytribeam is not installed but this script is run in-place from the repo,
# add the src directory to sys.path. This mirrors the existing Bruker tool style.
REPO_ROOT = Path(__file__).resolve().parents[5]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pytribeam.external_oem.bruker.config import load_bruker_eds_yaml
from pytribeam.external_oem.bruker.detector_motion import BrukerDetectorMotionController
from pytribeam.external_oem.bruker.runtime import validate_bruker_runtime_environment
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.types import (
    BrukerDetectorMotionSettings,
    BrukerEDSWorkflowResult,
    BrukerEDSWorkflowSettings,
)
from pytribeam.external_oem.bruker.workflow import run_bruker_eds_workflow

BCF_MIN_BYTES = 256

BRUKER_RUNTIME_OPERATOR_HINTS = (
    "Check that session.dll_dir exists on the machine running Python.",
    "Check that Bruker.API.Esprit64.dll exists in session.dll_dir.",
    "If using TCP mode, the Bruker API DLL still must exist locally on the "
    "Python machine.",
    "Bruker output paths are interpreted by the ESPRIT/Bruker machine.",
    "Do not interact with the ESPRIT GUI during Bruker API acquisition.",
    "Use bruker_detector_probe.py if the Bruker detector_index is uncertain.",
)


class TextLogger:
    """Timestamped console/file logger for operator-facing CLI output."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, msg: str) -> None:
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        print(line)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _default_log_path(config_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return config_path.parent / f"{config_path.stem}_safe_workflow_{stamp}.log"


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a standalone Bruker EDS workflow YAML directly. The YAML is "
            "the source of truth for ESPRIT connection, detector motion, map, "
            "and output settings. This CLI disables Bruker API readback and "
            "requires a non-trivial .bcf output."
        ),
        epilog=(
            "Runtime notes: session.dll_dir and Bruker.API.Esprit64.dll must "
            "exist on the Python host even in TCP mode; Bruker output paths are "
            "interpreted by the ESPRIT/Bruker machine; do not interact with the "
            "ESPRIT GUI during acquisition."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to standalone Bruker EDS workflow YAML.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        help=(
            "Optional detailed log path. Defaults to a timestamped log next to "
            "the Bruker YAML."
        ),
    )
    return parser.parse_args(argv)


def _motion_involved(settings: BrukerEDSWorkflowSettings) -> bool:
    detector = settings.detector
    return bool(
        detector.verify_park_before
        or detector.move_to_acquire_before
        or detector.park_after
    )


def _disable_readback_for_safe_cli(
    settings: BrukerEDSWorkflowSettings,
    log: TextLogger,
) -> BrukerEDSWorkflowSettings:
    """Disable Bruker API readback for this CLI run only."""
    if (
        settings.readback.enabled
        or settings.readback.save_element_npy
        or settings.readback.save_element_tiff
        or settings.readback.save_element_images
    ):
        log(
            "Readback disabled by safe workflow CLI policy. .bcf is the "
            "canonical Bruker output; large maps may exceed Bruker API "
            "readback limits."
        )

    return settings._replace(
        readback=settings.readback._replace(
            enabled=False,
            save_element_npy=False,
            save_element_tiff=False,
            save_element_images=False,
        )
    )


def _summarize_settings(settings: BrukerEDSWorkflowSettings, log: TextLogger) -> None:
    log("Bruker YAML loaded and validated")
    log(f"Session mode: {settings.session.mode}")
    log(f"DLL directory: {settings.session.dll_dir}")
    if settings.session.mode == "tcp":
        log(f"TCP host/port: {settings.session.host}:{settings.session.port}")
    log(f"Output root: {settings.output.output_dir}")
    log(f"Run name: {settings.output.run_name}")
    log(
        "Map: "
        f"{settings.map.name}, {settings.map.width_px}x{settings.map.height_px}, "
        f"pixel_time={settings.map.pixel_time_us} us"
    )
    if settings.map.roi is None:
        log("ROI: full frame")
    else:
        roi = settings.map.roi
        log(
            "ROI: "
            f"x={roi.x_start_px}, y={roi.y_start_px}, "
            f"w={roi.width_px}, h={roi.height_px}"
        )

    detector = settings.detector
    log(f"Detector index: {detector.detector_index}")
    log(
        "Detector motion settings: "
        f"verify_park_before={detector.verify_park_before}, "
        f"move_to_acquire_before={detector.move_to_acquire_before}, "
        f"park_after={detector.park_after}"
    )
    if _motion_involved(settings):
        log("Detector final position confirmation is required")
    else:
        log("Detector motion disabled; final detector confirmation will be skipped")
    log("Readback: disabled for safe CLI run")


def _run_runtime_preflight(
    settings: BrukerEDSWorkflowSettings,
    log: TextLogger,
) -> dict[str, str]:
    log("Validating Bruker runtime DLL environment")
    try:
        dll_info = validate_bruker_runtime_environment(settings.session)
    except FileNotFoundError as exc:
        log(f"ERROR: Bruker runtime preflight failed: {exc}")
        log("Operator checks before retrying:")
        for hint in BRUKER_RUNTIME_OPERATOR_HINTS:
            log(f"  - {hint}")
        raise

    log(f"DLL directory found: {dll_info['dll_dir']}")
    log(f"Required ESPRIT DLL found: {dll_info['esprit_dll']}")
    if "logging_dll" in dll_info:
        log(f"Optional Bruker logging DLL found: {dll_info['logging_dll']}")
    else:
        log("Optional Bruker logging DLL not found; continuing")
    return dll_info


def _validate_bcf_result(
    result: BrukerEDSWorkflowResult,
    log: TextLogger,
    min_size_bytes: int = BCF_MIN_BYTES,
) -> bool:
    if not result.bcf_path:
        log("ERROR: Workflow did not report a BCF path")
        return False

    bcf_path = Path(result.bcf_path)
    if not bcf_path.is_file():
        log(f"ERROR: BCF file does not exist: {bcf_path}")
        return False

    size = bcf_path.stat().st_size
    if size <= min_size_bytes:
        log(
            "ERROR: BCF file is unexpectedly small: "
            f"{bcf_path} ({size} bytes <= {min_size_bytes})"
        )
        return False

    log(f"BCF validated: {bcf_path} ({size} bytes)")
    return True


def _confirm_final_detector_position(
    session: BrukerSession,
    settings: BrukerEDSWorkflowSettings,
    log: TextLogger,
) -> bool:
    """Confirm final detector state when detector motion is enabled."""
    if not _motion_involved(settings):
        log("Detector motion disabled; final detector position check skipped")
        return True

    try:
        motion = BrukerDetectorMotionController(session)
        state = motion.get_eds_detector_position(settings.detector.detector_index)
    except Exception as exc:
        log(f"ERROR: final EDS detector position query failed: {exc}")
        return False

    log(
        "Final EDS detector position: "
        f"{state.position_name} (code={state.position_code})"
    )

    if settings.detector.park_after and state.position_name != "park":
        log(
            "ERROR: detector.park_after=true, but final EDS detector "
            f"position is {state.position_name!r}"
        )
        return False

    return True


def _best_effort_park(
    session: BrukerSession,
    settings: BrukerEDSWorkflowSettings,
    log: TextLogger,
) -> None:
    if not settings.detector.park_after:
        log("Skipping best-effort detector park because detector.park_after=false")
        return

    try:
        detector = settings.detector
        motion = BrukerDetectorMotionController(session)
        park_settings = BrukerDetectorMotionSettings(
            detector_index=detector.detector_index,
            target_position="park",
            timeout_s=detector.timeout_s,
            poll_interval_s=detector.poll_interval_s,
        )
        log("Attempting best-effort Bruker EDS detector park")
        state = motion.move_eds_detector(park_settings)
        log(
            "Best-effort Bruker EDS detector park completed: "
            f"{state.position_name} (code={state.position_code})"
        )
    except Exception as exc:  # pragma: no cover - hardware recovery path
        log(f"ERROR: best-effort Bruker EDS detector park failed: {exc}")


def _log_workflow_result(result: BrukerEDSWorkflowResult, log: TextLogger) -> None:
    log(f"Result: success={result.success}, elapsed={result.elapsed_s:.1f}s")
    if result.bcf_path:
        log(f"BCF path: {result.bcf_path}")
    if result.image_path:
        log(f"Image path: {result.image_path}")
    if result.errors:
        log(f"Workflow reported {len(result.errors)} error(s):")
        for err in result.errors:
            log(f"  ERROR: {err}")


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)

    config_path = args.config.expanduser().resolve(strict=False)
    log_path = (
        args.log_path.expanduser().resolve(strict=False)
        if args.log_path is not None
        else _default_log_path(config_path)
    )
    log = TextLogger(log_path)

    settings: Optional[BrukerEDSWorkflowSettings] = None
    session: Optional[BrukerSession] = None
    exit_code = 1

    log("=== Bruker EDS safe standalone workflow start ===")
    log(f"Config: {config_path}")
    log(f"Log path: {log_path}")
    log("Using standalone Bruker YAML workflow; no AutoScript or TFS Laser API")
    log("Reminder: do not interact with ESPRIT GUI during API acquisition")

    try:
        config_yaml_text = config_path.read_text(encoding="utf-8")
        settings = load_bruker_eds_yaml(config_path)
        settings = _disable_readback_for_safe_cli(settings, log)
        _summarize_settings(settings, log)
        _run_runtime_preflight(settings, log)

        log("Creating Bruker session")
        session = BrukerSession(settings.session)
        info = session.connect()
        log(f"Connected Bruker session CID={info.cid}")

        log("Starting Bruker EDS workflow")
        result = run_bruker_eds_workflow(
            settings=settings,
            log_fn=log,
            session=session,
            config_yaml_text=config_yaml_text,
        )
        _log_workflow_result(result, log)

        detector_ok = _confirm_final_detector_position(session, settings, log)

        if not result.success:
            log("Workflow failure: run_bruker_eds_workflow returned success=False")
        bcf_ok = _validate_bcf_result(result, log) if result.success else False

        if result.success and bcf_ok and detector_ok:
            log("=== Bruker EDS safe standalone workflow SUCCESS ===")
            exit_code = 0
        else:
            log("=== Bruker EDS safe standalone workflow FAILURE ===")
            exit_code = 1

    except Exception as exc:
        log(f"ERROR: Bruker EDS safe workflow failed: {type(exc).__name__}: {exc}")
        log("Traceback follows:")
        for line in traceback.format_exc().rstrip().splitlines():
            log(f"  {line}")
        if session is not None and settings is not None:
            _best_effort_park(session=session, settings=settings, log=log)
            _confirm_final_detector_position(
                session=session, settings=settings, log=log
            )
        log("=== Bruker EDS safe standalone workflow FAILURE ===")
        exit_code = 1

    finally:
        if (
            session is not None
            and settings is not None
            and settings.session.close_on_exit
        ):
            try:
                log("Closing Bruker session (close_on_exit=True)")
                session.close()
            except Exception as exc:
                log(f"ERROR: Bruker session close failed: {exc}")
                exit_code = 1
        log(f"Process exit code: {exit_code}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
