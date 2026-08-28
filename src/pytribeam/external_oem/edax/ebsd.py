#!/usr/bin/python3
"""
EDAX EBSD Module
================

Typed wrapper for the EBSD half of the EDAX IPAPI: mapping commands
(section 2.4), mapping parameters (section 2.5), and camera parameters
(section 2.6).

:class:`EdaxEbsdController` inherits the setup/collection/status/project
behavior shared with EDS from
:class:`pytribeam.external_oem.edax.base.EdaxMappingController` and adds the
camera slide, camera parameters, image capture, and EBSD scan geometry.

Classes
-------
EdaxEbsdController
    EBSD mapping, camera motion, camera configuration, and image capture.
"""

# Default python modules
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

# Local scripts
from pytribeam.external_oem.edax.base import EdaxMappingController
from pytribeam.external_oem.edax.errors import EdaxStateError, EdaxTimeoutError
from pytribeam.external_oem.edax.types import (
    EdaxCameraCapabilities,
    EdaxCameraInfo,
    EdaxCameraLimits,
    EdaxCameraParams,
    EdaxCameraSlidePositions,
    EdaxCameraStatus,
    EdaxCommand,
    EdaxEbsdMapParams,
    EdaxEbsdMode,
    EdaxEbsdResolution,
    EdaxEvent,
    EdaxGridType,
    EdaxLimit,
)

# Camera slide travel is slow; these defaults suit a TriBeam EBSD camera.
DEFAULT_SLIDE_TIMEOUT_S = 120.0
DEFAULT_SLIDE_POLL_S = 2.0
DEFAULT_SLIDE_SETTLE_S = 10.0


class EdaxEbsdController(EdaxMappingController):
    """
    EBSD mapping, camera motion, camera configuration, and image capture.

    Parameters
    ----------
    client : EdaxClient
        A connected IPAPI client.
    """

    SETUP_START = EdaxCommand.EBSD_SETUP_START
    SETUP_STOP = EdaxCommand.EBSD_SETUP_STOP
    SETUP_ABORT = EdaxCommand.EBSD_SETUP_ABORT
    COLLECTION_START = EdaxCommand.EBSD_COLLECTION_START
    COLLECTION_STOP = EdaxCommand.EBSD_COLLECTION_STOP
    COLLECTION_RESUME = EdaxCommand.EBSD_COLLECTION_RESUME
    COLLECTION_PAUSE = EdaxCommand.EBSD_COLLECTION_PAUSE
    GET_MAP_DURATION = EdaxCommand.EBSD_GET_MAP_DURATION
    GET_MAP_STATUS = EdaxCommand.EBSD_GET_MAP_STATUS
    GET_SYSTEM_ISAPPSTARTED = EdaxCommand.EBSD_GET_SYSTEM_ISAPPSTARTED
    SET_SYSTEM_REMOTEACCESSTYPE = EdaxCommand.EBSD_SET_SYSTEM_REMOTEACCESSTYPE
    SET_SYSTEM_PROJECTINFO = EdaxCommand.EBSD_SET_SYSTEM_PROJECTINFO
    SET_SYSTEM_PROJECTINFO_EXT = EdaxCommand.EBSD_SET_SYSTEM_PROJECTINFO_EXT
    COLLECTION_COMPLETE_EVENT = EdaxEvent.EBSD_COLLECTION_COMPLETE

    DETECTOR_NAME = "EBSD"

    # -- mapping parameters (section 2.5) ------------------------------------

    def apply_map_parameters(
        self,
        params: EdaxEbsdMapParams,
        timeout_s: Optional[float] = None,
    ) -> bool:
        """
        Apply every non-null field of an EBSD parameter set.

        Fields left as ``None`` are not sent, so the corresponding EDAX
        settings keep whatever value the application already holds. Ordering
        follows the IPAPI's dependencies: the resolution is set before either
        step size, because EDAX ignores step size unless the resolution is
        custom.

        Parameters
        ----------
        params : EdaxEbsdMapParams
            The parameters to apply.
        timeout_s : float, optional
            Response timeout for each command, in seconds.

        Returns
        -------
        bool
            True on success.
        """
        ordered = (
            (EdaxCommand.EBSD_SET_FOLDERPATH, params.folder_path),
            (EdaxCommand.EBSD_SET_MODE, params.mode),
            (EdaxCommand.EBSD_SET_RESOLUTION, params.resolution),
            (EdaxCommand.EBSD_SET_CUSTOMSTEPSIZE, params.custom_step_size_um),
            (EdaxCommand.EBSD_SET_STEPSIZE, params.step_size_um),
            (EdaxCommand.EBSD_SET_GRID, params.grid),
            (EdaxCommand.EBSD_SET_SAVEHOUGHPEAKS, params.save_hough_peaks),
            (EdaxCommand.EBSD_SET_SAVEPATTERNS, params.save_patterns),
            (EdaxCommand.EBSD_SET_SAVESPECTRA, params.save_spectra),
            (EdaxCommand.EBSD_SET_XSTART, params.x_start_um),
            (EdaxCommand.EBSD_SET_YSTART, params.y_start_um),
            (EdaxCommand.EBSD_SET_XSIZE, params.x_size_um),
            (EdaxCommand.EBSD_SET_YSIZE, params.y_size_um),
            (EdaxCommand.EBSD_SET_EDSNUMCHAN, params.eds_num_channels),
            (EdaxCommand.EBSD_SET_BYTESPERCHANNEL, params.bytes_per_channel),
        )
        for command, value in ordered:
            if value is None:
                continue
            self._client.execute(command, value, timeout_s=timeout_s)
        return True

    def map_parameters(self, timeout_s: Optional[float] = None) -> EdaxEbsdMapParams:
        """
        Read the full EBSD mapping parameter set back from the application.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout for each command, in seconds.

        Returns
        -------
        EdaxEbsdMapParams
            The parameters currently configured in the EDAX application.
        """
        client = self._client
        return EdaxEbsdMapParams(
            folder_path=Path(
                client.query(EdaxCommand.EBSD_GET_FOLDERPATH, timeout_s=timeout_s)
            ),
            mode=EdaxEbsdMode(
                client.query_int(EdaxCommand.EBSD_GET_MODE, timeout_s=timeout_s)
            ),
            resolution=EdaxEbsdResolution(
                client.query_int(EdaxCommand.EBSD_GET_RESOLUTION, timeout_s=timeout_s)
            ),
            grid=EdaxGridType(
                client.query_int(EdaxCommand.EBSD_GET_GRID, timeout_s=timeout_s)
            ),
            save_hough_peaks=client.query_bool(
                EdaxCommand.EBSD_GET_SAVEHOUGHPEAKS, timeout_s=timeout_s
            ),
            save_patterns=client.query_bool(
                EdaxCommand.EBSD_GET_SAVEPATTERNS, timeout_s=timeout_s
            ),
            save_spectra=client.query_bool(
                EdaxCommand.EBSD_GET_SAVESPECTRA, timeout_s=timeout_s
            ),
            x_start_um=client.query_float(
                EdaxCommand.EBSD_GET_XSTART, timeout_s=timeout_s
            ),
            y_start_um=client.query_float(
                EdaxCommand.EBSD_GET_YSTART, timeout_s=timeout_s
            ),
            x_size_um=client.query_float(
                EdaxCommand.EBSD_GET_XSIZE, timeout_s=timeout_s
            ),
            y_size_um=client.query_float(
                EdaxCommand.EBSD_GET_YSIZE, timeout_s=timeout_s
            ),
            step_size_um=client.query_float(
                EdaxCommand.EBSD_GET_STEPSIZE, timeout_s=timeout_s
            ),
            custom_step_size_um=client.query_float(
                EdaxCommand.EBSD_GET_CUSTOMSTEPSIZE, timeout_s=timeout_s
            ),
            eds_num_channels=client.query_int(
                EdaxCommand.EBSD_GET_EDSNUMCHAN, timeout_s=timeout_s
            ),
            bytes_per_channel=client.query_int(
                EdaxCommand.EBSD_GET_BYTESPERCHANNEL, timeout_s=timeout_s
            ),
        )

    # -- camera slide (section 2.4) ------------------------------------------

    def camera_status(self, timeout_s: Optional[float] = None) -> EdaxCameraStatus:
        """
        Return the current camera slide status.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        EdaxCameraStatus
            The reported slide status, or ``UNKNOWN`` when the IPAPI returns a
            value this wrapper does not recognize.
        """
        payload = self._client.query(
            EdaxCommand.EBSD_GET_CAMERA_STATUS, timeout_s=timeout_s
        )
        normalized = payload.strip().lower().replace(" ", "").replace("_", "")
        try:
            return EdaxCameraStatus(normalized)
        except ValueError:
            return EdaxCameraStatus.UNKNOWN

    def insert_camera(
        self,
        timeout_s: float = DEFAULT_SLIDE_TIMEOUT_S,
        poll_interval_s: float = DEFAULT_SLIDE_POLL_S,
        settle_s: float = DEFAULT_SLIDE_SETTLE_S,
        quiet: bool = False,
    ) -> bool:
        """
        Insert the EBSD camera and wait until the slide reports ``SLIDE_IN``.

        Returns immediately when the camera is already inserted.

        Parameters
        ----------
        timeout_s : float, optional
            Maximum time to wait for the slide to arrive, in seconds.
        poll_interval_s : float, optional
            Delay between status queries, in seconds.
        settle_s : float, optional
            Delay after issuing the move before polling begins, in seconds.
        quiet : bool, optional
            Suppress progress messages.

        Returns
        -------
        bool
            True once the camera is inserted.

        Raises
        ------
        EdaxTimeoutError
            If the slide does not arrive before the timeout.
        EdaxStateError
            If the slide reports an error state.
        """
        if self.camera_status() == EdaxCameraStatus.SLIDE_IN:
            return True

        if not quiet:
            print("\tInserting EDAX EBSD camera...")
        self._client.execute(EdaxCommand.EBSD_INSERT_CAMERA)
        time.sleep(settle_s)

        self.wait_for_camera_status(
            EdaxCameraStatus.SLIDE_IN,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )
        if not quiet:
            print("\tEDAX EBSD camera inserted")
        return True

    def retract_camera(
        self,
        timeout_s: float = DEFAULT_SLIDE_TIMEOUT_S,
        poll_interval_s: float = DEFAULT_SLIDE_POLL_S,
        settle_s: float = DEFAULT_SLIDE_SETTLE_S,
        quiet: bool = False,
    ) -> bool:
        """
        Retract the EBSD camera and wait until the slide reports ``SLIDE_OUT``.

        Returns immediately when the camera is already retracted. A slide that
        reports ``SLIDE_MOVE_WDOG`` has stalled mid-travel and is re-commanded
        once per poll, matching the recovery behavior EDAX expects.

        Parameters
        ----------
        timeout_s : float, optional
            Maximum time to wait for the slide to arrive, in seconds.
        poll_interval_s : float, optional
            Delay between status queries, in seconds.
        settle_s : float, optional
            Delay after issuing the move before polling begins, in seconds.
        quiet : bool, optional
            Suppress progress messages.

        Returns
        -------
        bool
            True once the camera is retracted.

        Raises
        ------
        EdaxTimeoutError
            If the slide does not arrive before the timeout.
        EdaxStateError
            If the slide reports an error state such as ``SLIDE_WATCHDOG``.
        """
        if self.camera_status() == EdaxCameraStatus.SLIDE_OUT:
            return True

        if not quiet:
            print("\tRetracting EDAX EBSD camera...")
        self._client.execute(EdaxCommand.EBSD_RETRACT_CAMERA)
        time.sleep(settle_s)

        def renew_retract(status: EdaxCameraStatus) -> None:
            if status == EdaxCameraStatus.SLIDE_MOVE_WDOG:
                self._client.execute(EdaxCommand.EBSD_RETRACT_CAMERA, timeout_s=60.0)

        self.wait_for_camera_status(
            EdaxCameraStatus.SLIDE_OUT,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
            on_poll=renew_retract,
        )
        if not quiet:
            print("\tEDAX EBSD camera retracted")
        return True

    def retract_camera_distance_mm(
        self,
        distance_mm: float,
        timeout_s: Optional[float] = None,
    ) -> bool:
        """
        Retract the EBSD camera by a fixed distance.

        Parameters
        ----------
        distance_mm : float
            Distance to retract, in millimeters.
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        bool
            True on success.
        """
        self._client.execute(
            EdaxCommand.EBSD_RETRACT_CAMERA_DISTANCE,
            distance_mm,
            timeout_s=timeout_s,
        )
        return True

    def wait_for_camera_status(
        self,
        target: EdaxCameraStatus,
        timeout_s: float = DEFAULT_SLIDE_TIMEOUT_S,
        poll_interval_s: float = DEFAULT_SLIDE_POLL_S,
        on_poll: Optional[Callable[[EdaxCameraStatus], None]] = None,
    ) -> EdaxCameraStatus:
        """
        Poll the camera slide until it reaches a target status.

        Parameters
        ----------
        target : EdaxCameraStatus
            The status to wait for.
        timeout_s : float, optional
            Maximum time to wait, in seconds.
        poll_interval_s : float, optional
            Delay between status queries, in seconds.
        on_poll : callable, optional
            Called with each observed status, before the error check. Used to
            re-issue a stalled move.

        Returns
        -------
        EdaxCameraStatus
            The target status, once reached.

        Raises
        ------
        EdaxStateError
            If the slide reports an error state.
        EdaxTimeoutError
            If the target is not reached before the timeout.
        """
        deadline = time.time() + timeout_s

        while True:
            status = self.camera_status(timeout_s=60.0)

            if on_poll is not None:
                on_poll(status)

            if status == target:
                return status
            if status.is_error:
                raise EdaxStateError(
                    f"EDAX EBSD camera slide reports '{status.value}' while "
                    f"moving to '{target.value}'. Please adjust the camera "
                    "manually and restart."
                )
            if time.time() >= deadline:
                raise EdaxTimeoutError(
                    command=f"camera slide move to {target.value}",
                    timeout_s=timeout_s,
                )

            time.sleep(min(poll_interval_s, max(deadline - time.time(), 0.0)))

    def slide_positions(
        self, timeout_s: Optional[float] = None
    ) -> EdaxCameraSlidePositions:
        """
        Read the camera slide travel limits and current position.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout for each command, in seconds.

        Returns
        -------
        EdaxCameraSlidePositions
            Current, fully-inserted, and fully-retracted positions, in mm.
        """
        client = self._client
        return EdaxCameraSlidePositions(
            current_mm=client.query_float(
                EdaxCommand.EBSD_GET_SLIDE_POSITION, timeout_s=timeout_s
            ),
            inserted_mm=client.query_float(
                EdaxCommand.EBSD_GET_SLIDE_POSITION_INSERTED, timeout_s=timeout_s
            ),
            retracted_mm=client.query_float(
                EdaxCommand.EBSD_GET_SLIDE_POSITION_RETRACTED, timeout_s=timeout_s
            ),
        )

    def set_slide_position_mm(
        self,
        position_mm: float,
        timeout_s: Optional[float] = None,
    ) -> bool:
        """
        Move the camera slide to an absolute position.

        Parameters
        ----------
        position_mm : float
            Target slide position in millimeters.
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        bool
            True on success.
        """
        self._client.execute(
            EdaxCommand.EBSD_SET_SLIDE_POSITION, position_mm, timeout_s=timeout_s
        )
        return True

    # -- measurements --------------------------------------------------------

    def camera_saturation(self, timeout_s: Optional[float] = None) -> float:
        """
        Return the camera saturation, in the range [0, 1].

        The value is only meaningful while the beam is scanning, so callers
        normally start an acquisition on the microscope first.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        float
            Camera saturation from 0.0 to 1.0.
        """
        return self._client.query_float(
            EdaxCommand.EBSD_GET_CAMERA_SATURATION, timeout_s=timeout_s
        )

    def average_ci(self, timeout_s: float = 60.0) -> float:
        """
        Return the average confidence index of the most recent EBSD map.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        float
            The average CI.
        """
        return self._client.query_float(
            EdaxCommand.EBSD_GET_MAP_AVG_CI, timeout_s=timeout_s
        )

    # -- image capture (section 2.4.25 - 2.4.30) -----------------------------

    def snapshot(self, timeout_s: float = 60.0) -> Tuple[int, ...]:
        """
        Capture an image and return one unsigned integer per pixel.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout in seconds. Captures are slow, so the default is
            generous.

        Returns
        -------
        Tuple[int, ...]
            Pixel values in row-major order.
        """
        return self._client.query_int_array(
            EdaxCommand.EBSD_CAMERA_SNAPSHOT, timeout_s=timeout_s
        )

    def capture_scan(self, timeout_s: float = 60.0) -> Tuple[int, ...]:
        """Capture an image using the current mapping settings."""
        return self._client.query_int_array(
            EdaxCommand.EBSD_CAMERA_CAPTURE_SCAN, timeout_s=timeout_s
        )

    def capture_background(
        self,
        auto: bool = False,
        smart: bool = False,
        timeout_s: float = 120.0,
    ) -> Tuple[int, ...]:
        """
        Capture a background image, replacing the current one.

        Parameters
        ----------
        auto : bool, optional
            Take external control of the beam and raster it while averaging.
        smart : bool, optional
            As ``auto``, and additionally reduce the SEM magnification first.
            Takes precedence over ``auto``.
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        Tuple[int, ...]
            Pixel values in row-major order.
        """
        if smart:
            command = EdaxCommand.EBSD_CAMERA_CAPTURE_BACKGROUND_SMART
        elif auto:
            command = EdaxCommand.EBSD_CAMERA_CAPTURE_BACKGROUND_AUTO
        else:
            command = EdaxCommand.EBSD_CAMERA_CAPTURE_BACKGROUND
        return self._client.query_int_array(command, timeout_s=timeout_s)

    def black_reference(self, timeout_s: float = 120.0) -> bool:
        """
        Capture a black reference image, for CMOS cameras.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        bool
            True on success.
        """
        self._client.execute(
            EdaxCommand.EBSD_CAMERA_BLACK_REFERENCE, timeout_s=timeout_s
        )
        return True

    # -- camera presets (section 2.4.31 - 2.4.33) ----------------------------

    def save_preset(
        self, user_id: str, preset_key: str, timeout_s: Optional[float] = None
    ) -> bool:
        """Save the current camera settings as a named preset."""
        self._client.execute(
            EdaxCommand.EBSD_CAMERA_SAVE_PRESET,
            user_id,
            preset_key,
            timeout_s=timeout_s,
        )
        return True

    def load_preset(
        self, user_id: str, preset_key: str, timeout_s: Optional[float] = None
    ) -> bool:
        """Load a named camera preset."""
        self._client.execute(
            EdaxCommand.EBSD_CAMERA_LOAD_PRESET,
            user_id,
            preset_key,
            timeout_s=timeout_s,
        )
        return True

    def delete_preset(
        self, user_id: str, preset_key: str, timeout_s: Optional[float] = None
    ) -> bool:
        """Delete a named camera preset."""
        self._client.execute(
            EdaxCommand.EBSD_CAMERA_DELETE_PRESET,
            user_id,
            preset_key,
            timeout_s=timeout_s,
        )
        return True

    # -- camera parameters (section 2.6) -------------------------------------

    def apply_camera_parameters(
        self,
        params: EdaxCameraParams,
        timeout_s: Optional[float] = None,
        skip_unsupported: bool = True,
    ) -> Tuple[str, ...]:
        """
        Apply every non-null field of a camera parameter set.

        Parameters
        ----------
        params : EdaxCameraParams
            The parameters to apply. Fields left as ``None`` are not sent.
        timeout_s : float, optional
            Response timeout for each command, in seconds.
        skip_unsupported : bool, optional
            Query the camera's capability flags first and skip parameters the
            camera does not support, rather than letting the IPAPI reject them.

        Returns
        -------
        Tuple[str, ...]
            Names of the parameters that were skipped as unsupported.
        """
        capabilities = (
            self.camera_capabilities(timeout_s=timeout_s) if skip_unsupported else None
        )
        skipped = []

        ordered = (
            ("binning", EdaxCommand.CAMERA_SET_BINNING, params.binning, None),
            (
                "binning_cumulative",
                EdaxCommand.CAMERA_SET_BINNINGCUMULATIVE,
                params.binning_cumulative,
                "binning_cumulative",
            ),
            (
                "double_scan_rate",
                EdaxCommand.CAMERA_SET_DOUBLESCANRATE,
                params.double_scan_rate,
                "double_scan_rate",
            ),
            ("dual_tap", EdaxCommand.CAMERA_SET_DUALTAP, params.dual_tap, "dual_tap"),
            ("exposure_ms", EdaxCommand.CAMERA_SET_EXPOSURE, params.exposure_ms, None),
            (
                "frame_avg_background",
                EdaxCommand.CAMERA_SET_FRAMEAVGBACKGROUND,
                params.frame_avg_background,
                None,
            ),
            (
                "frame_avg_scan",
                EdaxCommand.CAMERA_SET_FRAMEAVGSCAN,
                params.frame_avg_scan,
                None,
            ),
            (
                "frame_avg_snapshot",
                EdaxCommand.CAMERA_SET_FRAMEAVGSNAPSHOT,
                params.frame_avg_snapshot,
                None,
            ),
            ("gain", EdaxCommand.CAMERA_SET_GAIN, params.gain, "gain"),
            (
                "high_gain",
                EdaxCommand.CAMERA_SET_HIGHGAIN,
                params.high_gain,
                "high_gain",
            ),
            (
                "image_processing_mode",
                EdaxCommand.CAMERA_SET_IMAGEPROCESSINGMODEINT,
                params.image_processing_mode,
                None,
            ),
            (
                "reduced_bit_depth",
                EdaxCommand.CAMERA_SET_REDUCEDBITDEPTH,
                params.reduced_bit_depth,
                "reduced_bit_depth",
            ),
        )

        for name, command, value, capability in ordered:
            if value is None:
                continue
            if (
                capabilities is not None
                and capability is not None
                and not getattr(capabilities, capability)
            ):
                skipped.append(name)
                continue
            self._client.execute(command, value, timeout_s=timeout_s)

        return tuple(skipped)

    def camera_parameters(self, timeout_s: Optional[float] = None) -> EdaxCameraParams:
        """
        Read the writable camera parameters back from the application.

        ``high_gain`` has no getter in the IPAPI and is always reported as
        ``None``.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout for each command, in seconds.

        Returns
        -------
        EdaxCameraParams
            The camera's current configuration.
        """
        client = self._client
        return EdaxCameraParams(
            binning=client.query(EdaxCommand.CAMERA_GET_BINNING, timeout_s=timeout_s),
            binning_cumulative=client.query_bool(
                EdaxCommand.CAMERA_GET_BINNINGCUMULATIVE, timeout_s=timeout_s
            ),
            double_scan_rate=client.query_bool(
                EdaxCommand.CAMERA_GET_DOUBLESCANRATE, timeout_s=timeout_s
            ),
            dual_tap=client.query_bool(
                EdaxCommand.CAMERA_GET_DUALTAP, timeout_s=timeout_s
            ),
            exposure_ms=client.query_float(
                EdaxCommand.CAMERA_GET_EXPOSURE, timeout_s=timeout_s
            ),
            frame_avg_background=client.query_int(
                EdaxCommand.CAMERA_GET_FRAMEAVGBACKGROUND, timeout_s=timeout_s
            ),
            frame_avg_scan=client.query_int(
                EdaxCommand.CAMERA_GET_FRAMEAVGSCAN, timeout_s=timeout_s
            ),
            frame_avg_snapshot=client.query_int(
                EdaxCommand.CAMERA_GET_FRAMEAVGSNAPSHOT, timeout_s=timeout_s
            ),
            gain=client.query_float(EdaxCommand.CAMERA_GET_GAIN, timeout_s=timeout_s),
            high_gain=None,  # no getter exists in the IPAPI
            image_processing_mode=client.query_int(
                EdaxCommand.CAMERA_GET_IMAGEPROCESSINGMODEINT, timeout_s=timeout_s
            ),
            reduced_bit_depth=client.query_bool(
                EdaxCommand.CAMERA_GET_REDUCEDBITDEPTH, timeout_s=timeout_s
            ),
        )

    def camera_limits(self, timeout_s: Optional[float] = None) -> EdaxCameraLimits:
        """
        Read the min/max limits of the writable camera parameters.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout for each command, in seconds.

        Returns
        -------
        EdaxCameraLimits
            The camera's allowed parameter ranges.
        """
        client = self._client

        def limit(min_command, max_command, as_int: bool) -> EdaxLimit:
            query = client.query_int if as_int else client.query_float
            return EdaxLimit(
                min=query(min_command, timeout_s=timeout_s),
                max=query(max_command, timeout_s=timeout_s),
            )

        return EdaxCameraLimits(
            exposure_ms=limit(
                EdaxCommand.CAMERA_GET_EXPOSURE_MIN,
                EdaxCommand.CAMERA_GET_EXPOSURE_MAX,
                as_int=False,
            ),
            gain=limit(
                EdaxCommand.CAMERA_GET_GAIN_MIN,
                EdaxCommand.CAMERA_GET_GAIN_MAX,
                as_int=False,
            ),
            frame_avg_background=limit(
                EdaxCommand.CAMERA_GET_FRAMEAVGBACKGROUND_MIN,
                EdaxCommand.CAMERA_GET_FRAMEAVGBACKGROUND_MAX,
                as_int=True,
            ),
            frame_avg_scan=limit(
                EdaxCommand.CAMERA_GET_FRAMEAVGSCAN_MIN,
                EdaxCommand.CAMERA_GET_FRAMEAVGSCAN_MAX,
                as_int=True,
            ),
            frame_avg_snapshot=limit(
                EdaxCommand.CAMERA_GET_FRAMEAVGSNAPSHOT_MIN,
                EdaxCommand.CAMERA_GET_FRAMEAVGSNAPSHOT_MAX,
                as_int=True,
            ),
        )

    def camera_capabilities(
        self, timeout_s: Optional[float] = None
    ) -> EdaxCameraCapabilities:
        """
        Read the camera's feature-support flags.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout for each command, in seconds.

        Returns
        -------
        EdaxCameraCapabilities
            Which optional camera features are supported.
        """
        client = self._client
        return EdaxCameraCapabilities(
            binning_cumulative=client.query_bool(
                EdaxCommand.CAMERA_ISSUPPORT_BINNINGCUMULATIVE, timeout_s=timeout_s
            ),
            black_reference=client.query_bool(
                EdaxCommand.CAMERA_ISSUPPORT_BLACKREFERENCE, timeout_s=timeout_s
            ),
            double_scan_rate=client.query_bool(
                EdaxCommand.CAMERA_ISSUPPORT_DOUBLESCANRATE, timeout_s=timeout_s
            ),
            dual_tap=client.query_bool(
                EdaxCommand.CAMERA_ISSUPPORT_DUALTAP, timeout_s=timeout_s
            ),
            gain=client.query_bool(
                EdaxCommand.CAMERA_ISSUPPORT_GAIN, timeout_s=timeout_s
            ),
            high_gain=client.query_bool(
                EdaxCommand.CAMERA_ISSUPPORT_HIGHGAIN, timeout_s=timeout_s
            ),
            reduced_bit_depth=client.query_bool(
                EdaxCommand.CAMERA_ISSUPPORT_REDUCEDBITDEPTH, timeout_s=timeout_s
            ),
        )

    def camera_info(self, timeout_s: Optional[float] = None) -> EdaxCameraInfo:
        """
        Read the camera's frame geometry, bit depth, rate, and binning modes.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout for each command, in seconds.

        Returns
        -------
        EdaxCameraInfo
            Static camera description.
        """
        client = self._client
        return EdaxCameraInfo(
            width_px=client.query_int(
                EdaxCommand.CAMERA_GET_FRAME_WIDTH, timeout_s=timeout_s
            ),
            height_px=client.query_int(
                EdaxCommand.CAMERA_GET_FRAME_HEIGHT, timeout_s=timeout_s
            ),
            bit_depth=client.query_int(
                EdaxCommand.CAMERA_GET_FRAME_BITDEPTH, timeout_s=timeout_s
            ),
            frame_rate_hz=client.query_float(
                EdaxCommand.CAMERA_GET_FRAME_RATE, timeout_s=timeout_s
            ),
            binning_names=client.query_str_array(
                EdaxCommand.CAMERA_GET_BINNING_NAMES, timeout_s=timeout_s
            ),
        )
