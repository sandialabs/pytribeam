#!/usr/bin/python3
"""
Imaging Capabilities
====================

Tier 2 tools that change beam, detector, and scan settings and take images.
Every one of them scans the sample (an image, or auto contrast/brightness),
so all are annotated destructive.

Higher tiers add no tools; they lift guardrails on these:

* tier 3 allows retractable detectors, which are inserted if needed;
* tier 5 allows the ion beam, which removes material from whatever it scans.

This module reads ``config.max_tier`` to decide, the one exception to "one
module, one tier", because the alternative is three copies of every imaging
tool.

Settings are validated by building an ``image`` step in the experiment config
format and passing it to ``factory.image``, so the agent gets the same range
and schema checks as an experiment file. Every tool snapshots the microscope
state before and after it acts and returns what changed.

Imaging itself is pytribeam's: ``collect_single_image`` calls
``image.collect_single_image``, as the experiment workflow does, and
``prepare_imaging`` calls ``image.prepare_imaging``. This module checks the
request first (tier, scan time, guardrails, validation) and records the result.

Each pytribeam call sits in a small module-level function (``_validate``,
``_collect`` and so on) that imports pytribeam itself, so the server starts
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

from pytribeam.mcp import audit, state
from pytribeam.mcp.capabilities._helpers import (
    acted,
    agent_errors,
    collect_warnings,
    is_agent_error,
    snapshot,
)
from pytribeam.mcp.capabilities.records import image_content, sidecar_path
from pytribeam.mcp.capabilities.hardware import _beam  # one definition

TIER = 2
INSERT_TIER = 3  # lowest tier that may use (and insert) a retractable detector
ION_TIER = 5  # lowest tier that may use the ion beam

log = logging.getLogger("pytribeam.mcp.imaging")

Beam = Literal["electron", "ion"]

# Fixed time per frame on top of pixels x dwell: flyback, settling, transfer.
# Calibrate on the simulator against the acquisition_s each image reports.
FRAME_OVERHEAD_S = 1.0
PROGRESS_INTERVAL_S = 5.0

# collect_single_image applies the settings before it grabs: voltage and
# current changes wait about 5 s each, and auto contrast/brightness is a scan of
# its own. Added to the frame estimate for progress and the time limit.
SETTINGS_ALLOWANCE_S = 30.0

# A grab still running after estimate + max(60 s, 50 % of estimate) is
# abandoned and the fault set: see grab_limit_s().
GRAB_GRACE_MIN_S = 60.0
GRAB_GRACE_FRACTION = 0.5

# Retractable detector states in which pytribeam will not move it.
_AT_REST = ("Stationary",)
_INSERTED = "Inserted"
_FULL_FRAME_CB = {"left": 0.0, "top": 0.0, "width": 1.0, "height": 1.0}



# ---------------------------------------------------------------------------
# pytribeam calls. Tests replace these.
# ---------------------------------------------------------------------------
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


def _beam_is_on(microscope, beam: str) -> bool:
    from pytribeam import utilities as ut

    return bool(ut.beam_type(_beam(beam), microscope).is_on)


def _detector_state(microscope, detector: str) -> str:
    """The detector's ``RetractableDeviceState`` value, e.g. "Stationary".

    Leaves *detector* as the active detector type on the active device.
    """
    from pytribeam import insertable_devices as devices
    from pytribeam import types as tbt

    return devices.detector_state(microscope, tbt.DetectorType(detector)).value


class RestoreFailed(Exception):
    """A temporary UI change could not be undone; the caller sets the fault."""


def _validate(microscope, step: Dict[str, Any]):
    """Validated ``ImageSettings`` for an ``image`` step.

    Note that ``factory.image`` itself switches to quad 1 and the electron beam
    and sets the detector type while checking the detector.
    """
    from pytribeam import factory
    from pytribeam import image
    from pytribeam import types as tbt

    try:
        settings = factory.image(
            microscope, step, step_name="mcp", yml_format=tbt.YMLFormatVersion.V_1_0
        )
        # factory.image checks bit_depth but passes the int through unchanged.
        # AutoScript's GrabFrameSettings needs the ColorDepth member (a plain
        # 16 gave an 8-bit image on the simulator), and pytribeam reads
        # bit_depth.value, so convert it here.
        return settings._replace(bit_depth=tbt.ColorDepth(settings.bit_depth))
    finally:
        # Validation selects quad 1 and then the requested beam's device, so
        # an ion step leaves the ion beam in quad 1. Put the electron beam back.
        try:
            image.set_view(microscope, tbt.ViewQuad.UPPER_LEFT)
            image.set_beam_device(microscope, tbt.Device.ELECTRON_BEAM)
        except Exception as exc:
            raise RestoreFailed(
                f"after validating settings, could not put the electron beam "
                f"back in quad 1 ({exc})"
            ) from exc


def _prepare(microscope, settings) -> None:
    """Apply validated settings without imaging: ``image.prepare_imaging``.

    ``prepare_imaging`` applies every setting except the scan resolution,
    which pytribeam otherwise sets only when it grabs a frame. A preset
    resolution is applied here with pytribeam's ``beam_scan_resolution``, so
    the tool leaves the microscope with all the settings it reports.
    """
    from pytribeam import image
    from pytribeam import types as tbt

    image.set_view(microscope, settings.beam.default_view)
    image.prepare_imaging(settings)
    if isinstance(settings.scan.resolution, tbt.PresetResolution):
        image.beam_scan_resolution(
            settings.beam, microscope, settings.scan.resolution
        )


def _collect(settings, path: Path) -> None:
    """``image.collect_single_image``: set the view, apply the settings (and
    run auto contrast/brightness if requested), grab, and save to *path*."""
    from pytribeam import image

    image.collect_single_image(save_path=path, img_settings=settings)


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
    """``factory.string_to_res``, with its error rewritten for the agent."""
    from pytribeam import factory

    try:
        res = factory.string_to_res(resolution)
    except (AttributeError, ValueError):
        raise ToolError(
            f"Resolution {resolution!r} is not in the form WIDTHxHEIGHT, e.g. "
            "\"1536x1024\". get_imaging_limits lists the preset resolutions."
        ) from None
    return res.width, res.height


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


def build_step(
    beam: str, s: Dict[str, Any], auto_cb: bool, bit_depth: int, explicit=frozenset()
) -> Dict:
    """An ``image`` step in the experiment config format (YML version 1.0).

    ``factory.image`` accepts only Python floats for these values, so numbers
    are cast here, and ints from the agent (``1`` for ``1.0``) are accepted.

    Settings carried over from the microscope are left out where they do not
    apply (brightness and contrast with ``auto_cb``; angular correction on
    the ion beam). Settings the agent asked for (*explicit*) are always passed
    on, so pytribeam's own validation refuses a conflicting request.
    """
    def num(value):
        return None if value is None else float(value)

    def given(key, carried):
        return s[key] if key in explicit else carried

    on_ion = beam != "electron"

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
            "dynamic_focus": given("dynamic_focus", None) if on_ion else bool(s["dynamic_focus"]),
            "tilt_correction": given("tilt_correction", None) if on_ion else bool(s["tilt_correction"]),
        },
        "detector": {
            "type": s["detector"],
            "mode": s["detector_mode"],
            "brightness": num(given("brightness", None) if auto_cb else s["brightness"]),
            "contrast": num(given("contrast", None) if auto_cb else s["contrast"]),
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


def register(add, config, connection) -> None:
    """Register this module's tools."""
    states_dir, images_dir = config.states_dir, config.images_dir
    may_insert = config.max_tier >= INSERT_TIER
    may_use_ion = config.max_tier >= ION_TIER

    def abandon_grab(path: Path):
        """Hand the microscope to an abandoned grab until it ends, then delete
        whatever it wrote. Returns what the grab thread runs when it ends."""
        release = connection.hand_off(
            "an abandoned image acquisition that may still be running"
        )

        def on_late_finish() -> None:
            path.unlink(missing_ok=True)
            release()

        return on_late_finish

    def check_beam(beam: str) -> None:
        """Refuse the ion beam below its tier, before anything changes."""
        if beam == "ion" and not may_use_ion:
            raise ToolError(
                "The ion beam removes material from every area it scans; using "
                f"it needs tier {ION_TIER}. Use the electron beam, or ask the "
                "user to raise the tier."
            )

    def plan(
        microscope,
        beam: str,
        overrides: Dict[str, Any],
        auto_cb: bool,
        bit_depth: int,
        scans: bool,
        confirm_long: bool,
    ) -> Dict[str, Any]:
        """Check a request completely without applying any setting.

        Selects the beam, merges the agent's values into its current settings,
        checks the scan time if the call will scan (*scans*), validates with
        ``factory.image``, and enforces the guardrails. Returns the merged
        settings, the validated ``ImageSettings``, the scan estimate, and
        whether a detector will be inserted. The caller then hands the
        settings to pytribeam. Selecting the beam and validating change the
        view and detector selection, but no setting is applied before every
        check has passed.
        """
        if overrides.get("resolution") is not None:
            parse_resolution(overrides["resolution"])

        _select_beam(microscope, beam)
        merged = merge(_current(microscope), overrides)
        if beam == "electron":
            # Off unless set: a camera or the ion beam may report None.
            merged["dynamic_focus"] = bool(merged["dynamic_focus"])
            merged["tilt_correction"] = bool(merged["tilt_correction"])

        # Every scan is time-limited (an image, or auto contrast/brightness),
        # using the beam's own current settings for anything not given.
        estimate_s = frame_seconds(merged["resolution"], merged["dwell_us"])
        if scans:
            check_frame_time(estimate_s, config, confirm_long)

        try:
            explicit = {key for key, value in overrides.items() if value is not None}
            step = build_step(beam, merged, auto_cb, bit_depth, explicit)
            settings = _validate(microscope, step)
        except RestoreFailed as exc:
            connection.set_fault(str(exc))
            raise ToolError(
                f"Stopped: {exc}. The microscope UI may not be as expected; ask "
                "the operator to check it, then call clear_fault."
            ) from exc
        except Exception as exc:
            # factory.image also raises KeyError for a missing setting.
            if not (isinstance(exc, KeyError) or is_agent_error(exc)):
                raise
            # KeyError's str() wraps its message in quotes; use the message itself.
            message = (exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc))
            message = str(message) or type(exc).__name__
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

        return {
            "merged": merged,
            "settings": settings,
            "estimate_s": estimate_s,
            "detector_inserted": inserted,
        }

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
        confirm_long: bool = False,
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
        ``brightness``/``contrast``. It scans the sample, so it is checked
        against the same time limits as an image (see
        ``collect_single_image``; ``confirm_long`` applies), and with the ion
        beam it removes material.

        Refused if the beam is off (this server never turns a beam on), if
        the chamber is not pumped, if the detector is retractable and this
        session is below tier 3, or for the ion beam below tier 5. At tier 3
        a retractable detector is inserted if needed (``detector_inserted``)
        and left inserted.

        Returns the settings now applied, ``estimated_frame_s`` for one image
        at these settings, warnings, and what changed (state ids and diff).
        """
        check_beam(beam)
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
                # auto_cb is the one scan prepare_imaging starts.
                applied = plan(
                    microscope, beam, overrides, auto_cb, 8, scans=auto_cb, confirm_long=confirm_long
                )
                _prepare(microscope, applied["settings"])
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
        it scans, so it needs tier 5. Use the electron beam unless the ion
        beam is needed.

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
        check_beam(beam)
        overrides = {
            "voltage_kv": voltage_kv, "current_na": current_na, "hfw_mm": hfw_mm,
            "working_dist_mm": working_dist_mm, "dynamic_focus": dynamic_focus,
            "tilt_correction": tilt_correction, "detector": detector,
            "detector_mode": detector_mode, "brightness": brightness,
            "contrast": contrast, "rotation_deg": rotation_deg,
            "dwell_us": dwell_us, "resolution": resolution,
        }

        before = snapshot(connection, states_dir, f"before collect_single_image({beam})")
        path = state.next_path(images_dir, "i", ".tif")
        path.parent.mkdir(parents=True, exist_ok=True)

        with connection.use() as microscope, collect_warnings() as found:
            with agent_errors():
                applied = plan(
                    microscope, beam, overrides, auto_cb, bit_depth, scans=True, confirm_long=confirm_long
                )
                merged, estimate_s = applied["merged"], applied["estimate_s"]
                # pytribeam applies the settings, then grabs; allow for both.
                connection.expect(estimate_s + SETTINGS_ALLOWANCE_S)
                start = time.monotonic()
                try:
                    _acquire(
                        ctx,
                        estimate_s + SETTINGS_ALLOWANCE_S,
                        lambda: _collect(applied["settings"], path),
                        abandon=lambda: abandon_grab(path),
                    )
                except AcquisitionTimeout as exc:
                    path.unlink(missing_ok=True)
                    connection.set_fault(f"an image acquisition did not finish: {exc}")
                    raise ToolError(
                        f"Stopped waiting: {exc}. The microscope may still be "
                        "scanning, so its state is unknown. No image was saved. "
                        "Ask the operator to check the microscope, then call "
                        "clear_fault."
                    ) from exc
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
        saved_bits = image_stats["bit_depth"]
        # pytribeam already warns that a non-preset resolution is saved at 8
        # bits; only report a mismatch it did not explain.
        explained = any("non-preset resolution" in w.lower() for w in found)
        if saved_bits != bit_depth and not explained:
            found.append(
                f"Requested {bit_depth}-bit, but the saved image is {saved_bits}-bit."
            )
        result = {
            "image_id": path.stem,
            "path": str(path),
            "beam": beam,
            "detector": merged["detector"],
            "detector_mode": merged["detector_mode"],
            "resolution": merged["resolution"],
            "bit_depth": saved_bits,
            "requested_bit_depth": bit_depth,
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

    # Both scan the sample (auto_cb, or the image itself).
    add(prepare_imaging, destructive=True)
    add(collect_single_image, destructive=True)


def _write_sidecar(path: Path, result: Dict[str, Any], stage) -> None:
    import datetime

    record = {
        "recorded_at": datetime.datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "op_id": audit.current_op_id(),
        **{k: v for k, v in result.items() if k not in ("changes", "path")},
        "stage_position": stage,
    }
    side = sidecar_path(path)
    tmp = side.with_name(side.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(record, f, sort_keys=False, allow_unicode=True)
    tmp.replace(side)


class AcquisitionTimeout(Exception):
    """A grab ran past its time limit and was abandoned; the caller sets the
    fault, since the microscope may still be scanning."""


def grab_limit_s(estimate_s: float) -> float:
    """How long a grab may run before it is abandoned: the estimate, plus
    the larger of 60 s and half the estimate."""
    return estimate_s + max(GRAB_GRACE_MIN_S, GRAB_GRACE_FRACTION * estimate_s)


def _acquire(
    ctx: Optional[Context], estimate_s: float, grab, abandon=lambda: None
) -> None:
    """Run *grab* while reporting progress to the client every few seconds.

    The grab runs in a helper thread and this (the tool's worker) thread waits
    on it, because ``anyio.from_thread.run``, which progress needs, only works
    from the worker thread. AutoScript is still called from one thread at a
    time. Progress is best effort and never fails the tool.

    Warnings are recorded per thread, so those raised by *grab* are collected
    in the helper thread and re-issued here, where the tool collects them.

    If the grab is still running after :func:`grab_limit_s`, raise
    :class:`AcquisitionTimeout` and stop waiting. Python cannot kill the
    thread; it is left to finish or hang on its own. ``abandon()`` is called
    now and returns a function the thread runs if it ever finishes, so a late
    result is discarded and anything the caller still holds (the microscope)
    is released only then.
    """
    outcome: Dict[str, Any] = {"warnings": []}
    lock = threading.Lock()  # orders "finished" against "abandoned"
    state = {"finished": False, "on_late_finish": None}

    def run() -> None:
        with collect_warnings() as found:
            try:
                grab()
            except BaseException as exc:  # re-raised in the tool's thread
                outcome["error"] = exc
        outcome["warnings"] = found
        with lock:
            state["finished"] = True
            late = state["on_late_finish"]
        if late is not None:
            try:
                late()
            except Exception as exc:
                log.warning("cleaning up an abandoned grab failed: %r", exc)

    thread = threading.Thread(target=run, name="pytribeam-mcp-grab", daemon=True)
    start = time.monotonic()
    deadline = start + grab_limit_s(estimate_s)
    thread.start()
    while True:
        thread.join(timeout=max(0.0, min(PROGRESS_INTERVAL_S, deadline - time.monotonic())))
        if not thread.is_alive():
            break
        if time.monotonic() >= deadline:
            with lock:
                if state["finished"]:  # finished just now: use the result
                    break
                state["on_late_finish"] = abandon()
            raise AcquisitionTimeout(
                f"the frame was expected to take about {estimate_s:.1f} s but had "
                f"not finished after {time.monotonic() - start:.1f} s"
            )
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
