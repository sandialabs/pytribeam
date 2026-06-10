from typing import Any, Dict

import pytribeam.factory as factory
import pytribeam.image as image_mod

from pytribeam.mcp.adapters import (
    build_image_settings_from_mcp,
    build_minimal_beam_from_type,
)


IMAGE_REQUEST_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "beam_type": {
            "type": "string",
            "enum": ["electron", "ion"],
        },
        "beam": {
            "type": "object",
            "properties": {
                "voltage_kv": {"type": "number"},
                "voltage_tol_kv": {"type": "number"},
                "current_na": {"type": "number"},
                "current_tol_na": {"type": "number"},
                "hfw_mm": {"type": "number"},
                "working_dist_mm": {"type": "number"},
                "dynamic_focus": {"type": ["boolean", "null"]},
                "tilt_correction": {"type": ["boolean", "null"]},
            },
            "required": [
                "voltage_kv",
                "voltage_tol_kv",
                "current_na",
                "current_tol_na",
                "hfw_mm",
                "working_dist_mm",
            ],
        },
        "detector": {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "mode": {"type": "string"},
                "brightness": {"type": ["number", "null"]},
                "contrast": {"type": ["number", "null"]},
                "auto_cb": {
                    "type": ["object", "null"],
                    "properties": {
                        "left": {"type": "number"},
                        "top": {"type": "number"},
                        "width": {"type": "number"},
                        "height": {"type": "number"},
                    },
                },
            },
            "required": ["type", "mode"],
        },
        "scan": {
            "type": "object",
            "properties": {
                "resolution": {"type": "string"},
                "rotation_deg": {"type": "number"},
                "dwell_time_us": {"type": "number"},
            },
            "required": ["resolution", "rotation_deg", "dwell_time_us"],
        },
        "bit_depth": {
            "type": "integer",
            "enum": [8, 16],
        },
        "save_path": {"type": "string"},
    },
    "required": ["beam_type", "beam", "detector", "scan", "bit_depth", "save_path"],
}


CONNECT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "host": {"type": "string"},
        "port": {"type": ["integer", "null"]},
    },
    "required": ["host"],
}


BEAM_READY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "beam_type": {"type": "string", "enum": ["electron", "ion"]},
        "delay_s": {"type": "number"},
        "attempts": {"type": "integer"},
    },
    "required": ["beam_type"],
}


SET_BEAM_CURRENT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "beam_type": {"type": "string", "enum": ["electron", "ion"]},
        "current_na": {"type": "number"},
        "current_tol_na": {"type": "number"},
        "delay_s": {"type": "number"},
    },
    "required": ["beam_type", "current_na", "current_tol_na"],
}


SET_BEAM_VOLTAGE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "beam_type": {"type": "string", "enum": ["electron", "ion"]},
        "voltage_kv": {"type": "number"},
        "voltage_tol_kv": {"type": "number"},
        "delay_s": {"type": "number"},
    },
    "required": ["beam_type", "voltage_kv", "voltage_tol_kv"],
}


def get_image_tool_definitions(runtime):
    """
    Return a list of MCP tool definitions for imaging.
    Each entry contains metadata and a handler function.
    """

    def microscope_connect(arguments: Dict[str, Any]) -> Dict[str, Any]:
        with runtime.lock:
            host = arguments["host"]
            port = arguments.get("port")
            message = runtime.connect(host=host, port=port)
            return {
                "status": "ok",
                "message": message,
            }

    def microscope_disconnect(arguments: Dict[str, Any]) -> Dict[str, Any]:
        _ = arguments
        with runtime.lock:
            message = runtime.disconnect()
            return {
                "status": "ok",
                "message": message,
            }

    def microscope_status(arguments: Dict[str, Any]) -> Dict[str, Any]:
        _ = arguments
        with runtime.lock:
            microscope = runtime.require_microscope()
            return {
                "status": "ok",
                "connected": True,
                "host": runtime.host,
                "port": runtime.port,
                "vacuum_state": microscope.vacuum.chamber_state,
                "active_device": microscope.imaging.get_active_device(),
                "available_detector_types": factory.available_detector_types(microscope),
                "available_detector_modes": factory.available_detector_modes(microscope),
            }

    def imaging_prepare(arguments: Dict[str, Any]) -> Dict[str, Any]:
        with runtime.lock:
            microscope = runtime.require_microscope()
            _, img_settings = build_image_settings_from_mcp(
                microscope=microscope,
                request=arguments,
                step_name="mcp_imaging_prepare",
            )
            image_mod.prepare_imaging(img_settings=img_settings)
            return {
                "status": "ok",
                "beam_type": img_settings.beam.type.value,
                "resolution": img_settings.scan.resolution.value,
                "bit_depth": int(img_settings.bit_depth),
            }

    def imaging_collect_single_image(arguments: Dict[str, Any]) -> Dict[str, Any]:
        with runtime.lock:
            microscope = runtime.require_microscope()
            save_path, img_settings = build_image_settings_from_mcp(
                microscope=microscope,
                request=arguments,
                step_name="mcp_collect_single_image",
            )
            image_mod.collect_single_image(
                save_path=save_path,
                img_settings=img_settings,
            )
            return {
                "status": "ok",
                "save_path": str(save_path),
                "beam_type": img_settings.beam.type.value,
                "resolution": img_settings.scan.resolution.value,
                "bit_depth": int(img_settings.bit_depth),
            }

    def imaging_beam_ready(arguments: Dict[str, Any]) -> Dict[str, Any]:
        with runtime.lock:
            microscope = runtime.require_microscope()
            beam = build_minimal_beam_from_type(arguments["beam_type"])
            delay_s = arguments.get("delay_s", 5.0)
            attempts = arguments.get("attempts", 2)

            image_mod.beam_ready(
                beam=beam,
                microscope=microscope,
                delay_s=delay_s,
                attempts=attempts,
            )
            return {
                "status": "ok",
                "beam_type": beam.type.value,
                "delay_s": delay_s,
                "attempts": attempts,
            }

    def imaging_set_beam_current(arguments: Dict[str, Any]) -> Dict[str, Any]:
        with runtime.lock:
            microscope = runtime.require_microscope()
            beam = build_minimal_beam_from_type(arguments["beam_type"])

            image_mod.beam_current(
                beam=beam,
                microscope=microscope,
                current_na=arguments["current_na"],
                current_tol_na=arguments["current_tol_na"],
                delay_s=arguments.get("delay_s", 5.0),
            )
            return {
                "status": "ok",
                "beam_type": beam.type.value,
                "current_na": arguments["current_na"],
                "current_tol_na": arguments["current_tol_na"],
            }

    def imaging_set_beam_voltage(arguments: Dict[str, Any]) -> Dict[str, Any]:
        with runtime.lock:
            microscope = runtime.require_microscope()
            beam = build_minimal_beam_from_type(arguments["beam_type"])

            image_mod.beam_voltage(
                beam=beam,
                microscope=microscope,
                voltage_kv=arguments["voltage_kv"],
                voltage_tol_kv=arguments["voltage_tol_kv"],
                delay_s=arguments.get("delay_s", 5.0),
            )
            return {
                "status": "ok",
                "beam_type": beam.type.value,
                "voltage_kv": arguments["voltage_kv"],
                "voltage_tol_kv": arguments["voltage_tol_kv"],
            }

    return [
        {
            "name": "microscope_connect",
            "description": "Connect to a Thermo Fisher microscope using AutoScript.",
            "inputSchema": CONNECT_SCHEMA,
            "handler": microscope_connect,
        },
        {
            "name": "microscope_disconnect",
            "description": "Disconnect from the microscope.",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
            "handler": microscope_disconnect,
        },
        {
            "name": "microscope_status",
            "description": "Return basic microscope connection and detector status.",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
            "handler": microscope_status,
        },
        {
            "name": "imaging_prepare",
            "description": "Prepare beam, scan, and detector settings without collecting an image.",
            "inputSchema": IMAGE_REQUEST_SCHEMA,
            "handler": imaging_prepare,
        },
        {
            "name": "imaging_collect_single_image",
            "description": "Prepare microscope imaging conditions and collect a single image to disk.",
            "inputSchema": IMAGE_REQUEST_SCHEMA,
            "handler": imaging_collect_single_image,
        },
        {
            "name": "imaging_beam_ready",
            "description": "Ensure the requested beam is on and unblanked.",
            "inputSchema": BEAM_READY_SCHEMA,
            "handler": imaging_beam_ready,
        },
        {
            "name": "imaging_set_beam_current",
            "description": "Set the selected beam current in nanoamps.",
            "inputSchema": SET_BEAM_CURRENT_SCHEMA,
            "handler": imaging_set_beam_current,
        },
        {
            "name": "imaging_set_beam_voltage",
            "description": "Set the selected beam voltage in kilovolts.",
            "inputSchema": SET_BEAM_VOLTAGE_SCHEMA,
            "handler": imaging_set_beam_voltage,
        },
    ]
