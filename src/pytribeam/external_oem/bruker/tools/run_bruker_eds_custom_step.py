"""Run Bruker EDS from a pytribeam CUSTOM step.

This script is a conservative fallback/bridge path for Bruker EDS integration.
It is intended to be launched by pytribeam's existing CUSTOM step machinery
before full native OEM-aware EDS main-loop dispatch is available. It still uses
the standalone Bruker workflow runner and standalone Bruker YAML configuration.

Safety model
------------
* AutoScript is used only for microscope-side operations:
  - connect to the microscope
  - retract AutoScript-controlled insertable detectors (CBS/ABS/etc.)
  - optionally set electron-beam imaging conditions from an existing pytribeam
    IMAGE/EDS/EBSD step definition
* The TFS Laser API is not used.
* Bruker detector motion and EDS acquisition are handled by the standalone
  Bruker module under ``pytribeam.external_oem.bruker``.

Configuration is provided through command-line arguments. The script also
accepts PYTRIBEAM_* environment variables for standalone/manual use, but the
main pytribeam CUSTOM step can now pass all required values with generic
``script_args`` and ``environment`` settings.

Required input
--------------
--bruker-config or PYTRIBEAM_BRUKER_EDS_CONFIG
    Path to the standalone Bruker EDS workflow YAML file.

Optional inputs
---------------
--image-config or PYTRIBEAM_IMAGE_CONFIG
    Path to a main pytribeam YAML file. If provided, this script can use one
    of its IMAGE/EDS/EBSD/CUSTOM steps to set microscope imaging conditions
    before running Bruker acquisition. It also uses this file's general.exp_dir
    to find the transient slice_info.yml file written by pytribeam CUSTOM steps.
--image-step or PYTRIBEAM_IMAGE_STEP
    Step name in the image config to use for imaging-condition setup.
--image-step-number or PYTRIBEAM_IMAGE_STEP_NUMBER
    Step number in the image config to use if --image-step is not provided.
--slice-info-path or PYTRIBEAM_SLICE_INFO_PATH
    Explicit path to pytribeam's transient slice_info.yml file.
--slice-number or PYTRIBEAM_SLICE_NUMBER
    Explicit slice number override. Takes precedence over slice_info.yml.
--microscope-host/--microscope-port or PYTRIBEAM_MICROSCOPE_HOST/PORT
    Microscope connection settings used when --image-config is absent or does
    not provide them.
--preview-image or PYTRIBEAM_BRUKER_PREVIEW_IMAGE
    If set and --image-config is set, capture a normal pytribeam preview image
    before Bruker mapping.


Example CUSTOM step
-------------------
steps:
  bruker_eds_custom:
    step_general:
            step_number: 3
            step_type: custom
            frequency: 1
            stage:
              rotation_side: fsl_mill
              initial_position: {x_mm: 1.0, y_mm: 2.0, z_mm: 5.0, r_deg: -50.0, t_deg: 0.0}

    script_path: C:/path/to/run_bruker_eds_custom_step.py
    executable_path: C:/path/to/python.exe


    script_args:
      - --bruker-config
      - C:/path/to/bruker_eds_workflow.yml
      - --image-config
      - C:/path/to/main_pytribeam.yml
      - --image-step
      - bruker_eds_custom

"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Tuple

import yaml

# If pytribeam is not installed but this script is run in-place from the repo,
# add the src directory to sys.path. This mirrors the existing Bruker tool style.
REPO_ROOT = Path(__file__).resolve().parents[5]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pytribeam.factory as factory
import pytribeam.image as img
import pytribeam.insertable_devices as devices
import pytribeam.types as tbt
import pytribeam.utilities as ut
from pytribeam.external_oem.bruker.config import load_bruker_eds_yaml
from pytribeam.external_oem.bruker.detector_motion import BrukerDetectorMotionController
from pytribeam.external_oem.bruker.runtime import validate_bruker_runtime_environment
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.types import BrukerDetectorMotionSettings
from pytribeam.external_oem.bruker.workflow import run_bruker_eds_workflow

BRUKER_RUNTIME_OPERATOR_HINTS = (
    "Check that session.dll_dir exists on the machine running Python.",
    "Check that Bruker.API.Esprit64.dll exists in session.dll_dir.",
    "If using TCP mode, the Bruker API DLL still must exist locally on the "
    "Python machine.",
    "ESPRIT may be local or remote, but ctypes requires local Bruker API DLLs.",
    "Bruker output paths are interpreted by the ESPRIT/Bruker machine.",
    "Do not interact with the ESPRIT GUI during pytribeam/Bruker API acquisition.",
    "Use bruker_detector_probe.py if the Bruker detector_index is uncertain.",
)


class TextLogger:
    """Timestamped console/file logger for CUSTOM-step execution."""

    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, msg: str):
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        print(line)
        if self.log_path is not None:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y"}


def _env_int(name: str) -> Optional[int]:
    value = os.environ.get(name)
    if value in (None, ""):
        return None
    return int(value)


def _read_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML file did not contain a dictionary: {path}")
    return data


def _run_bruker_runtime_preflight(settings, log: TextLogger) -> dict[str, str]:
    """Validate local Bruker DLL availability before any Bruker session exists."""
    log("Checking local Bruker API DLL runtime preflight")
    try:
        dll_info = validate_bruker_runtime_environment(settings.session)
    except FileNotFoundError as exc:
        log(f"ERROR: Bruker runtime preflight failed: {exc}")
        log("Operator checks before retrying:")
        for hint in BRUKER_RUNTIME_OPERATOR_HINTS:
            log(f"  - {hint}")
        raise RuntimeError(
            "Bruker runtime preflight failed before creating a BrukerSession. "
            "Fix session.dll_dir / local Bruker API DLL availability on the "
            "Python host and retry. Operator checks: "
            + " ".join(BRUKER_RUNTIME_OPERATOR_HINTS)
        ) from exc

    log(f"Bruker runtime preflight passed: {dll_info['esprit_dll']}")
    if "logging_dll" in dll_info:
        log(f"Optional Bruker logging DLL found: {dll_info['logging_dll']}")
    else:
        log("Optional Bruker logging DLL not found; continuing")
    return dll_info


def _load_slice_number(
    image_config_path: Optional[Path],
    log: TextLogger,
    slice_number: Optional[int] = None,
    slice_info_path: Optional[Path] = None,
    exp_dir: Optional[Path] = None,
) -> Optional[int]:
    """Load slice number from args, env, or pytribeam's slice_info.yml."""
    if slice_number is not None:
        log(f"Using slice number from command line: {slice_number}")
        return slice_number

    env_slice = _env_int("PYTRIBEAM_SLICE_NUMBER")
    if env_slice is not None:
        log(f"Using slice number from PYTRIBEAM_SLICE_NUMBER={env_slice}")
        return env_slice

    candidates = []
    if slice_info_path is not None:
        candidates.append(slice_info_path)

    explicit_slice_info = os.environ.get("PYTRIBEAM_SLICE_INFO_PATH")
    if explicit_slice_info:
        candidates.append(Path(explicit_slice_info))

    if exp_dir is not None:
        candidates.append(exp_dir / "slice_info.yml")

    env_exp_dir = os.environ.get("PYTRIBEAM_EXP_DIR")
    if env_exp_dir:
        candidates.append(Path(env_exp_dir) / "slice_info.yml")

    if image_config_path is not None and image_config_path.is_file():
        cfg = _read_yaml(image_config_path)
        config_exp_dir = cfg.get("general", {}).get("exp_dir")
        if config_exp_dir:
            candidates.append(Path(config_exp_dir) / "slice_info.yml")

    for candidate in candidates:
        if candidate.is_file():
            info = _read_yaml(candidate)
            slice_number = info.get("slice_number")
            if slice_number is not None:
                log(f"Using slice number {slice_number} from {candidate}")
                return int(slice_number)

    log("No slice number found; Bruker output will use standalone run naming")
    return None


def _connection_from_image_config(
    image_config_path: Optional[Path],
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> Tuple[Optional[str], Optional[int]]:
    if host is not None or port is not None:
        return host, port

    if image_config_path is not None and image_config_path.is_file():
        cfg = _read_yaml(image_config_path)
        general = cfg.get("general", {})
        host = general.get("connection_host")
        port = general.get("connection_port")
        return host, port

    host = os.environ.get("PYTRIBEAM_MICROSCOPE_HOST")
    port = _env_int("PYTRIBEAM_MICROSCOPE_PORT")
    return host, port


def _find_image_step(
    image_config_path: Path,
    step_name: Optional[str] = None,
    step_number: Optional[int] = None,
) -> Tuple[float, str, dict[str, Any]]:
    yml_version = ut.yml_version(image_config_path)
    yml_format = ut.yml_format(version=yml_version)
    cfg = ut.yml_to_dict(
        yml_path_file=image_config_path,
        version=yml_version,
        required_keys=("general", "config_file_version"),
    )

    if step_name is None:
        step_name = os.environ.get("PYTRIBEAM_IMAGE_STEP")
    if step_name:
        steps = cfg.get(yml_format.step_section_key, {})
        if step_name not in steps:
            raise KeyError(f"Step '{step_name}' not found in {image_config_path}")
        return yml_version, step_name, steps[step_name]

    if step_number is None:
        step_number = _env_int("PYTRIBEAM_IMAGE_STEP_NUMBER")
    if step_number is None:
        raise ValueError(
            "PYTRIBEAM_IMAGE_CONFIG was provided, but neither "
            "PYTRIBEAM_IMAGE_STEP nor PYTRIBEAM_IMAGE_STEP_NUMBER was set."
        )

    found_name, step_settings = ut.step_settings(
        exp_settings=cfg,
        step_number_key=yml_format.step_number_key,
        step_number_val=step_number,
        yml_format=yml_format,
    )
    return yml_version, found_name, step_settings


def _prepare_imaging_from_pytribeam_step(
    microscope: tbt.Microscope,
    image_config_path: Path,
    log: TextLogger,
    step_name: Optional[str] = None,
    step_number: Optional[int] = None,
    set_autoscript_detector: bool = False,
    allow_insertable_autoscript_detector: bool = False,
    preview_image: bool = False,
    preview_image_dir: Optional[Path] = None,
):
    """Set AutoScript imaging conditions from a generic pytribeam step.

    By default this intentionally sets only beam and scan conditions. It does
    not insert any AutoScript-controlled detector, because this script is about
    to move the Bruker EDS detector independently. Stationary detector setup can
    be enabled for preview imaging with PYTRIBEAM_BRUKER_SET_AUTOSCRIPT_DETECTOR.
    """
    yml_version, step_name, step_settings = _find_image_step(
        image_config_path,
        step_name=step_name,
        step_number=step_number,
    )
    yml_format = ut.yml_format(version=yml_version)

    log(f"Preparing AutoScript imaging from step '{step_name}' in {image_config_path}")
    image_settings = factory.image(
        microscope=microscope,
        step_settings=step_settings,
        step_name=step_name,
        yml_format=yml_format,
    )
    img.set_view(microscope=microscope, quad=image_settings.beam.default_view)
    img.imaging_device(microscope=microscope, beam=image_settings.beam)
    img.imaging_scan(img_settings=image_settings)

    set_autoscript_detector = set_autoscript_detector or _env_bool(
        "PYTRIBEAM_BRUKER_SET_AUTOSCRIPT_DETECTOR",
        default=False,
    )
    if set_autoscript_detector:
        detector_state = devices.detector_state(
            microscope=microscope,
            detector=image_settings.detector.type,
        )
        if detector_state is not tbt.RetractableDeviceState.STATIONARY:
            allow_insertable_autoscript_detector = (
                allow_insertable_autoscript_detector
                or _env_bool(
                    "PYTRIBEAM_BRUKER_ALLOW_INSERTABLE_AUTOSCRIPT_DETECTOR",
                    default=False,
                )
            )
            if not allow_insertable_autoscript_detector:
                raise RuntimeError(
                    f"Refusing to insert AutoScript-controlled detector "
                    f"'{image_settings.detector.type.value}' before Bruker EDS. "
                    "Use a stationary detector for preview/setup or set "
                    "PYTRIBEAM_BRUKER_ALLOW_INSERTABLE_AUTOSCRIPT_DETECTOR=true "
                    "only after a site-specific collision review."
                )
        img.imaging_detector(img_settings=image_settings)

    preview_image = preview_image or _env_bool(
        "PYTRIBEAM_BRUKER_PREVIEW_IMAGE",
        default=False,
    )
    if preview_image:
        if not set_autoscript_detector:
            raise RuntimeError(
                "Preview imaging requires --set-autoscript-detector so detector "
                "setup is explicit before any AutoScript image acquisition."
            )
        preview_dir = preview_image_dir or Path(
            os.environ.get("PYTRIBEAM_PREVIEW_IMAGE_DIR", ".")
        )
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path = (
            preview_dir / f"bruker_custom_preview_{datetime.now():%Y%m%d_%H%M%S}.tif"
        )
        img.collect_single_image(save_path=preview_path, img_settings=image_settings)
        log(f"Saved AutoScript preview image: {preview_path}")


def _park_bruker_detector(session: BrukerSession, settings, log: TextLogger):
    """Best-effort Bruker detector park used on failure."""
    try:
        detector_cfg = settings.detector
        motion = BrukerDetectorMotionController(session)
        park_settings = BrukerDetectorMotionSettings(
            detector_index=detector_cfg.detector_index,
            target_position="park",
            timeout_s=detector_cfg.timeout_s,
            poll_interval_s=detector_cfg.poll_interval_s,
        )
        log("Attempting best-effort Bruker EDS detector park")
        motion.move_eds_detector(park_settings)
        log("Best-effort Bruker EDS detector park completed")
    except Exception as exc:  # pragma: no cover - hardware recovery path
        log(f"WARNING: best-effort Bruker EDS detector park failed: {exc}")


def _retract_autoscript_controlled_detectors(
    microscope: tbt.Microscope,
    log: TextLogger,
) -> bool:
    """Retract only microscope/AutoScript-controlled insertable detectors.

    This deliberately does not call devices.retract_all_devices(), retract_EDS(),
    or retract_EBSD(), because those legacy external-detector paths can require
    the TFS Laser API.
    """
    log("Retracting AutoScript-controlled insertable detectors")
    initial_view = tbt.ViewQuad(microscope.imaging.get_active_view())
    devices.device_access(microscope=microscope)

    for detector_value in microscope.detector.type.available_values:
        detector = tbt.DetectorType(detector_value)
        state = devices.detector_state(microscope=microscope, detector=detector)
        if state not in (
            tbt.RetractableDeviceState.STATIONARY,
            tbt.RetractableDeviceState.RETRACTED,
        ):
            log(
                f"Retracting AutoScript detector {detector.value} from state {state.value}"
            )
            devices.retract_device(microscope=microscope, detector=detector)

    img.set_view(microscope=microscope, quad=initial_view)
    log("AutoScript-controlled insertable detectors retracted")
    return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Bruker EDS from a pytribeam CUSTOM step using the standalone "
            "Bruker workflow YAML as a fallback/bridge before native main-loop "
            "integration. Values may also be supplied by PYTRIBEAM_* "
            "environment variables."
        ),
        epilog=(
            "Runtime notes: session.dll_dir and Bruker.API.Esprit64.dll must "
            "exist on the Python host even in TCP mode; Bruker output paths are "
            "interpreted by the ESPRIT/Bruker machine; do not interact with the "
            "ESPRIT GUI during acquisition; use bruker_detector_probe.py if the "
            "detector index is uncertain."
        ),
    )
    parser.add_argument(
        "--bruker-config",
        default=os.environ.get("PYTRIBEAM_BRUKER_EDS_CONFIG"),
        help="Path to standalone Bruker EDS workflow YAML.",
    )
    parser.add_argument(
        "--image-config",
        default=os.environ.get("PYTRIBEAM_IMAGE_CONFIG"),
        help="Optional main pytribeam YAML used to set beam/scan conditions.",
    )
    parser.add_argument(
        "--image-step",
        default=os.environ.get("PYTRIBEAM_IMAGE_STEP"),
        help="Optional step name in --image-config used for beam/scan setup.",
    )
    parser.add_argument(
        "--image-step-number",
        type=int,
        default=_env_int("PYTRIBEAM_IMAGE_STEP_NUMBER"),
        help="Optional step number in --image-config used for beam/scan setup.",
    )
    parser.add_argument(
        "--slice-number",
        type=int,
        default=_env_int("PYTRIBEAM_SLICE_NUMBER"),
        help="Optional explicit slice number for Bruker output naming.",
    )
    parser.add_argument(
        "--slice-info-path",
        default=os.environ.get("PYTRIBEAM_SLICE_INFO_PATH"),
        help="Optional explicit path to pytribeam slice_info.yml.",
    )
    parser.add_argument(
        "--exp-dir",
        default=os.environ.get("PYTRIBEAM_EXP_DIR"),
        help="Optional pytribeam experiment directory containing slice_info.yml.",
    )
    parser.add_argument(
        "--microscope-host",
        default=os.environ.get("PYTRIBEAM_MICROSCOPE_HOST"),
        help="Optional AutoScript microscope host override.",
    )
    parser.add_argument(
        "--microscope-port",
        type=int,
        default=_env_int("PYTRIBEAM_MICROSCOPE_PORT"),
        help="Optional AutoScript microscope port override.",
    )
    parser.add_argument(
        "--preview-image",
        action="store_true",
        help="Capture an AutoScript preview image before Bruker mapping.",
    )
    parser.add_argument(
        "--preview-image-dir",
        default=os.environ.get("PYTRIBEAM_PREVIEW_IMAGE_DIR"),
        help="Directory for optional preview image output.",
    )
    parser.add_argument(
        "--set-autoscript-detector",
        action="store_true",
        help="Also configure the AutoScript detector from the image step.",
    )
    parser.add_argument(
        "--allow-insertable-autoscript-detector",
        action="store_true",
        help="Allow inserting an AutoScript detector during setup after site safety review.",
    )
    parser.add_argument(
        "--log-path",
        default=os.environ.get("PYTRIBEAM_BRUKER_CUSTOM_LOG"),
        help="Optional explicit log file path.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if not args.bruker_config:
        raise ValueError(
            "PYTRIBEAM_BRUKER_EDS_CONFIG or --bruker-config must point to a "
            "Bruker EDS workflow YAML file."
        )

    bruker_config_path = Path(args.bruker_config)
    image_config_path = Path(args.image_config) if args.image_config else None

    config_yaml_text = bruker_config_path.read_text(encoding="utf-8")
    settings = load_bruker_eds_yaml(bruker_config_path)

    # Logger path defaults beside Bruker output root so logs are valid on the
    # Bruker/ESPRIT machine, consistent with the Bruker workflow output paths.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.log_path:
        log_path = Path(args.log_path)
    else:
        log_path = (
            Path(settings.output.output_dir)
            / f"{settings.output.run_name}_custom_{stamp}"
            / f"{settings.output.run_name}_custom_{stamp}.log"
        )
    log = TextLogger(log_path)

    log("=== Bruker EDS CUSTOM-step fallback start ===")
    log(f"Bruker config: {bruker_config_path}")
    log("Using standalone Bruker workflow runner and Bruker YAML config")
    log("Reminder: Bruker output paths are interpreted by the ESPRIT/Bruker machine")
    log("Reminder: do not interact with ESPRIT GUI during API acquisition")

    _run_bruker_runtime_preflight(settings=settings, log=log)

    slice_number = _load_slice_number(
        image_config_path=image_config_path,
        log=log,
        slice_number=args.slice_number,
        slice_info_path=Path(args.slice_info_path) if args.slice_info_path else None,
        exp_dir=Path(args.exp_dir) if args.exp_dir else None,
    )

    if slice_number is not None:
        settings = settings._replace(
            output=settings.output._replace(slice_number=slice_number)
        )

    microscope = tbt.Microscope()
    bruker_session = None

    try:
        host, port = _connection_from_image_config(
            image_config_path,
            host=args.microscope_host,
            port=args.microscope_port,
        )

        log(f"Connecting to microscope host={host!r}, port={port!r}")
        ut.connect_microscope(
            microscope=microscope,
            quiet_output=True,
            connection_host=host,
            connection_port=port,
        )

        _retract_autoscript_controlled_detectors(microscope=microscope, log=log)

        if image_config_path is not None:
            _prepare_imaging_from_pytribeam_step(
                microscope=microscope,
                image_config_path=image_config_path,
                log=log,
                step_name=args.image_step,
                step_number=args.image_step_number,
                set_autoscript_detector=args.set_autoscript_detector,
                allow_insertable_autoscript_detector=args.allow_insertable_autoscript_detector,
                preview_image=args.preview_image,
                preview_image_dir=Path(args.preview_image_dir)
                if args.preview_image_dir
                else None,
            )

            # Re-assert the safety baseline after imaging-condition setup.
            _retract_autoscript_controlled_detectors(microscope=microscope, log=log)
        else:
            log(
                "No PYTRIBEAM_IMAGE_CONFIG/--image-config provided; "
                "skipping AutoScript imaging setup"
            )

        log("Creating Bruker session")
        bruker_session = BrukerSession(settings.session)
        info = bruker_session.connect()
        log(f"Connected Bruker session CID={info.cid}")

        result = run_bruker_eds_workflow(
            settings=settings,
            log_fn=log,
            session=bruker_session,
            config_yaml_text=config_yaml_text,
        )

        log(f"Result: success={result.success}, elapsed={result.elapsed_s:.1f}s")
        if result.errors:
            for err in result.errors:
                log(f"  ERROR: {err}")
            raise RuntimeError(
                f"Bruker EDS workflow completed with errors: {result.errors}"
            )

        log("=== Bruker EDS CUSTOM-step fallback complete ===")
        return 0

    except Exception:
        if bruker_session is not None:
            _park_bruker_detector(session=bruker_session, settings=settings, log=log)
        raise
    finally:
        if bruker_session is not None and settings.session.close_on_exit:
            log("Closing Bruker session (close_on_exit=True)")
            bruker_session.close()
        if microscope.server_host is not None:
            log("Disconnecting microscope")
            ut.disconnect_microscope(microscope=microscope, quiet_output=True)


if __name__ == "__main__":
    raise SystemExit(main())
