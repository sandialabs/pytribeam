import ctypes as ct
import time
from pathlib import Path
from typing import Optional

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

    def acquire_map_with_profile(
        self,
        settings: BrukerEDSProfileMapSettings,
        poll_interval_s: float = 0.5,
        max_wait_s: float = 600.0,
    ) -> BrukerMapOutputs:
        """
        Acquire an EDS map using a generated Bruker HyperMap profile.

        This is the path for Python-selected EDS map elements.

        Note
        ----
        HyMapStartWithProfile does not expose RealTime in the header signature we have.
        Behavior should be validated empirically.
        """
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

        t0 = time.time()
        while True:
            progress = self.get_map_progress()
            if not progress.running:
                break

            if (time.time() - t0) > max_wait_s:
                raise TimeoutError(f"Profile map acquisition exceeded {max_wait_s} s")

            time.sleep(poll_interval_s)

        rc = self._session.dll.HyMapStop(self._session.cid, False)
        self._session._check(rc, "HyMapStop")

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
    ) -> BrukerMapOutputs:
        rc = self._session.dll.ImageSetConfiguration(
            self._session.cid,
            int(settings.width_px),
            int(settings.height_px),
            int(settings.pixel_time_us),
            True,
            False,
        )
        self._session._check(rc, "ImageSetConfiguration")

        rc = self._session.dll.HyMapStart(
            self._session.cid,
            int(settings.spu_device),
            int(settings.pixel_time_us),
            int(settings.real_time_s),
        )
        self._session._check(rc, "HyMapStart")

        t0 = time.time()
        while True:
            progress = self.get_map_progress()
            if not progress.running:
                break

            if (time.time() - t0) > max_wait_s:
                raise TimeoutError(f"Map acquisition exceeded {max_wait_s} s")

            time.sleep(poll_interval_s)

        rc = self._session.dll.HyMapStop(self._session.cid, False)
        self._session._check(rc, "HyMapStop")

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

    def get_element_data_bytes(
        self,
        element_index: int,
        initial_buffer_size: int = 8 * 1024 * 1024,
    ) -> bytes:
        """
        Return raw element data bytes from current HyperMap.

        We are not parsing this yet. This helps determine whether numeric
        element planes can be extracted directly.
        """
        for size_guess in (initial_buffer_size, 32 * 1024 * 1024, 128 * 1024 * 1024):
            size = c_u32(size_guess)
            buf = (ct.c_uint8 * size.value)()

            rc = self._session.dll.HyMapGetElementData(
                self._session.cid,
                int(element_index),
                ct.cast(buf, ct.c_void_p),
                ct.byref(size),
            )

            if rc == 0:
                return ct.string_at(ct.addressof(buf), size.value)

            if rc == -11:
                continue

            self._session._check(rc, "HyMapGetElementData")

        raise RuntimeError("HyMapGetElementData failed: buffer insufficient")

    def get_element_data_array(
        self,
        element_index: int,
        width_px: int,
        height_px: int,
        dtype: str = "uint16",
    ):
        """
        Return numeric element map plane as a NumPy array.

        Empirical Bruker behavior:
        - HyMapGetElementData returns width * height * 2 bytes
        - dtype is uint16
        - shape is (height_px, width_px)
        - element_index is zero-based and follows settings.elements order
        """
        import numpy as np

        data = self.get_element_data_bytes(element_index=element_index)

        np_dtype = np.dtype(dtype)
        arr = np.frombuffer(data, dtype=np_dtype)

        expected_pixels = int(width_px) * int(height_px)
        if arr.size != expected_pixels:
            raise ValueError(
                f"Element data size mismatch for index {element_index}: "
                f"got {arr.size} pixels, expected {expected_pixels}; "
                f"bytes={len(data)}, dtype={np_dtype}"
            )

        return arr.reshape((int(height_px), int(width_px))).copy()

    def read_profile_element_maps(
        self,
        settings: BrukerEDSProfileMapSettings,
        dtype: str = "uint16",
    ):
        """
        Read all requested element maps from the current HyperMap.

        Returns
        -------
        tuple[np.ndarray, ...]
            One array per requested element, in settings.elements order.

        Notes
        -----
        Bruker may expose one extra all-zero plane after the requested elements.
        We intentionally ignore it and read only 0..len(elements)-1.
        """
        arrays = []

        for idx, _element in enumerate(settings.elements):
            arr = self.get_element_data_array(
                element_index=idx,
                width_px=settings.width_px,
                height_px=settings.height_px,
                dtype=dtype,
            )
            arrays.append(arr)

        return tuple(arrays)

    def save_profile_element_maps_npy(
        self,
        settings: BrukerEDSProfileMapSettings,
        output_dir: str,
        prefix: Optional[str] = None,
        dtype: str = "uint16",
    ):
        """
        Save all requested element maps as .npy arrays.

        Returns
        -------
        tuple[str, ...]
            Paths to saved .npy files.
        """
        import json
        from pathlib import Path

        import numpy as np

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if prefix is None:
            prefix = settings.name

        arrays = self.read_profile_element_maps(settings=settings, dtype=dtype)

        paths = []
        metadata = []

        for idx, (element, arr) in enumerate(zip(settings.elements, arrays)):
            safe_line = element.line.replace(" ", "_")
            fname = f"{prefix}_element_{idx}_Z{element.atomic_number}_{safe_line}.npy"
            path = out_dir / fname

            np.save(path, arr)
            paths.append(str(path))

            metadata.append(
                {
                    "element_index": idx,
                    "atomic_number": int(element.atomic_number),
                    "line": element.line,
                    "energy_keV": float(element.energy_keV),
                    "width": float(element.width),
                    "shape": list(arr.shape),
                    "dtype": str(arr.dtype),
                    "min": int(arr.min()),
                    "max": int(arr.max()),
                    "sum": int(arr.sum()),
                    "nonzero": int((arr != 0).sum()),
                    "path": str(path),
                }
            )

        metadata_path = out_dir / f"{prefix}_element_maps_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        return tuple(paths)
