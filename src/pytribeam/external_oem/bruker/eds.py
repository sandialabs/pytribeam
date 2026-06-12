import time
import ctypes as ct
from pathlib import Path
from typing import Optional

from .bindings import bind_eds
from .ctypes_types import c_bool, c_dbl, c_i32, c_u32
from .session import BrukerSession
from .types import BrukerEDSMapSettings, BrukerMapProgress, BrukerMapOutputs


class BrukerEDSController:
    def __init__(self, session: BrukerSession):
        self._session = session
        bind_eds(self._session.dll)

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
