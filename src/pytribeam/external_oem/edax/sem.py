#!/usr/bin/python3
"""
EDAX SEM Control Module
=======================

Wrapper for the SEM commands the EDAX IPAPI exposes (sections 2.4.34 - 2.4.42).

These commands are documented under the EBSD heading but act on the microscope
rather than on either detector, so they live in their own controller. On a
TriBeam the microscope is normally driven through AutoScript instead; this
interface matters when EDAX must take external beam control, for example while
capturing a background image.

Classes
-------
EdaxSemController
    SEM magnification, beam control, image geometry, pretilt, and beam position.
"""

# Default python modules
from typing import Optional

# Local scripts
from pytribeam.external_oem.edax.client import EdaxClient
from pytribeam.external_oem.edax.types import EdaxCommand, EdaxSemState


class EdaxSemController:
    """
    SEM magnification, beam control, image geometry, pretilt, and beam position.

    Parameters
    ----------
    client : EdaxClient
        A connected IPAPI client.
    """

    def __init__(self, client: EdaxClient):
        self._client = client

    @property
    def client(self) -> EdaxClient:
        """Return the IPAPI client this controller drives."""
        return self._client

    # -- magnification -------------------------------------------------------

    def magnification(self, timeout_s: Optional[float] = None) -> int:
        """Return the SEM magnification."""
        return self._client.query_int(
            EdaxCommand.SEM_GET_MAGNIFICATION, timeout_s=timeout_s
        )

    def set_magnification(
        self, magnification: int, timeout_s: Optional[float] = None
    ) -> bool:
        """
        Set the SEM magnification.

        Parameters
        ----------
        magnification : int
            The requested magnification.
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        bool
            True on success.
        """
        self._client.execute(
            EdaxCommand.SEM_SET_MAGNIFICATION, int(magnification), timeout_s=timeout_s
        )
        return True

    # -- external beam control ------------------------------------------------

    def external_beam_control(self, timeout_s: Optional[float] = None) -> bool:
        """Return True when the SEM is under external beam control."""
        return self._client.query_bool(
            EdaxCommand.SEM_GET_EXTERNAL_BEAM_CONTROL, timeout_s=timeout_s
        )

    def set_external_beam_control(
        self, enabled: bool, timeout_s: Optional[float] = None
    ) -> bool:
        """
        Hand beam control to, or take it back from, the EDAX application.

        Parameters
        ----------
        enabled : bool
            True to place the SEM under external beam control.
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        bool
            True on success.
        """
        self._client.execute(
            EdaxCommand.SEM_SET_EXTERNAL_BEAM_CONTROL, enabled, timeout_s=timeout_s
        )
        return True

    # -- image geometry -------------------------------------------------------

    def image_width_px(self, timeout_s: Optional[float] = None) -> int:
        """Return the SEM image width in pixels."""
        return self._client.query_int(
            EdaxCommand.SEM_GET_IMAGE_WIDTH, timeout_s=timeout_s
        )

    def image_height_px(self, timeout_s: Optional[float] = None) -> int:
        """Return the SEM image height in pixels."""
        return self._client.query_int(
            EdaxCommand.SEM_GET_IMAGE_HEIGHT, timeout_s=timeout_s
        )

    def set_beam_location_px(
        self, x_px: int, y_px: int, timeout_s: Optional[float] = None
    ) -> bool:
        """
        Park the beam at a pixel location in the SEM image.

        Parameters
        ----------
        x_px : int
            X location in pixels.
        y_px : int
            Y location in pixels.
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        bool
            True on success.
        """
        self._client.execute(
            EdaxCommand.SEM_SET_BEAM_LOCATION,
            int(x_px),
            int(y_px),
            timeout_s=timeout_s,
        )
        return True

    # -- pretilt --------------------------------------------------------------

    def pretilt_deg(self, timeout_s: Optional[float] = None) -> float:
        """Return the pretilt holder angle in degrees."""
        return self._client.query_float(
            EdaxCommand.SEM_GET_PRETILT_ANGLE, timeout_s=timeout_s
        )

    def set_pretilt_deg(self, angle_deg: float, timeout_s: Optional[float] = None):
        """
        Set the pretilt holder angle.

        Parameters
        ----------
        angle_deg : float
            Pretilt holder angle in degrees.
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        bool
            True on success.
        """
        self._client.execute(
            EdaxCommand.SEM_SET_PRETILT_ANGLE, angle_deg, timeout_s=timeout_s
        )
        return True

    # -- aggregate ------------------------------------------------------------

    def state(self, timeout_s: Optional[float] = None) -> EdaxSemState:
        """
        Read every SEM value the IPAPI exposes in one call.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout for each command, in seconds.

        Returns
        -------
        EdaxSemState
            The SEM state as EDAX sees it.
        """
        return EdaxSemState(
            magnification=self.magnification(timeout_s=timeout_s),
            external_beam_control=self.external_beam_control(timeout_s=timeout_s),
            image_width_px=self.image_width_px(timeout_s=timeout_s),
            image_height_px=self.image_height_px(timeout_s=timeout_s),
            pretilt_deg=self.pretilt_deg(timeout_s=timeout_s),
        )
