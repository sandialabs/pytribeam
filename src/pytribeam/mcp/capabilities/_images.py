#!/usr/bin/python3
"""
Image Previews and Statistics
=============================

Turns a saved microscope image into what the agent sees: a small PNG preview
and a few numbers that judge it better than the eye can.

The preview is never contrast-stretched. 16-bit images are mapped to 8 bits by
a fixed shift, so a dark, washed-out, or clipped image looks that way to the
agent too; stretching each image to fill the range would hide exactly the
problems it is looking for.

Only numpy and Pillow are used, so everything here works without AutoScript.
"""

from __future__ import annotations

import io
import string
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image as PILImage
from PIL import ImageDraw

# Claude sees images up to this long edge without rescaling them itself.
MAX_PREVIEW_PX = 1568
MIN_REGION_PX = 16

# Decoding limits, checked from the header before any pixel is read. The
# largest preset scan is 6144x4096; twice that leaves room for custom ones.
MAX_IMAGE_PIXELS = 6144 * 4096 * 2
MAX_FILE_BYTES = 512 * 1024 * 1024
# Above this, statistics use every 2nd pixel in each direction.
STATS_SUBSAMPLE_PIXELS = 16_000_000

# Pillow has its own decompression-bomb check; make it agree with ours.
PILImage.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

Region = Dict[str, float]  # {"left", "top", "width", "height"}, fractions 0-1


class ImageTooLarge(ValueError):
    """An image is refused before decoding because it exceeds the limits."""


def _check_size(width: int, height: int, pages: int, path: Path) -> None:
    if pages > 1:
        raise ImageTooLarge(
            f"{Path(path).name} has {pages} pages; only single-image files are supported."
        )
    if width * height > MAX_IMAGE_PIXELS:
        raise ImageTooLarge(
            f"{Path(path).name} is {width}x{height} px, more than the "
            f"{MAX_IMAGE_PIXELS:,} px this server will decode."
        )


def load(path: Path) -> Tuple[np.ndarray, int]:
    """Read a grayscale image as a 2-D array, with its bit depth (8 or 16).

    Sizes are checked from the file header before any pixels are decoded:
    files over :data:`MAX_FILE_BYTES`, images over :data:`MAX_IMAGE_PIXELS`,
    and multi-page files raise :class:`ImageTooLarge`.

    TIFFs are read with tifffile (a scikit-image dependency), which keeps the
    sample type stored in the file. Pillow opens a 16-bit RGB TIFF as 8-bit
    "RGB" and would report it as 8 bits. Multi-channel images are reduced to
    their first channel; microscope images are gray in every channel.
    """
    size = Path(path).stat().st_size
    if size > MAX_FILE_BYTES:
        raise ImageTooLarge(
            f"{Path(path).name} is {size / 1e6:.0f} MB, more than the "
            f"{MAX_FILE_BYTES / 1e6:.0f} MB this server will read."
        )

    data = None
    try:
        import tifffile

        with tifffile.TiffFile(path) as tif:  # parses tags only
            page = tif.pages[0]
            height, width = page.shape[:2] if page.ndim >= 2 else (1, page.shape[0])
            _check_size(width, height, len(tif.pages), path)
            data = page.asarray()
    except ImageTooLarge:
        raise
    except Exception:  # not a TIFF tifffile can read; fall back to Pillow
        data = None

    if data is None:
        with PILImage.open(path) as img:  # header only, until pixels are used
            _check_size(img.size[0], img.size[1], getattr(img, "n_frames", 1), path)
            if img.mode.startswith("I;16"):
                data = np.array(img, dtype=np.uint16)
            elif img.mode == "I":  # 32-bit integer; seen for some 16-bit TIFFs
                data = np.clip(np.array(img), 0, 65535).astype(np.uint16)
            else:
                data = np.array(img.convert("L"), dtype=np.uint8)

    data = np.asarray(data)
    while data.ndim > 2:  # (rows, cols, channels)
        data = data[..., 0]
    if data.dtype.itemsize > 1:
        return np.clip(data, 0, 65535).astype(np.uint16), 16
    return data.astype(np.uint8), 8


def stats(data: np.ndarray, bits: int) -> Dict[str, float]:
    """Intensity statistics and a sharpness score for a full-resolution image.

    Values are in the image's own units (0-255 or 0-65535). ``clipped_*_frac``
    are the fractions of pixels at the lowest and highest possible value.
    ``sharpness`` is the variance of a 3x3 Laplacian divided by the mean
    squared intensity, so it does not change with brightness; it only means
    something compared with other images of the same area.

    Images over :data:`STATS_SUBSAMPLE_PIXELS` use every 2nd pixel each way,
    to bound memory, and say so in ``subsampled``. Their ``sharpness`` is then
    measured at half the resolution: compare it only with other subsampled
    images.
    """
    subsampled = data.size > STATS_SUBSAMPLE_PIXELS
    if subsampled:
        data = data[::2, ::2]
    top = (1 << bits) - 1
    flat = data.ravel()
    p1, p50, p99 = np.percentile(flat, [1, 50, 99])
    values = data.astype(np.float64)
    lap = (
        -4 * values[1:-1, 1:-1]
        + values[:-2, 1:-1]
        + values[2:, 1:-1]
        + values[1:-1, :-2]
        + values[1:-1, 2:]
    )
    mean_sq = float(np.mean(values**2))
    return {
        "bit_depth": bits,
        "min": int(flat.min()),
        "max": int(flat.max()),
        "mean": round(float(flat.mean()), 2),
        "std": round(float(flat.std()), 2),
        "p1": float(p1),
        "p50": float(p50),
        "p99": float(p99),
        "clipped_low_frac": round(float(np.mean(flat == 0)), 6),
        "clipped_high_frac": round(float(np.mean(flat == top)), 6),
        "sharpness": round(float(lap.var()) / mean_sq, 6) if mean_sq and lap.size else 0.0,
        "subsampled": subsampled,
    }


def crop(data: np.ndarray, region: Optional[Region]) -> Tuple[np.ndarray, Dict[str, int]]:
    """Cut *region* out of *data*; returns the crop and its pixel bounds.

    Raises ``ValueError`` for a region outside 0-1 or smaller than
    :data:`MIN_REGION_PX` on a side.
    """
    height, width = data.shape
    if region is None:
        return data, {"left": 0, "top": 0, "width": width, "height": height}

    keys = ("left", "top", "width", "height")
    missing = [k for k in keys if k not in region]
    if missing:
        raise ValueError(f"region needs {', '.join(keys)}; missing {', '.join(missing)}.")
    left, top, w, h = (float(region[k]) for k in keys)
    if not (0 <= left < 1 and 0 <= top < 1 and w > 0 and h > 0):
        raise ValueError(
            "region values are fractions of the image: 0 <= left, top < 1 and "
            "width, height > 0."
        )
    if left + w > 1 + 1e-9 or top + h > 1 + 1e-9:
        raise ValueError("region extends past the image: left + width and top + height must be <= 1.")

    x0, y0 = int(round(left * width)), int(round(top * height))
    x1 = min(width, int(round((left + w) * width)))
    y1 = min(height, int(round((top + h) * height)))
    if x1 - x0 < MIN_REGION_PX or y1 - y0 < MIN_REGION_PX:
        raise ValueError(
            f"region is {x1 - x0}x{y1 - y0} px; it must be at least "
            f"{MIN_REGION_PX} px on each side."
        )
    return data[y0:y1, x0:x1], {"left": x0, "top": y0, "width": x1 - x0, "height": y1 - y0}


def to_8bit(data: np.ndarray, bits: int) -> Tuple[np.ndarray, str]:
    """Map to 8 bits by a fixed shift, never stretching. Returns the mapping used."""
    if bits == 8:
        return data.astype(np.uint8), "identity (8-bit)"
    return (data >> 8).astype(np.uint8), "16-bit value >> 8, no contrast stretch"


def _grid_labels(n: int) -> List[str]:
    letters = string.ascii_uppercase
    return [letters[i] if i < 26 else letters[i // 26 - 1] + letters[i % 26] for i in range(n)]


def preview(
    data: np.ndarray,
    bits: int,
    max_px: int,
    grid: bool = False,
    origin: Tuple[int, int] = (0, 0),
    grid_cells: int = 8,
) -> Tuple[bytes, Dict[str, Any]]:
    """Encode *data* as a PNG whose long edge is at most *max_px*.

    *origin* is where *data* sits in the full image (for a crop), so grid cell
    bounds are reported in full-image pixels. With *grid*, the long edge gets
    *grid_cells* cells and the short edge as many as keep the cells square;
    columns are lettered A, B, ... and rows numbered 1, 2, ...
    """
    max_px = max(MIN_REGION_PX, min(int(max_px), MAX_PREVIEW_PX))
    height, width = data.shape
    scale = min(1.0, max_px / max(width, height))
    size = (max(1, round(width * scale)), max(1, round(height * scale)))

    pixels, mapping = to_8bit(data, bits)
    img = PILImage.fromarray(pixels)  # uint8 2-D -> mode "L"
    if scale < 1.0:
        img = img.resize(size, PILImage.LANCZOS)

    info: Dict[str, Any] = {
        "width": size[0],
        "height": size[1],
        "scale": round(size[0] / width, 6),
        "mapping": mapping,
    }

    if grid:
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        cell = max(width, height) / grid_cells  # in source pixels
        cols, rows = max(1, round(width / cell)), max(1, round(height / cell))
        cw, ch = width / cols, height / rows
        col_names = _grid_labels(cols)
        cells = {}
        for r in range(rows):
            for c in range(cols):
                x0, y0 = round(c * cw), round(r * ch)
                x1, y1 = round((c + 1) * cw), round((r + 1) * ch)
                cells[f"{col_names[c]}{r + 1}"] = {
                    "left": origin[0] + x0,
                    "top": origin[1] + y0,
                    "width": x1 - x0,
                    "height": y1 - y0,
                }
        sx, sy = size[0] / width, size[1] / height
        color = (255, 255, 0)
        for c in range(1, cols):
            x = round(c * cw * sx)
            draw.line([(x, 0), (x, size[1])], fill=color, width=1)
        for r in range(1, rows):
            y = round(r * ch * sy)
            draw.line([(0, y), (size[0], y)], fill=color, width=1)
        for r in range(rows):
            for c in range(cols):
                x, y = round(c * cw * sx) + 2, round(r * ch * sy) + 1
                label = f"{col_names[c]}{r + 1}"
                draw.text((x + 1, y + 1), label, fill=(0, 0, 0))  # shadow, for contrast
                draw.text((x, y), label, fill=color)
        info["grid"] = {"columns": cols, "rows": rows, "cells": cells}

    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), info
