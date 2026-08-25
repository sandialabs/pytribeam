"""Prepare a pytribeam main YAML for the Bruker EDS CUSTOM-step fallback.

This helper updates a GUI-created pytribeam workflow YAML so its selected
``custom`` step launches ``run_bruker_eds_custom_step.py`` with the correct
Bruker config path, main-config path, step name/number, and optional log path.

It is intentionally a YAML preparation helper only. It does not connect to
AutoScript, ESPRIT, Bruker DLLs, or hardware.

Example:
    python prepare_bruker_eds_custom_step.py \
        --main-config config.yml \
        --bruker-config bruker_eds_workflow.yml \
        --custom-step custom_1 \
        --python-exe "C:/Program Files/Enthought/Python/envs/AutoScript/python.exe" \
        --copy-imaging-from image_1 \
        --output-main-config config_bruker_custom.yml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

# If pytribeam is not installed but this script is run in-place from the repo,
# add the src directory to sys.path. This mirrors the existing Bruker tool style.
REPO_ROOT = Path(__file__).resolve().parents[5]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

BRUKER_CUSTOM_RUNNER = Path(__file__).with_name("run_bruker_eds_custom_step.py")
IMAGING_KEYS = ("beam", "detector", "scan", "bit_depth")


def _read_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML file did not contain a mapping: {path}")
    return data


def _write_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def _yaml_path(path: Path) -> str:
    """Return an absolute path string that is friendly in YAML on Windows."""
    return str(path.expanduser().resolve(strict=False)).replace("\\", "/")


def _find_step(
    cfg: Dict[str, Any],
    step_name: Optional[str] = None,
    step_number: Optional[int] = None,
) -> Tuple[str, Dict[str, Any]]:
    steps = cfg.get("steps")
    if not isinstance(steps, dict):
        raise ValueError("Main pytribeam YAML must contain a 'steps' mapping")

    if step_name:
        if step_name not in steps:
            raise KeyError(
                f"Step '{step_name}' was not found. Available steps: {list(steps)}"
            )
        step = steps[step_name]
        if not isinstance(step, dict):
            raise ValueError(f"Step '{step_name}' must be a mapping")
        return step_name, step

    if step_number is None:
        raise ValueError("Provide either --custom-step or --custom-step-number")

    matches = []
    for name, step in steps.items():
        if not isinstance(step, dict):
            continue
        actual_number = step.get("step_general", {}).get("step_number")
        if actual_number == step_number:
            matches.append((name, step))

    if not matches:
        raise KeyError(f"No step with step_general.step_number={step_number} found")
    if len(matches) > 1:
        names = [name for name, _ in matches]
        raise ValueError(f"Multiple steps have step_number={step_number}: {names}")
    return matches[0]


def _step_number(step_name: str, step: Dict[str, Any]) -> int:
    try:
        return int(step["step_general"]["step_number"])
    except KeyError as exc:
        raise KeyError(
            f"Custom step '{step_name}' is missing step_general.step_number"
        ) from exc


def _ensure_custom_step(step_name: str, step: Dict[str, Any]) -> None:
    step_type = step.get("step_general", {}).get("step_type")
    if step_type != "custom":
        raise ValueError(
            f"Selected step '{step_name}' has step_type={step_type!r}; expected 'custom'"
        )


def _copy_imaging_settings(
    cfg: Dict[str, Any],
    custom_step: Dict[str, Any],
    source_step_name: Optional[str],
) -> None:
    if source_step_name is None:
        return

    source_name, source_step = _find_step(cfg, step_name=source_step_name)
    for key in IMAGING_KEYS:
        if key not in source_step:
            raise KeyError(
                f"Source step '{source_name}' is missing '{key}', so imaging "
                "settings cannot be copied"
            )
        custom_step[key] = source_step[key]


def prepare_config(
    main_config: Path,
    bruker_config: Path,
    output_main_config: Path,
    custom_step_name: Optional[str],
    custom_step_number: Optional[int],
    python_exe: Path,
    script_path: Path,
    copy_imaging_from: Optional[str],
    log_path: Optional[Path],
    preserve_oems: bool,
) -> Tuple[str, int]:
    cfg = _read_yaml(main_config)
    resolved_step_name, custom_step = _find_step(
        cfg, step_name=custom_step_name, step_number=custom_step_number
    )
    _ensure_custom_step(resolved_step_name, custom_step)
    resolved_step_number = _step_number(resolved_step_name, custom_step)

    if not preserve_oems:
        general = cfg.setdefault("general", {})
        general["EBSD_OEM"] = None
        general["EDS_OEM"] = None

    _copy_imaging_settings(cfg, custom_step, copy_imaging_from)

    custom_step["executable_path"] = _yaml_path(python_exe)
    custom_step["script_path"] = _yaml_path(script_path)

    script_args = [
        "--bruker-config",
        _yaml_path(bruker_config),
        "--image-config",
        _yaml_path(output_main_config),
        "--image-step",
        resolved_step_name,
        "--image-step-number",
        str(resolved_step_number),
    ]
    if log_path is not None:
        script_args.extend(["--log-path", _yaml_path(log_path)])
    custom_step["script_args"] = script_args

    missing_imaging = [key for key in IMAGING_KEYS if key not in custom_step]
    if missing_imaging:
        print(
            "WARNING: custom step is missing image-setup keys "
            f"{missing_imaging}. The custom runner may fail during beam/scan "
            "setup unless you omit --image-config for a Bruker-only smoke test."
        )

    _write_yaml(output_main_config, cfg)
    return resolved_step_name, resolved_step_number


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--main-config",
        type=Path,
        required=True,
        help="GUI-created main pytribeam YAML to update or use as input.",
    )
    parser.add_argument(
        "--bruker-config",
        type=Path,
        required=True,
        help="Standalone Bruker EDS workflow YAML.",
    )
    parser.add_argument(
        "--output-main-config",
        type=Path,
        help=(
            "Output main YAML. Defaults to '<main stem>_bruker_custom.yml' next "
            "to --main-config unless --in-place is used."
        ),
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Modify --main-config in place. Otherwise write a new YAML file.",
    )
    parser.add_argument(
        "--custom-step",
        help="Name of the custom step to prepare, e.g. custom_1.",
    )
    parser.add_argument(
        "--custom-step-number",
        type=int,
        help="Step number of the custom step if --custom-step is not supplied.",
    )
    parser.add_argument(
        "--python-exe",
        type=Path,
        required=True,
        help="Python executable used by the pytribeam CUSTOM subprocess.",
    )
    parser.add_argument(
        "--script-path",
        type=Path,
        default=BRUKER_CUSTOM_RUNNER,
        help=f"Path to run_bruker_eds_custom_step.py. Default: {BRUKER_CUSTOM_RUNNER}",
    )
    parser.add_argument(
        "--copy-imaging-from",
        help=(
            "Optional image/EDS/EBSD step name whose beam/detector/scan/bit_depth "
            "blocks should be copied into the custom step."
        ),
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        help="Optional explicit custom-runner log path to add to script_args.",
    )
    parser.add_argument(
        "--preserve-oems",
        action="store_true",
        help=(
            "Do not force general.EBSD_OEM/general.EDS_OEM to null. For the "
            "Bruker CUSTOM fallback, leaving this off is usually safest."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.in_place and args.output_main_config is not None:
        raise ValueError("Use either --in-place or --output-main-config, not both")

    if args.in_place:
        output_main_config = args.main_config
    elif args.output_main_config is not None:
        output_main_config = args.output_main_config
    else:
        output_main_config = args.main_config.with_name(
            f"{args.main_config.stem}_bruker_custom{args.main_config.suffix}"
        )

    step_name, step_number = prepare_config(
        main_config=args.main_config,
        bruker_config=args.bruker_config,
        output_main_config=output_main_config,
        custom_step_name=args.custom_step,
        custom_step_number=args.custom_step_number,
        python_exe=args.python_exe,
        script_path=args.script_path,
        copy_imaging_from=args.copy_imaging_from,
        log_path=args.log_path,
        preserve_oems=args.preserve_oems,
    )

    print("Prepared Bruker CUSTOM-step workflow YAML")
    print(f"  Output main config: {_yaml_path(output_main_config)}")
    print(f"  Custom step: {step_name} (step_number={step_number})")
    print(f"  Bruker config: {_yaml_path(args.bruker_config)}")
    print(f"  Runner script: {_yaml_path(args.script_path)}")
    print(f"  Python executable: {_yaml_path(args.python_exe)}")
    if args.log_path is not None:
        print(f"  Custom log: {_yaml_path(args.log_path)}")
    print("Next: run pytribeam with the output main config.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
