#!/usr/bin/python3
"""
Imaging Capabilities
====================

Tier 1 tools that change beam, detector, and scan settings and take images.

Tier 2 adds no tools. It lifts one guardrail on these: at tier 1 a retractable
detector is refused, and at tier 2 and above it may be used and is inserted if
needed. This module reads ``config.max_tier`` to decide, the one exception to
"one module, one tier", because the alternative is a second copy of every
imaging tool.

Settings are validated by building an ``image`` step in the experiment config
format and passing it to ``factory.image``, so the agent gets the same range
and schema checks as an experiment file. Every tool snapshots the microscope
state before and after it acts and returns what changed.

Each pytribeam call sits in a small module-level function (``_validate``,
``_grab`` and so on) that imports pytribeam itself, so the server starts
without AutoScript and tests can replace the hardware.
"""

from __future__ import annotations

import logging
import threading
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import anyio.from_thread
import yaml
from mcp.server.mcpserver import Context, Image
from mcp.server.mcpserver.exceptions import ToolError

from pytribeam.mcp import state
from pytribeam.mcp.capabilities import _images
from pytribeam.mcp.capabilities._helpers import (
    acted,
    agent_errors,
    collect_warnings,
    is_agent_error,
    snapshot,
)
from pytribeam.mcp.capabilities.images import image_content, sidecar_path

TIER = 1
INSERT_TIER = 2  # lowest tier that may use (and insert) a retractable detector

log = logging.getLogger("pytribeam.mcp.imaging")

Beam = Literal["electron", "ion"]

# Fixed time per frame on top of pixels x dwell: flyback, settling, transfer.
# Calibrate on the simulator against the acquisition_s each image reports.
FRAME_OVERHEAD_S = 1.0
PROGRESS_INTERVAL_S = 5.0

# Retractable detector states in which pytribeam will not move it.
_AT_REST = ("Stationary",)
_INSERTED = "Inserted"
_FULL_FRAME_CB = {"left": 0.0, "top": 0.0, "width": 1.0, "height": 1.0}

# Smallest brightness/contrast used in place of an out-of-range current value;
# pytribeam rejects exactly 0.
LEVEL_MIN = 0.001



# ---------------------------------------------------------------------------
# pytribeam calls. Tests replace these.
# ---------------------------------------------------------------------------
def _beam(beam: str):
    from pytribeam import types as tbt

    if beam == "electron":
        return tbt.ElectronBeam(settings=tbt.BeamSettings())
    return tbt.IonBeam(settings=tbt.BeamSettings())


def _read_view(microscope) -> Dict[str, Any]:
    from pytribeam import types as tbt

    return {
        "active_view": int(microscope.imaging.get_active_view()),
        "active_device": tbt.Device(microscope.imaging.get_active_device()).name,
    }


def _set_view(microscope, quad: int) -> None:
    from pytribeam import image
    from pytribeam import types as tbt

    image.set_view(microscope, tbt.ViewQuad(quad))


def _select_beam(microscope, beam: str) -> None:
    """Switch to the beam's default quad and device."""
    from pytribeam import image

    beam_obj = _beam(beam)
    image.set_view(microscope, beam_obj.default_view)
    image.set_beam_device(microscope, beam_obj.device)


def _current(microscope) -> Dict[str, Any]:
    """The active device's settings, flattened to tool argument names."""
    from pytribeam import factory

    settings = factory.active_image_settings(microscope)
    b, d, s = settings.beam.settings, settings.detector, settings.scan
    return {
        "voltage_kv": b.voltage_kv,
        "current_na": b.current_na,
        "hfw_mm": b.hfw_mm,
        "working_dist_mm": b.working_dist_mm,
        "dynamic_focus": b.dynamic_focus,
        "tilt_correction": b.tilt_correction,
        "detector": d.type.value,
        "detector_mode": d.mode.value,
        "brightness": d.brightness,
        "contrast": d.contrast,
        "rotation_deg": s.rotation_deg,
        "dwell_us": s.dwell_time_us,
        "resolution": f"{s.resolution.width}x{s.resolution.height}",
    }


def _scan(microscope, beam: str) -> Dict[str, Any]:
    """The beam's current resolution and dwell, read without changing the view."""
    from pytribeam import utilities as ut
    from pytribeam.constants import Conversions

    scanning = ut.beam_type(_beam(beam), microscope).scanning
    return {
        "resolution": str(scanning.resolution.value),
        "dwell_us": scanning.dwell_time.value * Conversions.S_TO_US,
    }


def _beam_is_on(microscope, beam: str) -> bool:
    from pytribeam import utilities as ut

    return bool(ut.beam_type(_beam(beam), microscope).is_on)


def _detector_modes(microscope, detector: str) -> Optional[List[str]]:
    """The modes *detector* offers on the active device, or None if it cannot
    be selected there (validation then reports why).

    Leaves *detector* as the active detector type on the active device.
    """
    from pytribeam import image
    from pytribeam import types as tbt

    try:
        image.detector_type(microscope, tbt.DetectorType(detector))
    except Exception:
        return None
    return [str(mode) for mode in microscope.detector.mode.available_values]


def _detector_state(microscope, detector: str) -> str:
    """The detector's ``RetractableDeviceState`` value, e.g. "Stationary".

    Leaves *detector* as the active detector type on the active device.
    """
    from pytribeam import insertable_devices as devices
    from pytribeam import types as tbt

    return devices.detector_state(microscope, tbt.DetectorType(detector)).value


def _validate(microscope, step: Dict[str, Any]):
    """Validated ``ImageSettings`` for an ``image`` step.

    Note that ``factory.image`` itself switches to quad 1 and the electron beam
    and sets the detector type while checking the detector.
    """
    from pytribeam import factory
    from pytribeam import image
    from pytribeam import types as tbt

    try:
        return factory.image(
            microscope, step, step_name="mcp", yml_format=tbt.YMLFormatVersion.V_1_0
        )
    finally:
        # Validation selects quad 1 and then the requested beam's device, so
        # an ion step leaves the ion beam in quad 1. Put the electron beam back.
        image.set_view(microscope, tbt.ViewQuad.UPPER_LEFT)
        image.set_beam_device(microscope, tbt.Device.ELECTRON_BEAM)


def _prepare(microscope, settings) -> None:
    """Apply validated settings, including a preset resolution."""
    from pytribeam import image
    from pytribeam import types as tbt

    image.set_view(microscope, settings.beam.default_view)
    image.prepare_imaging(settings)
    if isinstance(settings.scan.resolution, tbt.PresetResolution):
        image.beam_scan_resolution(
            settings.beam, microscope, settings.scan.resolution
        )


def _grab(microscope, settings, path: Path) -> None:
    """Acquire one frame with already-applied *settings* and save it to *path*.

    Preset resolutions grab in memory and save with metadata. Others are
    written straight to disk by AutoScript, always at 8 bits.
    """
    from pytribeam import image
    from pytribeam import types as tbt

    if isinstance(settings.scan.resolution, tbt.PresetResolution):
        frame = image.grab_preset_resolution_frame(settings)
        frame.save(str(path))
        return
    warnings.warn(
        f"Non-preset resolution {settings.scan.resolution.value}: AutoScript "
        "writes it straight to disk at 8-bit depth."
    )
    if settings.bit_depth != tbt.ColorDepth.BITS_8:
        warnings.warn(
            f"Requested {settings.bit_depth.value}-bit depth was ignored; "
            "non-preset resolutions are always saved at 8 bits."
        )
    image.grab_custom_resolution_frame(settings, path)


def _stage_position(microscope) -> Optional[Dict[str, Any]]:
    """RAW stage position for the sidecar, or None if it cannot be read."""
    from pytribeam.mcp.capabilities.hardware import _stage_position as read

    try:
        return read(microscope)
    except Exception as exc:  # e.g. the compustage is in
        log.info("stage position not recorded: %r", exc)
        return None


# ---------------------------------------------------------------------------
# Plain logic
# ---------------------------------------------------------------------------
def parse_resolution(resolution: str) -> Tuple[int, int]:
    try:
        width, height = (int(v) for v in resolution.lower().split("x"))
    except (AttributeError, ValueError):
        raise ToolError(
            f"Resolution {resolution!r} is not in the form WIDTHxHEIGHT, e.g. "
            "\"1536x1024\". get_imaging_limits lists the preset resolutions."
        ) from None
    return width, height


def frame_seconds(resolution: str, dwell_us: float) -> float:
    """Estimated time for one frame, in s."""
    width, height = parse_resolution(resolution)
    return width * height * dwell_us * 1e-6 + FRAME_OVERHEAD_S


def check_frame_time(estimate_s: float, config, confirm_long: bool) -> None:
    """Refuse a frame expected to take longer than the configured limits."""
    advice = "Use a shorter dwell_us or a smaller resolution"
    if estimate_s > config.hard_max_frame_s:
        raise ToolError(
            f"This frame would take about {estimate_s:.0f} s, more than this "
            f"server's limit of {config.hard_max_frame_s:.0f} s. {advice}; "
            "only the operator can raise the limit."
        )
    if estimate_s > config.max_frame_s and not confirm_long:
        raise ToolError(
            f"This frame would take about {estimate_s:.0f} s (limit without "
            f"confirmation: {config.max_frame_s:.0f} s). {advice}, or call "
            "again with confirm_long=true if the user wants this frame."
        )


def merge(current: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """The current settings with every non-None override applied."""
    merged = dict(current)
    merged.update({k: v for k, v in overrides.items() if v is not None})
    return merged


def build_step(beam: str, s: Dict[str, Any], auto_cb: bool, bit_depth: int) -> Dict:
    """An ``image`` step in the experiment config format (YML version 1.0).

    ``factory.image`` accepts only Python floats for these values, so numbers
    are cast here, and ints from the agent (``1`` for ``1.0``) are accepted.
    """
    def num(value):
        return None if value is None else float(value)

    return {
        "step_general": {"step_type": "image", "frequency": 1, "step_number": 1},
        "beam": {
            "type": beam,
            "voltage_kv": num(s["voltage_kv"]),
            "voltage_tol_kv": num(s["voltage_kv"]) * 0.05,
            "current_na": num(s["current_na"]),
            "current_tol_na": num(s["current_na"]) * 0.05,
            "hfw_mm": num(s["hfw_mm"]),
            "working_dist_mm": num(s["working_dist_mm"]),
            # beam_angular_correction treats None as "off", so always fill.
            "dynamic_focus": bool(s["dynamic_focus"]) if beam == "electron" else None,
            "tilt_correction": bool(s["tilt_correction"]) if beam == "electron" else None,
        },
        "detector": {
            "type": s["detector"],
            "mode": s["detector_mode"],
            "brightness": None if auto_cb else num(s["brightness"]),
            "contrast": None if auto_cb else num(s["contrast"]),
            "auto_cb": dict(_FULL_FRAME_CB) if auto_cb else {
                "left": None, "top": None, "width": None, "height": None
            },
        },
        "scan": {
            "rotation_deg": num(s["rotation_deg"]),
            "dwell_time_us": num(s["dwell_us"]),
            "resolution": s["resolution"],
        },
        "bit_depth": bit_depth,
    }


def _check_overrides(beam: str, overrides: Dict[str, Any], auto_cb: bool) -> None:
    if auto_cb and (
        overrides.get("brightness") is not None or overrides.get("contrast") is not None
    ):
        raise ToolError(
            "Use either auto_cb or fixed brightness/contrast, not both: "
            "auto_cb chooses brightness and contrast itself."
        )
    if beam == "ion":
        electron_only = [
            k for k in ("dynamic_focus", "tilt_correction") if overrides.get(k) is not None
        ]
        if electron_only:
            raise ToolError(
                f"{' and '.join(electron_only)} apply only to the electron beam."
            )
    for key in ("brightness", "contrast"):
        value = overrides.get(key)
        if value is not None and not 0 < value <= 1:
            raise ToolError(f"{key} must be greater than 0 and at most 1, got {value}.")


def register(add, config, connection) -> None:
    """Register this module's tools."""
    states_dir, images_dir = config.states_dir, config.images_dir
    may_insert = config.max_tier >= INSERT_TIER

    def apply(
        microscope, beam: str, overrides: Dict[str, Any], auto_cb: bool, bit_depth: int
    ) -> Dict[str, Any]:
        """Validate the request, enforce the guardrails, and apply the settings.

        Returns the merged settings, the validated ``ImageSettings``, and
        whether a detector was inserted. Nothing is changed on the microscope
        before validation and the guardrails pass, except that validation
        itself selects views and detectors.
        """
        _check_overrides(beam, overrides, auto_cb)
        if overrides.get("resolution") is not None:
            parse_resolution(overrides["resolution"])

        _select_beam(microscope, beam)
        merged = merge(_current(microscope), overrides)
        if beam == "electron":
            # Off unless set: a camera or the ion beam may report None.
            merged["dynamic_focus"] = bool(merged["dynamic_focus"])
            merged["tilt_correction"] = bool(merged["tilt_correction"])
        if overrides.get("detector_mode") is None:
            choose_mode(microscope, merged)
        if not auto_cb:
            for key in ("brightness", "contrast"):
                if overrides.get(key) is None:
                    clamp_level(merged, key)

        try:
            settings = _validate(microscope, build_step(beam, merged, auto_cb, bit_depth))
        except Exception as exc:
            # factory.image also raises KeyError for a missing setting.
            if not (isinstance(exc, KeyError) or is_agent_error(exc)):
                raise
            message = str(exc).strip("'\"") or type(exc).__name__
            raise ToolError(f"Invalid imaging settings: {message}") from exc

        # Guardrails, checked after validation (which also confirms the
        # detector exists on this beam) and before prepare_imaging acts.
        # Validation leaves quad 1 on the electron beam, so reselect first:
        # the detector check must run on this beam's own device.
        _select_beam(microscope, beam)
        if not _beam_is_on(microscope, beam):
            raise ToolError(
                f"The {beam} beam is off; ask the operator to turn it on. "
                "This server does not turn beams on."
            )
        detector_state = _detector_state(microscope, merged["detector"])
        inserted = False
        if detector_state not in _AT_REST:
            if not may_insert:
                raise ToolError(
                    f"{merged['detector']} is a retractable detector "
                    f"(currently {detector_state}); using it needs tier "
                    f"{INSERT_TIER}. Choose a fixed detector (see "
                    "get_available_detector_types), or ask the user to raise "
                    "the tier."
                )
            inserted = detector_state != _INSERTED

        _prepare(microscope, settings)
        return {"merged": merged, "settings": settings, "detector_inserted": inserted}

    def clamp_level(merged: Dict[str, Any], key: str) -> None:
        """Move a carried-over brightness or contrast into (0, 1].

        pytribeam accepts only 0 < value <= 1, but the microscope can report
        0.0 (the simulator does). Only a value the agent did not ask for is
        moved; an explicit one is checked by ``_check_overrides``.
        """
        value = merged.get(key)
        if value is None or 0 < value <= 1:
            return
        new = min(max(value, LEVEL_MIN), 1.0)
        warnings.warn(
            f"Current {key} of {value} is outside the accepted range "
            f"(0 < {key} <= 1); using {new}. Pass {key}, or auto_cb, to set it."
        )
        merged[key] = new

    def choose_mode(microscope, merged: Dict[str, Any]) -> None:
        """Replace a carried-over detector mode the detector does not offer.

        The microscope can report a mode such as "None" that its own detector
        does not accept (the simulator's TLD2 does), and a new ``detector``
        without a ``detector_mode`` would otherwise inherit the old
        detector's mode. Only a mode the agent did not ask for is replaced;
        an explicit one is left for validation to accept or refuse.
        """
        modes = _detector_modes(microscope, merged["detector"])
        if not modes or merged["detector_mode"] in modes:
            return
        warnings.warn(
            f"Detector mode {merged['detector_mode']!r} is not available on "
            f"{merged['detector']}; using {modes[0]!r} (available: "
            f"{', '.join(modes)}). Pass detector_mode to choose another."
        )
        merged["detector_mode"] = modes[0]

    def set_view(quad: Literal[1, 2, 3, 4]) -> dict:
        """Make one of the four imaging quadrants in the microscope UI active.

        Quads are 1 = upper left, 2 = upper right, 3 = lower left, 4 = lower
        right. By pytribeam convention the electron beam is in quad 1 and the
        ion beam in quad 2. Detector settings in ``get_state`` belong to the
        active quad, so they change when the view changes. Returns the new
        ``active_view`` and ``active_device`` and what changed. Moves nothing.
        """
        before = snapshot(connection, states_dir, f"before set_view({quad})")
        with connection.use() as microscope, agent_errors():
            _set_view(microscope, quad)
            view = _read_view(microscope)
        after = snapshot(connection, states_dir, f"after set_view({quad})")
        return {**view, **acted(before, after)}

    def prepare_imaging(
        beam: Beam,
        voltage_kv: Optional[float] = None,
        current_na: Optional[float] = None,
        hfw_mm: Optional[float] = None,
        working_dist_mm: Optional[float] = None,
        dynamic_focus: Optional[bool] = None,
        tilt_correction: Optional[bool] = None,
        detector: Optional[str] = None,
        detector_mode: Optional[str] = None,
        brightness: Optional[float] = None,
        contrast: Optional[float] = None,
        auto_cb: bool = False,
        rotation_deg: Optional[float] = None,
        dwell_us: Optional[float] = None,
        resolution: Optional[str] = None,
    ) -> dict:
        """Apply imaging settings to a beam without taking an image.

        Every argument left out keeps its current value. Units: kV, nA, mm,
        degrees, microseconds; ``brightness`` and ``contrast`` are 0-1 (above
        0). ``detector`` and ``detector_mode`` are names such as "ETD" and
        "SecondaryElectrons" (see ``get_available_detector_types`` and
        ``get_available_detector_modes``). ``resolution`` is "WIDTHxHEIGHT";
        ``get_imaging_limits`` lists the presets and every valid range.
        ``dynamic_focus`` and ``tilt_correction`` are electron beam only.

        Switches the UI to the beam's quad (electron 1, ion 2). Changing
        voltage or current waits about 5 s each. For the electron beam,
        angular correction is set to Automatic, and a nonzero rotation is
        refused while dynamic focus or tilt correction is on. Ion beam
        currents are discrete: pick one from ``get_imaging_limits``; others
        are matched within 5% or refused.

        ``auto_cb`` runs auto contrast/brightness over the whole frame and
        reports the values it chose; it cannot be combined with
        ``brightness``/``contrast``. It scans the sample, and with the ion
        beam that removes material.

        Refused if the beam is off (this server never turns a beam on), if
        the chamber is not pumped, or if the detector is retractable and
        this session is below tier 2. At tier 2 a retractable detector is
        inserted if needed (``detector_inserted``) and left inserted.

        Returns the settings now applied, ``estimated_frame_s`` for one image
        at these settings, warnings, and what changed (state ids and diff).
        """
        overrides = {
            "voltage_kv": voltage_kv, "current_na": current_na, "hfw_mm": hfw_mm,
            "working_dist_mm": working_dist_mm, "dynamic_focus": dynamic_focus,
            "tilt_correction": tilt_correction, "detector": detector,
            "detector_mode": detector_mode, "brightness": brightness,
            "contrast": contrast, "rotation_deg": rotation_deg,
            "dwell_us": dwell_us, "resolution": resolution,
        }
        before = snapshot(connection, states_dir, f"before prepare_imaging({beam})")
        with connection.use() as microscope, collect_warnings() as found:
            with agent_errors():
                applied = apply(microscope, beam, overrides, auto_cb, 8)
                now = _current(microscope)
        after = snapshot(connection, states_dir, f"after prepare_imaging({beam})")
        return {
            "beam": beam,
            "settings": now,
            "auto_cb": auto_cb,
            "detector_inserted": applied["detector_inserted"],
            "estimated_frame_s": round(frame_seconds(now["resolution"], now["dwell_us"]), 1),
            "warnings": found,
            **acted(before, after),
        }

    def collect_single_image(
        beam: Beam,
        ctx: Context,
        voltage_kv: Optional[float] = None,
        current_na: Optional[float] = None,
        hfw_mm: Optional[float] = None,
        working_dist_mm: Optional[float] = None,
        dynamic_focus: Optional[bool] = None,
        tilt_correction: Optional[bool] = None,
        detector: Optional[str] = None,
        detector_mode: Optional[str] = None,
        brightness: Optional[float] = None,
        contrast: Optional[float] = None,
        auto_cb: bool = False,
        rotation_deg: Optional[float] = None,
        dwell_us: Optional[float] = None,
        resolution: Optional[str] = None,
        bit_depth: Literal[8, 16] = 8,
        description: str = "",
        confirm_long: bool = False,
        preview: bool = True,
        preview_px: int = 768,
    ) -> List[Union[dict, Image]]:
        """Take one image and save it to the project, applying settings first.

        Takes the same settings as ``prepare_imaging``, with the same rules,
        guardrails, and side effects; arguments left out keep their current
        values. The image is saved as ``images/iNNNN.tif`` with a record of
        how it was taken; ``list_images`` and ``view_image`` show it later.

        ION BEAM IMAGING REMOVES MATERIAL: the ion beam sputters every area
        it scans. Use the electron beam unless the ion beam is needed.

        Time: about width x height x dwell_us plus ~1 s. The estimate is
        checked before anything changes. Frames over the server's limit
        (``get_server_info``) are refused unless ``confirm_long`` is true,
        which you should only pass when the user wants that frame; frames
        over the hard limit are always refused. Progress is reported while
        the frame acquires. If the call is cancelled, the frame still
        finishes and is saved; the microscope stays busy until then.

        Non-preset resolutions are always saved at 8 bits. Dynamic focus and
        tilt correction are left as they were set, and reported.

        Returns the image id, settings, ``pixel_size_nm``, timing, ``stats``,
        and what changed; then, if ``preview``, the image itself (long edge
        ``preview_px``, max 1568, never contrast-stretched). Use the picture
        to see what is there, and ``stats`` to judge the settings:
        ``clipped_high_frac`` or ``clipped_low_frac`` above about 0.01 means
        lower or raise brightness/contrast; ``p1``-``p99`` spanning only a
        small part of the range means raise contrast; for focus, compare
        ``sharpness`` between images of the same area at the same settings
        (higher is sharper; it means nothing on its own).
        """
        overrides = {
            "voltage_kv": voltage_kv, "current_na": current_na, "hfw_mm": hfw_mm,
            "working_dist_mm": working_dist_mm, "dynamic_focus": dynamic_focus,
            "tilt_correction": tilt_correction, "detector": detector,
            "detector_mode": detector_mode, "brightness": brightness,
            "contrast": contrast, "rotation_deg": rotation_deg,
            "dwell_us": dwell_us, "resolution": resolution,
        }

        # Check the time before anything changes. Settings left out are read,
        # without switching the view, to complete the estimate.
        planned = {"resolution": resolution, "dwell_us": dwell_us}
        if resolution is None or dwell_us is None:
            with connection.use() as microscope, agent_errors():
                planned = merge(_scan(microscope, beam), planned)
        estimate_s = frame_seconds(planned["resolution"], planned["dwell_us"])
        check_frame_time(estimate_s, config, confirm_long)

        before = snapshot(connection, states_dir, f"before collect_single_image({beam})")
        path = state.next_path(images_dir, "i", ".tif")
        path.parent.mkdir(parents=True, exist_ok=True)

        with connection.use() as microscope, collect_warnings() as found:
            with agent_errors():
                applied = apply(microscope, beam, overrides, auto_cb, bit_depth)
                merged = applied["merged"]
                estimate_s = frame_seconds(merged["resolution"], merged["dwell_us"])
                connection.expect(estimate_s + 5.0)  # + saving and the after-state
                start = time.monotonic()
                try:
                    _acquire(
                        ctx, estimate_s, lambda: _grab(microscope, applied["settings"], path)
                    )
                except BaseException:
                    path.unlink(missing_ok=True)  # never leave a partial image
                    raise
                acquisition_s = time.monotonic() - start
                now = _current(microscope)
                stage = _stage_position(microscope)
        after = snapshot(connection, states_dir, f"after collect_single_image({beam})")

        width, height = parse_resolution(merged["resolution"])
        try:
            image_stats, info, picture = image_content(path, preview_px if preview else 16)
        except Exception as exc:
            # The image is saved and valid as far as AutoScript is concerned;
            # report it rather than losing the record of it.
            log.exception("could not read back %s", path)
            found.append(f"The image was saved but could not be read back for a preview: {exc}")
            image_stats, info, picture, preview = {"bit_depth": bit_depth}, None, None, False
        result = {
            "image_id": path.stem,
            "path": str(path),
            "beam": beam,
            "detector": merged["detector"],
            "detector_mode": merged["detector_mode"],
            "resolution": merged["resolution"],
            "bit_depth": image_stats["bit_depth"],
            "dwell_us": merged["dwell_us"],
            "hfw_mm": merged["hfw_mm"],
            "pixel_size_nm": round(merged["hfw_mm"] * 1e6 / width, 4),
            "brightness": now["brightness"],
            "contrast": now["contrast"],
            "auto_cb": auto_cb,
            "dynamic_focus": now["dynamic_focus"],
            "tilt_correction": now["tilt_correction"],
            "detector_inserted": applied["detector_inserted"],
            "estimated_frame_s": round(estimate_s, 1),
            "acquisition_s": round(acquisition_s, 1),
            "stats": image_stats,
            "description": description,
            **acted(before, after),
        }
        _write_sidecar(path, result, stage)
        result["warnings"] = found
        result["preview"] = info if preview else None
        return [result, picture] if preview else [result]

    add(set_view)
    add(prepare_imaging)
    add(collect_single_image, destructive=True)


def _write_sidecar(path: Path, result: Dict[str, Any], stage) -> None:
    import datetime

    record = {
        "recorded_at": datetime.datetime.now().astimezone().isoformat(timespec="milliseconds"),
        **{k: v for k, v in result.items() if k not in ("changes", "path")},
        "stage_position": stage,
    }
    side = sidecar_path(path)
    tmp = side.with_name(side.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(record, f, sort_keys=False, allow_unicode=True)
    tmp.replace(side)


def _acquire(ctx: Optional[Context], estimate_s: float, grab) -> None:
    """Run *grab* while reporting progress to the client every few seconds.

    The grab runs in a helper thread and this (the tool's worker) thread waits
    on it, because ``anyio.from_thread.run``, which progress needs, only works
    from the worker thread. AutoScript is still called from one thread at a
    time. Progress is best effort and never fails the tool.

    Warnings are recorded per thread, so those raised by *grab* are collected
    in the helper thread and re-issued here, where the tool collects them.
    """
    outcome: Dict[str, Any] = {"warnings": []}

    def run() -> None:
        with collect_warnings() as found:
            try:
                grab()
            except BaseException as exc:  # re-raised in the tool's thread
                outcome["error"] = exc
        outcome["warnings"] = found

    thread = threading.Thread(target=run, name="pytribeam-mcp-grab", daemon=True)
    start = time.monotonic()
    thread.start()
    while True:
        thread.join(timeout=PROGRESS_INTERVAL_S)
        if not thread.is_alive():
            break
        if ctx is not None:
            elapsed = time.monotonic() - start
            try:
                anyio.from_thread.run(
                    ctx.report_progress,
                    round(min(elapsed, estimate_s), 1),
                    round(estimate_s, 1),
                    f"acquiring frame: {elapsed:.0f} of about {estimate_s:.0f} s",
                )
            except Exception as exc:
                log.debug("progress not reported: %r", exc)
    for message in outcome["warnings"]:
        warnings.warn(message)
    if "error" in outcome:
        raise outcome["error"]
