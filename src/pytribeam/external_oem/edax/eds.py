#!/usr/bin/python3
"""
EDAX EDS Module
===============

Typed wrapper for the EDS half of the EDAX IPAPI: mapping commands
(section 2.2) and mapping parameters (section 2.3).

:class:`EdaxEdsController` inherits the setup/collection/status/project
behavior shared with EBSD from
:class:`pytribeam.external_oem.edax.base.EdaxMappingController` and adds the
EDS detector slide, detector cooling, and EDS scan geometry.

Classes
-------
EdaxEdsController
    EDS mapping, detector motion, cooling, and scan configuration.
"""

# Default python modules
import time
from pathlib import Path
from typing import Optional

# Local scripts
from pytribeam.external_oem.edax.base import EdaxMappingController
from pytribeam.external_oem.edax.errors import EdaxTimeoutError
from pytribeam.external_oem.edax.types import (
    EdaxCommand,
    EdaxDetectorSlideStatus,
    EdaxDetectorStatus,
    EdaxEdsMapParams,
    EdaxEvent,
)

DEFAULT_SLIDE_TIMEOUT_S = 120.0
DEFAULT_SLIDE_POLL_S = 2.0


class EdaxEdsController(EdaxMappingController):
    """
    EDS mapping, detector motion, cooling, and scan configuration.

    Parameters
    ----------
    client : EdaxClient
        A connected IPAPI client.
    """

    SETUP_START = EdaxCommand.EDS_SETUP_START
    SETUP_STOP = EdaxCommand.EDS_SETUP_STOP
    SETUP_ABORT = EdaxCommand.EDS_SETUP_ABORT
    COLLECTION_START = EdaxCommand.EDS_COLLECTION_START
    COLLECTION_STOP = EdaxCommand.EDS_COLLECTION_STOP
    COLLECTION_RESUME = EdaxCommand.EDS_COLLECTION_RESUME
    COLLECTION_PAUSE = EdaxCommand.EDS_COLLECTION_PAUSE
    GET_MAP_DURATION = EdaxCommand.EDS_GET_MAP_DURATION
    GET_MAP_STATUS = EdaxCommand.EDS_GET_MAP_STATUS
    GET_SYSTEM_ISAPPSTARTED = EdaxCommand.EDS_GET_SYSTEM_ISAPPSTARTED
    SET_SYSTEM_REMOTEACCESSTYPE = EdaxCommand.EDS_SET_SYSTEM_REMOTEACCESSTYPE
    SET_SYSTEM_PROJECTINFO = EdaxCommand.EDS_SET_SYSTEM_PROJECTINFO
    SET_SYSTEM_PROJECTINFO_EXT = EdaxCommand.EDS_SET_SYSTEM_PROJECTINFO_EXT
    COLLECTION_COMPLETE_EVENT = EdaxEvent.EDS_COLLECTION_COMPLETE

    DETECTOR_NAME = "EDS"

    # -- mapping parameters (section 2.3) ------------------------------------

    def apply_map_parameters(
        self,
        params: EdaxEdsMapParams,
        timeout_s: Optional[float] = None,
    ) -> bool:
        """
        Apply every non-null field of an EDS parameter set.

        Fields left as ``None`` are not sent, so the corresponding EDAX
        settings keep whatever value the application already holds.

        Parameters
        ----------
        params : EdaxEdsMapParams
            The parameters to apply.
        timeout_s : float, optional
            Response timeout for each command, in seconds.

        Returns
        -------
        bool
            True on success.
        """
        ordered = (
            (EdaxCommand.EDS_SET_FOLDERPATH, params.folder_path),
            (EdaxCommand.EDS_SET_EDSCHANNEL, params.eds_channel),
            (EdaxCommand.EDS_SET_NUMFRAMES, params.num_frames),
            (EdaxCommand.EDS_SET_NUMPOINTS, params.num_points),
            (EdaxCommand.EDS_SET_NUMLINES, params.num_lines),
            (EdaxCommand.EDS_SET_PRESETDWELL, params.preset_dwell_us),
            (EdaxCommand.EDS_SET_EDSNUMCHAN, params.eds_num_channels),
            (EdaxCommand.EDS_SET_BYTESPERCHANNEL, params.bytes_per_channel),
            (EdaxCommand.EDS_SET_IPD, params.inter_pixel_delay),
            (EdaxCommand.EDS_SET_NUMREADS, params.num_reads),
        )
        for command, value in ordered:
            if value is None:
                continue
            self._client.execute(command, value, timeout_s=timeout_s)
        return True

    def map_parameters(self, timeout_s: Optional[float] = None) -> EdaxEdsMapParams:
        """
        Read the full EDS mapping parameter set back from the application.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout for each command, in seconds.

        Returns
        -------
        EdaxEdsMapParams
            The parameters currently configured in the EDAX application.
        """
        client = self._client
        return EdaxEdsMapParams(
            folder_path=Path(
                client.query(EdaxCommand.EDS_GET_FOLDERPATH, timeout_s=timeout_s)
            ),
            eds_channel=client.query_int(
                EdaxCommand.EDS_GET_EDSCHANNEL, timeout_s=timeout_s
            ),
            num_frames=client.query_int(
                EdaxCommand.EDS_GET_NUMFRAMES, timeout_s=timeout_s
            ),
            num_points=client.query_int(
                EdaxCommand.EDS_GET_NUMPOINTS, timeout_s=timeout_s
            ),
            num_lines=client.query_int(
                EdaxCommand.EDS_GET_NUMLINES, timeout_s=timeout_s
            ),
            preset_dwell_us=client.query_float(
                EdaxCommand.EDS_GET_PRESETDWELL, timeout_s=timeout_s
            ),
            eds_num_channels=client.query_int(
                EdaxCommand.EDS_GET_EDSNUMCHAN, timeout_s=timeout_s
            ),
            bytes_per_channel=client.query_int(
                EdaxCommand.EDS_GET_BYTESPERCHANNEL, timeout_s=timeout_s
            ),
            inter_pixel_delay=client.query_int(
                EdaxCommand.EDS_GET_IPD, timeout_s=timeout_s
            ),
            num_reads=client.query_int(
                EdaxCommand.EDS_GET_NUMREADS, timeout_s=timeout_s
            ),
        )

    # -- detector status (section 2.2.10, 2.2.20) ----------------------------

    def detector_status(self, timeout_s: Optional[float] = None) -> EdaxDetectorStatus:
        """
        Return whether the EDS detector is ready for collection.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        EdaxDetectorStatus
            ``READY`` or ``NOT_READY``.

        Raises
        ------
        EdaxResponseError
            If the IPAPI returns an unrecognized status.
        """
        payload = self._client.query(
            EdaxCommand.EDS_GET_SYSTEM_DETECTOR_STATUS, timeout_s=timeout_s
        )
        normalized = payload.strip().lower().replace(" ", "").replace("_", "")
        try:
            return EdaxDetectorStatus(normalized)
        except ValueError:
            return EdaxDetectorStatus.NOT_READY

    def slide_status(
        self, timeout_s: Optional[float] = None
    ) -> EdaxDetectorSlideStatus:
        """
        Return the EDS detector slide position status.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        EdaxDetectorSlideStatus
            The reported slide status, or ``UNKNOWN`` when the IPAPI returns a
            value this wrapper does not recognize. The IPAPI documents this
            command as returning an enum value, so a bare integer is accepted
            as well as a name.
        """
        payload = self._client.query(
            EdaxCommand.EDS_GET_DETECTOR_STATUS, timeout_s=timeout_s
        )
        normalized = payload.strip().lower().replace(" ", "").replace("_", "")

        # The IPAPI documents an enum value here rather than a string.
        numeric = {
            "0": EdaxDetectorSlideStatus.SLIDE_OUT,
            "1": EdaxDetectorSlideStatus.SLIDE_IN,
            "100": EdaxDetectorSlideStatus.UNKNOWN,
        }
        if normalized in numeric:
            return numeric[normalized]

        try:
            return EdaxDetectorSlideStatus(normalized)
        except ValueError:
            return EdaxDetectorSlideStatus.UNKNOWN

    # -- detector motion (section 2.2.16 - 2.2.17) ---------------------------

    def insert_detector(
        self,
        timeout_s: float = DEFAULT_SLIDE_TIMEOUT_S,
        poll_interval_s: float = DEFAULT_SLIDE_POLL_S,
        quiet: bool = False,
    ) -> bool:
        """
        Insert the EDS detector slide and wait until it reports ``SLIDE_IN``.

        Returns immediately when the detector is already inserted.

        Parameters
        ----------
        timeout_s : float, optional
            Maximum time to wait for the slide to arrive, in seconds.
        poll_interval_s : float, optional
            Delay between status queries, in seconds.
        quiet : bool, optional
            Suppress progress messages.

        Returns
        -------
        bool
            True once the detector is inserted.

        Raises
        ------
        EdaxTimeoutError
            If the slide does not arrive before the timeout.
        """
        if self.slide_status() == EdaxDetectorSlideStatus.SLIDE_IN:
            return True

        if not quiet:
            print("\tInserting EDAX EDS detector...")
        self._client.execute(EdaxCommand.EDS_INSERT_DETECTOR, timeout_s=timeout_s)
        self.wait_for_slide_status(
            EdaxDetectorSlideStatus.SLIDE_IN,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )
        if not quiet:
            print("\tEDAX EDS detector inserted")
        return True

    def retract_detector(
        self,
        timeout_s: float = DEFAULT_SLIDE_TIMEOUT_S,
        poll_interval_s: float = DEFAULT_SLIDE_POLL_S,
        quiet: bool = False,
    ) -> bool:
        """
        Retract the EDS detector slide and wait until it reports ``SLIDE_OUT``.

        Returns immediately when the detector is already retracted.

        Parameters
        ----------
        timeout_s : float, optional
            Maximum time to wait for the slide to arrive, in seconds.
        poll_interval_s : float, optional
            Delay between status queries, in seconds.
        quiet : bool, optional
            Suppress progress messages.

        Returns
        -------
        bool
            True once the detector is retracted.

        Raises
        ------
        EdaxTimeoutError
            If the slide does not arrive before the timeout.
        """
        if self.slide_status() == EdaxDetectorSlideStatus.SLIDE_OUT:
            return True

        if not quiet:
            print("\tRetracting EDAX EDS detector...")
        self._client.execute(EdaxCommand.EDS_RETRACT_DETECTOR, timeout_s=timeout_s)
        self.wait_for_slide_status(
            EdaxDetectorSlideStatus.SLIDE_OUT,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )
        if not quiet:
            print("\tEDAX EDS detector retracted")
        return True

    def wait_for_slide_status(
        self,
        target: EdaxDetectorSlideStatus,
        timeout_s: float = DEFAULT_SLIDE_TIMEOUT_S,
        poll_interval_s: float = DEFAULT_SLIDE_POLL_S,
    ) -> EdaxDetectorSlideStatus:
        """
        Poll the EDS detector slide until it reaches a target status.

        Parameters
        ----------
        target : EdaxDetectorSlideStatus
            The status to wait for.
        timeout_s : float, optional
            Maximum time to wait, in seconds.
        poll_interval_s : float, optional
            Delay between status queries, in seconds.

        Returns
        -------
        EdaxDetectorSlideStatus
            The target status, once reached.

        Raises
        ------
        EdaxTimeoutError
            If the target is not reached before the timeout.
        """
        deadline = time.time() + timeout_s

        while True:
            status = self.slide_status(timeout_s=60.0)
            if status == target:
                return status
            if time.time() >= deadline:
                raise EdaxTimeoutError(
                    command=f"EDS detector slide move to {target.value}",
                    timeout_s=timeout_s,
                )
            time.sleep(min(poll_interval_s, max(deadline - time.time(), 0.0)))

    # -- detector cooling (section 2.2.18 - 2.2.19) --------------------------

    def set_cooling(self, enabled: bool, timeout_s: Optional[float] = None) -> bool:
        """
        Turn EDS detector cooling on or off.

        Parameters
        ----------
        enabled : bool
            True to enable cooling, False to disable it.
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        bool
            True on success.
        """
        self._client.execute(
            EdaxCommand.EDS_SET_DETECTOR_COOLING, enabled, timeout_s=timeout_s
        )
        return True

    def cooling_enabled(self, timeout_s: Optional[float] = None) -> bool:
        """
        Return the cooling status of the EDS detector.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        bool
            True when the detector is cooling.
        """
        return self._client.query_bool(
            EdaxCommand.EDS_GET_DETECTOR_COOLING_STATUS, timeout_s=timeout_s
        )
