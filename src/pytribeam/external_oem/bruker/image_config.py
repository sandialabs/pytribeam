"""
Bruker Image Configuration Module
==================================

Provides methods to query the current image/scan device configuration
and field width from the Bruker ESPRIT API.

These are useful for:
- Verifying that ImageSetConfiguration was accepted as requested
- Diagnosing resolution-related failures
- Determining physical scan dimensions for ROI calculations
"""

import ctypes as ct
from typing import Callable, Optional

from pytribeam.external_oem.bruker.bindings import bind_image_config
from pytribeam.external_oem.bruker.ctypes_types import c_bool, c_dbl, c_u32
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.types import (
    BrukerFieldWidth,
    BrukerImageConfiguration,
)


class BrukerImageConfigController:
    """Controller for querying image/scan device configuration.

    Parameters
    ----------
    session : BrukerSession
        An active, connected Bruker session.
    """

    def __init__(self, session: BrukerSession):
        self._session = session
        bind_image_config(self._session.dll)

    def get_image_configuration(self) -> BrukerImageConfiguration:
        """Read current image device configuration from ESPRIT.

        Returns the currently active image configuration, which may differ
        from what was requested via ImageSetConfiguration if the hardware
        does not support the requested values exactly.

        Returns
        -------
        BrukerImageConfiguration
            Current width, height, average (pixel time), and channel states.
        """
        width = c_u32(0)
        height = c_u32(0)
        average = c_u32(0)
        ch1 = c_bool(False)
        ch2 = c_bool(False)

        rc = self._session.dll.ImageGetConfiguration(
            self._session.cid,
            ct.byref(width),
            ct.byref(height),
            ct.byref(average),
            ct.byref(ch1),
            ct.byref(ch2),
        )
        self._session._check(rc, "ImageGetConfiguration")

        return BrukerImageConfiguration(
            width_px=int(width.value),
            height_px=int(height.value),
            average=int(average.value),
            ch1=bool(ch1.value),
            ch2=bool(ch2.value),
        )

    def get_field_width_um(self) -> float:
        """Read the image field width from scan settings and SEM magnification.

        Returns
        -------
        float
            Field width in micrometers.
        """
        field_width = c_dbl(0.0)

        rc = self._session.dll.ImageGetFieldWidth(
            self._session.cid,
            ct.byref(field_width),
        )
        self._session._check(rc, "ImageGetFieldWidth")

        return float(field_width.value)

    def log_configuration_comparison(
        self,
        requested_width: int,
        requested_height: int,
        requested_pixel_time_us: int,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> BrukerImageConfiguration:
        """Read back configuration and log comparison with requested values.

        This is a convenience method to call after ImageSetConfiguration
        to verify the hardware accepted the requested settings.

        Parameters
        ----------
        requested_width : int
            Width in pixels that was requested.
        requested_height : int
            Height in pixels that was requested.
        requested_pixel_time_us : int
            Pixel time in microseconds that was requested.
        log_fn : callable, optional
            Logging callback. If None, no logging is performed.

        Returns
        -------
        BrukerImageConfiguration
            The actual accepted configuration.
        """
        actual = self.get_image_configuration()

        if log_fn:
            width_match = actual.width_px == requested_width
            height_match = actual.height_px == requested_height
            avg_match = actual.average == requested_pixel_time_us

            log_fn(
                f"Image config comparison: "
                f"width={requested_width}->{actual.width_px} "
                f"({'OK' if width_match else 'MISMATCH'}), "
                f"height={requested_height}->{actual.height_px} "
                f"({'OK' if height_match else 'MISMATCH'}), "
                f"average/pixel_time={requested_pixel_time_us}->{actual.average} "
                f"({'OK' if avg_match else 'MISMATCH'}), "
                f"ch1={actual.ch1}, ch2={actual.ch2}"
            )

            if not (width_match and height_match):
                log_fn(
                    "WARNING: Accepted image dimensions differ from requested. "
                    "This may indicate hardware limitations or unsupported resolution."
                )

        return actual
