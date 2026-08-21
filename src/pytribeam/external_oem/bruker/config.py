"""
Bruker EDS Configuration Module
================================

Provides YAML configuration parsing and schema validation for Bruker EDS
mapping workflows.

Parses YAML into immutable NamedTuple settings with validation using the
``schema`` library (matching the main pytribeam factory.py pattern).
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import yaml
from schema import And, Optional as SchemaOptional, Or, Schema, SchemaError

from pytribeam.external_oem.bruker.types import (
    BrukerDetectorMotionSettings,
    BrukerEDSElementMapSetting,
    BrukerEDSMapSettings,
    BrukerEDSOutputSettings,
    BrukerEDSProfileMapSettings,
    BrukerEDSReadbackSettings,
    BrukerEDSWorkflowSettings,
    BrukerRectROI,
    BrukerSessionSettings,
)


def load_bruker_eds_yaml(path: Union[str, Path]) -> BrukerEDSWorkflowSettings:
    """Load and parse a Bruker EDS workflow YAML configuration file.

    Parameters
    ----------
    path : str or Path
        Path to the YAML configuration file.

    Returns
    -------
    BrukerEDSWorkflowSettings
        Fully validated, immutable workflow settings.

    Raises
    ------
    FileNotFoundError
        If the YAML file does not exist.
    SchemaError
        If the YAML contents do not pass validation.
    ValueError
        If semantic validation fails (e.g., empty element list).
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Bruker EDS config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    validate_bruker_eds_config(cfg)

    session = parse_session_settings(cfg)
    detector = parse_detector_motion_settings(cfg)
    output = parse_output_settings(cfg)
    readback = parse_readback_settings(cfg)
    map_settings = parse_map_settings(cfg, output)

    return BrukerEDSWorkflowSettings(
        session=session,
        detector=detector,
        map=map_settings,
        output=output,
        readback=readback,
    )


def validate_bruker_eds_config(cfg: Dict[str, Any]) -> bool:
    """Validate top-level structure of the Bruker EDS YAML config.

    Parameters
    ----------
    cfg : dict
        Parsed YAML dictionary.

    Returns
    -------
    bool
        True if validation passes.

    Raises
    ------
    SchemaError
        If required sections are missing or have wrong types.
    """
    top_level_schema = Schema(
        {
            "session": dict,
            "output": dict,
            "detector": dict,
            "map": dict,
            SchemaOptional("readback"): Or(dict, None),
        }
    )
    top_level_schema.validate(cfg)

    # Validate session section
    session_schema = Schema(
        {
            "dll_dir": And(str, len),
            SchemaOptional("mode"): And(str, lambda s: s in ("local", "tcp")),
            SchemaOptional("server"): str,
            SchemaOptional("user"): str,
            SchemaOptional("password"): str,
            SchemaOptional("host"): Or(str, None),
            SchemaOptional("port"): Or(int, None),
            SchemaOptional("close_on_exit"): bool,
            SchemaOptional("keep_connection_open"): bool,
        }
    )
    session_schema.validate(cfg["session"])

    # Validate output section
    output_schema = Schema(
        {
            "root_dir": And(str, len),
            SchemaOptional("run_name"): str,
            SchemaOptional("slice_number"): Or(int, None),
            SchemaOptional("repeat_index"): Or(int, None),
            SchemaOptional("save_bcf"): bool,
            SchemaOptional("save_image"): bool,
            SchemaOptional("image_format"): str,
        }
    )
    output_schema.validate(cfg["output"])

    # Validate map section
    map_schema = Schema(
        {
            SchemaOptional("mode"): And(
                str, lambda s: s.lower() in ("profile", "simple")
            ),
            SchemaOptional("name"): str,
            "width_px": And(int, lambda x: x > 0),
            "height_px": And(int, lambda x: x > 0),
            "pixel_time_us": And(int, lambda x: x > 0),
            SchemaOptional("real_time_s"): And(int, lambda x: x >= 0),
            SchemaOptional("spu_device"): And(int, lambda x: x > 0),
            SchemaOptional("save_bcf"): bool,
            SchemaOptional("save_image"): bool,
            SchemaOptional("image_format"): str,
            SchemaOptional("poll_interval_s"): And(float, lambda x: x > 0),
            SchemaOptional("max_wait_s"): And(float, lambda x: x > 0),
            SchemaOptional("profile"): dict,
            SchemaOptional("roi"): Or(dict, None),
        },
        ignore_extra_keys=True,
    )
    map_schema.validate(cfg["map"])

    # Validate ROI if present
    roi_cfg = cfg["map"].get("roi")
    if roi_cfg is not None:
        roi_schema = Schema(
            {
                "x_start_px": And(int, lambda x: x >= 0),
                "y_start_px": And(int, lambda x: x >= 0),
                "width_px": And(int, lambda x: x > 0),
                "height_px": And(int, lambda x: x > 0),
            }
        )
        roi_schema.validate(roi_cfg)

        # Bounds check
        map_w = cfg["map"]["width_px"]
        map_h = cfg["map"]["height_px"]
        if roi_cfg["x_start_px"] + roi_cfg["width_px"] > map_w:
            raise SchemaError(
                f"ROI x_start_px({roi_cfg['x_start_px']}) + width_px({roi_cfg['width_px']}) "
                f"= {roi_cfg['x_start_px'] + roi_cfg['width_px']} exceeds map width_px({map_w})"
            )
        if roi_cfg["y_start_px"] + roi_cfg["height_px"] > map_h:
            raise SchemaError(
                f"ROI y_start_px({roi_cfg['y_start_px']}) + height_px({roi_cfg['height_px']}) "
                f"= {roi_cfg['y_start_px'] + roi_cfg['height_px']} exceeds map height_px({map_h})"
            )

    # Validate profile elements if profile mode
    map_mode = cfg["map"].get("mode", "profile").lower()
    if map_mode == "profile":
        profile = cfg["map"].get("profile", {})
        elements = profile.get("elements", [])
        if not elements:
            raise SchemaError(
                "Profile map mode requires at least one element in map.profile.elements"
            )
        if len(elements) > 51:
            raise SchemaError(
                f"Bruker supports at most 51 elements, got {len(elements)}"
            )

        for i, elem in enumerate(elements):
            elem_schema = Schema(
                {
                    "atomic_number": And(int, lambda x: 1 <= x <= 118),
                    SchemaOptional("symbol"): str,
                    SchemaOptional("line"): str,
                    SchemaOptional("energy_keV"): And(float, lambda x: x >= 0),
                    SchemaOptional("width"): And(float, lambda x: x > 0),
                    SchemaOptional("display_rgb"): And(list, lambda x: len(x) == 3),
                    SchemaOptional("rgb"): And(list, lambda x: len(x) == 3),
                },
                ignore_extra_keys=True,
            )
            try:
                elem_schema.validate(elem)
            except SchemaError as exc:
                raise SchemaError(
                    f"Validation failed for element {i} in map.profile.elements: {exc}"
                )

    return True


def parse_session_settings(cfg: Dict[str, Any]) -> BrukerSessionSettings:
    """Parse session settings from config dictionary."""
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


def parse_detector_motion_settings(cfg: Dict[str, Any]) -> BrukerDetectorMotionSettings:
    """Parse detector motion settings from config dictionary."""
    d = cfg["detector"]

    return BrukerDetectorMotionSettings(
        detector_index=int(d.get("detector_index", 1)),
        target_position="acquire",
        timeout_s=float(d.get("move_timeout_s", 60.0)),
        poll_interval_s=float(d.get("poll_interval_s", 0.5)),
    )

    """Parse output settings from config dictionary.

    The slice_number and repeat_index fields are typically set by the
    higher-level workflow dispatch (not from YAML directly), but are
    supported in YAML for standalone testing.
    """
    o = cfg["output"]

    return BrukerEDSOutputSettings(
        output_dir=str(o["root_dir"]),
        run_name=str(o.get("run_name", "bruker_eds")),
        slice_number=o.get("slice_number", None),
        repeat_index=o.get("repeat_index", None),
        save_bcf=bool(cfg["map"].get("save_bcf", True)),
        save_image=bool(cfg["map"].get("save_image", True)),
        image_format=str(cfg["map"].get("image_format", "bmp")),
    )


def parse_readback_settings(cfg: Dict[str, Any]) -> BrukerEDSReadbackSettings:
    """Parse readback settings from config dictionary."""
    r = cfg.get("readback", {}) or {}

    return BrukerEDSReadbackSettings(
        enabled=bool(r.get("save_element_npy", True)),
        dtype="uint16",
        save_element_npy=bool(r.get("save_element_npy", True)),
        save_element_images=bool(r.get("save_element_images", False)),
        log_element_stats=bool(r.get("log_element_stats", True)),
    )


def parse_roi_settings(cfg: Dict[str, Any]) -> Optional[BrukerRectROI]:
    """Parse optional ROI settings from map config."""
    roi_cfg = cfg["map"].get("roi")
    if roi_cfg is None:
        return None

    return BrukerRectROI(
        x_start_px=int(roi_cfg["x_start_px"]),
        y_start_px=int(roi_cfg["y_start_px"]),
        width_px=int(roi_cfg["width_px"]),
        height_px=int(roi_cfg["height_px"]),
    )


def _parse_optional_rgb(
    element_cfg: Dict[str, Any],
) -> Optional[Tuple[int, int, int]]:
    """Parse optional display RGB from element config."""
    rgb = element_cfg.get("display_rgb", element_cfg.get("rgb", None))
    if rgb is None:
        return None
    return (int(rgb[0]), int(rgb[1]), int(rgb[2]))


def parse_map_settings(
    cfg: Dict[str, Any],
    output: BrukerEDSOutputSettings,
) -> Union[BrukerEDSMapSettings, BrukerEDSProfileMapSettings]:
    """Parse map settings, returning either simple or profile map settings.

    Output paths (bcf, image) are constructed from the output settings
    and will be finalized by the workflow runner with timestamps.
    """
    m = cfg["map"]
    roi = parse_roi_settings(cfg)

    # Placeholder paths — the workflow runner will set final paths with timestamps
    bcf_path = "__pending__"
    image_path = "__pending__" if output.save_image else None
    image_format = output.image_format if output.save_image else None

    map_mode = str(m.get("mode", "profile")).lower().strip()

    if map_mode == "simple":
        return BrukerEDSMapSettings(
            name=str(m.get("name", "eds_simple_map")),
            width_px=int(m["width_px"]),
            height_px=int(m["height_px"]),
            pixel_time_us=int(m["pixel_time_us"]),
            real_time_s=int(m.get("real_time_s", 0)),
            output_bcf_path=bcf_path,
            output_image_path=image_path,
            output_image_format=image_format,
            spu_device=int(m.get("spu_device", 1)),
            roi=roi,
        )

    # Profile mode
    profile = m.get("profile", {})
    elements = []
    for e in profile.get("elements", []):
        elements.append(
            BrukerEDSElementMapSetting(
                atomic_number=int(e["atomic_number"]),
                line=str(e.get("line", "KA")),
                energy_keV=float(e.get("energy_keV", 0.0)),
                width=float(e.get("width", 1.0)),
                display_rgb=_parse_optional_rgb(e),
            )
        )

    return BrukerEDSProfileMapSettings(
        name=str(m.get("name", "eds_profile_map")),
        width_px=int(m["width_px"]),
        height_px=int(m["height_px"]),
        pixel_time_us=int(m["pixel_time_us"]),
        output_bcf_path=bcf_path,
        output_image_path=image_path,
        output_image_format=image_format,
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
        roi=roi,
    )
