"""Bruker EDS Workflow Sandbox

Demonstrates the full workflow runner using YAML config.
Tests: config parsing, schema validation, session, detector motion,
profile map acquisition, readback, and structured result output.

Usage:
    python bruker_eds_workflow_sandbox.py
    python bruker_eds_workflow_sandbox.py path/to/custom_config.yml
"""

import sys
import traceback
from datetime import datetime
from pathlib import Path

# If package is not installed, uncomment/adjust this block.
REPO_ROOT = Path(__file__).resolve().parents[5]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from pytribeam.external_oem.bruker.config import load_bruker_eds_yaml
from pytribeam.external_oem.bruker.workflow import run_bruker_eds_workflow

# Default config path
DEFAULT_CONFIG = Path(__file__).parent.parent / "tools" / "bruker_eds_workflow_test.yml"


def log(msg: str):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)


def main():
    # Accept optional config path from command line
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    else:
        config_path = DEFAULT_CONFIG

    log("=== Bruker EDS Workflow Sandbox ===")
    log(f"Config: {config_path}")

    if not config_path.exists():
        log(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)

    # --- Step 1: Parse and validate config ---
    log("Parsing and validating YAML config...")
    try:
        settings = load_bruker_eds_yaml(config_path)
        log("Config validation passed")
        log(f"  Session mode: {settings.session.mode}")
        log(f"  DLL dir: {settings.session.dll_dir}")
        log(f"  Output dir: {settings.output.output_dir}")
        log(f"  Map name: {settings.map.name}")
        log(f"  Map dimensions: {settings.map.width_px}x{settings.map.height_px}")
        log(f"  Pixel time: {settings.map.pixel_time_us} us")
        if hasattr(settings.map, "elements"):
            log(f"  Elements: {len(settings.map.elements)}")
            for i, elem in enumerate(settings.map.elements):
                log(f"    [{i}] Z={elem.atomic_number}, line={elem.line}")
        if settings.map.roi is not None:
            log(
                f"  ROI: x={settings.map.roi.x_start_px}, "
                f"y={settings.map.roi.y_start_px}, "
                f"w={settings.map.roi.width_px}, h={settings.map.roi.height_px}"
            )
        else:
            log("  ROI: None (full-frame)")
        log(f"  Readback enabled: {settings.readback.enabled}")
    except Exception as exc:
        log(f"ERROR: Config validation failed: {exc}")
        traceback.print_exc()
        sys.exit(1)

    # --- Step 2: Run workflow ---
    log("")
    log("Running Bruker EDS workflow...")
    config_yaml_text = config_path.read_text(encoding="utf-8")

    try:
        result = run_bruker_eds_workflow(
            settings=settings,
            log_fn=log,
            config_yaml_text=config_yaml_text,
        )
    except Exception as exc:
        log(f"ERROR: Workflow failed with exception: {exc}")
        traceback.print_exc()
        sys.exit(1)

    # --- Step 3: Report results ---
    log("")
    log("=== Workflow Result ===")
    log(f"  Success: {result.success}")
    log(f"  Elapsed: {result.elapsed_s:.1f}s")
    log(f"  BCF path: {result.bcf_path}")
    log(f"  Image path: {result.image_path}")

    if result.element_readback_results:
        successful = [r for r in result.element_readback_results if r.error is None]
        failed = [r for r in result.element_readback_results if r.error is not None]
        log(f"  Readback: {len(successful)} succeeded, {len(failed)} failed")
        for r in successful:
            log(
                f"    [{r.element_index}] Z={r.atomic_number} {r.line}: "
                f"shape={r.shape}, min={r.min_val}, max={r.max_val}, "
                f"nonzero={r.nonzero}"
            )
        for r in failed:
            log(
                f"    [{r.element_index}] Z={r.atomic_number} {r.line}: ERROR={r.error}"
            )

    if result.errors:
        log(f"  Errors ({len(result.errors)}):")
        for err in result.errors:
            log(f"    - {err}")

    log("")
    log("=== Bruker EDS Workflow Sandbox Complete ===")


if __name__ == "__main__":
    main()
