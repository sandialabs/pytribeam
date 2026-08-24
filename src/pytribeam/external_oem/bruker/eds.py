import ctypes as ct
import time
from pathlib import Path
from typing import Callable, Optional

from pytribeam.external_oem.bruker.bindings import bind_eds
from pytribeam.external_oem.bruker.ctypes_types import (
    TFeatureData,
    TRTElementRegion,
    TRTHyMapProfileSettings,
    TSegment,
    c_bool,
    c_dbl,
    c_i32,
    c_u32,
)
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.types import (
    BrukerEDSElementMapSetting,
    BrukerEDSMapSettings,
    BrukerEDSProfileMapSettings,
    BrukerMapOutputs,
    BrukerMapProgress,
    BrukerRectROI,
)

DEFAULT_EDS_ELEMENT_COLORS = (
    (255, 0, 0),  # red
    (0, 255, 0),  # green
    (0, 0, 255),  # blue
    (255, 255, 0),  # yellow
    (255, 0, 255),  # magenta
    (0, 255, 255),  # cyan
    (255, 128, 0),  # orange
    (128, 0, 255),  # purple
    (0, 180, 90),  # teal/green
    (255, 80, 120),  # pink
)


class BrukerEDSController:
    def __init__(self, session: BrukerSession):
        self._session = session
        bind_eds(self._session.dll)

    def _build_rect_region(
        self, width_px: int, height_px: int, x_start_px: int = 0, y_start_px: int = 0
    ):
        """
        Build a Bruker TFeatureData rectangular region.

        Bruker selected-area mapping uses line segments, not directly x/y/width/height.
        For a rectangle, create one segment per y-line.

        Returns
        -------
        feature : TFeatureData
        segments : ctypes array
            Must be kept alive at least until the DLL call returns.
        """
        segments = (TSegment * int(height_px))()

        for i in range(int(height_px)):
            segments[i].Y = int(y_start_px + i)
            segments[i].XStart = int(x_start_px)
            segments[i].XCount = int(width_px)

        feature = TFeatureData(
            SegmentCount=int(height_px),
            Segments=ct.cast(segments, ct.POINTER(TSegment)),
        )
        return feature, segments

    @staticmethod
    def _validate_roi(roi: BrukerRectROI, map_width_px: int, map_height_px: int):
        """Validate that a ROI fits within the configured map dimensions.

        Parameters
        ----------
        roi : BrukerRectROI
            The ROI to validate.
        map_width_px : int
            Full map width from ImageSetConfiguration.
        map_height_px : int
            Full map height from ImageSetConfiguration.

        Raises
        ------
        ValueError
            If the ROI is out of bounds or has invalid dimensions.
        """
        if roi.width_px <= 0 or roi.height_px <= 0:
            raise ValueError(
                f"ROI dimensions must be positive: "
                f"width_px={roi.width_px}, height_px={roi.height_px}"
            )
        if roi.x_start_px < 0 or roi.y_start_px < 0:
            raise ValueError(
                f"ROI origin must be non-negative: "
                f"x_start_px={roi.x_start_px}, y_start_px={roi.y_start_px}"
            )
        if roi.x_start_px + roi.width_px > map_width_px:
            raise ValueError(
                f"ROI exceeds map width: "
                f"x_start_px({roi.x_start_px}) + width_px({roi.width_px}) = "
                f"{roi.x_start_px + roi.width_px} > map_width_px({map_width_px})"
            )
        if roi.y_start_px + roi.height_px > map_height_px:
            raise ValueError(
                f"ROI exceeds map height: "
                f"y_start_px({roi.y_start_px}) + height_px({roi.height_px}) = "
                f"{roi.y_start_px + roi.height_px} > map_height_px({map_height_px})"
            )

    def _element_setting_to_region(
        self,
        setting: BrukerEDSElementMapSetting,
        element_index: int = 0,
    ) -> TRTElementRegion:
        line_bytes = setting.line.encode("ascii", errors="ignore")[:9]
        line_buf = line_bytes.ljust(10, b"\x00")

        if setting.display_rgb is None:
            r, g, b = DEFAULT_EDS_ELEMENT_COLORS[
                element_index % len(DEFAULT_EDS_ELEMENT_COLORS)
            ]
        else:
            r, g, b = setting.display_rgb

        region = TRTElementRegion()
        region.Element = int(setting.atomic_number)
        region.IdentifierLength = len(line_bytes)
        region.Line = line_buf
        region.Energy = float(setting.energy_keV)
        region.Width = float(setting.width)
        region.R = int(r)
        region.G = int(g)
        region.B = int(b)
        return region

    def build_hymap_profile_settings(
        self,
        settings: BrukerEDSProfileMapSettings,
    ) -> TRTHyMapProfileSettings:
        if len(settings.elements) > 51:
            raise ValueError(
                "Bruker HyperMap profile supports at most 51 element regions"
            )

        profile_settings = TRTHyMapProfileSettings()
        profile_settings.Version = 1
        profile_settings.ElementCount = int(len(settings.elements))

        for idx, element in enumerate(settings.elements):
            profile_settings.ElementRegions[idx] = self._element_setting_to_region(
                element,
                element_index=idx,
            )

        profile_settings.ImageFilter = int(settings.image_filter)
        profile_settings.MapFilter = int(settings.map_filter)
        profile_settings.MapFilterWidth = int(settings.map_filter_width)
        profile_settings.ColorMixMethod = int(settings.color_mix_method)
        profile_settings.Brightness = float(settings.brightness)
        profile_settings.Gamma = float(settings.gamma)
        profile_settings.ColorSaturation = float(settings.color_saturation)
        profile_settings.AbsoluteScaling = bool(settings.absolute_scaling)
        profile_settings.Normalization = bool(settings.normalization)
        profile_settings.Deconvolution = bool(settings.deconvolution)

        return profile_settings

    def create_hymap_profile(
        self,
        settings: BrukerEDSProfileMapSettings,
        initial_bufsize: int = 64 * 1024,
    ) -> str:
        """
        Create XML serialized HyperMap profile using Bruker API.
        """
        profile_settings = self.build_hymap_profile_settings(settings)

        for size_guess in (initial_bufsize, 256 * 1024, 1024 * 1024):
            buf = ct.create_string_buffer(size_guess)
            bufsize = c_i32(size_guess)

            rc = self._session.dll.HyMapCreateProfile(
                ct.byref(profile_settings),
                buf,
                ct.byref(bufsize),
            )

            if rc == 0:
                return buf.value.decode(errors="replace")

            # IFC_ERROR_RESULT_BUFFER_INSUFFICIENT = -11
            if rc == -11:
                continue

            self._session._check(rc, "HyMapCreateProfile")

        raise RuntimeError("HyMapCreateProfile failed: buffer insufficient after 1 MB")

    def stop_map(self, discard: bool = False) -> None:
        """Stop the current HyperMap acquisition via ``HyMapStop``.

        This is exposed primarily for operator/recovery scripts. During normal
        acquisition, ``acquire_map`` and ``acquire_map_with_profile`` call it
        automatically after ESPRIT reports that acquisition is no longer running.
        """
        rc = self._session.dll.HyMapStop(self._session.cid, bool(discard))
        self._session._check(rc, "HyMapStop")

    def _best_effort_stop_map(
        self,
        discard: bool = True,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Attempt to stop a running HyperMap without masking the original error."""
        try:
            if log_fn:
                log_fn("Attempting best-effort HyMapStop after acquisition error")
            self.stop_map(discard=discard)
        except Exception as stop_exc:
            if log_fn:
                log_fn(f"Best-effort HyMapStop failed: {stop_exc}")

    def acquire_map_with_profile(
        self,
        settings: BrukerEDSProfileMapSettings,
        poll_interval_s: float = 0.5,
        max_wait_s: float = 600.0,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> BrukerMapOutputs:
        """
        Acquire an EDS map using a generated Bruker HyperMap profile.

        This is the path for Python-selected EDS map elements.

        Parameters
        ----------
        settings : BrukerEDSProfileMapSettings
            Map acquisition settings.
        poll_interval_s : float
            Seconds between progress polls.
        max_wait_s : float
            Maximum time to wait before raising TimeoutError.
        log_fn : callable, optional
            Logging callback. Called with progress messages during acquisition.

        Note
        ----
        HyMapStartWithProfile does not expose RealTime in the header signature we have.
        Behavior should be validated empirically.
        """
        # SAFETY: validate ROI before any DLL/API call. Out-of-bounds ROIs have
        # been observed to freeze ESPRIT when passed to Bruker acquisition calls.
        if settings.roi is not None:
            self._validate_roi(settings.roi, settings.width_px, settings.height_px)

        # Configure scan/image dimensions first
        rc = self._session.dll.ImageSetConfiguration(
            self._session.cid,
            int(settings.width_px),
            int(settings.height_px),
            int(settings.pixel_time_us),
            True,
            False,
        )
        self._session._check(rc, "ImageSetConfiguration")

        profile_xml = self.create_hymap_profile(settings)
        profile_buf = ct.create_string_buffer(
            profile_xml.encode("ascii", errors="ignore") + b"\x00"
        )

        # Build region from ROI if provided, otherwise full-frame
        if settings.roi is not None:
            self._validate_roi(settings.roi, settings.width_px, settings.height_px)
            region, segments_keepalive = self._build_rect_region(
                width_px=settings.roi.width_px,
                height_px=settings.roi.height_px,
                x_start_px=settings.roi.x_start_px,
                y_start_px=settings.roi.y_start_px,
            )
            if log_fn:
                log_fn(
                    f"Using ROI: x={settings.roi.x_start_px}, "
                    f"y={settings.roi.y_start_px}, "
                    f"w={settings.roi.width_px}, h={settings.roi.height_px}"
                )
        else:
            region, segments_keepalive = self._build_rect_region(
                width_px=settings.width_px,
                height_px=settings.height_px,
                x_start_px=0,
                y_start_px=0,
            )

        rc = self._session.dll.HyMapStartWithProfile(
            self._session.cid,
            int(settings.spu_device),
            int(settings.pixel_time_us),
            region,
            profile_buf,
        )
        self._session._check(rc, "HyMapStartWithProfile")

        # Keep references alive until after start call.
        _ = segments_keepalive, profile_buf

        if log_fn:
            log_fn(
                f"Profile map acquisition started: "
                f"{settings.width_px}x{settings.height_px}, "
                f"pixel_time={settings.pixel_time_us} us, "
                f"{len(settings.elements)} elements"
            )

        t0 = time.time()
        try:
            while True:
                progress = self.get_map_progress()
                if not progress.running:
                    break

                elapsed = time.time() - t0
                if log_fn:
                    eta_s = None
                    if progress.percent_complete > 0:
                        eta_s = (
                            elapsed
                            / progress.percent_complete
                            * (100.0 - progress.percent_complete)
                        )
                    eta_str = f", ETA={eta_s:.1f}s" if eta_s is not None else ""
                    log_fn(
                        f"Map progress: {progress.percent_complete:.1f}%, "
                        f"line={progress.current_line}, "
                        f"elapsed={elapsed:.1f}s{eta_str}"
                    )

                if elapsed > max_wait_s:
                    raise TimeoutError(
                        f"Profile map acquisition exceeded {max_wait_s} s"
                    )

                time.sleep(poll_interval_s)
        except BaseException:
            self._best_effort_stop_map(discard=True, log_fn=log_fn)
            raise

        elapsed_total = time.time() - t0
        if log_fn:
            log_fn(f"Profile map acquisition complete: elapsed={elapsed_total:.1f}s")

        self.stop_map(discard=False)

        output_bcf = str(Path(settings.output_bcf_path))
        rc = self._session.dll.HyMapSaveToFile(self._session.cid, output_bcf.encode())
        self._session._check(rc, "HyMapSaveToFile")

        output_image: Optional[str] = None
        if settings.output_image_path and settings.output_image_format:
            output_image = self.save_map_image(
                output_path=settings.output_image_path,
                fmt=settings.output_image_format,
                image_channel=0,
            )

        return BrukerMapOutputs(
            output_bcf_path=output_bcf,
            output_image_path=output_image,
        )

    def get_map_progress(self) -> BrukerMapProgress:
        running = c_bool(True)
        state = c_dbl(0.0)
        line = c_i32(0)

        rc = self._session.dll.HyMapGetStateEx(
            self._session.cid,
            ct.byref(running),
            ct.byref(state),
            ct.byref(line),
        )
        self._session._check(rc, "HyMapGetStateEx")

        return BrukerMapProgress(
            running=bool(running.value),
            percent_complete=float(state.value),
            current_line=int(line.value),
        )

    def acquire_map(
        self,
        settings: BrukerEDSMapSettings,
        poll_interval_s: float = 0.5,
        max_wait_s: float = 600.0,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> BrukerMapOutputs:
        # SAFETY: validate ROI before any DLL/API call. Out-of-bounds ROIs have
        # been observed to freeze ESPRIT when passed to Bruker acquisition calls.
        if settings.roi is not None:
            self._validate_roi(settings.roi, settings.width_px, settings.height_px)

        rc = self._session.dll.ImageSetConfiguration(
            self._session.cid,
            int(settings.width_px),
            int(settings.height_px),
            int(settings.pixel_time_us),
            True,
            False,
        )
        self._session._check(rc, "ImageSetConfiguration")

        # Use HyMapStartEx with region if ROI is specified, otherwise HyMapStart
        if settings.roi is not None:
            self._validate_roi(settings.roi, settings.width_px, settings.height_px)
            region, segments_keepalive = self._build_rect_region(
                width_px=settings.roi.width_px,
                height_px=settings.roi.height_px,
                x_start_px=settings.roi.x_start_px,
                y_start_px=settings.roi.y_start_px,
            )
            rc = self._session.dll.HyMapStartEx(
                self._session.cid,
                int(settings.spu_device),
                int(settings.pixel_time_us),
                int(settings.real_time_s),
                region,
            )
            self._session._check(rc, "HyMapStartEx")
            # Keep segment array alive
            _ = segments_keepalive

            if log_fn:
                log_fn(
                    f"Using ROI: x={settings.roi.x_start_px}, "
                    f"y={settings.roi.y_start_px}, "
                    f"w={settings.roi.width_px}, h={settings.roi.height_px}"
                )
        else:
            rc = self._session.dll.HyMapStart(
                self._session.cid,
                int(settings.spu_device),
                int(settings.pixel_time_us),
                int(settings.real_time_s),
            )
            self._session._check(rc, "HyMapStart")

        if log_fn:
            log_fn(
                f"Simple map acquisition started: "
                f"{settings.width_px}x{settings.height_px}, "
                f"pixel_time={settings.pixel_time_us} us, "
                f"real_time={settings.real_time_s} s"
            )

        t0 = time.time()
        try:
            while True:
                progress = self.get_map_progress()
                if not progress.running:
                    break

                elapsed = time.time() - t0
                if log_fn:
                    eta_s = None
                    if progress.percent_complete > 0:
                        eta_s = (
                            elapsed
                            / progress.percent_complete
                            * (100.0 - progress.percent_complete)
                        )
                    eta_str = f", ETA={eta_s:.1f}s" if eta_s is not None else ""
                    log_fn(
                        f"Map progress: {progress.percent_complete:.1f}%, "
                        f"line={progress.current_line}, "
                        f"elapsed={elapsed:.1f}s{eta_str}"
                    )

                if elapsed > max_wait_s:
                    raise TimeoutError(f"Map acquisition exceeded {max_wait_s} s")

                time.sleep(poll_interval_s)
        except BaseException:
            self._best_effort_stop_map(discard=True, log_fn=log_fn)
            raise

        elapsed_total = time.time() - t0
        if log_fn:
            log_fn(f"Simple map acquisition complete: elapsed={elapsed_total:.1f}s")

        self.stop_map(discard=False)

        output_bcf = str(Path(settings.output_bcf_path))
        rc = self._session.dll.HyMapSaveToFile(self._session.cid, output_bcf.encode())
        self._session._check(rc, "HyMapSaveToFile")

        output_image: Optional[str] = None
        if settings.output_image_path and settings.output_image_format:
            output_image = self.save_map_image(
                output_path=settings.output_image_path,
                fmt=settings.output_image_format,
                image_channel=0,
            )

        return BrukerMapOutputs(
            output_bcf_path=output_bcf,
            output_image_path=output_image,
        )

    def save_map_image(
        self, output_path: str, fmt: str = "bmp", image_channel: int = 0
    ) -> str:
        size = c_u32(8 * 1024 * 1024)
        buf = (ct.c_uint8 * size.value)()

        rc = self._session.dll.HyMapGetImage(
            self._session.cid,
            fmt.encode(),
            int(image_channel),
            ct.cast(buf, ct.c_void_p),
            ct.byref(size),
        )
        self._session._check(rc, "HyMapGetImage")

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        data = ct.string_at(ct.addressof(buf), size.value)
        with open(out_path, "wb") as f:
            f.write(data)

        return str(out_path)

    def save_element_image(
        self,
        output_path: str,
        element_index: int,
        fmt: str = "bmp",
        initial_buffer_size: int = 8 * 1024 * 1024,
    ) -> str:
        """
        Save a rendered element image from the current HyperMap.

        Notes
        -----
        Element indexing may be Bruker-version/context dependent.
        Test index 0, 1, 2 after a known two-element profile map.
        """
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        for size_guess in (initial_buffer_size, 32 * 1024 * 1024, 128 * 1024 * 1024):
            size = c_u32(size_guess)
            buf = (ct.c_uint8 * size.value)()

            rc = self._session.dll.HyMapGetElementImage(
                self._session.cid,
                fmt.encode(),
                int(element_index),
                ct.cast(buf, ct.c_void_p),
                ct.byref(size),
            )

            if rc == 0:
                data = ct.string_at(ct.addressof(buf), size.value)
                with open(out_path, "wb") as f:
                    f.write(data)
                return str(out_path)

            # IFC_ERROR_RESULT_BUFFER_INSUFFICIENT = -11
            if rc == -11:
                continue

            self._session._check(rc, "HyMapGetElementImage")

        raise RuntimeError("HyMapGetElementImage failed: buffer insufficient")

    def save_mixed_map_image(
        self,
        output_path: str,
        fmt: str = "bmp",
        initial_buffer_size: int = 8 * 1024 * 1024,
    ) -> str:
        """
        Save rendered mixed RGB element map from current HyperMap.
        """
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        for size_guess in (initial_buffer_size, 32 * 1024 * 1024, 128 * 1024 * 1024):
            size = c_u32(size_guess)
            buf = (ct.c_uint8 * size.value)()

            rc = self._session.dll.HyMapGetMixedMapImage(
                self._session.cid,
                fmt.encode(),
                ct.cast(buf, ct.c_void_p),
                ct.byref(size),
            )

            if rc == 0:
                data = ct.string_at(ct.addressof(buf), size.value)
                with open(out_path, "wb") as f:
                    f.write(data)
                return str(out_path)

            if rc == -11:
                continue

            self._session._check(rc, "HyMapGetMixedMapImage")

        raise RuntimeError("HyMapGetMixedMapImage failed: buffer insufficient")
