"""
Bruker EDS Element Map Readback Module
======================================

Provides hardened numeric element map readback from Bruker HyperMaps.

Key design principles:
- Use exact expected buffer size first (width * height * 2 bytes for uint16)
- Fall back to larger buffers only on IFC_ERROR_RESULT_BUFFER_INSUFFICIENT (-11)
- Per-element error capture: one element failing does not crash the entire readback
- Returns structured BrukerElementReadbackResult tuples with error information
"""

import ctypes as ct
import json
from pathlib import Path
from typing import Callable, Optional, Tuple

from pytribeam.external_oem.bruker.bindings import bind_eds
from pytribeam.external_oem.bruker.ctypes_types import c_u32
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.types import (
    BrukerEDSProfileMapSettings,
    BrukerElementReadbackResult,
)


class BrukerEDSReadbackController:
    """Controller for reading back numeric element map data from a HyperMap.

    This controller should be used after a successful map acquisition while
    the HyperMap data is still loaded in ESPRIT.

    Parameters
    ----------
    session : BrukerSession
        An active, connected Bruker session.
    """

    def __init__(self, session: BrukerSession):
        self._session = session
        bind_eds(self._session.dll)

    def get_element_data_bytes(
        self,
        element_index: int,
        expected_size: Optional[int] = None,
    ) -> bytes:
        """Return raw element data bytes from the current HyperMap.

        Parameters
        ----------
        element_index : int
            Zero-based index of the element to read.
        expected_size : int, optional
            If provided, this exact buffer size is tried first. This should
            be ``width_px * height_px * bytes_per_pixel`` (typically * 2 for
            uint16). Using the exact size avoids over-allocation and may
            surface Bruker-side errors more clearly.

        Returns
        -------
        bytes
            Raw element plane data.

        Raises
        ------
        RuntimeError
            If all buffer size attempts fail.
        """
        # Build size attempts: exact size first if provided, then fallbacks.
        size_attempts = []
        if expected_size is not None and expected_size > 0:
            size_attempts.append(expected_size)
        size_attempts.extend([8 * 1024 * 1024, 32 * 1024 * 1024, 128 * 1024 * 1024])

        for size_guess in size_attempts:
            size = c_u32(size_guess)
            buf = (ct.c_uint8 * size_guess)()

            rc = self._session.dll.HyMapGetElementData(
                self._session.cid,
                int(element_index),
                ct.cast(buf, ct.c_void_p),
                ct.byref(size),
            )

            if rc == 0:
                return ct.string_at(ct.addressof(buf), size.value)

            # IFC_ERROR_RESULT_BUFFER_INSUFFICIENT = -11
            if rc == -11:
                continue

            self._session._check(rc, "HyMapGetElementData")

        raise RuntimeError(
            f"HyMapGetElementData failed for element_index={element_index}: "
            f"buffer insufficient after all attempts"
        )

    def get_element_data_array(
        self,
        element_index: int,
        width_px: int,
        height_px: int,
        dtype: str = "uint16",
    ):
        """Return numeric element map plane as a NumPy array.

        Parameters
        ----------
        element_index : int
            Zero-based index of the element to read.
        width_px : int
            Expected map width in pixels.
        height_px : int
            Expected map height in pixels.
        dtype : str
            NumPy dtype string (default "uint16").

        Returns
        -------
        np.ndarray
            Element map with shape (height_px, width_px).

        Raises
        ------
        ValueError
            If the returned data size does not match expected dimensions.
        """
        import numpy as np

        np_dtype = np.dtype(dtype)
        expected_pixels = int(width_px) * int(height_px)
        expected_bytes = expected_pixels * np_dtype.itemsize

        data = self.get_element_data_bytes(
            element_index=element_index,
            expected_size=expected_bytes,
        )

        arr = np.frombuffer(data, dtype=np_dtype)

        if arr.size != expected_pixels:
            raise ValueError(
                f"Element data size mismatch for index {element_index}: "
                f"got {arr.size} pixels, expected {expected_pixels}; "
                f"bytes={len(data)}, dtype={np_dtype}"
            )

        return arr.reshape((int(height_px), int(width_px))).copy()

    @staticmethod
    def _effective_readback_dimensions(
        settings: BrukerEDSProfileMapSettings,
    ) -> Tuple[int, int]:
        """Determine the pixel dimensions for element data readback.

        When a ROI is active, Bruker returns element data sized to the ROI,
        not the full configured map dimensions.

        Returns
        -------
        tuple of (width_px, height_px)
            The dimensions to use for array reshaping.
        """
        if settings.roi is not None:
            return (settings.roi.width_px, settings.roi.height_px)
        return (settings.width_px, settings.height_px)

    def read_all_element_maps(
        self,
        settings: BrukerEDSProfileMapSettings,
        dtype: str = "uint16",
        strict: bool = False,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> Tuple[BrukerElementReadbackResult, ...]:
        """Read all requested element maps from the current HyperMap.

        Per-element error capture: if one element fails, the others are still
        attempted. Failed elements have their ``error`` field populated.

        Parameters
        ----------
        settings : BrukerEDSProfileMapSettings
            The profile map settings used for acquisition.
        dtype : str
            NumPy dtype string (default "uint16").
        strict : bool
            If True, raise on the first element readback failure.
            If False (default), capture errors and continue.
        log_fn : callable, optional
            Logging callback for progress messages.

        Returns
        -------
        tuple of BrukerElementReadbackResult
            One result per requested element, in settings.elements order.
        """

        readback_width, readback_height = self._effective_readback_dimensions(settings)
        results = []

        for idx, element in enumerate(settings.elements):
            try:
                if log_fn:
                    log_fn(
                        f"Reading element {idx}: "
                        f"Z={element.atomic_number}, line={element.line}"
                    )

                arr = self.get_element_data_array(
                    element_index=idx,
                    width_px=readback_width,
                    height_px=readback_height,
                    dtype=dtype,
                )

                result = BrukerElementReadbackResult(
                    element_index=idx,
                    atomic_number=element.atomic_number,
                    line=element.line,
                    shape=(int(arr.shape[0]), int(arr.shape[1])),
                    dtype=str(arr.dtype),
                    min_val=int(arr.min()),
                    max_val=int(arr.max()),
                    sum_val=int(arr.sum()),
                    nonzero=int((arr != 0).sum()),
                )
                results.append(result)

            except Exception as exc:
                if strict:
                    raise

                error_msg = f"{type(exc).__name__}: {exc}"
                if log_fn:
                    log_fn(
                        f"Element {idx} (Z={element.atomic_number}, "
                        f"line={element.line}) readback failed: {error_msg}"
                    )

                result = BrukerElementReadbackResult(
                    element_index=idx,
                    atomic_number=element.atomic_number,
                    line=element.line,
                    error=error_msg,
                )
                results.append(result)

        return tuple(results)

    def save_element_maps_npy(
        self,
        settings: BrukerEDSProfileMapSettings,
        output_dir: str,
        prefix: Optional[str] = None,
        dtype: str = "uint16",
        strict: bool = False,
        save_element_tiff: bool = False,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> Tuple[BrukerElementReadbackResult, ...]:
        """Save all requested element maps as .npy arrays with metadata.

        Each element is read back individually. Failures are captured
        per-element unless ``strict=True``.

        A summary JSON file is always written alongside the .npy files
        containing per-element metadata and statistics.

        Parameters
        ----------
        settings : BrukerEDSProfileMapSettings
            The profile map settings used for acquisition.
        output_dir : str
            Directory to write .npy files and metadata JSON.
        prefix : str, optional
            File name prefix. Defaults to settings.name.
        dtype : str
            NumPy dtype string (default "uint16").
        strict : bool
            If True, raise on the first element readback failure.
        save_element_tiff : bool
            If True, also save each successful numeric element map as a 16-bit
            TIFF using the same base filename as the .npy file.
        log_fn : callable, optional
            Logging callback for progress messages.

        Returns
        -------
        tuple of BrukerElementReadbackResult
            One result per requested element, with ``path`` populated on
            success.
        """
        import numpy as np

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if prefix is None:
            prefix = settings.name

        readback_width, readback_height = self._effective_readback_dimensions(settings)
        results = []

        for idx, element in enumerate(settings.elements):
            safe_line = element.line.replace(" ", "_")
            base_name = f"{prefix}_element_{idx}_Z{element.atomic_number}_{safe_line}"
            npy_path = out_dir / f"{base_name}.npy"
            tiff_path = out_dir / f"{base_name}.tiff"

            try:
                if log_fn:
                    log_fn(
                        f"Reading element {idx}: "
                        f"Z={element.atomic_number}, line={element.line}"
                    )

                arr = self.get_element_data_array(
                    element_index=idx,
                    width_px=readback_width,
                    height_px=readback_height,
                    dtype=dtype,
                )

                np.save(npy_path, arr)

                tiff_path_str = None
                if save_element_tiff:
                    self._save_array_as_tiff(arr, tiff_path)
                    tiff_path_str = str(tiff_path)

                result = BrukerElementReadbackResult(
                    element_index=idx,
                    atomic_number=element.atomic_number,
                    line=element.line,
                    path=str(npy_path),
                    tiff_path=tiff_path_str,
                    shape=(int(arr.shape[0]), int(arr.shape[1])),
                    dtype=str(arr.dtype),
                    min_val=int(arr.min()),
                    max_val=int(arr.max()),
                    sum_val=int(arr.sum()),
                    nonzero=int((arr != 0).sum()),
                )
                results.append(result)

                if log_fn:
                    tiff_msg = f", tiff={tiff_path.name}" if tiff_path_str else ""
                    log_fn(
                        f"Saved element {idx}: {npy_path.name}{tiff_msg} "
                        f"shape={arr.shape} min={arr.min()} max={arr.max()}"
                    )

            except Exception as exc:
                if strict:
                    raise

                error_msg = f"{type(exc).__name__}: {exc}"
                if log_fn:
                    log_fn(
                        f"Element {idx} (Z={element.atomic_number}, "
                        f"line={element.line}) failed: {error_msg}"
                    )

                result = BrukerElementReadbackResult(
                    element_index=idx,
                    atomic_number=element.atomic_number,
                    line=element.line,
                    error=error_msg,
                )
                results.append(result)

        # Write metadata/summary JSON
        self._write_readback_summary(
            results=tuple(results),
            settings=settings,
            output_dir=out_dir,
            prefix=prefix,
            dtype=dtype,
        )

        return tuple(results)

    @staticmethod
    def _save_array_as_tiff(arr, path: Path) -> str:
        """Save a numeric element map array as a TIFF image.

        For uint16 arrays this writes a 16-bit grayscale TIFF. This file is a
        portable numeric image export of the same data stored in the .npy file.
        """
        from PIL import Image

        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(arr).save(path)
        return str(path)

    def _write_readback_summary(
        self,
        results: Tuple[BrukerElementReadbackResult, ...],
        settings: BrukerEDSProfileMapSettings,
        output_dir: Path,
        prefix: str,
        dtype: str,
    ) -> str:
        """Write a summary JSON file for element readback results.

        Returns
        -------
        str
            Path to the written summary JSON file.
        """
        successful = [r for r in results if r.error is None]
        failed = [r for r in results if r.error is not None]

        summary = {
            "map_name": settings.name,
            "map_width_px": settings.width_px,
            "map_height_px": settings.height_px,
            "roi": settings.roi._asdict() if settings.roi is not None else None,
            "pixel_time_us": settings.pixel_time_us,
            "dtype": dtype,
            "elements_requested": len(settings.elements),
            "elements_successful": len(successful),
            "elements_failed": len(failed),
            "results": [r._asdict() for r in results],
        }

        summary_path = output_dir / f"{prefix}_readback_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        return str(summary_path)
