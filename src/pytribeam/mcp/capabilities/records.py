#!/usr/bin/python3
"""
Record Capabilities
===================

Tier 0 tools for looking back at what the server has already saved: states
and images. They read only files under ``<project_dir>``, never the
microscope, so they take no hardware lock and answer even while an
acquisition is running or the microscope is unreachable.

Every image ``iNNNN.tif`` has a sidecar ``iNNNN.yml`` written by
``collect_single_image``, holding its settings, statistics, and stage
position, so listing never has to parse TIFFs.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError

from pytribeam.mcp import state
from pytribeam.mcp.capabilities import _images
from pytribeam.mcp.capabilities.state import _STATE_ID

TIER = 0

_IMAGE_ID = re.compile(r"^i\d+$")

# Fields of a sidecar shown by list_images; the rest is in the sidecar itself.
LISTED = (
    "recorded_at",
    "description",
    "beam",
    "detector",
    "detector_mode",
    "resolution",
    "bit_depth",
    "hfw_mm",
    "pixel_size_nm",
    "stage_position",
    "before_state_id",
    "after_state_id",
)


def sidecar_path(image: Path) -> Path:
    return image.with_suffix(".yml")


def read_sidecar(image: Path) -> Optional[Dict[str, Any]]:
    """The sidecar for *image*, or None if it has none (or it is unreadable)."""
    path = sidecar_path(image)
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError:
        return None


def image_ids(images_dir: Path) -> List[str]:
    """Saved image ids, oldest first."""
    if not images_dir.is_dir():
        return []
    ids = (p.stem for p in images_dir.glob("i*.tif") if _IMAGE_ID.match(p.stem))
    return sorted(ids, key=lambda image_id: int(image_id[1:]))


def image_content(
    path: Path,
    max_px: int,
    region: Optional[Dict[str, float]] = None,
    grid: bool = False,
) -> tuple:
    """Load *path* and return ``(stats, preview_info, Image)``.

    Statistics are for the region shown (the whole image if *region* is None),
    at full resolution.
    """
    data, bits = _images.load(path)
    shown, bounds = _images.crop(data, region)
    png, info = _images.preview(
        shown, bits, max_px, grid=grid, origin=(bounds["left"], bounds["top"])
    )
    info["region_px"] = bounds
    info["full_size"] = {"width": data.shape[1], "height": data.shape[0]}
    return _images.stats(shown, bits), info, Image(data=png, format="png")


def register(add, config, connection) -> None:
    """Register this module's tools."""
    images_dir = config.images_dir
    states_dir = config.states_dir

    def list_states(limit: int = 20) -> dict:
        """List the most recent saved states, oldest first.

        Includes states from earlier sessions in this project. ``limit`` caps
        how many are returned; ``total`` is how many exist. Pass ids to
        ``compare_states``. Reads files only; touches no hardware.
        """
        ids = sorted(
            (p.stem for p in states_dir.glob("s*.yml") if _STATE_ID.match(p.stem)),
            key=lambda state_id: int(state_id[1:]),
        )
        recent = []
        for state_id in ids[-limit:] if limit > 0 else []:
            saved = state.load(states_dir / f"{state_id}.yml")
            recent.append(
                {
                    "state_id": state_id,
                    "recorded_at": saved["recorded_at"],
                    "description": saved.get("description") or "",
                }
            )
        return {"total": len(ids), "states": recent}

    def locate(image_id: str) -> Path:
        path = images_dir / f"{image_id}.tif"
        if not _IMAGE_ID.match(image_id) or not path.is_file():
            raise ToolError(
                f"No image with id {image_id!r}; list_images shows the saved ids."
            )
        return path

    def list_images(limit: int = 20) -> dict:
        """List the most recent saved images, oldest first, newest last.

        Includes images from earlier sessions in this project. Each entry has
        the settings it was taken with, its pixel size, the stage position
        (RAW, mm and deg, as ``get_stage_position`` reports), and the state
        ids from before and after it was taken. ``limit`` caps how many are
        returned; ``total`` is how many exist. Pass an ``image_id`` to
        ``view_image`` to see one. Reads files only; touches no hardware.
        """
        ids = image_ids(images_dir)
        recent = []
        for image_id in ids[-limit:] if limit > 0 else []:
            path = images_dir / f"{image_id}.tif"
            side = read_sidecar(path)
            entry: Dict[str, Any] = {"image_id": image_id}
            if side is None:
                entry["note"] = "no record of how this image was taken"
                entry["size_bytes"] = path.stat().st_size
            else:
                entry.update({key: side.get(key) for key in LISTED})
            recent.append(entry)
        return {"total": len(ids), "images": recent}

    def view_image(
        image_id: str,
        region: Optional[Dict[str, float]] = None,
        max_px: int = 1024,
        grid: bool = False,
    ) -> List[Union[dict, Image]]:
        """Show a saved image, or part of it, without taking a new one.

        ``region`` crops before downsampling, so a small region is seen at up
        to full resolution: ``{"left", "top", "width", "height"}`` as
        fractions 0-1 of the full image, origin at the top left. Use it to
        zoom in on a feature or to check focus. ``max_px`` is the long edge
        of the returned picture (capped at 1568); larger costs more tokens.

        ``grid`` draws a labelled grid (columns A, B, ..., rows 1, 2, ...)
        on the picture only, never on the saved image, and returns each
        cell's bounds in full-image pixels, so you can name a location
        ("the particle in C4") or turn it into a ``region``.

        Returns the image's record, ``stats`` for the region shown (see
        ``collect_single_image``), and the picture. The picture is never
        contrast-stretched: a dark or washed-out image looks that way. Reads
        files only; touches no hardware.
        """
        path = locate(image_id)
        try:
            image_stats, info, picture = image_content(path, max_px, region, grid)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        record = read_sidecar(path) or {}
        return [
            {
                "image_id": image_id,
                **{key: record.get(key) for key in LISTED if key in record},
                "pixel_size_nm": record.get("pixel_size_nm"),
                "stats": image_stats,
                "preview": info,
            },
            picture,
        ]

    add(list_states, read_only=True, uses_microscope=False)
    add(list_images, read_only=True, uses_microscope=False)
    add(view_image, read_only=True, uses_microscope=False)
