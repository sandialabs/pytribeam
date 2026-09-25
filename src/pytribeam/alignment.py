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

The implementation uses scikit-image's ``match_template`` for normalized
template matching. For subpixel localization, the integer-pixel correlation
peak is refined by fitting local parabolas through the peak and its immediate
neighbors in x and y.

Coordinate convention
---------------------
Images use the usual array/image coordinate system:

- origin is at the upper-left corner;
- +X points right;
- +Y points down.

The template-match position returned by :func:`template_match` and
:func:`template_match_subpixel` is the upper-left coordinate of the best
matching patch in ``input_image``. For alignment control, this module also
provides :func:`relative_shift_px` and :func:`measure_template_offset` to compare
the current match to a baseline/reference match.

Python compatibility: Python 3.8. No new dependencies beyond packages already
used in the project.
"""

__all__ = [
    "ShiftPx",
    "ShiftDistanceM",
    "TemplateMatchSettings",
    "TemplateMatchMeasurement",
    "TemplateMatchBatchRow",
    "px_to_dist_m",
    "template_match",
    "template_match_subpixel",
    "relative_shift_px",
    "measure_template_offset",
    "save_template_match_debug_image",
    "save_template_match_heatmap",
    "find_template_match_images",
    "analyze_template_match_folder",
    "write_template_match_batch_csv",
    "plot_template_match_batch_differences",
]

import csv
import re
from pathlib import Path
from typing import Iterable, List, NamedTuple, Optional, Tuple
import numpy as np
from PIL import Image, ImageDraw
from skimage.feature import match_template

import pytribeam.constants as cs


class ShiftPx(NamedTuple):
    """2D displacement or location in pixel units.

    For template-match locations, ``dx`` and ``dy`` are the best-match
    upper-left ``x`` and ``y`` pixel coordinates. For relative shifts, they are
    current-minus-baseline displacement in pixels.
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
        """Euclidean displacement magnitude in meters."""

        return float(np.hypot(self.dx, self.dy))

    @property
    def magnitude_um(self) -> float:
        """Euclidean displacement magnitude in micrometers."""

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
    use_subpixel_refinement
        If true, :func:`measure_template_offset` uses
        :func:`template_match_subpixel`. If false, it uses integer-pixel
        :func:`template_match`.
    save_debug_heatmap
        If true, save the normalized template-match response image when a debug
        directory is available. This is disabled by default because heatmaps can
        be large and are usually only needed during tuning.
    """

    reference_patch_path: Path
    reference_image_path: Optional[Path] = None
    match_threshold: float = 0.8
    max_pixel_shift: float = 2.0
    max_iterations: int = 3
    debug_dir: Optional[Path] = None
    save_debug_images: bool = True
    use_subpixel_refinement: bool = True
    save_debug_heatmap: bool = False


class TemplateMatchMeasurement(NamedTuple):
    """Result from matching one reference patch in one image."""

    match_position_px: ShiftPx
    relative_shift_px: ShiftPx
    relative_shift_m: ShiftDistanceM
    score: float
    input_image_path: Path
    reference_patch_path: Path
    debug_image_path: Optional[Path] = None
    debug_heatmap_path: Optional[Path] = None


class TemplateMatchBatchRow(NamedTuple):
    """One row of batch template-match comparison output.

    This compares integer-pixel template matching to subpixel quadratic peak
    refinement for the same input image and template.

    Coordinates are template upper-left coordinates in image pixels.
    """

    slice_number: int
    iteration: int
    input_image_path: Path

    integer_match_px: ShiftPx
    subpixel_match_px: ShiftPx

    subpixel_minus_integer_px: ShiftPx
    subpixel_minus_integer_magnitude_px: float

    score: float

    heatmap_png_path: Optional[Path] = None
    heatmap_npy_path: Optional[Path] = None


def _load_grayscale_array(path: Path) -> np.ndarray:
    """Load an image as a 2D float32 grayscale array.

    This function intentionally normalizes image dimensionality, not intensity.
    If the input is RGB/RGBA, it is converted to luminance using PIL. If the
    input is already a single-channel image, its native pixel values are
    preserved and converted to ``float32``.

    Preserving native scalar intensity is useful for microscope images that may
    be 12-bit or 16-bit. Avoiding unconditional ``convert("L")`` prevents
    unnecessary quantization to 8-bit.
    """

    with Image.open(path) as pil_image:
        array = np.asarray(pil_image)

    if array.ndim == 2:
        return array.astype(np.float32, copy=False)

    if array.ndim == 3:
        # Drop alpha if present.
        if array.shape[2] >= 3:
            rgb = array[:, :, :3].astype(np.float32, copy=False)
            # Standard luma transform.
            return (
                0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
            ).astype(np.float32, copy=False)

        if array.shape[2] == 1:
            return array[:, :, 0].astype(np.float32, copy=False)

    raise ValueError(
        f"Unsupported image shape for grayscale loading: {array.shape} from {path}"
    )


def _validate_template_size(image_array: np.ndarray, patch_array: np.ndarray) -> None:
    """Raise if the patch cannot be matched inside the image."""

    if patch_array.ndim != 2 or image_array.ndim != 2:
        raise ValueError(
            "Template matching expects 2D grayscale arrays. "
            f"Got image ndim={image_array.ndim}, patch ndim={patch_array.ndim}."
        )

    if (
        patch_array.shape[0] > image_array.shape[0]
        or patch_array.shape[1] > image_array.shape[1]
    ):
        raise ValueError(
            f"Reference patch shape {patch_array.shape} is larger than "
            f"input image shape {image_array.shape}."
        )


def _template_match_response(
    input_image: Path,
    reference_patch: Path,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load images and compute the normalized template-match response.

    Returns
    -------
    image_array
        2D float32 grayscale input image.
    patch_array
        2D float32 grayscale reference patch.
    response
        Normalized cross-correlation response from ``skimage.feature.match_template``.
        Response coordinates are template upper-left coordinates in the input
        image when ``pad_input=False``, which is the default.
    """

    image_array = _load_grayscale_array(input_image)
    patch_array = _load_grayscale_array(reference_patch)
    _validate_template_size(image_array=image_array, patch_array=patch_array)

    response = match_template(
        image=image_array,
        template=patch_array,
        pad_input=False,
    )

    return image_array, patch_array, response


def _find_integer_peak(response: np.ndarray) -> Tuple[int, int, float]:
    """Return integer row, column, and score of the maximum response."""

    if response.size == 0:
        raise ValueError("Template-match response is empty.")

    peak_row, peak_col = np.unravel_index(np.argmax(response), response.shape)
    peak_score = float(response[peak_row, peak_col])
    return int(peak_row), int(peak_col), peak_score


def _parabolic_peak_offset(
    value_minus: float,
    value_center: float,
    value_plus: float,
    max_abs_offset: float = 1.0,
) -> float:
    """Estimate subpixel offset of a 1D peak using a quadratic fit.

    The parabola is fit through three samples located at ``x = -1, 0, +1``.
    The returned offset is the fitted vertex position relative to the center
    sample.

    For a clean local maximum, this usually lies in approximately
    ``[-0.5, +0.5]``. Larger values can happen when the local neighborhood is
    flat, noisy, non-parabolic, or not actually centered on a well-behaved peak.
    The result is therefore clipped to ``[-max_abs_offset, +max_abs_offset]`` as
    a conservative safety measure.

    Formula
    -------
    Given samples ``f(-1)``, ``f(0)``, and ``f(+1)``, the vertex offset is

        0.5 * (f(-1) - f(+1)) / (f(-1) - 2*f(0) + f(+1))
    """

    denominator = value_minus - 2.0 * value_center + value_plus

    if abs(denominator) < 1.0e-12:
        return 0.0

    offset = 0.5 * (value_minus - value_plus) / denominator

    if not np.isfinite(offset):
        return 0.0

    return float(np.clip(offset, -max_abs_offset, max_abs_offset))


def _refine_peak_quadratic(
    response: np.ndarray,
    peak_row: int,
    peak_col: int,
) -> Tuple[float, float]:
    """Refine an integer response peak using separable quadratic fits.

    Parameters
    ----------
    response
        2D template-match response image.
    peak_row, peak_col
        Integer coordinates of the peak response.

    Returns
    -------
    subpixel_row, subpixel_col
        Refined peak coordinates in response-array coordinates.

    Notes
    -----
    This performs independent 1D quadratic fits in row and column directions.
    It is a standard, simple subpixel peak estimator for a smooth correlation
    response. Because the response coordinate is the template's upper-left
    coordinate, the returned subpixel coordinate is also the template's
    upper-left coordinate.

    If the peak lies on the response border, there is not enough neighboring
    information to refine along that axis, so the integer coordinate is kept for
    that axis.
    """

    subpixel_row = float(peak_row)
    subpixel_col = float(peak_col)

    if 0 < peak_row < response.shape[0] - 1:
        row_offset = _parabolic_peak_offset(
            value_minus=float(response[peak_row - 1, peak_col]),
            value_center=float(response[peak_row, peak_col]),
            value_plus=float(response[peak_row + 1, peak_col]),
        )
        subpixel_row += row_offset

    if 0 < peak_col < response.shape[1] - 1:
        col_offset = _parabolic_peak_offset(
            value_minus=float(response[peak_row, peak_col - 1]),
            value_center=float(response[peak_row, peak_col]),
            value_plus=float(response[peak_row, peak_col + 1]),
        )
        subpixel_col += col_offset

    return subpixel_row, subpixel_col


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
    """Return integer-pixel best template location and normalized match score.

    The returned position is the upper-left corner of the best matching patch in
    ``input_image``. Use :func:`relative_shift_px` to compare it to a baseline
    match position from a reference image.

    This function intentionally returns the integer-pixel maximum of the
    normalized template-match response. For subpixel localization, use
    :func:`template_match_subpixel`.
    """

    _, _, response = _template_match_response(
        input_image=input_image,
        reference_patch=reference_patch,
    )

    peak_row, peak_col, peak_score = _find_integer_peak(response)

    return ShiftPx(dx=float(peak_col), dy=float(peak_row)), peak_score


def template_match_subpixel(
    input_image: Path,
    reference_patch: Path,
) -> Tuple[ShiftPx, float]:
    """Return subpixel best template location and normalized match score.

    This uses normalized template matching followed by local quadratic peak
    refinement. The returned position is the subpixel upper-left corner of the
    best matching patch in ``input_image``.

    The returned score is the normalized template-match score at the integer
    response maximum. It remains directly comparable to the score returned by
    :func:`template_match`.
    """

    _, _, response = _template_match_response(
        input_image=input_image,
        reference_patch=reference_patch,
    )

    peak_row, peak_col, peak_score = _find_integer_peak(response)
    subpixel_row, subpixel_col = _refine_peak_quadratic(
        response=response,
        peak_row=peak_row,
        peak_col=peak_col,
    )

    return ShiftPx(dx=float(subpixel_col), dy=float(subpixel_row)), peak_score


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

    For subpixel matches, the rectangle is drawn at the nearest integer pixel
    location, while the label includes the subpixel coordinate.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(input_image).convert("RGB") as image_pil:
        with Image.open(reference_patch) as patch_pil:
            patch_width, patch_height = patch_pil.size

        draw = ImageDraw.Draw(image_pil)

        x0_float = float(match_position_px.dx)
        y0_float = float(match_position_px.dy)

        x0 = int(round(x0_float))
        y0 = int(round(y0_float))
        x1 = x0 + patch_width
        y1 = y0 + patch_height

        draw.rectangle([x0, y0, x1, y1], outline="red", width=3)

        label = f"score={score:.4f}, x={x0_float:.2f}, y={y0_float:.2f}"
        draw.text((x0, max(0, y0 - 14)), label, fill="red")

        image_pil.save(output_path)

    return output_path


def save_template_match_heatmap(
    input_image: Path,
    reference_patch: Path,
    output_path: Path,
) -> Path:
    """Save the normalized template-match response as an image.

    This is optional diagnostic output. The heatmap image is not saved by
    :func:`template_match` or :func:`template_match_subpixel` because those
    functions should be side-effect-free.

    The response is linearly scaled to 8-bit for visualization. This means the
    saved image is for debugging only, not for quantitative analysis.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)

    _, _, response = _template_match_response(
        input_image=input_image,
        reference_patch=reference_patch,
    )

    response = np.asarray(response, dtype=np.float32)

    response_min = float(np.min(response))
    response_max = float(np.max(response))

    if response_max > response_min:
        scaled = (response - response_min) / (response_max - response_min)
    else:
        scaled = np.zeros_like(response, dtype=np.float32)

    heatmap_uint8 = np.clip(255.0 * scaled, 0.0, 255.0).astype(np.uint8)
    Image.fromarray(heatmap_uint8).save(output_path)

    return output_path


def save_template_match_response_npy(
    input_image: Path,
    reference_patch: Path,
    output_path: Path,
) -> Path:
    """Save the raw normalized template-match response as a NumPy array.

    This is preferable to PNG heatmaps for quantitative logging or later
    reanalysis because it preserves the actual floating-point response values.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)

    _, _, response = _template_match_response(
        input_image=input_image,
        reference_patch=reference_patch,
    )

    np.save(output_path, np.asarray(response, dtype=np.float32))

    return output_path


_TEMPLATE_IMAGE_RE = re.compile(
    r"^(?P<slice_number>\d{4})_(?P<iteration>\d{2})\.tif$", re.IGNORECASE
)


def find_template_match_images(
    image_dir: Path,
) -> List[Tuple[int, int, Path]]:
    """Find images named like ``0001_00.tif`` in a directory.

    Parameters
    ----------
    image_dir
        Directory containing images named ``{slice_number:04d}_{iteration:02d}.tif``.

    Returns
    -------
    list
        Sorted list of ``(slice_number, iteration, image_path)`` tuples.
    """

    image_dir = Path(image_dir)

    rows = []

    for image_path in image_dir.iterdir():
        if not image_path.is_file():
            continue

        match = _TEMPLATE_IMAGE_RE.match(image_path.name)
        if match is None:
            continue

        slice_number = int(match.group("slice_number"))
        iteration = int(match.group("iteration"))

        rows.append((slice_number, iteration, image_path))

    rows.sort(key=lambda item: (item[0], item[1], item[2].name))
    return rows


def _analyze_one_template_match_response(
    response: np.ndarray,
) -> Tuple[ShiftPx, ShiftPx, ShiftPx, float, float]:
    """Analyze one already-computed template-match response.

    Returns
    -------
    integer_match_px
        Integer-pixel upper-left template location.
    subpixel_match_px
        Subpixel upper-left template location.
    subpixel_minus_integer_px
        Difference between subpixel and integer position.
    subpixel_minus_integer_magnitude_px
        Euclidean magnitude of the difference in pixels.
    score
        Normalized template-match score at the integer maximum.
    """

    peak_row, peak_col, score = _find_integer_peak(response)

    subpixel_row, subpixel_col = _refine_peak_quadratic(
        response=response,
        peak_row=peak_row,
        peak_col=peak_col,
    )

    integer_match_px = ShiftPx(
        dx=float(peak_col),
        dy=float(peak_row),
    )

    subpixel_match_px = ShiftPx(
        dx=float(subpixel_col),
        dy=float(subpixel_row),
    )

    diff_px = ShiftPx(
        dx=subpixel_match_px.dx - integer_match_px.dx,
        dy=subpixel_match_px.dy - integer_match_px.dy,
    )

    diff_mag_px = float(np.hypot(diff_px.dx, diff_px.dy))

    return (
        integer_match_px,
        subpixel_match_px,
        diff_px,
        diff_mag_px,
        score,
    )


def _save_response_png_from_array(
    response: np.ndarray,
    output_path: Path,
) -> Path:
    """Save an already-computed template-match response as an 8-bit PNG."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    response = np.asarray(response, dtype=np.float32)

    response_min = float(np.min(response))
    response_max = float(np.max(response))

    if response_max > response_min:
        scaled = (response - response_min) / (response_max - response_min)
    else:
        scaled = np.zeros_like(response, dtype=np.float32)

    heatmap_uint8 = np.clip(255.0 * scaled, 0.0, 255.0).astype(np.uint8)
    Image.fromarray(heatmap_uint8).save(output_path)

    return output_path


def analyze_template_match_folder(
    image_dir: Path,
    reference_patch: Path,
    output_dir: Optional[Path] = None,
    save_heatmap_png: bool = False,
    save_heatmap_npy: bool = False,
    save_csv: bool = True,
    csv_name: str = "template_match_subpixel_comparison.csv",
) -> List[TemplateMatchBatchRow]:
    """Compare integer and subpixel template matching for all matching images.

    The input images must be named using this pattern:

        ``{slice_number:04d}_{iteration:02d}.tif``

    Example filenames:

        ``0000_00.tif``
        ``0000_01.tif``
        ``0001_00.tif``

    Parameters
    ----------
    image_dir
        Folder containing images to analyze.
    reference_patch
        Template/fiducial patch image.
    output_dir
        Optional output directory for CSV and heatmaps. If omitted, outputs are
        written under ``image_dir / "template_match_analysis"`` when needed.
    save_heatmap_png
        Save an 8-bit visual heatmap image for each match.
    save_heatmap_npy
        Save the raw float32 template-match response for each match.
    save_csv
        Write a CSV summary table.
    csv_name
        Name of the CSV summary file.

    Returns
    -------
    list of TemplateMatchBatchRow
        One result row per matched image.
    """

    image_dir = Path(image_dir)
    reference_patch = Path(reference_patch)

    if output_dir is None:
        output_dir = image_dir / "template_match_analysis"
    else:
        output_dir = Path(output_dir)

    if save_csv or save_heatmap_png or save_heatmap_npy:
        output_dir.mkdir(parents=True, exist_ok=True)

    image_rows = find_template_match_images(image_dir=image_dir)

    results: List[TemplateMatchBatchRow] = []

    for slice_number, iteration, image_path in image_rows:
        _, _, response = _template_match_response(
            input_image=image_path,
            reference_patch=reference_patch,
        )

        (
            integer_match_px,
            subpixel_match_px,
            diff_px,
            diff_mag_px,
            score,
        ) = _analyze_one_template_match_response(response=response)

        heatmap_png_path = None
        heatmap_npy_path = None

        heatmap_stem = f"{slice_number:04d}_{iteration:02d}_template_response"

        if save_heatmap_png:
            heatmap_png_path = _save_response_png_from_array(
                response=response,
                output_path=output_dir / "heatmaps_png" / f"{heatmap_stem}.png",
            )

        if save_heatmap_npy:
            heatmap_npy_path = output_dir / "heatmaps_npy" / f"{heatmap_stem}.npy"
            heatmap_npy_path.parent.mkdir(parents=True, exist_ok=True)
            np.save(heatmap_npy_path, np.asarray(response, dtype=np.float32))

        results.append(
            TemplateMatchBatchRow(
                slice_number=slice_number,
                iteration=iteration,
                input_image_path=image_path,
                integer_match_px=integer_match_px,
                subpixel_match_px=subpixel_match_px,
                subpixel_minus_integer_px=diff_px,
                subpixel_minus_integer_magnitude_px=diff_mag_px,
                score=score,
                heatmap_png_path=heatmap_png_path,
                heatmap_npy_path=heatmap_npy_path,
            )
        )

    if save_csv:
        write_template_match_batch_csv(
            rows=results,
            output_path=output_dir / csv_name,
        )

    return results


def write_template_match_batch_csv(
    rows: Iterable[TemplateMatchBatchRow],
    output_path: Path,
) -> Path:
    """Write batch template-match comparison rows to CSV."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "slice_number",
        "iteration",
        "input_image_path",
        "integer_x_px",
        "integer_y_px",
        "subpixel_x_px",
        "subpixel_y_px",
        "subpixel_minus_integer_dx_px",
        "subpixel_minus_integer_dy_px",
        "subpixel_minus_integer_magnitude_px",
        "score",
        "heatmap_png_path",
        "heatmap_npy_path",
    ]

    with output_path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    "slice_number": row.slice_number,
                    "iteration": row.iteration,
                    "input_image_path": str(row.input_image_path),
                    "integer_x_px": row.integer_match_px.dx,
                    "integer_y_px": row.integer_match_px.dy,
                    "subpixel_x_px": row.subpixel_match_px.dx,
                    "subpixel_y_px": row.subpixel_match_px.dy,
                    "subpixel_minus_integer_dx_px": row.subpixel_minus_integer_px.dx,
                    "subpixel_minus_integer_dy_px": row.subpixel_minus_integer_px.dy,
                    "subpixel_minus_integer_magnitude_px": row.subpixel_minus_integer_magnitude_px,
                    "score": row.score,
                    "heatmap_png_path": (
                        ""
                        if row.heatmap_png_path is None
                        else str(row.heatmap_png_path)
                    ),
                    "heatmap_npy_path": (
                        ""
                        if row.heatmap_npy_path is None
                        else str(row.heatmap_npy_path)
                    ),
                }
            )

    return output_path


def plot_template_match_batch_differences(
    rows: Iterable[TemplateMatchBatchRow],
    output_path: Optional[Path] = None,
    show: bool = False,
) -> Optional[Path]:
    """Plot subpixel-minus-integer differences across slice/iteration images.

    This function imports matplotlib lazily so the core alignment module does not
    require matplotlib unless plotting is requested.

    Parameters
    ----------
    rows
        Batch rows returned by :func:`analyze_template_match_folder`.
    output_path
        Optional path for saved plot image.
    show
        If true, show the plot interactively.

    Returns
    -------
    Optional[Path]
        The saved plot path, or ``None`` if no output path was provided.
    """

    import matplotlib.pyplot as plt

    rows = list(rows)

    if len(rows) == 0:
        raise ValueError("No batch rows to plot.")

    x_labels = [f"{row.slice_number:04d}_{row.iteration:02d}" for row in rows]
    dx_values = [row.subpixel_minus_integer_px.dx for row in rows]
    dy_values = [row.subpixel_minus_integer_px.dy for row in rows]
    mag_values = [row.subpixel_minus_integer_magnitude_px for row in rows]
    scores = [row.score for row in rows]

    x = np.arange(len(rows))

    fig, axes = plt.subplots(
        nrows=3,
        ncols=1,
        figsize=(max(10.0, 0.25 * len(rows)), 9.0),
        sharex=True,
    )

    axes[0].plot(x, dx_values, marker=".", label="dx")
    axes[0].plot(x, dy_values, marker=".", label="dy")
    axes[0].axhline(0.0, color="black", linewidth=0.8)
    axes[0].set_ylabel("subpixel - integer [px]")
    axes[0].legend(loc="best")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(x, mag_values, marker=".", color="tab:purple")
    axes[1].set_ylabel("difference magnitude [px]")
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(x, scores, marker=".", color="tab:green")
    axes[2].set_ylabel("NCC score")
    axes[2].set_xlabel("slice_iteration")
    axes[2].grid(True, alpha=0.3)

    if len(rows) <= 80:
        axes[2].set_xticks(x)
        axes[2].set_xticklabels(x_labels, rotation=90)
    else:
        # Too many labels becomes unreadable.
        tick_count = min(20, len(rows))
        tick_indices = np.linspace(0, len(rows) - 1, tick_count).astype(int)
        axes[2].set_xticks(tick_indices)
        axes[2].set_xticklabels(
            [x_labels[index] for index in tick_indices], rotation=90
        )

    fig.tight_layout()

    saved_path = None

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150)
        saved_path = output_path

    if show:
        plt.show()
    else:
        plt.close(fig)

    return saved_path


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
    shift to meters, optionally saves debug output, and returns all values in a
    single immutable result object.

    By default, this uses subpixel peak refinement because
    ``TemplateMatchSettings.use_subpixel_refinement`` defaults to true.
    """

    if settings.use_subpixel_refinement:
        match_position_px, score = template_match_subpixel(
            input_image=input_image,
            reference_patch=settings.reference_patch_path,
        )
    else:
        match_position_px, score = template_match(
            input_image=input_image,
            reference_patch=settings.reference_patch_path,
        )

    rel_px = relative_shift_px(
        current_match_px=match_position_px,
        baseline_match_px=baseline_match_px,
    )

    rel_m = px_to_dist_m(
        shift_px=rel_px,
        px_res_m=px_res_m,
    )

    debug_image_path = None
    debug_heatmap_path = None

    if settings.debug_dir is not None:
        if debug_name is None:
            debug_stem = input_image.stem
        else:
            debug_stem = Path(debug_name).stem

        if settings.save_debug_images:
            debug_image_path = save_template_match_debug_image(
                input_image=input_image,
                reference_patch=settings.reference_patch_path,
                match_position_px=match_position_px,
                score=score,
                output_path=settings.debug_dir / f"{debug_stem}_template_match.png",
            )

        if settings.save_debug_heatmap:
            debug_heatmap_path = save_template_match_heatmap(
                input_image=input_image,
                reference_patch=settings.reference_patch_path,
                output_path=settings.debug_dir / f"{debug_stem}_template_heatmap.png",
            )

    return TemplateMatchMeasurement(
        match_position_px=match_position_px,
        relative_shift_px=rel_px,
        relative_shift_m=rel_m,
        score=score,
        input_image_path=input_image,
        reference_patch_path=settings.reference_patch_path,
        debug_image_path=debug_image_path,
        debug_heatmap_path=debug_heatmap_path,
    )
