"""Bruker EDS resolution and element-count matrix runner.

This is an explicit, operator-run validation tool for ESPRIT simulator or real
hardware. It does not depend on TFS AutoScript or the TFS Laser API.

Usage:
    python bruker_eds_resolution_matrix.py bruker_eds_resolution_matrix.yml

Safety:
    The YAML key detector.move_detector defaults to false. Set it to true only
    after hardware safety review; if true, this script moves the EDS detector to
    acquire before the matrix and attempts to park it in a finally block.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml

REPO_ROOT = Path(__file__).resolve().parents[5]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from pytribeam.external_oem.bruker.detector_motion import BrukerDetectorMotionController
from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.image_config import BrukerImageConfigController
from pytribeam.external_oem.bruker.readback import BrukerEDSReadbackController
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.spectrometer import BrukerSpectrometerController
from pytribeam.external_oem.bruker.types import (
    BrukerDetectorMotionSettings,
    BrukerEDSElementMapSetting,
    BrukerEDSProfileMapSettings,
    BrukerSessionSettings,
)

BRUKER_HARDWARE_ENV_VAR = "PYTRIBEAM_RUN_BRUKER_HARDWARE"
BRUKER_TEST_ENV_VAR = "PYTRIBEAM_BRUKER_TEST_ENV"


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class TextLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, msg: str):
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        print(line, flush=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _env_flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _require_hardware_motion_opt_in():
    bruker_env = os.environ.get(BRUKER_TEST_ENV_VAR, "").strip().lower()
    if bruker_env != "hardware" or not _env_flag_enabled(BRUKER_HARDWARE_ENV_VAR):
        raise RuntimeError(
            "detector.move_detector=true requires explicit true-hardware opt-in: "
            f"set {BRUKER_TEST_ENV_VAR}=hardware and {BRUKER_HARDWARE_ENV_VAR}=1"
        )


def _session_settings(cfg: Dict[str, Any]) -> BrukerSessionSettings:
    s = cfg["session"]

    return BrukerSessionSettings(
        dll_dir=str(s["dll_dir"]),
        mode=str(s.get("mode", "local")),
        server=str(s.get("server", "Lokaler Server")),
        user=str(s.get("user", "edx")),
        password=str(s.get("password", "edx")),
        host=s.get("host"),
        port=s.get("port"),
        close_on_exit=bool(s.get("close_on_exit", False)),
        keep_connection_open=bool(s.get("keep_connection_open", True)),
    )


def _move_settings(cfg: Dict[str, Any], target: str) -> BrukerDetectorMotionSettings:
    d = cfg.get("detector", {})
    return BrukerDetectorMotionSettings(
        detector_index=int(d.get("detector_index", 1)),
        target_position=target,
        timeout_s=float(d.get("move_timeout_s", 60.0)),
        poll_interval_s=float(d.get("poll_interval_s", 0.5)),
    )


def _elements(cfg: Dict[str, Any], count: int):
    elems = cfg["profile"]["elements"][:count]
    if len(elems) != count:
        raise ValueError(
            f"Requested {count} elements, but only {len(elems)} configured"
        )
    return tuple(
        BrukerEDSElementMapSetting(
            atomic_number=int(e["atomic_number"]),
            line=str(e.get("line", "KA")),
            energy_keV=float(e.get("energy_keV", 0.0)),
            width=float(e.get("width", 1.0)),
        )
        for e in elems
    )


def _profile_settings(
    cfg: Dict[str, Any],
    case_dir: Path,
    width: int,
    height: int,
    element_count: int,
) -> BrukerEDSProfileMapSettings:
    m = cfg["map"]
    name = f"res_{width}x{height}_elements_{element_count}"
    image_format = str(m.get("image_format", "bmp"))
    save_image = bool(m.get("save_image", True))

    return BrukerEDSProfileMapSettings(
        name=name,
        width_px=int(width),
        height_px=int(height),
        pixel_time_us=int(m.get("pixel_time_us", 1024)),
        output_bcf_path=str(case_dir / f"{name}.bcf"),
        output_image_path=str(case_dir / f"{name}.{image_format}")
        if save_image
        else None,
        output_image_format=image_format if save_image else None,
        spu_device=int(m.get("spu_device", 1)),
        elements=_elements(cfg, element_count),
        image_filter=int(m.get("image_filter", 0)),
        map_filter=int(m.get("map_filter", 0)),
        map_filter_width=int(m.get("map_filter_width", 3)),
        color_mix_method=int(m.get("color_mix_method", 0)),
        brightness=float(m.get("brightness", 0.0)),
        gamma=float(m.get("gamma", 1.0)),
        color_saturation=float(m.get("color_saturation", 1.0)),
        absolute_scaling=bool(m.get("absolute_scaling", False)),
        normalization=bool(m.get("normalization", True)),
        deconvolution=bool(m.get("deconvolution", False)),
        roi=None,
    )


def _path_size(path_str):
    if not path_str:
        return None
    path = Path(path_str)
    if not path.exists():
        return None
    return path.stat().st_size


def _safe_spectrometer_status(session, log):
    try:
        spec = BrukerSpectrometerController(session)
        status = spec.get_spectrometer_status(spu=1)
        active = [d._asdict() for d in status.detector_statuses if d.status != -1]
        return {
            "available": True,
            "status": status._asdict(),
            "active_detectors": active,
        }
    except Exception as exc:
        log(f"Spectrometer status unavailable: {exc}")
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def _write_outputs(rows: List[Dict[str, Any]], summary_path: Path, csv_path: Path):
    summary_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    fieldnames = [
        "width_px",
        "height_px",
        "element_count",
        "pixel_count",
        "width_mod_2",
        "height_mod_2",
        "width_mod_4",
        "height_mod_4",
        "width_mod_8",
        "height_mod_8",
        "width_mod_16",
        "height_mod_16",
        "accepted_width_px",
        "accepted_height_px",
        "accepted_pixel_time_us",
        "acquisition_success",
        "readback_success_count",
        "readback_failure_count",
        "bcf_path",
        "bcf_size",
        "bmp_path",
        "bmp_size",
        "acquisition_elapsed_s",
        "readback_delay_s",
        "readback_elapsed_s",
        "error",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def run_matrix(config_path: Path) -> int:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    run_dir = (
        Path(cfg["output"]["root_dir"])
        / f"{cfg['output'].get('run_name', 'eds_resolution_matrix')}_{_stamp()}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    log = TextLogger(run_dir / "resolution_matrix.log")
    summary_path = run_dir / "resolution_matrix_summary.json"
    csv_path = run_dir / "resolution_matrix_summary.csv"

    log("=== Bruker EDS resolution matrix start ===")
    log(f"Config: {config_path}")
    log(f"Run dir: {run_dir}")

    session = BrukerSession(_session_settings(cfg))
    rows: List[Dict[str, Any]] = []

    try:
        info = session.connect()
        log(f"Connected CID={info.cid}")
        log(f"QueryInfo: {info.query_info}")
        session.check_connection()

        motion = BrukerDetectorMotionController(session)
        if bool(cfg.get("detector", {}).get("move_detector", False)):
            _require_hardware_motion_opt_in()
            log("Moving EDS detector to acquire")
            motion.move_eds_detector(_move_settings(cfg, "acquire"))
        else:
            log("detector.move_detector=false; detector motion disabled")

        pre_status = _safe_spectrometer_status(session, log)
        eds = BrukerEDSController(session)
        img = BrukerImageConfigController(session)
        readback = BrukerEDSReadbackController(session)

        resolutions = cfg["matrix"]["resolutions"]
        element_counts = cfg["matrix"]["element_counts"]

        for width, height in resolutions:
            for element_count in element_counts:
                case_dir = run_dir / f"{width}x{height}" / f"elements_{element_count}"
                case_dir.mkdir(parents=True, exist_ok=True)
                settings = _profile_settings(
                    cfg, case_dir, width, height, element_count
                )
                row: Dict[str, Any] = {
                    "width_px": int(width),
                    "height_px": int(height),
                    "element_count": int(element_count),
                    "pixel_count": int(width) * int(height),
                    "width_mod_2": int(width) % 2,
                    "height_mod_2": int(height) % 2,
                    "width_mod_4": int(width) % 4,
                    "height_mod_4": int(height) % 4,
                    "width_mod_8": int(width) % 8,
                    "height_mod_8": int(height) % 8,
                    "width_mod_16": int(width) % 16,
                    "height_mod_16": int(height) % 16,
                    "pre_spectrometer_status": pre_status,
                }

                log(f"--- Case {width}x{height}, elements={element_count} ---")
                t_acq = time.time()
                try:
                    outputs = eds.acquire_map_with_profile(
                        settings,
                        poll_interval_s=float(cfg["map"].get("poll_interval_s", 0.5)),
                        max_wait_s=float(cfg["map"].get("max_wait_s", 1200.0)),
                        log_fn=log,
                    )
                    row["acquisition_success"] = True
                    row["bcf_path"] = outputs.output_bcf_path
                    row["bmp_path"] = outputs.output_image_path
                    row["bcf_size"] = _path_size(outputs.output_bcf_path)
                    row["bmp_size"] = _path_size(outputs.output_image_path)
                except Exception as exc:
                    row["acquisition_success"] = False
                    row["error"] = f"{type(exc).__name__}: {exc}"
                    log(f"Acquisition failed: {row['error']}")
                finally:
                    row["acquisition_elapsed_s"] = round(time.time() - t_acq, 3)

                try:
                    actual = img.get_image_configuration()
                    row["accepted_width_px"] = actual.width_px
                    row["accepted_height_px"] = actual.height_px
                    row["accepted_pixel_time_us"] = actual.average
                except Exception as exc:
                    row["image_configuration_error"] = f"{type(exc).__name__}: {exc}"

                if row.get("acquisition_success") and bool(
                    cfg.get("readback", {}).get("enabled", True)
                ):
                    readback_delay_s = float(
                        cfg.get("readback", {}).get("delay_s", 0.0)
                    )
                    row["readback_delay_s"] = readback_delay_s
                    if readback_delay_s > 0:
                        log(f"Waiting {readback_delay_s:.1f} s before numeric readback")
                        time.sleep(readback_delay_s)

                    t_read = time.time()
                    results = readback.save_element_maps_npy(
                        settings=settings,
                        output_dir=str(case_dir / "readback"),
                        prefix=settings.name,
                        dtype=str(cfg.get("readback", {}).get("dtype", "uint16")),
                        strict=bool(cfg.get("readback", {}).get("strict", False)),
                        save_element_tiff=bool(
                            cfg.get("readback", {}).get("save_element_tiff", False)
                        ),
                        log_fn=log,
                    )

                    row["readback_elapsed_s"] = round(time.time() - t_read, 3)
                    row["readback_results"] = [r._asdict() for r in results]
                    row["readback_success_count"] = len(
                        [r for r in results if r.error is None]
                    )
                    row["readback_failure_count"] = len(
                        [r for r in results if r.error is not None]
                    )
                else:
                    row["readback_success_count"] = 0
                    row["readback_failure_count"] = 0

                rows.append(row)
                _write_outputs(rows, summary_path, csv_path)

        log("=== Bruker EDS resolution matrix complete ===")
        return 0
    finally:
        try:
            if bool(cfg.get("detector", {}).get("move_detector", False)):
                log("Moving EDS detector to park")
                BrukerDetectorMotionController(session).move_eds_detector(
                    _move_settings(cfg, "park")
                )
        except Exception as exc:
            log(f"WARNING: failed to park EDS detector: {exc}")
        if session.settings.close_on_exit:
            session.close()
        _write_outputs(rows, summary_path, csv_path)


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="Path to matrix YAML config")
    args = parser.parse_args()
    raise SystemExit(run_matrix(args.config))


if __name__ == "__main__":
    main()
