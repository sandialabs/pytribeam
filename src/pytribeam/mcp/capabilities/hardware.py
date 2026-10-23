#!/usr/bin/python3
"""
Hardware Capabilities
=====================

Tier 1 tools that answer "what can this microscope do, and where is it?"
before the agent asks a higher-tier tool to act. None of them moves hardware
or exposes the sample, but most change the UI, which is why they are tier 1:

* ``get_available_*`` find out which detectors and modes work by trying them.
  They switch the active quadrant's device and detector, so the operator sees
  the screen change for a few seconds. pytribeam puts them back afterwards,
  even if probing fails, and raises ``RestoreError`` if it cannot; that sets
  the connection's fault. Results are cached on the connection until
  ``reconnect``, since the hardware does not change during a session. Probing
  the ion device needs tier 5, like everything else on the ion beam.
* The stage tools set the stage's default coordinate system to RAW.
* ``get_imaging_limits`` only reads, and is annotated read-only.

Each pytribeam call sits in a small module-level function (``_detector_types``
and so on) that imports pytribeam itself, so the server starts without
AutoScript and tests can replace the hardware.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional, Tuple

from mcp.server.mcpserver.exceptions import ToolError

from pytribeam.mcp.capabilities._helpers import agent_errors, collect_warnings

TIER = 1
ION_TIER = 5  # probing the ion device needs the ion beam's tier

log = logging.getLogger("pytribeam.mcp.hardware")

Beam = Literal["electron", "ion"]

SIGNIFICANT_FIGURES = 12  # matches pytribeam.mcp.state.capture


def _round(value: float) -> float:
    """Strip binary noise from unit conversions (0.8999999999 -> 0.9)."""
    return float(f"{value:.{SIGNIFICANT_FIGURES}g}")


def _limit(limit) -> Dict[str, float]:
    return {"min": _round(limit.min), "max": _round(limit.max)}


# ---------------------------------------------------------------------------
# pytribeam calls. Tests replace these.
# ---------------------------------------------------------------------------
def _beam(beam: str):
    """The pytribeam beam object for "electron" or "ion"."""
    from pytribeam import factory
    from pytribeam import types as tbt

    return factory.beam_object_type(tbt.BeamType(beam))(settings=tbt.BeamSettings())


def _device(beam: str):
    """The imaging device for a beam."""
    return _beam(beam).device


def _detector_types(microscope, beam: str) -> List[str]:
    from pytribeam import image

    found = image.get_available_detector_types(microscope, _device(beam))
    return [dt.value for dt in found]


def _detector_modes(microscope, beam: str, detector: str) -> Optional[List[str]]:
    """Modes for *detector*, or None if it does not work on this beam.

    Raises ``ValueError`` if *detector* is not a detector type at all.
    """
    from pytribeam import image
    from pytribeam import types as tbt

    modes = image.get_available_detector_modes(
        microscope, _device(beam), tbt.DetectorType(detector)
    )
    return None if modes is None else [dm.value for dm in modes]


def _current_detector(microscope, beam: str) -> str:
    """The detector type selected on the beam's device. Selecting the device
    to read it is undone by pytribeam's ``detector_settings_restored``."""
    from pytribeam import image

    with image.detector_settings_restored(microscope, _device(beam)) as current:
        return current.value


def _insertable_detectors(microscope) -> List[Tuple[str, str]]:
    from pytribeam import image

    found = image.get_available_insertable_detector_states(microscope)
    return [(dt.value, state.value) for dt, state in found]


def _imaging_limits(microscope, beam: str) -> Dict[str, Any]:
    from pytribeam import factory
    from pytribeam import types as tbt
    from pytribeam import utilities as ut
    from pytribeam.constants import Conversions

    beam_obj = _beam(beam)
    selected = ut.beam_type(beam_obj, microscope)
    beam_limits = factory.beam_limits(selected, beam_obj.type)
    scan_limits = factory.scan_limits(selected)

    result = {
        "voltage_kv": _limit(beam_limits.voltage_kv),
        "current_na": _limit(beam_limits.current_na),
        "hfw_mm": _limit(beam_limits.hfw_mm),
        "working_dist_mm": _limit(beam_limits.working_distance_mm),
        "rotation_deg": _limit(scan_limits.rotation_deg),
        "dwell_us": _limit(scan_limits.dwell_us),
        "preset_resolutions": [
            f"{res.width}x{res.height}" for res in tbt.PresetResolution
        ],
    }
    if beam == "ion":
        result["available_currents_na"] = sorted(
            _round(amps * Conversions.A_TO_NA)
            for amps in selected.beam_current.available_values
        )
    return result


def _stage_position(microscope) -> Dict[str, Any]:
    from pytribeam import factory

    pos = factory.active_stage_position_settings(microscope)
    return {
        "x_mm": _round(pos.x_mm),
        "y_mm": _round(pos.y_mm),
        "z_mm": _round(pos.z_mm),
        "r_deg": _round(pos.r_deg),
        "t_deg": _round(pos.t_deg),
        "coordinate_system": str(pos.coordinate_system.value),
    }


def _stage_limits(microscope) -> Dict[str, Dict[str, float]]:
    from pytribeam import factory

    limits = factory.stage_limits(microscope)
    return {axis: _limit(getattr(limits, axis)) for axis in limits._fields}


# ---------------------------------------------------------------------------
# Restoring the operator's view
# ---------------------------------------------------------------------------
def _stage_errors(exc: Exception) -> None:
    """Raise a readable ToolError for a stage read refused by the microscope,
    e.g. "Bulk stage is not an active stage" while the compustage is in."""
    if type(exc).__name__ == "ApplicationServerException":
        raise ToolError(f"The microscope refused to read the stage: {exc}") from exc


def register(add, config, connection) -> None:
    """Register this module's tools."""
    cache = connection.cache

    def check_beam(beam: str) -> None:
        """Refuse probing the ion device below its tier, before anything changes."""
        if beam == "ion" and config.max_tier < ION_TIER:
            raise ToolError(
                "Probing the ion beam selects the ion device and its detectors; "
                f"anything on the ion beam needs tier {ION_TIER}. Ask the user "
                "to raise the tier. get_imaging_limits(beam=\"ion\") works at "
                "this tier: it only reads."
            )

    def restore_failed(exc: Exception) -> ToolError:
        """pytribeam could not put the UI back after probing: fail closed."""
        connection.set_fault(f"after probing detectors: {exc}")
        return ToolError(
            f"Probing changed the microscope UI and could not restore it ({exc}). "
            "Ask the operator to check the active quadrant, then call clear_fault."
        )

    def probe(key, run) -> Dict[str, Any]:
        """Run *run* once per connection, returning its result with warnings.

        The pytribeam probes restore the device and detector themselves, even
        on failure, and raise ``RestoreError`` if they cannot; that sets the
        fault, and nothing is cached.
        """
        if key in cache:
            return {**cache[key], "cached": True, "warnings": []}
        with connection.use() as microscope, collect_warnings() as found:
            with agent_errors():
                try:
                    result = run(microscope)
                except Exception as exc:
                    if type(exc).__name__ == "RestoreError":
                        raise restore_failed(exc) from exc
                    raise
        cache[key] = result
        return {**result, "cached": False, "warnings": found}

    def get_available_detector_types(beam: Beam = "electron") -> dict:
        """List the detector types that work with a beam, e.g. ["ETD", "TLD"].

        Not a passive read: it switches the active quadrant to the beam's
        device and tries every detector type in turn, so the operator will
        see the screen change for a few seconds. The device and detector are
        restored afterwards, even on failure; if they cannot be, the call
        fails and state-changing tools are blocked until the operator has
        checked the microscope and called ``clear_fault``. The result is
        cached until ``reconnect``, so later calls are instant and touch
        nothing (``cached: true``). Probing the ion beam needs tier 5.
        """
        check_beam(beam)

        def run(microscope):
            return {"beam": beam, "detector_types": _detector_types(microscope, beam)}

        return probe(("detector_types", beam), run)

    def get_available_detector_modes(
        beam: Beam = "electron", detector: Optional[str] = None
    ) -> dict:
        """List the modes of one detector on a beam, e.g. "SecondaryElectrons".

        ``detector`` is a detector type as returned by
        ``get_available_detector_types``, such as "ETD". If omitted, the
        detector currently selected for that beam is used, and the result
        says which one it was. A detector that does not work with the beam
        is refused, listing the ones that do.

        Not a passive read: it switches the active quadrant to the beam's
        device and detector, so the operator will see the screen change
        briefly. Everything is restored afterwards, even on failure (see
        ``get_available_detector_types``). Results
        are cached per beam and detector until ``reconnect``. Probing the ion
        beam needs tier 5.
        """
        check_beam(beam)
        key = ("detector_modes", beam, detector)
        if detector is not None and key in cache:
            return {**cache[key], "cached": True, "warnings": []}

        invalid = False
        with connection.use() as microscope, collect_warnings() as found:
            with agent_errors():
                try:
                    detector = detector or _current_detector(microscope, beam)
                    modes = _detector_modes(microscope, beam, detector)
                except ValueError:
                    modes, invalid = None, True
                except Exception as exc:
                    if type(exc).__name__ == "RestoreError":
                        raise restore_failed(exc) from exc
                    raise
            if modes is None:
                valid = get_available_detector_types(beam)["detector_types"]
                reason = "is not a detector type" if invalid else "does not work"
                raise ToolError(
                    f"Detector {detector!r} {reason} with the {beam} beam on this "
                    f"microscope. Available detector types: {', '.join(valid)}."
                )

        result = {"beam": beam, "detector": detector, "modes": modes}
        cache[("detector_modes", beam, detector)] = result
        return {**result, "cached": False, "warnings": found}

    def get_available_insertable_detectors() -> dict:
        """List the retractable detectors and the state of each.

        States are e.g. "Retracted" or "Inserted". Insertable detectors are
        only reachable from the electron beam, so this always probes on the
        electron beam's device, whatever beam the active quadrant shows.

        Not a passive read: it switches the active quadrant's device and
        tries every detector type in turn, so the operator will see the
        screen change for a few seconds. Everything is restored afterwards,
        even on failure (see ``get_available_detector_types``). The result is
        cached until ``reconnect``, so a cached state may be stale if the
        operator has since inserted or retracted a detector; call
        ``reconnect`` first if that matters.
        """

        def run(microscope):
            found = _insertable_detectors(microscope)
            return {
                "detectors": [
                    {"detector": detector, "state": state} for detector, state in found
                ]
            }

        return probe(("insertable_detectors",), run)

    def get_imaging_limits(beam: Beam = "electron") -> dict:
        """Report the valid range of each imaging setting for a beam.

        Ranges are ``{"min", "max"}`` in the units of the imaging tools'
        arguments: ``voltage_kv``, ``current_na``, ``hfw_mm``,
        ``working_dist_mm``, ``rotation_deg``, ``dwell_us``.
        ``preset_resolutions`` are "WIDTHxHEIGHT" strings. Ion beam currents
        are discrete, so for the ion beam ``available_currents_na`` lists
        every allowed value; pick one of those. The HFW range depends on the
        current voltage and working distance. Only reads; changes nothing.
        """
        with connection.use() as microscope, agent_errors():
            return {"beam": beam, **_imaging_limits(microscope, beam)}

    def get_stage_position() -> dict:
        """Report the stage position in the RAW coordinate system, in mm and deg.

        RAW is the coordinate system ``move_to_position`` uses, so these
        values can be passed to it directly. ``get_state`` reports the stage
        in meters and radians in whatever coordinate system is current
        (often "Specimen"); do not feed those values into a move.

        Side effect: sets the stage's default coordinate system to RAW, which
        later ``get_state`` captures will show. Does not move the stage.
        Refused while the bulk stage is not active (e.g. the compustage is in).
        """
        with connection.use() as microscope, agent_errors():
            try:
                return _stage_position(microscope)
            except Exception as exc:
                _stage_errors(exc)
                raise

    def get_stage_limits() -> dict:
        """Report the travel limits of each stage axis in the RAW coordinate system.

        ``x_mm``, ``y_mm``, ``z_mm`` in mm and ``r_deg``, ``t_deg`` in
        degrees, each as ``{"min", "max"}``. These are the limits
        ``move_to_position`` enforces, in the units ``get_stage_position``
        reports. Side effect: sets the stage's default coordinate system to
        RAW. Does not move the stage.
        """
        with connection.use() as microscope, agent_errors():
            try:
                return _stage_limits(microscope)
            except Exception as exc:
                _stage_errors(exc)
                raise

    # Not read-only: the probes switch the UI, and the stage tools set the
    # coordinate system. None moves hardware, so none is destructive.
    add(get_available_detector_types)
    add(get_available_detector_modes)
    add(get_available_insertable_detectors)
    add(get_imaging_limits, read_only=True)
    add(get_stage_position)
    add(get_stage_limits)
