#!/usr/bin/python3
"""Template-matching helpers for FIB-only serial sectioning alignment.

This module intentionally contains image-registration logic, not microscope
workflow logic. The FIB serial-sectioning workflow should ask this module:

    "Where did my saved fiducial patch appear in the current image?"

and then the workflow decides what to do with that measured offset:

- apply beam/image shift;
- shift the FIB milling pattern;
- move the physical stage;
- fail if the match is poor or the shift is too large.

The first implementation uses scikit-image's ``match_template``. That is a good
fit for the planned workflow because the experiment will save a reference patch
from the fiducial region and repeatedly match it in newly acquired alignment
images.

Coordinate convention
---------------------
Images use the usual array/image coordinate system:

- origin is at the upper-left corner;
- +X points right;
- +Y points down.

The raw template-match position returned by :func:`template_match` is the
upper-left pixel coordinate of the best match. For alignment control we usually
care about **relative** motion, so this module also provides
:func:`relative_shift_px` and :func:`measure_template_offset` to compare the
current match to a baseline/reference match.

Python compatibility: Python 3.8. No new dependencies beyond packages already
used in the project.
"""

__all__ = [
    "ShiftPx",
    "ShiftDistanceM",
    "TemplateMatchSettings",
    "TemplateMatchMeasurement",
    "px_to_dist_m",
    "template_match",
    "relative_shift_px",
    "measure_template_offset",
    "save_template_match_debug_image",
]

from pathlib import Path
from typing import NamedTuple, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw
from skimage.feature import match_template
from skimage.registration import phase_cross_correlation
from scipy.signal import windows

import pytribeam.constants as cs


class ShiftPx(NamedTuple):
    """2D displacement or location in pixel units.

    For template-match locations, ``dx`` and ``dy`` are actually the best-match
    upper-left ``x`` and ``y`` pixel coordinates. For relative shifts, they are
    current minus baseline displacement in pixels.
    """

    dx: float
    dy: float


class ShiftDistanceM(NamedTuple):
    """2D displacement in meters in image coordinates.

    Coordinate convention is still image-like: +X right, +Y down. Workflow code
    must convert signs when applying stage, beam, or pattern corrections.
    """

    dx: float
    dy: float

    @property
    def magnitude_m(self) -> float:
        return float(np.hypot(self.dx, self.dy))

    @property
    def magnitude_um(self) -> float:
        return self.magnitude_m * cs.Conversions.M_TO_UM


class TemplateMatchSettings(NamedTuple):
    """Settings for one template-matching alignment target.

    Parameters
    ----------
    reference_patch_path
        Path to the saved fiducial patch/template.
    reference_image_path
        Optional path to the image from which the baseline match position should
        be measured. If omitted, caller must provide a baseline match position.
    match_threshold
        Minimum acceptable normalized template-match score.
    max_pixel_shift
        Pixel residual considered converged during iterative correction.
    max_iterations
        Maximum beam-shift / correction iterations.
    debug_dir
        Optional directory for debug overlay images.
    save_debug_images
        If true, save debug match overlays when a debug directory is available.
    """

    reference_patch_path: Path
    reference_image_path: Optional[Path] = None
    match_threshold: float = 0.8
    max_pixel_shift: float = 2.0
    max_iterations: int = 3
    debug_dir: Optional[Path] = None
    save_debug_images: bool = True


class TemplateMatchMeasurement(NamedTuple):
    """Result from matching one reference patch in one image."""

    match_position_px: ShiftPx
    relative_shift_px: ShiftPx
    relative_shift_m: ShiftDistanceM
    score: float
    input_image_path: Path
    reference_patch_path: Path
    debug_image_path: Optional[Path] = None


def _load_grayscale_array(path: Path) -> np.ndarray:
    """Load an image as a 2D floating point array for matching."""

    with Image.open(path) as pil_image:
        # Convert to grayscale so template matching is not affected by image mode.
        return np.asarray(pil_image.convert("L"), dtype=np.float32)


def px_to_dist_m(shift_px: ShiftPx, px_res_m: float) -> ShiftDistanceM:
    """Convert a pixel displacement to meters using a scalar pixel size."""

    return ShiftDistanceM(
        dx=shift_px.dx * px_res_m,
        dy=shift_px.dy * px_res_m,
    )


def template_match(
    input_image: Path,
    reference_patch: Path,
) -> Tuple[ShiftPx, float]:
    """Return best template location and normalized match score.

    The returned position is the upper-left corner of the best matching patch in
    ``input_image``. Use :func:`relative_shift_px` to compare it to a baseline
    match position from a reference image.
    """

    # # Potentially weird behvior in here:
    # image_array = _load_grayscale_array(input_image)
    # patch_array = _load_grayscale_array(reference_patch)

    image_array = Image.open(input_image)
    image_array = np.array(image_array)

    patch_array = Image.open(reference_patch)
    patch_array = np.array(patch_array)

    if (
        patch_array.shape[0] > image_array.shape[0]
        or patch_array.shape[1] > image_array.shape[1]
    ):
        raise ValueError(
            f"Reference patch {reference_patch} with shape {patch_array.shape} "
            f"is larger than input image {input_image} with shape {image_array.shape}."
        )

    result = match_template(image_array, patch_array)
    # result[result > 1.0] = 0
    img = Image.fromarray(result)
    img.save(input_image.parent.joinpath(f"{input_image.stem}_heatmap.tif"))

    max_score = float(np.max(result))
    ij = np.unravel_index(np.argmax(result), result.shape)
    x, y = ij[::-1]
    return ShiftPx(dx=float(x), dy=float(y)), max_score


def center_pad_template(template: np.ndarray, reference_shape: tuple) -> tuple:
    """
    Center-pad a template to match the reference image shape.

    Parameters
    ----------
    template : np.ndarray
        The template / moving image (smaller than reference).
    reference_shape : tuple
        (rows, cols) shape of the reference image.

    Returns
    -------
    padded_template : np.ndarray
        The template centered in a zero-padded array of size reference_shape.
    pad_offsets : tuple of (int, int)
        (pad_top, pad_left) — the offset of the template's top-left corner
        within the padded array.
    """
    t_rows, t_cols = template.shape[:2]
    r_rows, r_cols = reference_shape[:2]

    if t_rows > r_rows or t_cols > r_cols:
        raise ValueError(
            f"Template shape {template.shape[:2]} must be smaller than or equal to "
            f"reference shape {reference_shape[:2]} in both dimensions."
        )

    pad_top = (r_rows - t_rows) // 2
    pad_bottom = r_rows - t_rows - pad_top
    pad_left = (r_cols - t_cols) // 2
    pad_right = r_cols - t_cols - pad_left

    # Handle both 2D and multichannel images
    if template.ndim == 2:
        pad_width = ((pad_top, pad_bottom), (pad_left, pad_right))
    else:
        pad_width = ((pad_top, pad_bottom), (pad_left, pad_right), (0, 0))

    padded_template = np.pad(template, pad_width, mode="constant", constant_values=0)

    return padded_template, (pad_top, pad_left)


def phase_correlate_subpixel(
    reference: np.ndarray,
    template: np.ndarray,
    upsample_factor: int = 100,
) -> tuple:
    """
    Run phase cross-correlation between the reference and a center-padded template.

    Parameters
    ----------
    reference : np.ndarray
        The reference / fixed image.
    template : np.ndarray
        The template / moving image (smaller than reference). Will be
        center-padded internally to match the reference size.
    upsample_factor : int
        Upsampling factor for subpixel precision. 100 gives 1/100th pixel
        accuracy.

    Returns
    -------
    shift : np.ndarray
        Raw (row, col) shift returned by phase_cross_correlation. This is
        the shift to move the *padded* template onto the reference.
    error : float
        Translation invariant normalized RMS error.
    phasediff : float
        Global phase difference.
    pad_offsets : tuple of (int, int)
        (pad_top, pad_left) used for padding, needed for coordinate transform.
    """

    # preprocess the patch to avoid dissconitunity errors
    # zero-centering:
    template_normalized = template - np.mean(template)
    # Hann windowing
    h_y = windows.hann(template.shape[0])
    h_x = windows.hann(template.shape[1])
    window_2d = np.outer(h_y, h_x)
    template_windowed = template_normalized * window_2d
    # center padding
    padded_template, pad_offsets = center_pad_template(
        template_windowed, reference.shape
    )

    import matplotlib.pyplot as plt

    plt.imshow(padded_template)
    plt.show()

    shift, error, phasediff = phase_cross_correlation(
        reference_image=reference,
        moving_image=padded_template,
        upsample_factor=upsample_factor,
    )

    print("here")

    return shift, error, phasediff, pad_offsets


def shift_to_template_match_coords(
    shift: np.ndarray,
    pad_offsets: tuple,
) -> np.ndarray:
    """
    Convert the raw phase-correlation shift into template-matching coordinates.

    Phase correlation returns the shift that aligns the *padded* template to
    the reference. In the padded template the actual content sits at
    (pad_top, pad_left). We need the position of the template's top-left
    corner in the reference image — the same thing template matching reports.

    Derivation
    ----------
    Let the template content start at position ``pad_offsets`` inside the
    padded array. Phase correlation says "move the padded array by ``shift``
    to align it with the reference." After that shift, the template content
    lands at::

        position_in_reference = pad_offsets + shift

    This is exactly the (row, col) of the template's top-left corner in the
    reference — the template-matching convention.

    Parameters
    ----------
    shift : array-like, shape (2,)
        Raw (row_shift, col_shift) from phase_cross_correlation.
    pad_offsets : tuple of (int, int)
        (pad_top, pad_left) from center_pad_template.

    Returns
    -------
    position : np.ndarray, shape (2,)
        (row, col) of the template's top-left corner in the reference image,
        with subpixel precision.
    """
    shift = np.asarray(shift, dtype=float)
    pad_offsets = np.asarray(pad_offsets, dtype=float)
    return pad_offsets + shift


def find_template_subpixel(
    reference: np.ndarray,
    template: np.ndarray,
    upsample_factor: int = 100,
) -> dict:
    """
    Locate a template in a reference image with subpixel accuracy via phase
    correlation, returning results in the template-matching coordinate system
    (top-left corner origin).

    This is the main entry point that combines center-padding, phase
    correlation, and coordinate transformation.

    Parameters
    ----------
    reference : np.ndarray
        The reference / fixed image (2-D grayscale).
    template : np.ndarray
        The template / moving image, must be smaller than the reference in
        both dimensions.
    upsample_factor : int
        Upsampling factor for subpixel precision (default 100 → 0.01 px).

    Returns
    -------
    result : dict
        'position'   : np.ndarray (2,) — (row, col) of the template's
                        top-left corner in the reference, subpixel.
        'error'      : float — normalised RMS error from phase correlation.
        'phasediff'  : float — global phase difference.
        'raw_shift'  : np.ndarray (2,) — raw shift from phase correlation.
        'pad_offsets' : tuple (pad_top, pad_left).

    Example
    -------
    >>> import numpy as np
    >>> from phase_correlation_template_match import find_template_subpixel
    >>> reference = np.random.rand(512, 512)
    >>> template = reference[100:200, 150:250].copy()
    >>> result = find_template_subpixel(reference, template, upsample_factor=100)
    >>> print(result['position'])  # should be close to [100.0, 150.0]
    """
    shift, error, phasediff, pad_offsets = phase_correlate_subpixel(
        reference, template, upsample_factor=upsample_factor
    )

    position = shift_to_template_match_coords(shift, pad_offsets)

    return {
        "position": position,
        "error": error,
        "phasediff": phasediff,
        "raw_shift": shift,
        "pad_offsets": pad_offsets,
    }


def template_match_subpixel(
    input_image: Path,
    reference_patch: Path,
    upsample_factor: float = 100,
) -> Tuple[ShiftPx, float]:
    """
    Locate a template in a reference image with subpixel accuracy via phase
    correlation, returning results in the template-matching coordinate system
    (top-left corner origin).

    This is the main entry point that combines center-padding, phase
    correlation, and coordinate transformation.
    """
    image_array = Image.open(input_image)
    image_array = np.array(image_array)

    patch_array = Image.open(reference_patch)
    patch_array = np.array(patch_array)

    shift, error, phasediff, pad_offsets = phase_correlate_subpixel(
        reference=image_array, template=patch_array, upsample_factor=upsample_factor
    )

    position = shift_to_template_match_coords(shift, pad_offsets)

    return ShiftPx(dx=float(position[1]), dy=float(position[0])), error


def relative_shift_px(
    current_match_px: ShiftPx,
    baseline_match_px: ShiftPx,
) -> ShiftPx:
    """Return current-minus-baseline template-match shift in pixels."""

    return ShiftPx(
        dx=current_match_px.dx - baseline_match_px.dx,
        dy=current_match_px.dy - baseline_match_px.dy,
    )


def save_template_match_debug_image(
    input_image: Path,
    reference_patch: Path,
    match_position_px: ShiftPx,
    score: float,
    output_path: Path,
) -> Path:
    """Save an overlay image showing the matched template rectangle.

    This is intended for experiment debugging and audit trails. It draws the
    template bounding box on the current image and writes a small score label.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(input_image).convert("RGB") as image_pil:
        with Image.open(reference_patch) as patch_pil:
            patch_width, patch_height = patch_pil.size

        draw = ImageDraw.Draw(image_pil)
        x0 = int(round(match_position_px.dx))
        y0 = int(round(match_position_px.dy))
        x1 = x0 + patch_width
        y1 = y0 + patch_height
        draw.rectangle([x0, y0, x1, y1], outline="red", width=3)
        draw.text((x0, max(0, y0 - 14)), f"score={score:.4f}", fill="red")
        image_pil.save(output_path)
    return output_path


def measure_template_offset(
    input_image: Path,
    settings: TemplateMatchSettings,
    baseline_match_px: ShiftPx,
    px_res_m: float,
    debug_name: Optional[str] = None,
) -> TemplateMatchMeasurement:
    """Measure current template offset relative to a baseline match.

    This is the main helper the workflow should call for one alignment image.
    It performs matching, computes current-minus-baseline shift, converts that
    shift to meters, optionally saves a debug overlay, and returns all values in
    a single immutable result object.
    """

    match_position_px, score = template_match(
        input_image=input_image,
        reference_patch=settings.reference_patch_path,
    )
    rel_px = relative_shift_px(
        current_match_px=match_position_px,
        baseline_match_px=baseline_match_px,
    )
    rel_m = px_to_dist_m(shift_px=rel_px, px_res_m=px_res_m)

    debug_image_path = None
    if settings.save_debug_images and settings.debug_dir is not None:
        if debug_name is None:
            debug_name = input_image.stem + "_template_match.png"
        debug_image_path = save_template_match_debug_image(
            input_image=input_image,
            reference_patch=settings.reference_patch_path,
            match_position_px=match_position_px,
            score=score,
            output_path=settings.debug_dir / debug_name,
        )

    return TemplateMatchMeasurement(
        match_position_px=match_position_px,
        relative_shift_px=rel_px,
        relative_shift_m=rel_m,
        score=score,
        input_image_path=input_image,
        reference_patch_path=settings.reference_patch_path,
        debug_image_path=debug_image_path,
    )
