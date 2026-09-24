#!/usr/bin/python3
"""FIB-only serial sectioning workflow with fiducial-based alignment.

This module is the production-oriented version of the proof-of-concept script
that demonstrated iterative ion-beam-shift correction using template matching.
It keeps the same core behavior that worked experimentally:

1. acquire an ion/FIB alignment image;
2. match a saved reference fiducial patch;
3. compare the match location to the baseline/reference match location;
4. convert the pixel residual to a physical distance;
5. apply a beam-shift correction;
6. iterate until the apparent fiducial offset is within a pixel threshold.

The goal is to turn that script-like logic into small functions that can be
called from a real experiment loop and extended later with optional stage moves,
pattern-placement updates, SEM alignment, and richer HDF5 logging.

Design notes
------------
- This file should remain a high-level FIB-only serial-sectioning workflow.
- Template matching/image registration lives in :mod:`pytribeam.fibss_alignment`.
- Beam shift low-level helpers live in :mod:`pytribeam.image`.
- Physical stage movement is intentionally separated from measurement and beam
  correction. The stage move path is still a TODO placeholder here because it
  needs sign/coordinate calibration.
- Settings are represented with ``NamedTuple`` objects to match the rest of the
  codebase and preserve immutability for hardware control.
- Python 3.8 compatible; no new dependencies beyond those already available.

A useful way to explain the control loop is:

``measure -> decide -> correct -> verify``

Measurement is template matching. Decision chooses beam shift vs future stage
move. Correction applies the selected hardware action. Verification is another
alignment image and another template match.
"""

__all__ = [
    "FIBSSControlSettings",
    "IterativeAlignmentResult",
    "step_alignment_enabled",
    "alignment_settings_for_step",
    "image_settings_for_alignment_step",
    "step_alignment_policy",
    "compute_image_pixel_size_m",
    "acquire_alignment_image",
    "apply_beam_shift_delta",
    "stage_move_required",
    "move_stage_for_alignment_placeholder",
    "iterate_beam_shift_alignment",
    "pattern_shift_from_image_shift_m",
    "perform_step_alignment",
    "perform_fibss_operation",
    "perform_fibss_step",
    "run_fib_ss_experiment_cli",
]


import math
from pathlib import Path
from typing import NamedTuple, Optional, Tuple

import pytribeam.constants as cs
import pytribeam.factory as factory
import pytribeam.fib as fib
import pytribeam.image as img
import pytribeam.insertable_devices as devices
import pytribeam.stage as stage
import pytribeam.types as tbt
import pytribeam.utilities as ut
import pytribeam.log as log
from pytribeam.alignment import (
    ShiftDistanceM,
    ShiftPx,
    TemplateMatchMeasurement,
    TemplateMatchSettings,
    measure_template_offset,
    template_match,
)
from pytribeam.image import read_beam_shift, set_beam_shift
from pytribeam.workflow import perform_operation, setup_experiment


class FIBSSControlSettings(NamedTuple):
    """Experiment-level defaults for FIB-only serial sectioning alignment.

    These settings define the default behavior for alignment-enabled steps. A
    step may override some or all of these values later through an optional
    per-step alignment settings field. This lets simple experiments use one
    consistent alignment policy, while advanced experiments can tune individual
    alignment steps.

    Attributes
    ----------
    stage_move_threshold_um
        Residual offset magnitude above which stage recentering should be used
        instead of continuing to correct only with beam shift. This should be a
        practical stage-scale value, not a nanometer-scale value.
    template_match_threshold
        Minimum acceptable normalized template-match score. Below this score,
        alignment is considered unreliable.
    max_alignment_iterations
        Maximum number of acquire-match-correct iterations.
    max_pixel_shift
        Residual pixel magnitude considered converged.
    reference_image_path
        Optional experiment-level reference image path. If absent, defaults to
        ``exp_dir/templates/fib_image.tif``.
    reference_patch_path
        Optional experiment-level reference patch/template path. If absent,
        defaults to ``exp_dir/templates/fib_template.tif``.
    save_debug_images
        Save template match overlays for debugging/audit trail.
    """

    stage_move_threshold_um: float = 50.0
    template_match_threshold: float = 0.85
    max_alignment_iterations: int = 3
    max_pixel_shift: float = 2.0
    reference_image_path: Optional[Path] = None
    reference_patch_path: Optional[Path] = None
    save_debug_images: bool = True
    fib_pattern_advance_axis: str = "y"
    fib_pattern_advance_sign: float = 1.0
    fib_pattern_advance_offset_slices: int = 0  # first slice at original pattern center


class IterativeAlignmentResult(NamedTuple):
    """Result from iterative beam-shift alignment for one slice/step."""

    converged: bool
    iterations: int
    final_shift_px: ShiftPx
    final_shift_m: ShiftDistanceM
    final_score: float
    image_paths: Tuple[Path, ...]
    scores: Tuple[float, ...]
    shifts_px: Tuple[ShiftPx, ...]
    measurements: Tuple[TemplateMatchMeasurement, ...]


def _coalesce_none(value, default):
    """Return default when value is None."""

    return default if value is None else value


def _get_optional_attr(obj, name: str, default=None):
    """Return optional attribute from possibly-extended NamedTuple objects.

    During development, some branches may add optional fields such as
    ``template_matching`` or ``alignment_settings`` to ``tbt.Step``. Using this
    helper keeps this workflow tolerant of both old and new settings objects.
    """

    return getattr(obj, name, default)


def step_alignment_enabled(step: tbt.Step) -> bool:
    """Return whether a step should run template-matching alignment.

    Alignment is controlled only by ``step.alignment_settings.enabled``. This is
    more explicit than checking ad hoc flags such as ``step.template_matching``
    and gives us room to add different alignment modes later without changing
    the workflow loop.

    Factory validation should ensure that any step with enabled alignment also
    has usable image settings plus a reference image/patch configuration.
    """

    alignment_settings = _get_optional_attr(step, "alignment_settings", None)
    return bool(_get_optional_attr(alignment_settings, "enabled", False))


def alignment_settings_for_step(
    step: tbt.Step,
    general_settings: tbt.GeneralSettings,
    defaults: FIBSSControlSettings,
) -> TemplateMatchSettings:
    """Build template-match settings for a step using defaults plus overrides.

    This is the bridge between workflow-level defaults and optional per-step
    settings. It intentionally accepts several likely field names so that the
    implementation can evolve without rewriting the control loop.

    TODO: once the final ``StepAlignmentSettings`` type is decided, simplify
    this function to use that exact schema.
    """

    step_alignment = _get_optional_attr(step, "alignment_settings", None)

    if step_alignment is None:
        raise ValueError(
            f"Step '{step.name}' requested alignment settings, but no "
            "step.alignment_settings object was found."
        )

    exp_dir = Path(general_settings.exp_dir)

    reference_image_path = (
        defaults.reference_image_path or exp_dir / "templates" / "fib_image.tif"
    )
    reference_patch_path = (
        defaults.reference_patch_path or exp_dir / "templates" / "fib_template.tif"
    )

    if step_alignment is not None:
        reference_image_path = _get_optional_attr(
            step_alignment, "reference_image_path", reference_image_path
        )
        reference_patch_path = _get_optional_attr(
            step_alignment, "reference_patch_path", reference_patch_path
        )

    return TemplateMatchSettings(
        reference_image_path=reference_image_path,
        reference_patch_path=reference_patch_path,
        match_threshold=_coalesce_none(
            _get_optional_attr(step_alignment, "match_threshold", None),
            defaults.template_match_threshold,
        ),
        max_pixel_shift=_coalesce_none(
            _get_optional_attr(step_alignment, "max_pixel_shift", None),
            defaults.max_pixel_shift,
        ),
        max_iterations=_coalesce_none(
            _get_optional_attr(step_alignment, "max_iterations", None),
            defaults.max_alignment_iterations,
        ),
        debug_dir=_coalesce_none(
            _get_optional_attr(step_alignment, "debug_dir", None),
            exp_dir / "alignment_debug" / step.name,
        ),
        save_debug_images=_coalesce_none(
            _get_optional_attr(step_alignment, "save_debug_images", None),
            defaults.save_debug_images,
        ),
    )


def control_settings_for_step(
    step: tbt.Step,
    defaults: FIBSSControlSettings,
) -> FIBSSControlSettings:
    """Return FIB-SS control settings with per-step alignment overrides."""

    alignment = _get_optional_attr(step, "alignment_settings", None)
    if alignment is None:
        return defaults

    return defaults._replace(
        stage_move_threshold_um=_coalesce_none(
            _get_optional_attr(alignment, "stage_move_threshold_um", None),
            defaults.stage_move_threshold_um,
        ),
    )


def image_settings_for_alignment_step(step: tbt.Step) -> tbt.ImageSettings:
    """Return the image settings used to acquire alignment imagery for a step.

    This helper is what makes alignment step-wise and beam-agnostic:

    - IMAGE steps align using their own ``ImageSettings``.
    - FIB steps align using the embedded ion image settings in ``FIBSettings.image``.
    - Future operation types can opt in by exposing an ``image`` attribute.

    Keeping this logic centralized avoids a long chain of type checks throughout
    the workflow loop and gives factory validation one clear behavior to enforce.
    """

    operation_settings = step.operation_settings
    if isinstance(operation_settings, tbt.ImageSettings):
        return operation_settings
    if isinstance(operation_settings, tbt.FIBSettings):
        return operation_settings.image
    image_settings = _get_optional_attr(operation_settings, "image", None)
    if isinstance(image_settings, tbt.ImageSettings):
        return image_settings
    raise ValueError(
        f"Step '{step.name}' has template matching enabled but does not expose image settings."
    )


def step_alignment_policy(step: tbt.Step) -> Tuple[bool, bool, bool]:
    """Return ``(use_beam_shift, use_stage_recenter, use_pattern_shift)``.

    Alignment behavior is a pipeline, not a mutually exclusive mode.

    1. use beam shift for fine correction;
    2. if the residual/beam shift becomes too large, use stage recentering;
    3. for FIB steps, shift the milling pattern by the final residual.
    """

    alignment = _get_optional_attr(step, "alignment_settings", None)
    return (
        bool(_get_optional_attr(alignment, "use_beam_shift", True)),
        bool(_get_optional_attr(alignment, "use_stage_recenter", True)),
        bool(_get_optional_attr(alignment, "use_pattern_shift", True)),
    )


def compute_image_pixel_size_m(image_settings: tbt.ImageSettings) -> float:
    """Return approximate pixel size in meters from HFW and image width.

    This assumes a full-frame image and square pixels. It is the same conversion
    used in the proof-of-concept script. If reduced-area scans or non-square
    calibration are added later, replace this with a full image calibration
    transform.
    """

    hfw_m = image_settings.beam.settings.hfw_mm * cs.Conversions.MM_TO_M
    return hfw_m / float(image_settings.scan.resolution.width)


def acquire_alignment_image(
    step: tbt.Step,
    general_settings: tbt.GeneralSettings,
    slice_number: int,
    iteration: int,
) -> Path:
    """Acquire the alignment image for a step and return its expected path.

    The step must expose image settings either directly, for an ``IMAGE`` step,
    or through an embedded ``.image`` field, for a ``FIB`` step. The image is
    saved with an iteration suffix so every match/correction attempt has an
    audit trail.

    The project branch currently supports ``image_operation(...,
    suffix=iteration)``. This helper tries that call first. If the local
    ``image_operation`` implementation does not yet support ``suffix``, it falls
    back to using a temporary step name containing the iteration number.
    """

    image_settings = image_settings_for_alignment_step(step)
    image_step = tbt.Step(
        type=tbt.StepType.IMAGE,
        name=f"{step.name}_alignment",
        number=step.number,
        frequency=step.frequency,
        stage=step.stage,
        operation_settings=image_settings,
    )

    try:
        img.image_operation(
            step=image_step,
            image_settings=image_settings,
            general_settings=general_settings,
            slice_number=slice_number,
            suffix=iteration,
            perform_autofocus=False,
        )
        return Path(general_settings.exp_dir).joinpath(
            image_step.name, f"{slice_number:04}_{iteration:02}.tif"
        )
    except TypeError:
        # Compatibility path for older image.image_operation implementations
        # that do not accept a suffix argument. Use a unique step name so each
        # alignment iteration is still saved separately.
        iter_step = image_step._replace(name=f"{image_step.name}_{iteration:02}")
        img.image_operation(
            step=iter_step,
            image_settings=image_settings,
            general_settings=general_settings,
            slice_number=slice_number,
            perform_autofocus=False,
        )
        return Path(general_settings.exp_dir).joinpath(
            iter_step.name, f"{slice_number:04}.tif"
        )


def apply_beam_shift_delta(
    beam: tbt.Beam,
    microscope: tbt.Microscope,
    delta: ShiftDistanceM,
    max_beam_shift_um: Optional[float] = None,
) -> bool:
    """Apply an empirically calibrated beam-shift correction.

    ``delta`` is a current-minus-reference image displacement in meters using
    image coordinates (+X right, +Y down). The sign convention below matches the
    proof-of-concept behavior that converged in 2-3 iterations on the microscope.

    Keep this sign convention isolated here. If the microscope API or image
    coordinate convention changes, this is the only place that should need sign
    updates.
    """

    current_shift = read_beam_shift(beam=beam, microscope=microscope)
    new_shift = tbt.Point(
        x=current_shift.x - delta.dx,
        y=current_shift.y + delta.dy,
    )

    if max_beam_shift_um is not None:
        new_shift_um = math.hypot(new_shift.x, new_shift.y) * cs.Conversions.M_TO_UM
        if new_shift_um > max_beam_shift_um:
            raise ValueError(
                f"Requested beam shift magnitude {new_shift_um:.6g} µm exceeds "
                f"max_beam_shift_um={max_beam_shift_um:.6g}."
            )

    set_beam_shift(beam=beam, microscope=microscope, shift=new_shift)
    return True


def stage_move_required(
    shift_m: ShiftDistanceM,
    control: FIBSSControlSettings,
) -> bool:
    """Return true when a measured shift is too large for fine correction.

    The comparison uses vector magnitude, not signed X/Y values. This avoids the
    proof-of-concept bug where large negative shifts would not trigger the stage
    path.
    """

    return shift_m.magnitude_um >= control.stage_move_threshold_um


def stage_move_from_image_shift_m(
    shift_m: ShiftDistanceM,
    general_settings: tbt.GeneralSettings,
    x_sign: float = 1.0,
    y_sign: float = 1.0,
) -> Tuple[float, float]:
    """Convert image-coordinate shift to an approximate raw stage X/Y move.

    ``shift_m`` is measured from template matching using image coordinates:
    +X is right and +Y is down. Stage moves are commanded in the repository's
    user units, but this helper returns meters so the math stays close to the
    image/beam-shift calculation.

    The X component is usually a direct image-to-stage lateral correction after
    applying the calibrated sign.

    The Y component may need a tilt correction because raw stage Y motion is not
    always equal to apparent image Y motion when the specimen is tilted. This
    first implementation uses the configured pre-tilt angle and divides by
    cos(tilt) to estimate the raw stage displacement needed to generate the
    observed projected image displacement.

    TODO: calibrate ``x_sign``, ``y_sign``, and the tilt projection empirically.
    This function is deliberately small so that sign/trig changes happen in one
    place after calibration.
    """

    pre_tilt_rad = general_settings.pre_tilt_deg * cs.Conversions.DEG_TO_RAD
    cos_tilt = math.cos(pre_tilt_rad)
    if math.isclose(cos_tilt, 0.0, abs_tol=1e-9):
        raise ValueError("Cannot compute stage Y correction near 90 degree tilt.")

    stage_dx_m = x_sign * shift_m.dx
    stage_dy_m = y_sign * (shift_m.dy / cos_tilt)
    return stage_dx_m, stage_dy_m


def move_stage_for_alignment_placeholder(
    microscope: tbt.Microscope,
    beam: tbt.Beam,
    shift_m: ShiftDistanceM,
    general_settings: tbt.GeneralSettings,
    reset_beam_shift: bool = True,
) -> bool:
    """Coarsely recenter the stage from a measured image shift.

    This is still labelled as a placeholder because the sign convention and Y
    tilt projection need hardware calibration. The math mirrors the beam-shift
    path: template matching gives a pixel shift, HFW converts it to meters, and
    that physical displacement is used to build a relative stage move.

    If ``reset_beam_shift`` is true, the current beam shift is included in the
    stage recentering estimate and then zeroed. This is useful when the beam has
    been used for fine correction for several slices and we want to recenter the
    stage so future beam-shift corrections start near zero.

    TODO: verify the following on hardware:
    - image X/Y sign relative to raw stage X/Y;
    - whether raw stage Y should use cos(pre_tilt), sin(pre_tilt), or a more
      complete SEM/FIB image-to-stage transform;
    - whether beam-shift readback maps 1:1 to image displacement for the active
      beam and HFW.
    """

    total_shift_m = shift_m
    if reset_beam_shift:
        current_beam_shift = read_beam_shift(beam=beam, microscope=microscope)
        total_shift_m = ShiftDistanceM(
            dx=shift_m.dx + current_beam_shift.x,
            dy=shift_m.dy + current_beam_shift.y,
        )

    stage_dx_m, stage_dy_m = stage_move_from_image_shift_m(
        shift_m=total_shift_m,
        general_settings=general_settings,
    )

    current_position = factory.active_stage_position_settings(microscope=microscope)
    target_position = current_position._replace(
        x_mm=current_position.x_mm + stage_dx_m * cs.Conversions.M_TO_MM,
        y_mm=current_position.y_mm + stage_dy_m * cs.Conversions.M_TO_MM,
    )

    print(f"Current position: {current_position}")
    print(f"Target position: {target_position}")
    raise NotImplementedError("Don't move the stage yet!")
    stage.move_to_position(
        microscope=microscope,
        target_position=target_position,
        stage_tolerance=general_settings.stage_tolerance,
    )

    if reset_beam_shift:
        set_beam_shift(
            beam=beam,
            microscope=microscope,
            shift=tbt.Point(x=0.0, y=0.0),
        )

    return True


def iterate_beam_shift_alignment(
    step: tbt.Step,
    general_settings: tbt.GeneralSettings,
    microscope: tbt.Microscope,
    beam: tbt.Beam,
    alignment_settings: TemplateMatchSettings,
    baseline_match_px: ShiftPx,
    px_res_m: float,
    slice_number: int,
    control: FIBSSControlSettings,
    use_beam_shift: bool = True,
    use_stage_recenter: bool = True,
    max_beam_shift_um: Optional[float] = None,
) -> IterativeAlignmentResult:
    """Iteratively align a FIB/ion image using beam shift.

    This function is the productionized version of the working script loop. It
    repeatedly acquires an alignment image, finds the template, computes the
    residual relative to the baseline reference match, and applies beam shift
    until the residual is within ``alignment_settings.max_pixel_shift``.

    Measurement, decision, and correction are deliberately separate:
    - measurement: ``measure_template_offset``;
    - decision: score / pixel residual / stage threshold checks;
    - correction: beam shift now, stage move later.
    """

    image_paths = []
    scores = []
    shifts_px = []
    measurements = []
    final_measurement = None

    for iteration in range(1, alignment_settings.max_iterations + 1):
        image_path = acquire_alignment_image(
            step=step,
            general_settings=general_settings,
            slice_number=slice_number,
            iteration=iteration,
        )
        measurement = measure_template_offset(
            input_image=image_path,
            settings=alignment_settings,
            baseline_match_px=baseline_match_px,
            px_res_m=px_res_m,
            debug_name=f"slice_{slice_number:04}_iter_{iteration:02}.png",
        )
        final_measurement = measurement
        image_paths.append(image_path)
        scores.append(measurement.score)
        shifts_px.append(measurement.relative_shift_px)
        measurements.append(measurement)

        pixel_shift_magnitude = math.hypot(
            measurement.relative_shift_px.dx,
            measurement.relative_shift_px.dy,
        )

        print(
            f"\n\tTemplate matching round {iteration} of {alignment_settings.max_iterations}.",
            f"\n\t\tTemplate match score: {measurement.score}",
            f"\n\t\tFound pixel shift: {measurement.relative_shift_px}",
            f"\n\t\tPixel shift magnitude: {pixel_shift_magnitude} pixels",
            f"\n\t\tPhysical shift: {measurement.relative_shift_m.magnitude_um:.6g} µm",
        )

        if measurement.score < alignment_settings.match_threshold:
            raise ValueError(
                f"Template match score {measurement.score} is below threshold "
                f"{alignment_settings.match_threshold}."
            )

        if pixel_shift_magnitude <= alignment_settings.max_pixel_shift:
            return IterativeAlignmentResult(
                converged=True,
                iterations=iteration,
                final_shift_px=measurement.relative_shift_px,
                final_shift_m=measurement.relative_shift_m,
                final_score=measurement.score,
                image_paths=tuple(image_paths),
                scores=tuple(scores),
                shifts_px=tuple(shifts_px),
                measurements=tuple(measurements),
            )

        if stage_move_required(measurement.relative_shift_m, control):
            if not use_stage_recenter:
                raise ValueError(
                    f"Alignment residual {measurement.relative_shift_m.magnitude_um:.6g} µm "
                    "exceeds stage threshold, but stage recentering is disabled."
                )
            # Stage recentering should be followed by another acquisition rather
            # than applying beam shift to the pre-stage-move measurement.
            move_stage_for_alignment_placeholder(
                microscope=microscope,
                beam=beam,
                shift_m=measurement.relative_shift_m,
                general_settings=general_settings,
            )
            continue

        if not use_beam_shift:
            raise ValueError(
                f"Alignment residual is {pixel_shift_magnitude:.6g} pixels, "
                "but beam-shift correction is disabled and stage recentering was not required."
            )

        apply_beam_shift_delta(
            beam=beam,
            microscope=microscope,
            delta=measurement.relative_shift_m,
            max_beam_shift_um=max_beam_shift_um,
        )

    if final_measurement is None:
        raise RuntimeError("Alignment loop did not acquire any measurements.")

    return IterativeAlignmentResult(
        converged=False,
        iterations=alignment_settings.max_iterations,
        final_shift_px=final_measurement.relative_shift_px,
        final_shift_m=final_measurement.relative_shift_m,
        final_score=final_measurement.score,
        image_paths=tuple(image_paths),
        scores=tuple(scores),
        shifts_px=tuple(shifts_px),
        measurements=tuple(measurements),
    )


def pattern_shift_from_image_shift_m(shift_m: ShiftDistanceM) -> Tuple[float, float]:
    """Convert image residual to FIB pattern-center shift in micrometers.

    Image coordinates use +Y downward from the upper-left corner. FIB pattern
    coordinates are represented with origin at the pattern/image center and +Y
    in the opposite direction for the existing pattern-center update convention.

    This preserves the sign convention from the proof-of-concept
    ``update_pattern_center_um`` function:

    - pattern X shift = +image residual X;
    - pattern Y shift = -image residual Y.

    TODO: validate this sign convention with a deliberate known pattern shift on
    hardware and document the result.
    """

    return (
        shift_m.dx * cs.Conversions.M_TO_UM,
        -shift_m.dy * cs.Conversions.M_TO_UM,
    )


def shift_fib_pattern_for_slice(
    fib_settings: tbt.FIBSettings,
    general_settings: tbt.GeneralSettings,
    slice_number: int,
    control: FIBSSControlSettings,
    alignment_result: Optional[IterativeAlignmentResult],
    use_pattern_shift: bool,
) -> tbt.FIBSettings:
    """Apply nominal slice advance plus optional alignment residual to FIB pattern."""

    dx_um, dy_um = nominal_fib_pattern_advance_um(
        slice_number=slice_number,
        general_settings=general_settings,
        control=control,
    )

    if alignment_result is not None and use_pattern_shift:
        residual_dx_um, residual_dy_um = pattern_shift_from_image_shift_m(
            alignment_result.final_shift_m
        )
        dx_um += residual_dx_um
        dy_um += residual_dy_um

    return shift_fib_pattern_center_um(
        fib_settings=fib_settings,
        dx_um=dx_um,
        dy_um=dy_um,
    )


def shift_fib_pattern_center_um(
    fib_settings: tbt.FIBSettings,
    dx_um: float,
    dy_um: float,
) -> tbt.FIBSettings:
    """Return FIB settings with a box-like pattern center shifted in micrometers"""

    pattern = fib_settings.pattern
    geometry = pattern.geometry

    if not isinstance(
        geometry,
        (
            tbt.FIBRectanglePattern,
            tbt.FIBRegularCrossSection,
            tbt.FIBCleaningCrossSection,
        ),
    ):
        raise NotImplementedError(
            f"FIB pattern shifting is not implemented for geometry type {type(geometry)}."
        )

    shifted_geometry = shift_fib_box_geometry_um(
        geometry=geometry,
        dx_um=dx_um,
        dy_um=dy_um,
    )

    shifted_pattern = pattern._replace(geometry=shifted_geometry)
    return fib_settings._replace(pattern=shifted_pattern)


def nominal_fib_pattern_advance_um(
    slice_number: int,
    general_settings: tbt.GeneralSettings,
    control: FIBSSControlSettings,
) -> Tuple[float, float]:
    """Return nominal FIB pattern advance from slice number and slice thickness

    with fib_pattern_advance_offset_slices = 0:
        slice 1 advances by 0 * slice_thickness_um
        slice 2 advances by 1 * slice_thickness_um

    with fib_pattern_advance_offset_slices = 1:
        slice 1 advances by 1 * slice_thickness_um
        slice 2 advances by 2 * slice_thickness_um
    """

    advance_count = slice_number - 1 + control.fib_pattern_advance_offset_slices
    advance_um = (
        control.fib_pattern_advance_sign
        * advance_count
        * general_settings.slice_thickness_um
    )

    if control.fib_pattern_advance_axis.lower() == "x":
        return advance_um, 0.0
    if control.fib_pattern_advance_axis.lower() == "y":
        return 0.0, advance_um

    raise ValueError(
        "fib_pattern_advance_axis must be either 'x' or 'y', "
        f"but {control.fib_pattern_advance_axis!r} was provided."
    )


def shift_fib_box_geometry_um(geometry, dx_um: float, dy_um: float):
    """Return a shifted copy of a box-like FIB geometry object."""

    new_center = tbt.Point(
        x=geometry.center_um.x + dx_um,
        y=geometry.center_um.y + dy_um,
    )
    return geometry._replace(center_um=new_center)


# def shift_fib_pattern_from_alignment(
#     fib_settings: tbt.FIBSettings,
#     alignment_result: IterativeAlignmentResult,
# ) -> tbt.FIBSettings:
#     """Return FIB settings with pattern center shifted by alignment residual.

#     This is the most important FIB-SS behavior: after alignment, the milling
#     pattern center is updated from the measured residual fiducial displacement.
#     If beam-shift iteration has converged, this residual should be small. If the
#     step is configured for pattern-shift-only alignment later, this residual may
#     be the primary pattern-placement correction.
#     """

#     pattern = fib_settings.pattern
#     geometry = pattern.geometry

#     if not isinstance(
#         geometry,
#         (
#             tbt.FIBRectanglePattern,
#             tbt.FIBRegularCrossSection,
#             tbt.FIBCleaningCrossSection,
#         ),
#     ):
#         raise NotImplementedError(
#             f"FIB pattern shifting is not implemented for geometry type {type(geometry)}."
#         )

#     dx_um, dy_um = pattern_shift_from_image_shift_m(alignment_result.final_shift_m)
#     shifted_geometry = shift_fib_box_geometry_um(
#         geometry=geometry,
#         dx_um=dx_um,
#         dy_um=dy_um,
#     )
#     shifted_pattern = pattern._replace(geometry=shifted_geometry)
#     return fib_settings._replace(pattern=shifted_pattern)


def perform_step_alignment(
    step: tbt.Step,
    general_settings: tbt.GeneralSettings,
    microscope: tbt.Microscope,
    control: FIBSSControlSettings,
    slice_number: int,
) -> Optional[IterativeAlignmentResult]:
    """Run alignment for one step if the step has alignment enabled.

    This is the generalized step-wise entry point. It does not care whether the
    alignment image comes from an electron image step or from a FIB step's ion
    image settings. The image source is inferred from the step operation settings.
    """

    if not step_alignment_enabled(step):
        return None

    alignment_settings = alignment_settings_for_step(
        step=step,
        general_settings=general_settings,
        defaults=control,
    )
    step_control = control_settings_for_step(
        step=step,
        defaults=control,
    )
    image_settings = image_settings_for_alignment_step(step)
    px_res_m = compute_image_pixel_size_m(image_settings)

    max_beam_shift_um = _get_optional_attr(
        _get_optional_attr(step, "alignment_settings", None),
        "max_beam_shift_um",
        None,
    )

    if alignment_settings.reference_image_path is None:
        raise ValueError(
            f"Step '{step.name}' has alignment enabled but no reference image path."
        )

    baseline_match_px, baseline_score = template_match(
        input_image=alignment_settings.reference_image_path,
        reference_patch=alignment_settings.reference_patch_path,
    )
    if baseline_score < alignment_settings.match_threshold:
        raise ValueError(
            f"Baseline template match score {baseline_score} for step '{step.name}' "
            f"is below threshold {alignment_settings.match_threshold}."
        )

    use_beam_shift, use_stage_recenter, _ = step_alignment_policy(step)
    if use_beam_shift or use_stage_recenter:
        return iterate_beam_shift_alignment(
            step=step,
            general_settings=general_settings,
            microscope=microscope,
            beam=image_settings.beam,
            alignment_settings=alignment_settings,
            baseline_match_px=baseline_match_px,
            px_res_m=px_res_m,
            slice_number=slice_number,
            control=step_control,
            use_beam_shift=use_beam_shift,
            use_stage_recenter=use_stage_recenter,
            max_beam_shift_um=max_beam_shift_um,
        )

    # Measurement-only path. This is useful when a FIB step wants to use the
    # measured residual for pattern shift but does not want beam or stage
    # correction before milling.
    if not use_beam_shift and not use_stage_recenter:
        image_path = acquire_alignment_image(
            step=step,
            general_settings=general_settings,
            slice_number=slice_number,
            iteration=1,
        )
        measurement = measure_template_offset(
            input_image=image_path,
            settings=alignment_settings,
            baseline_match_px=baseline_match_px,
            px_res_m=px_res_m,
            debug_name=f"slice_{slice_number:04}_iter_01.png",
        )
        if measurement.score < alignment_settings.match_threshold:
            raise ValueError(
                f"Template match score {measurement.score} for step '{step.name}' "
                f"is below threshold {alignment_settings.match_threshold}."
            )
        return IterativeAlignmentResult(
            converged=True,
            iterations=1,
            final_shift_px=measurement.relative_shift_px,
            final_shift_m=measurement.relative_shift_m,
            final_score=measurement.score,
            image_paths=(image_path,),
            scores=(measurement.score,),
            shifts_px=(measurement.relative_shift_px,),
            measurements=(measurement,),
        )


def pattern_shift_allowed_for_step(
    step: tbt.Step,
    alignment_result: IterativeAlignmentResult,
) -> bool:
    """Validate optional maximum residual before applying FIB pattern shift."""

    alignment = _get_optional_attr(step, "alignment_settings", None)
    max_residual_um = _get_optional_attr(
        alignment,
        "max_residual_for_pattern_shift_um",
        None,
    )

    if max_residual_um is None:
        return True

    residual_um = alignment_result.final_shift_m.magnitude_um
    if residual_um > max_residual_um:
        raise ValueError(
            f"Step '{step.name}' final alignment residual is {residual_um:.6g} µm, "
            f"which exceeds max_residual_for_pattern_shift_um={max_residual_um:.6g}."
        )

    return True


def perform_fibss_operation(
    step: tbt.Step,
    general_settings: tbt.GeneralSettings,
    slice_number: int,
    alignment_result: Optional[IterativeAlignmentResult],
    control: FIBSSControlSettings,
) -> bool:
    """Perform a step after optional FIB-SS alignment.

    FIB steps are special because the milling pattern should be shifted from the
    residual alignment measurement before milling. Non-FIB steps are delegated to
    the existing workflow operation dispatcher.
    """

    if isinstance(step.operation_settings, tbt.FIBSettings):
        fib_settings = step.operation_settings
        original_center = fib_settings.pattern.geometry.center_um

        _, _, use_pattern_shift = step_alignment_policy(step)

        # update and create new step object, keeping original one intact
        fib_settings = shift_fib_pattern_for_slice(
            fib_settings=fib_settings,
            general_settings=general_settings,
            slice_number=slice_number,
            control=control,
            alignment_result=alignment_result,
            use_pattern_shift=use_pattern_shift,
        )
        shifted_center = fib_settings.pattern.geometry.center_um

        print(
            f"\tFIB pattern center update for step '{step.name}', slice {slice_number}: "
            f"({original_center.x:.6g}, {original_center.y:.6g}) um -> "
            f"({shifted_center.x:.6g}, {shifted_center.y:.6g}) um"
        )

        step = step._replace(operation_settings=fib_settings)

        fib.mill_operation(
            step=step,
            fib_settings=fib_settings,
            general_settings=general_settings,
            slice_number=slice_number,
        )
        return True

    return perform_operation(
        step.operation_settings,
        step=step,
        general_settings=general_settings,
        slice_number=slice_number,
    )


def perform_fibss_step(
    slice_number: int,
    step_number: int,
    experiment_settings: tbt.ExperimentSettings,
) -> None:
    """Perform one workflow step with optional alignment first."""

    # # breakout experiment settings elements
    microscope = experiment_settings.microscope
    general_settings = experiment_settings.general_settings
    step_sequence = experiment_settings.step_sequence
    enable_EBSD = experiment_settings.enable_EBSD
    enable_EDS = experiment_settings.enable_EDS

    # get operation (step) settings, execute operation.
    step = step_sequence[step_number - 1]  # l;ist is 0-indexed
    control_settings = step.alignment_settings

    control = FIBSSControlSettings(
        stage_move_threshold_um=control_settings.stage_move_threshold_um,
        template_match_threshold=control_settings.match_threshold,
        max_alignment_iterations=control_settings.max_iterations,
        max_pixel_shift=control_settings.max_pixel_shift,
        reference_image_path=control_settings.reference_image_path,
        reference_patch_path=control_settings.reference_patch_path,
        save_debug_images=control_settings.save_debug_images,
    )

    print(
        f"Slice {slice_number}, Step {step_number} of {general_settings.step_count}, '{step.name}', a {step.type.value} type step."
    )

    if (slice_number - 1) % step.frequency != 0:
        print(
            f"\tStep '{step.name}' frequency is every {step.frequency} slices. Skipping."
        )
        return

    # log step_start position
    log.position(
        step_number=step_number,
        step_name=step.name,
        slice_number=slice_number,
        log_filepath=general_settings.log_filepath,
        dataset_name=cs.Constants.pre_position_dataset_name,
        current_position=factory.active_stage_position_settings(
            microscope=microscope,
        ),
    )

    # retract all devices
    print("\tRetracting all devices...")
    # with ut.nostdout():
    devices.retract_all_devices(
        microscope=microscope,
        enable_EBSD=enable_EBSD,
        enable_EDS=enable_EDS,
    )
    print("\tDevices retracted.")

    # move stage to starting position for slice
    stage.step_start_position(
        microscope=microscope,
        slice_number=slice_number,
        operation=step,
        general_settings=general_settings,
    )

    # perform alignment if indicated
    alignment_result = perform_step_alignment(
        step=step,
        general_settings=general_settings,
        microscope=microscope,
        control=control,
        slice_number=slice_number,
    )
    if alignment_result is not None and not alignment_result.converged:
        raise ValueError(
            f"Alignment did not converge for step '{step.name}' on slice {slice_number}."
        )

    # perform specific operation
    perform_fibss_operation(
        step=step,
        general_settings=general_settings,
        slice_number=slice_number,
        alignment_result=alignment_result,
        control=control,
    )

    # log step end position
    log.position(
        step_number=step_number,
        step_name=step.name,
        slice_number=slice_number,
        log_filepath=general_settings.log_filepath,
        dataset_name=cs.Constants.post_position_dataset_name,
        current_position=factory.active_stage_position_settings(
            microscope=microscope,
        ),
    )

    # retract all devices
    print("\tRetracting all devices...")
    # with ut.nostdout():
    devices.retract_all_devices(
        microscope=microscope,
        enable_EBSD=enable_EBSD,
        enable_EDS=enable_EDS,
    )
    print("\tDevices retracted. Step Complete.\n")


def run_fib_ss_experiment_cli(
    start_slice: int,
    start_step: int,
    yaml_path: Path,
) -> None:
    """Run the generalized FIB-only serial sectioning workflow.

    This loop no longer looks for the first FIB step as the only alignment step.
    Instead, every configured step is inspected. If the step has template
    matching enabled, alignment runs first. The step operation then runs with any
    alignment result available to it.

    For FIB steps, ``perform_fibss_operation`` shifts the pattern center from the
    final alignment residual before milling. For non-FIB steps, it delegates to
    the existing ``workflow.perform_operation`` dispatcher.

    ``start_step`` is one-indexed, matching the existing workflow module. It is
    only used on ``start_slice``. After the first slice completes, subsequent
    slices begin at step 1. This allows safe restart/recovery from the middle of
    a slice without permanently skipping earlier steps on later slices.
    """

    experiment_settings = setup_experiment(yml_path=yaml_path)
    general_settings = experiment_settings.general_settings
    microscope = experiment_settings.microscope

    num_steps = len(experiment_settings.step_sequence)
    if start_step < 1 or start_step > num_steps:
        raise ValueError(
            f"start_step must satisfy 1 <= start_step <= {num_steps}, "
            f"but {start_step} was provided."
        )

    devices.retract_all_devices(
        microscope=microscope,
        enable_EBSD=experiment_settings.enable_EBSD,
        enable_EDS=experiment_settings.enable_EDS,
    )

    print(
        f"\n\nBeginning generalized FIB-only serial sectioning at "
        f"slice {start_slice}, step {start_step} of {num_steps}.\n"
    )

    for slice_number in range(start_slice, general_settings.max_slice_number + 1):
        print(f"\nSlice {slice_number} of {general_settings.max_slice_number}")

        first_step_for_this_slice = start_step if slice_number == start_slice else 1
        for step_number, step in enumerate(experiment_settings.step_sequence, start=1):
            if step_number < first_step_for_this_slice:
                print(
                    f"\tSkipping step {step_number} on start slice {slice_number}; "
                    f"restart requested step {first_step_for_this_slice}."
                )
                continue

            perform_fibss_step(
                slice_number=slice_number,
                step_number=step_number,
                experiment_settings=experiment_settings,
            )

    ut.disconnect_microscope(microscope=microscope, quiet_output=True)
