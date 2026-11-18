"""
Bruker EDS Configuration Module
================================

Provides configuration parsing and schema validation for Bruker EDS and EBSD
mapping workflows.

Two entry points:

- :func:`parse_bruker_settings` parses the ``Bruker_settings`` block of a
  pyTriBeam experiment YAML (v1.2+) into a :class:`BrukerSettings`.
- :func:`load_bruker_eds_yaml` reads a standalone Bruker EDS YAML file, as used
  by the deprecated custom-step tooling in ``bruker/tools``.

The ``Bruker_settings`` block has this layout. ``eds`` uses the same sections as
the standalone EDS YAML, minus ``session``, which is shared::

    Bruker_settings:
      session: {dll_dir, mode, server, user, password, host, port, ...}
      eds:                      # optional
        output: {root_dir, run_name}
        detector: {...}
        map: {...}
        readback: {...}
      ebsd:                     # optional; not yet hardware-validated
        output: {root_dir, run_name}
        detector: {inserted_position_mm, retracted_position_mm, ...}
        acquisition: {profile_name, width_px, height_px, pixel_time_us, ...}

Parses YAML into immutable NamedTuple settings with validation using the
``schema`` library (matching the main pytribeam factory.py pattern).
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import yaml
from schema import SchemaError

from pytribeam.external_oem.bruker.types import (
    BrukerDetectorMotionSettings,
    BrukerEBSDDetectorSettings,
    BrukerEBSDScanAreaSettings,
    BrukerEBSDWorkflowSettings,
    BrukerEDSElementMapSetting,
    BrukerEDSMapSettings,
    BrukerEDSOutputSettings,
    BrukerEDSProfileMapSettings,
    BrukerEDSReadbackSettings,
    BrukerEDSWorkflowSettings,
    BrukerRectROI,
    BrukerSessionSettings,
    BrukerSettings,
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

    return parse_bruker_eds_config(cfg)


def parse_bruker_eds_config(cfg: Dict[str, Any]) -> BrukerEDSWorkflowSettings:
    """Validate and parse a Bruker EDS configuration dictionary.

    The dictionary has the standalone EDS YAML layout: ``session``, ``output``,
    ``detector``, ``map`` and optional ``readback`` sections.

    Raises
    ------
    SchemaError
        If the contents do not pass validation.
    """
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


def parse_bruker_settings(cfg: Dict[str, Any]) -> BrukerSettings:
    """Validate and parse a ``Bruker_settings`` block from an experiment YAML.

    Parameters
    ----------
    cfg : dict
        The ``Bruker_settings`` mapping. It needs a ``session`` section and at
        least one of ``eds`` or ``ebsd``.

    Returns
    -------
    BrukerSettings
        Immutable settings; ``eds`` / ``ebsd`` are None when absent.

    Raises
    ------
    SchemaError
        If the contents do not pass validation.
    """
    if not isinstance(cfg, dict):
        raise SchemaError("Bruker_settings must be a mapping/dictionary")
    _require_keys(cfg, "Bruker_settings", ("session",))
    for section_name in ("session", "eds", "ebsd"):
        section = cfg.get(section_name)
        if section is not None and not isinstance(section, dict):
            raise SchemaError(
                f"Bruker_settings.{section_name} must be a mapping/dictionary"
            )
    if cfg.get("eds") is None and cfg.get("ebsd") is None:
        raise SchemaError(
            "Bruker_settings must contain an 'eds' and/or an 'ebsd' section"
        )

    eds = None
    if cfg.get("eds") is not None:
        eds = parse_bruker_eds_config({**cfg["eds"], "session": cfg["session"]})

    ebsd = None
    if cfg.get("ebsd") is not None:
        ebsd = parse_bruker_ebsd_config({**cfg["ebsd"], "session": cfg["session"]})

    session = eds.session if eds is not None else ebsd.session
    return BrukerSettings(session=session, eds=eds, ebsd=ebsd)


def parse_bruker_ebsd_config(cfg: Dict[str, Any]) -> BrukerEBSDWorkflowSettings:
    """Validate and parse a Bruker EBSD configuration dictionary.

    The dictionary has ``session``, ``output``, ``detector`` and
    ``acquisition`` sections.

    Raises
    ------
    SchemaError
        If the contents do not pass validation.
    """
    validate_bruker_ebsd_config(cfg)

    d = cfg["detector"]
    a = cfg["acquisition"]
    o = cfg["output"]
    detector = BrukerEBSDDetectorSettings(
        inserted_position_mm=float(d["inserted_position_mm"]),
        retracted_position_mm=float(d["retracted_position_mm"]),
        speed_mm_per_s=float(d.get("speed_mm_per_s", 2.0)),
        tolerance_mm=float(d.get("tolerance_mm", 0.10)),
        timeout_s=float(d.get("move_timeout_s", 60.0)),
        poll_interval_s=float(d.get("poll_interval_s", 0.5)),
        stable_polls=int(d.get("stable_polls", 2)),
    )
    return BrukerEBSDWorkflowSettings(
        session=parse_session_settings(cfg),
        detector=detector,
        profile_name=str(a["profile_name"]),
        scan_area=BrukerEBSDScanAreaSettings(
            width_px=int(a["width_px"]),
            height_px=int(a["height_px"]),
            pixel_time_us=int(a["pixel_time_us"]),
        ),
        output=BrukerEDSOutputSettings(
            output_dir=str(o["root_dir"]),
            run_name=str(o.get("run_name", "bruker_ebsd")),
        ),
        with_patterns=bool(a.get("with_patterns", False)),
        poll_interval_s=float(a.get("poll_interval_s", 1.0)),
        timeout_s=float(a.get("timeout_s", 3600.0)),
    )


def _require_keys(section: Dict[str, Any], section_name: str, keys: Tuple[str, ...]):
    for key in keys:
        if key not in section:
            path = f"{section_name}.{key}" if section_name else key
            raise SchemaError(f"Missing required setting: {path}")


def _require_type(value: Any, expected_type, path: str):
    if not isinstance(value, expected_type):
        expected_name = getattr(expected_type, "__name__", str(expected_type))
        raise SchemaError(
            f"{path} must be {expected_name}; got {type(value).__name__}: {value!r}"
        )


def _require_nonempty_str(value: Any, path: str):
    _require_type(value, str, path)
    if not value:
        raise SchemaError(f"{path} must be a non-empty string")


def _require_bool(value: Any, path: str):
    if not isinstance(value, bool):
        raise SchemaError(f"{path} must be true or false; got {value!r}")


def _require_int(value: Any, path: str):
    if not isinstance(value, int) or isinstance(value, bool):
        raise SchemaError(f"{path} must be an integer; got {value!r}")


def _require_positive_int(value: Any, path: str):
    _require_int(value, path)
    if value <= 0:
        raise SchemaError(f"{path} must be a positive integer; got {value}")


def _require_nonnegative_int(value: Any, path: str):
    _require_int(value, path)
    if value < 0:
        raise SchemaError(f"{path} must be a non-negative integer; got {value}")


def _require_positive_number(value: Any, path: str):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise SchemaError(f"{path} must be a positive number; got {value!r}")
    if value <= 0:
        raise SchemaError(f"{path} must be a positive number; got {value}")


def _require_nonnegative_number(value: Any, path: str):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise SchemaError(f"{path} must be a non-negative number; got {value!r}")
    if value < 0:
        raise SchemaError(f"{path} must be a non-negative number; got {value}")


def _require_optional_type(section: Dict[str, Any], key: str, expected_type, path: str):
    if key in section and section[key] is not None:
        _require_type(section[key], expected_type, path)


def validate_bruker_eds_config(cfg: Dict[str, Any]) -> bool:
    """Validate top-level structure and semantic constraints of Bruker EDS YAML."""
    if not isinstance(cfg, dict):
        raise SchemaError("Bruker EDS YAML must parse to a mapping/dictionary")

    _require_keys(cfg, "", ("session", "output", "detector", "map"))
    for section_name in ("session", "output", "detector", "map"):
        if not isinstance(cfg[section_name], dict):
            raise SchemaError(f"{section_name} must be a mapping/dictionary")
    if (
        "readback" in cfg
        and cfg["readback"] is not None
        and not isinstance(cfg["readback"], dict)
    ):
        raise SchemaError("readback must be a mapping/dictionary or null")

    _validate_session_config(cfg["session"])

    output_cfg = cfg["output"]
    _require_keys(output_cfg, "output", ("root_dir",))
    _require_nonempty_str(output_cfg["root_dir"], "output.root_dir")
    _require_optional_type(output_cfg, "run_name", str, "output.run_name")
    for key in ("slice_number", "repeat_index"):
        if key in output_cfg and output_cfg[key] is not None:
            _require_int(output_cfg[key], f"output.{key}")
    for key in ("save_bcf", "save_image"):
        if key in output_cfg:
            _require_bool(output_cfg[key], f"output.{key}")
    _require_optional_type(output_cfg, "image_format", str, "output.image_format")

    detector_cfg = cfg["detector"]
    if "detector_index" in detector_cfg:
        _require_positive_int(detector_cfg["detector_index"], "detector.detector_index")
    for key in (
        "move_detector",
        "verify_park_before",
        "move_to_acquire_before",
        "park_after",
    ):
        if key in detector_cfg:
            _require_bool(detector_cfg[key], f"detector.{key}")
    if "move_timeout_s" in detector_cfg:
        _require_positive_number(
            detector_cfg["move_timeout_s"], "detector.move_timeout_s"
        )
    if "poll_interval_s" in detector_cfg:
        _require_positive_number(
            detector_cfg["poll_interval_s"], "detector.poll_interval_s"
        )

    map_cfg = cfg["map"]
    _require_keys(map_cfg, "map", ("width_px", "height_px", "pixel_time_us"))
    map_mode = map_cfg.get("mode", "profile")
    _require_type(map_mode, str, "map.mode")
    map_mode = map_mode.lower().strip()
    if map_mode not in ("profile", "simple"):
        raise SchemaError(
            f"map.mode must be one of ['profile', 'simple']; got {map_cfg.get('mode')!r}"
        )
    _require_optional_type(map_cfg, "name", str, "map.name")
    _require_positive_int(map_cfg["width_px"], "map.width_px")
    _require_positive_int(map_cfg["height_px"], "map.height_px")
    _require_positive_int(map_cfg["pixel_time_us"], "map.pixel_time_us")
    if "real_time_s" in map_cfg:
        _require_nonnegative_int(map_cfg["real_time_s"], "map.real_time_s")
    if "spu_device" in map_cfg:
        _require_positive_int(map_cfg["spu_device"], "map.spu_device")
    for key in ("save_bcf", "save_image"):
        if key in map_cfg:
            _require_bool(map_cfg[key], f"map.{key}")
    _require_optional_type(map_cfg, "image_format", str, "map.image_format")
    if "poll_interval_s" in map_cfg:
        _require_positive_number(map_cfg["poll_interval_s"], "map.poll_interval_s")
    if "max_wait_s" in map_cfg:
        _require_positive_number(map_cfg["max_wait_s"], "map.max_wait_s")
    if (
        "profile" in map_cfg
        and map_cfg["profile"] is not None
        and not isinstance(map_cfg["profile"], dict)
    ):
        raise SchemaError("map.profile must be a mapping/dictionary")

    roi_cfg = map_cfg.get("roi")
    if roi_cfg is not None:
        if not isinstance(roi_cfg, dict):
            raise SchemaError("map.roi must be a mapping/dictionary or null")
        _require_keys(
            roi_cfg, "map.roi", ("x_start_px", "y_start_px", "width_px", "height_px")
        )
        _require_nonnegative_int(roi_cfg["x_start_px"], "map.roi.x_start_px")
        _require_nonnegative_int(roi_cfg["y_start_px"], "map.roi.y_start_px")
        _require_positive_int(roi_cfg["width_px"], "map.roi.width_px")
        _require_positive_int(roi_cfg["height_px"], "map.roi.height_px")
        if roi_cfg["x_start_px"] + roi_cfg["width_px"] > map_cfg["width_px"]:
            raise SchemaError(
                "map.roi exceeds map width: "
                f"x_start_px({roi_cfg['x_start_px']}) + width_px({roi_cfg['width_px']}) "
                f"= {roi_cfg['x_start_px'] + roi_cfg['width_px']} > map.width_px({map_cfg['width_px']})"
            )
        if roi_cfg["y_start_px"] + roi_cfg["height_px"] > map_cfg["height_px"]:
            raise SchemaError(
                "map.roi exceeds map height: "
                f"y_start_px({roi_cfg['y_start_px']}) + height_px({roi_cfg['height_px']}) "
                f"= {roi_cfg['y_start_px'] + roi_cfg['height_px']} > map.height_px({map_cfg['height_px']})"
            )

    if map_mode == "profile":
        profile = map_cfg.get("profile", {})
        elements = profile.get("elements", []) if isinstance(profile, dict) else []
        if not isinstance(elements, list):
            raise SchemaError("map.profile.elements must be a list")
        if not elements:
            raise SchemaError(
                "map.profile.elements must contain at least one element for profile maps"
            )
        if len(elements) > 51:
            raise SchemaError(
                f"map.profile.elements supports at most 51 elements; got {len(elements)}"
            )
        for idx, element in enumerate(elements):
            if not isinstance(element, dict):
                raise SchemaError(
                    f"map.profile.elements[{idx}] must be a mapping/dictionary"
                )
            path = f"map.profile.elements[{idx}]"
            _require_keys(element, path, ("atomic_number",))
            _require_int(element["atomic_number"], f"{path}.atomic_number")
            if not 1 <= element["atomic_number"] <= 118:
                raise SchemaError(
                    f"{path}.atomic_number must be between 1 and 118; "
                    f"got {element['atomic_number']}"
                )
            _require_optional_type(element, "symbol", str, f"{path}.symbol")
            _require_optional_type(element, "line", str, f"{path}.line")
            if "energy_keV" in element:
                _require_nonnegative_number(element["energy_keV"], f"{path}.energy_keV")
            if "width" in element:
                _require_positive_number(element["width"], f"{path}.width")
            for rgb_key in ("display_rgb", "rgb"):
                if rgb_key in element:
                    rgb = element[rgb_key]
                    if not isinstance(rgb, list) or len(rgb) != 3:
                        raise SchemaError(f"{path}.{rgb_key} must be a 3-item RGB list")
                    for channel_idx, channel in enumerate(rgb):
                        _require_int(channel, f"{path}.{rgb_key}[{channel_idx}]")
                        if not 0 <= channel <= 255:
                            raise SchemaError(
                                f"{path}.{rgb_key}[{channel_idx}] must be 0..255; got {channel}"
                            )

    return True


def _validate_session_config(session_cfg: Dict[str, Any]) -> None:
    """Validate the ``session`` section shared by EDS and EBSD configs."""
    _require_keys(session_cfg, "session", ("dll_dir",))
    _require_nonempty_str(session_cfg["dll_dir"], "session.dll_dir")
    mode = session_cfg.get("mode", "local")
    _require_type(mode, str, "session.mode")
    if mode not in ("local", "tcp"):
        raise SchemaError(f"session.mode must be one of ['local', 'tcp']; got {mode!r}")
    for key in ("server", "user", "password"):
        _require_optional_type(session_cfg, key, str, f"session.{key}")
    if "host" in session_cfg and session_cfg["host"] is not None:
        _require_type(session_cfg["host"], str, "session.host")
    if "port" in session_cfg and session_cfg["port"] is not None:
        _require_int(session_cfg["port"], "session.port")
    for key in ("close_on_exit", "keep_connection_open"):
        if key in session_cfg:
            _require_bool(session_cfg[key], f"session.{key}")


def validate_bruker_ebsd_config(cfg: Dict[str, Any]) -> bool:
    """Validate the structure and values of a Bruker EBSD configuration."""
    if not isinstance(cfg, dict):
        raise SchemaError("Bruker EBSD config must be a mapping/dictionary")

    sections = ("session", "output", "detector", "acquisition")
    _require_keys(cfg, "", sections)
    for section_name in sections:
        if not isinstance(cfg[section_name], dict):
            raise SchemaError(f"{section_name} must be a mapping/dictionary")

    _validate_session_config(cfg["session"])

    output_cfg = cfg["output"]
    _require_keys(output_cfg, "output", ("root_dir",))
    _require_nonempty_str(output_cfg["root_dir"], "output.root_dir")
    _require_optional_type(output_cfg, "run_name", str, "output.run_name")

    detector_cfg = cfg["detector"]
    _require_keys(
        detector_cfg, "detector", ("inserted_position_mm", "retracted_position_mm")
    )
    for key in ("inserted_position_mm", "retracted_position_mm"):
        _require_nonnegative_number(detector_cfg[key], f"detector.{key}")
    for key in ("speed_mm_per_s", "tolerance_mm", "move_timeout_s", "poll_interval_s"):
        if key in detector_cfg:
            _require_positive_number(detector_cfg[key], f"detector.{key}")
    if "stable_polls" in detector_cfg:
        _require_positive_int(detector_cfg["stable_polls"], "detector.stable_polls")
    tolerance = detector_cfg.get("tolerance_mm", 0.10)
    separation = abs(
        detector_cfg["inserted_position_mm"] - detector_cfg["retracted_position_mm"]
    )
    if separation <= tolerance:
        raise SchemaError(
            "detector.inserted_position_mm and detector.retracted_position_mm must "
            f"differ by more than tolerance_mm ({tolerance}); got a separation of "
            f"{separation}"
        )

    acquisition_cfg = cfg["acquisition"]
    _require_keys(
        acquisition_cfg,
        "acquisition",
        ("profile_name", "width_px", "height_px", "pixel_time_us"),
    )
    _require_nonempty_str(acquisition_cfg["profile_name"], "acquisition.profile_name")
    for key in ("width_px", "height_px", "pixel_time_us"):
        _require_positive_int(acquisition_cfg[key], f"acquisition.{key}")
    if "with_patterns" in acquisition_cfg:
        _require_bool(acquisition_cfg["with_patterns"], "acquisition.with_patterns")
    for key in ("poll_interval_s", "timeout_s"):
        if key in acquisition_cfg:
            _require_positive_number(acquisition_cfg[key], f"acquisition.{key}")

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

    # Convenience switch used by simulator/characterization configs. If the
    # more specific keys below are omitted, move_detector controls all detector
    # position API calls. Hardware configs should generally leave this true and
    # keep verify_park_before/park_after enabled for safety.
    detector_motion_enabled = bool(d.get("move_detector", True))

    return BrukerDetectorMotionSettings(
        detector_index=int(d.get("detector_index", 1)),
        target_position="acquire",
        timeout_s=float(d.get("move_timeout_s", 60.0)),
        poll_interval_s=float(d.get("poll_interval_s", 0.5)),
        verify_park_before=bool(d.get("verify_park_before", detector_motion_enabled)),
        move_to_acquire_before=bool(
            d.get("move_to_acquire_before", detector_motion_enabled)
        ),
        park_after=bool(d.get("park_after", detector_motion_enabled)),
    )


def parse_output_settings(cfg: Dict[str, Any]) -> BrukerEDSOutputSettings:
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
        save_element_tiff=bool(r.get("save_element_tiff", False)),
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
