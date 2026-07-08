import argparse
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import sys

import yaml

# If package is not installed, uncomment/adjust this block.
REPO_ROOT = Path(__file__).resolve().parents[5]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.types import (
    BrukerDetectorMotionSettings,
    BrukerEDSElementMapSetting,
    BrukerEDSMapSettings,
    BrukerEDSProfileMapSettings,
    BrukerSessionSettings,
)
from pytribeam.external_oem.bruker.detector_motion import BrukerDetectorMotionController
from pytribeam.external_oem.bruker.eds import BrukerEDSController


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class TextLogger:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, msg: str):
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        print(line)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_optional_rgb(element_cfg: Dict[str, Any]) -> Optional[Tuple[int, int, int]]:
    """
    Accept either display_rgb or rgb if present.
    Colors are display hints only.
    """
    rgb = element_cfg.get("display_rgb", element_cfg.get("rgb", None))
    if rgb is None:
        return None

    if len(rgb) != 3:
        raise ValueError(f"RGB/display_rgb must have length 3, got {rgb}")

    return (int(rgb[0]), int(rgb[1]), int(rgb[2]))


def parse_session_settings(cfg: Dict[str, Any]) -> BrukerSessionSettings:
    s = cfg["session"]

    return BrukerSessionSettings(
        dll_dir=str(s["dll_dir"]),
        mode=str(s.get("mode", "local")),
        server=str(s.get("server", "Lokaler Server")),
        user=str(s.get("user", "edx")),
        password=str(s.get("password", "edx")),
        host=s.get("host", None),
        port=s.get("port", None),
        close_on_exit=bool(s.get("close_on_exit", False)),
        keep_connection_open=bool(s.get("keep_connection_open", True)),
    )


def make_output_paths(cfg: Dict[str, Any]) -> Dict[str, Path]:
    output_cfg = cfg["output"]

    root_dir = Path(output_cfg["root_dir"])
    run_name = str(output_cfg.get("run_name", "bruker_eds_validation"))
    stamp = _now_stamp()

    run_dir = root_dir / f"{run_name}_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    return {
        "run_dir": run_dir,
        "log_path": run_dir / f"{run_name}_{stamp}.log",
        "config_copy_path": run_dir / f"{run_name}_{stamp}_config.yml",
        "bcf_path": run_dir / f"{run_name}_{stamp}.bcf",
        "bmp_path": run_dir / f"{run_name}_{stamp}.bmp",
        "readback_dir": run_dir / "readback",
        "summary_json_path": run_dir / f"{run_name}_{stamp}_summary.json",
    }


def parse_detector_motion_settings(
    cfg: Dict[str, Any],
    target_position: str,
) -> BrukerDetectorMotionSettings:
    d = cfg["detector"]

    return BrukerDetectorMotionSettings(
        detector_index=int(d.get("detector_index", 1)),
        target_position=target_position,
        timeout_s=float(d.get("move_timeout_s", 60.0)),
        poll_interval_s=float(d.get("poll_interval_s", 0.5)),
    )


def parse_simple_map_settings(
    cfg: Dict[str, Any],
    bcf_path: Path,
    bmp_path: Path,
) -> BrukerEDSMapSettings:
    m = cfg["map"]

    save_image = bool(m.get("save_image", True))
    image_format = str(m.get("image_format", "bmp"))

    return BrukerEDSMapSettings(
        name=str(m.get("name", "eds_simple_map")),
        width_px=int(m["width_px"]),
        height_px=int(m["height_px"]),
        pixel_time_us=int(m["pixel_time_us"]),
        real_time_s=int(m.get("real_time_s", 0)),
        output_bcf_path=str(bcf_path),
        output_image_path=str(bmp_path) if save_image else None,
        output_image_format=image_format if save_image else None,
        spu_device=int(m.get("spu_device", 1)),
    )


def parse_profile_map_settings(
    cfg: Dict[str, Any],
    bcf_path: Path,
    bmp_path: Path,
) -> BrukerEDSProfileMapSettings:
    m = cfg["map"]
    profile = m.get("profile", {})

    save_image = bool(m.get("save_image", True))
    image_format = str(m.get("image_format", "bmp"))

    elements = []
    for e in profile.get("elements", []):
        elements.append(
            BrukerEDSElementMapSetting(
                atomic_number=int(e["atomic_number"]),
                line=str(e.get("line", "KA")),
                energy_keV=float(e.get("energy_keV", 0.0)),
                width=float(e.get("width", 1.0)),
                display_rgb=get_optional_rgb(e),
            )
        )

    if not elements:
        raise ValueError("Profile map requires at least one element")

    return BrukerEDSProfileMapSettings(
        name=str(m.get("name", "eds_profile_map")),
        width_px=int(m["width_px"]),
        height_px=int(m["height_px"]),
        pixel_time_us=int(m["pixel_time_us"]),
        output_bcf_path=str(bcf_path),
        output_image_path=str(bmp_path) if save_image else None,
        output_image_format=image_format if save_image else None,
        spu_device=int(m.get("spu_device", 1)),
        elements=tuple(elements),
        image_filter=int(profile.get("image_filter", 0)),
        map_filter=int(profile.get("map_filter", 0)),
        map_filter_width=int(profile.get("map_filter_width", 3)),
        color_mix_method=int(profile.get("color_mix_method", 0)),
        brightness=float(profile.get("brightness", 0.0)),
        gamma=float(profile.get("gamma", 1.0)),
        color_saturation=float(profile.get("color_saturation", 1.0)),
        absolute_scaling=bool(profile.get("absolute_scaling", False)),
        normalization=bool(profile.get("normalization", True)),
        deconvolution=bool(profile.get("deconvolution", False)),
    )


def summarize_element_arrays(settings, arrays) -> list:
    summary = []

    for idx, (element, arr) in enumerate(zip(settings.elements, arrays)):
        summary.append(
            {
                "element_index": idx,
                "atomic_number": int(element.atomic_number),
                "line": element.line,
                "energy_keV": float(element.energy_keV),
                "width": float(element.width),
                "shape": list(arr.shape),
                "dtype": str(arr.dtype),
                "min": int(arr.min()),
                "max": int(arr.max()),
                "sum": int(arr.sum()),
                "nonzero": int((arr != 0).sum()),
            }
        )

    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="Path to Bruker EDS validation YAML file")
    args = parser.parse_args()

    config_path = Path(args.config)
    cfg = load_yaml(config_path)
    paths = make_output_paths(cfg)
    log = TextLogger(paths["log_path"])

    # Copy config into run folder for provenance.
    paths["config_copy_path"].write_text(
        config_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    log("=== Bruker EDS YAML hardware validation start ===")
    log(f"Config: {config_path}")
    log(f"Run dir: {paths['run_dir']}")
    log(f"Log path: {paths['log_path']}")
    log(f"BCF path: {paths['bcf_path']}")
    log(f"BMP path: {paths['bmp_path']}")

    session_settings = parse_session_settings(cfg)
    session = None

    summary: Dict[str, Any] = {
        "config": str(config_path),
        "run_dir": str(paths["run_dir"]),
        "bcf_path": str(paths["bcf_path"]),
        "bmp_path": str(paths["bmp_path"]),
        "element_maps": [],
        "errors": [],
    }

    try:
        log("Creating BrukerSession")
        session = BrukerSession(session_settings)

        log("Connecting to Esprit")
        info = session.connect()
        log(f"Connected with CID={info.cid}")
        log("QueryInfo:")
        for line in info.query_info.splitlines():
            log(f"  {line}")
        summary["query_info"] = info.query_info

        log("Checking connection")
        session.check_connection()
        log("CheckConnection passed")

        motion = BrukerDetectorMotionController(session)
        eds = BrukerEDSController(session)

        detector_cfg = cfg.get("detector", {})
        detector_index = int(detector_cfg.get("detector_index", 1))

        log("Querying initial EDS detector position")
        initial_state = motion.get_eds_detector_position(detector_index)
        log(f"Initial EDS detector position: {initial_state}")
        summary["initial_detector_position"] = initial_state._asdict()

        if bool(detector_cfg.get("verify_park_before", False)):
            if initial_state.position_name != "park":
                log(
                    "WARNING: Detector was not in park at start. "
                    f"Initial state={initial_state}"
                )

        if bool(detector_cfg.get("move_to_acquire_before", True)):
            log("Moving EDS detector to acquire")
            acquire_settings = parse_detector_motion_settings(
                cfg, target_position="acquire"
            )
            acquire_state = motion.move_eds_detector(acquire_settings)
            log(f"EDS detector after acquire move: {acquire_state}")
            summary["acquire_detector_position"] = acquire_state._asdict()

        map_mode = str(cfg["map"].get("mode", "profile")).lower().strip()
        log(f"Map mode: {map_mode}")

        if map_mode == "profile":
            map_settings = parse_profile_map_settings(
                cfg,
                bcf_path=paths["bcf_path"],
                bmp_path=paths["bmp_path"],
            )
            log(f"Profile map settings: {map_settings}")

            log("Creating profile XML preview")
            profile_xml = eds.create_hymap_profile(map_settings)
            profile_path = paths["run_dir"] / f"{map_settings.name}_profile.xml"
            profile_path.write_text(profile_xml, encoding="cp1252", errors="replace")
            log(f"Profile XML written: {profile_path}")
            log(f"Profile XML length: {len(profile_xml)}")
            log(f"Profile XML preview: {profile_xml[:500]}")

            log("Acquiring profile EDS map")
            outputs = eds.acquire_map_with_profile(
                settings=map_settings,
                poll_interval_s=float(cfg["map"].get("poll_interval_s", 0.5)),
                max_wait_s=float(cfg["map"].get("max_wait_s", 600.0)),
            )
            log(f"Profile map outputs: {outputs}")

            readback_cfg = cfg.get("readback", {})
            if bool(readback_cfg.get("save_element_npy", True)):
                log("Saving numeric element maps as .npy")
                paths["readback_dir"].mkdir(parents=True, exist_ok=True)

                npy_paths = eds.save_profile_element_maps_npy(
                    settings=map_settings,
                    output_dir=str(paths["readback_dir"]),
                    prefix=map_settings.name,
                    dtype="uint16",
                )

                for p in npy_paths:
                    log(f"Saved .npy: {p}")

                arrays = eds.read_profile_element_maps(map_settings, dtype="uint16")
                element_summary = summarize_element_arrays(map_settings, arrays)
                summary["element_maps"] = element_summary

                if bool(readback_cfg.get("log_element_stats", True)):
                    for item in element_summary:
                        log(
                            "Element stats: "
                            f"index={item['element_index']}, "
                            f"Z={item['atomic_number']}, "
                            f"line={item['line']}, "
                            f"shape={item['shape']}, "
                            f"dtype={item['dtype']}, "
                            f"min={item['min']}, max={item['max']}, "
                            f"sum={item['sum']}, nonzero={item['nonzero']}"
                        )

        elif map_mode == "simple":
            map_settings = parse_simple_map_settings(
                cfg,
                bcf_path=paths["bcf_path"],
                bmp_path=paths["bmp_path"],
            )
            log(f"Simple map settings: {map_settings}")

            log("Acquiring simple EDS map")
            outputs = eds.acquire_map(
                settings=map_settings,
                poll_interval_s=float(cfg["map"].get("poll_interval_s", 0.5)),
                max_wait_s=float(cfg["map"].get("max_wait_s", 600.0)),
            )
            log(f"Simple map outputs: {outputs}")

        else:
            raise ValueError(f"Unsupported map.mode: {map_mode}")

        if paths["bcf_path"].exists():
            log(f"BCF exists size={paths['bcf_path'].stat().st_size}")
            summary["bcf_size"] = paths["bcf_path"].stat().st_size
        else:
            log("WARNING: BCF missing")
            summary["errors"].append("BCF missing")

        if paths["bmp_path"].exists():
            log(f"BMP exists size={paths['bmp_path'].stat().st_size}")
            with open(paths["bmp_path"], "rb") as f:
                magic = f.read(2)
            log(f"BMP magic={magic!r}")
            summary["bmp_size"] = paths["bmp_path"].stat().st_size
            summary["bmp_magic"] = repr(magic)
        else:
            log("BMP missing or not requested")

        if bool(detector_cfg.get("park_after", True)):
            log("Moving EDS detector to park")
            park_settings = parse_detector_motion_settings(cfg, target_position="park")
            park_state = motion.move_eds_detector(park_settings)
            log(f"EDS detector after park move: {park_state}")
            summary["park_detector_position"] = park_state._asdict()

        final_state = motion.get_eds_detector_position(detector_index)
        log(f"Final EDS detector position: {final_state}")
        summary["final_detector_position"] = final_state._asdict()

        if bool(detector_cfg.get("verify_park_after", True)):
            if final_state.position_name != "park":
                msg = f"Detector final state is not park: {final_state}"
                log(f"WARNING: {msg}")
                summary["errors"].append(msg)

        log("EDS YAML hardware validation complete")

    except Exception as exc:
        msg = f"ERROR: {exc}"
        log(msg)
        summary["errors"].append(str(exc))

        tb = traceback.format_exc()
        for line in tb.splitlines():
            log(line)

    finally:
        paths["summary_json_path"].write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
        log(f"Summary JSON written: {paths['summary_json_path']}")

        if session is not None:
            if session_settings.close_on_exit:
                log("Closing Bruker session because close_on_exit=True")
                session.close()
            else:
                log("Leaving Esprit connection open (close_on_exit=False)")

        log("=== Bruker EDS YAML hardware validation end ===")


if __name__ == "__main__":
    main()
