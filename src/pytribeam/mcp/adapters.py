from pathlib import Path
from typing import Any, Dict, Tuple

import pytribeam.factory as factory
import pytribeam.types as tbt
import pytribeam.utilities as ut


def _normalize_beam_type(value: str) -> str:
    value = value.strip().lower()
    if value not in {"electron", "ion"}:
        raise ValueError(
            f"Unsupported beam_type '{value}'. Supported values are ['electron', 'ion']."
        )
    return value


def _normalize_bit_depth(value: int) -> tbt.ColorDepth:
    if value == 8:
        return tbt.ColorDepth.BITS_8
    if value == 16:
        return tbt.ColorDepth.BITS_16
    raise ValueError("bit_depth must be 8 or 16.")


def _normalize_resolution_string(value: str) -> str:
    """
    Accept:
    - 'PRESET_768X512'
    - '768x512'

    Return canonical WIDTHxHEIGHT string expected by factory validation.
    """
    value = value.strip()

    preset_name = value.upper()
    if hasattr(tbt.PresetResolution, preset_name):
        preset = getattr(tbt.PresetResolution, preset_name)
        return preset.value

    # Validate arbitrary WIDTHxHEIGHT
    res = factory.string_to_res(value)
    return res.value


def _normalize_detector_type(value: str) -> str:
    """
    Convert user-friendly enum names to actual enum values.
    Accepts either enum member name or enum value.
    """
    raw = value.strip()

    for item in tbt.DetectorType:
        if raw == item.name or raw.upper() == item.name or raw == item.value:
            return item.value

    raise ValueError(
        f"Unsupported detector_type '{value}'. "
        f"Supported values include {[i.name for i in tbt.DetectorType]}."
    )


def _normalize_detector_mode(value: str) -> str:
    raw = value.strip()

    for item in tbt.DetectorMode:
        if raw == item.name or raw.upper() == item.name or raw == item.value:
            return item.value

    raise ValueError(
        f"Unsupported detector_mode '{value}'. "
        f"Supported values include {[i.name for i in tbt.DetectorMode]}."
    )


def _null_auto_cb() -> Dict[str, Any]:
    return {
        "left": None,
        "top": None,
        "width": None,
        "height": None,
    }


def build_image_settings_from_mcp(
    microscope: tbt.Microscope,
    request: Dict[str, Any],
    step_name: str = "mcp_image_request",
    yml_format: tbt.YMLFormatVersion = tbt.YMLFormatVersion.V_1_0,
) -> Tuple[Path, tbt.ImageSettings]:
    """
    Convert a plain MCP request dict into validated pytribeam ImageSettings.

    Expected request structure:
    {
      "beam_type": "electron" | "ion",
      "beam": {
        "voltage_kv": float,
        "voltage_tol_kv": float,
        "current_na": float,
        "current_tol_na": float,
        "hfw_mm": float,
        "working_dist_mm": float,
        "dynamic_focus": bool | null,
        "tilt_correction": bool | null
      },
      "detector": {
        "type": str,
        "mode": str,
        "brightness": float | null,
        "contrast": float | null,
        "auto_cb": {
          "left": float,
          "top": float,
          "width": float,
          "height": float
        } | null
      },
      "scan": {
        "resolution": str,
        "rotation_deg": float,
        "dwell_time_us": float
      },
      "bit_depth": 8 | 16,
      "save_path": str
    }
    """
    if not isinstance(request, dict):
        raise TypeError("request must be a dictionary.")

    try:
        beam_type_value = _normalize_beam_type(request["beam_type"])
        beam_type = tbt.BeamType(beam_type_value)

        beam_in = request["beam"]
        detector_in = request["detector"]
        scan_in = request["scan"]
        save_path = Path(request["save_path"])
        bit_depth = _normalize_bit_depth(request["bit_depth"])
    except KeyError as exc:
        raise KeyError(f"Missing required image request key: {exc}") from exc

    auto_cb_in = detector_in.get("auto_cb")
    if auto_cb_in in (None, {}, "null", "None"):
        auto_cb_db = _null_auto_cb()
    else:
        auto_cb_db = {
            "left": auto_cb_in.get("left"),
            "top": auto_cb_in.get("top"),
            "width": auto_cb_in.get("width"),
            "height": auto_cb_in.get("height"),
        }

    beam_db = {
        "type": beam_type.value,
        "voltage_kv": beam_in["voltage_kv"],
        "voltage_tol_kv": beam_in["voltage_tol_kv"],
        "current_na": beam_in["current_na"],
        "current_tol_na": beam_in["current_tol_na"],
        "hfw_mm": beam_in["hfw_mm"],
        "working_dist_mm": beam_in["working_dist_mm"],
        "dynamic_focus": beam_in.get("dynamic_focus"),
        "tilt_correction": beam_in.get("tilt_correction"),
    }

    detector_db = {
        "type": _normalize_detector_type(detector_in["type"]),
        "mode": _normalize_detector_mode(detector_in["mode"]),
        "brightness": detector_in.get("brightness"),
        "contrast": detector_in.get("contrast"),
        "auto_cb": auto_cb_db,
    }

    scan_db = {
        "resolution": _normalize_resolution_string(scan_in["resolution"]),
        "rotation_deg": scan_in["rotation_deg"],
        "dwell_time_us": scan_in["dwell_time_us"],
    }

    factory.validate_beam_settings(
        microscope=microscope,
        beam_type=beam_type,
        settings=beam_db,
        yml_format=yml_format,
        step_name=step_name,
    )

    factory.validate_auto_cb_settings(
        settings=auto_cb_db,
        yml_format=yml_format,
        step_name=step_name,
    )

    factory.validate_detector_settings(
        microscope=microscope,
        beam_type=beam_type,
        settings=detector_db,
        yml_format=yml_format,
        step_name=step_name,
    )

    factory.validate_scan_settings(
        microscope=microscope,
        beam_type=beam_type,
        settings=scan_db,
        yml_format=yml_format,
        step_name=step_name,
    )

    beam_settings = tbt.BeamSettings(
        voltage_kv=beam_db["voltage_kv"],
        voltage_tol_kv=beam_db["voltage_tol_kv"],
        current_na=beam_db["current_na"],
        current_tol_na=beam_db["current_tol_na"],
        hfw_mm=beam_db["hfw_mm"],
        working_dist_mm=beam_db["working_dist_mm"],
        dynamic_focus=beam_db["dynamic_focus"],
        tilt_correction=beam_db["tilt_correction"],
    )

    auto_cb_settings = tbt.ScanArea(
        left=auto_cb_db["left"],
        top=auto_cb_db["top"],
        width=auto_cb_db["width"],
        height=auto_cb_db["height"],
    )

    detector_settings = tbt.Detector(
        type=tbt.DetectorType(detector_db["type"]),
        mode=tbt.DetectorMode(detector_db["mode"]),
        brightness=detector_db["brightness"],
        contrast=detector_db["contrast"],
        auto_cb_settings=auto_cb_settings,
    )

    resolution = factory.string_to_res(scan_db["resolution"])
    if ut.valid_enum_entry(obj=resolution, check_type=tbt.PresetResolution):
        resolution = tbt.PresetResolution(resolution)

    scan_settings = tbt.Scan(
        rotation_deg=scan_db["rotation_deg"],
        dwell_time_us=scan_db["dwell_time_us"],
        resolution=resolution,
    )

    if beam_settings.dynamic_focus or beam_settings.tilt_correction:
        if scan_settings.rotation_deg != 0.0:
            raise ValueError(
                "dynamic_focus or tilt_correction requires scan rotation to be 0.0 degrees."
            )

    beam_obj = factory.beam_object_type(beam_type)(settings=beam_settings)

    image_settings = tbt.ImageSettings(
        microscope=microscope,
        beam=beam_obj,
        detector=detector_settings,
        scan=scan_settings,
        bit_depth=bit_depth,
    )

    return save_path, image_settings


def build_minimal_beam_from_type(beam_type: str) -> tbt.Beam:
    """
    Create a beam object with empty settings for functions that only need beam identity.
    """
    normalized = _normalize_beam_type(beam_type)
    internal_type = tbt.BeamType(normalized)
    return factory.beam_object_type(internal_type)(settings=tbt.BeamSettings())
