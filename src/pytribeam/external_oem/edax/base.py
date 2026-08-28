#!/usr/bin/python3
"""
EDAX Mapping Controller Base
============================

The EDS and EBSD halves of the IPAPI are near-mirror images of one another:
both expose setup, collection, status, duration, project, and remote-access
commands whose names differ only by an ``_EBSD`` suffix. This module captures
that symmetry once.

:class:`EdaxMappingController` implements the shared behavior and declares the
commands it needs as class attributes. Subclasses bind those attributes to the
concrete command names for their detector, and add whatever is unique to it.

Classes
-------
EdaxMappingController
    Shared setup, collection, status, and project behavior for EDS and EBSD.
"""

# Default python modules
import time
from typing import Callable, Optional

# Local scripts
from pytribeam.external_oem.edax.client import EdaxClient
from pytribeam.external_oem.edax.errors import EdaxStateError, EdaxTimeoutError
from pytribeam.external_oem.edax.types import (
    EdaxAccessType,
    EdaxCommand,
    EdaxEvent,
    EdaxMappingStatus,
    EdaxProjectInfo,
)

# The IPAPI reports durations in .NET ticks, which are 100 ns each.
TICKS_PER_SECOND = 1.0e7


class EdaxMappingController:
    """
    Shared setup, collection, status, and project behavior for EDS and EBSD.

    Subclasses bind the class-level command attributes to the concrete IPAPI
    command names for their detector.

    Parameters
    ----------
    client : EdaxClient
        A connected IPAPI client.
    """

    # Commands bound by subclasses.
    SETUP_START: EdaxCommand
    SETUP_STOP: EdaxCommand
    SETUP_ABORT: EdaxCommand
    COLLECTION_START: EdaxCommand
    COLLECTION_STOP: EdaxCommand
    COLLECTION_RESUME: EdaxCommand
    COLLECTION_PAUSE: EdaxCommand
    GET_MAP_DURATION: EdaxCommand
    GET_MAP_STATUS: EdaxCommand
    GET_SYSTEM_ISAPPSTARTED: EdaxCommand
    SET_SYSTEM_REMOTEACCESSTYPE: EdaxCommand
    SET_SYSTEM_PROJECTINFO: EdaxCommand
    SET_SYSTEM_PROJECTINFO_EXT: EdaxCommand
    COLLECTION_COMPLETE_EVENT: EdaxEvent

    #: Human-readable detector name used in progress and error messages.
    DETECTOR_NAME = "map"

    def __init__(self, client: EdaxClient):
        self._client = client

    @property
    def client(self) -> EdaxClient:
        """Return the IPAPI client this controller drives."""
        return self._client

    # -- application and project --------------------------------------------

    def app_started(self, timeout_s: Optional[float] = None) -> bool:
        """
        Report whether the EDAX application is running.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        bool
            True when the EDAX application is started.
        """
        return self._client.query_bool(
            self.GET_SYSTEM_ISAPPSTARTED, timeout_s=timeout_s
        )

    def set_access_type(
        self,
        access_type: EdaxAccessType,
        timeout_s: Optional[float] = None,
    ) -> bool:
        """
        Set the remote access source type used during map setup.

        Parameters
        ----------
        access_type : EdaxAccessType
            Normal, NoWait, or None. NoWait requires that the folder path be
            set over the IPAPI before mapping begins.
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        bool
            True on success.
        """
        self._client.execute(
            self.SET_SYSTEM_REMOTEACCESSTYPE,
            int(access_type),
            timeout_s=timeout_s,
        )
        return True

    def set_project_info(
        self,
        project: EdaxProjectInfo,
        timeout_s: Optional[float] = None,
    ) -> bool:
        """
        Set project identity, and slice geometry when it is supplied.

        The extended command is used whenever the project carries 3D slice
        information, matching IPAPI sections 2.2.15 and 2.4.18.

        Parameters
        ----------
        project : EdaxProjectInfo
            Project GUID, name, and optional slice count and thickness.
        timeout_s : float, optional
            Response timeout in seconds. Project creation can be slow, so
            callers usually pass a generous value.

        Returns
        -------
        bool
            True on success.
        """
        if project.num_slices is None and project.slice_thickness_um is None:
            self._client.execute(
                self.SET_SYSTEM_PROJECTINFO,
                project.guid,
                project.name,
                timeout_s=timeout_s,
            )
            return True

        self._client.execute(
            self.SET_SYSTEM_PROJECTINFO_EXT,
            project.guid,
            project.name,
            project.num_slices,
            project.slice_thickness_um,
            timeout_s=timeout_s,
        )
        return True

    # -- setup --------------------------------------------------------------

    def setup_start(self, timeout_s: Optional[float] = None) -> bool:
        """
        Start mapping setup asynchronously.

        The IPAPI returns immediately and raises a setup-complete event later.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        bool
            True on success.
        """
        self._client.execute(self.SETUP_START, timeout_s=timeout_s)
        return True

    def setup_stop(self, timeout_s: Optional[float] = None) -> bool:
        """Stop mapping setup."""
        self._client.execute(self.SETUP_STOP, timeout_s=timeout_s)
        return True

    def setup_abort(self, timeout_s: Optional[float] = None) -> bool:
        """Abort mapping setup."""
        self._client.execute(self.SETUP_ABORT, timeout_s=timeout_s)
        return True

    # -- collection ---------------------------------------------------------

    def collection_start(self, tag: str, timeout_s: Optional[float] = None) -> bool:
        """
        Start map collection asynchronously.

        Parameters
        ----------
        tag : str
            Unique identifier for the map in the EDAX database. Each map must
            live in its own folder, or share a folder under a distinct tag.
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        bool
            True on success.
        """
        self._client.execute(self.COLLECTION_START, tag, timeout_s=timeout_s)
        return True

    def collection_stop(self, timeout_s: Optional[float] = None) -> bool:
        """Stop the map after the current frame."""
        self._client.execute(self.COLLECTION_STOP, timeout_s=timeout_s)
        return True

    def collection_pause(self, timeout_s: Optional[float] = None) -> bool:
        """Pause map collection."""
        self._client.execute(self.COLLECTION_PAUSE, timeout_s=timeout_s)
        return True

    def collection_resume(self, timeout_s: Optional[float] = None) -> bool:
        """Resume a paused map."""
        self._client.execute(self.COLLECTION_RESUME, timeout_s=timeout_s)
        return True

    # -- status and duration -------------------------------------------------

    def map_status(self, timeout_s: Optional[float] = None) -> EdaxMappingStatus:
        """
        Return the current mapping status.

        Parameters
        ----------
        timeout_s : float, optional
            Response timeout in seconds.

        Returns
        -------
        EdaxMappingStatus
            The reported status, or ``UNKNOWN`` when the IPAPI returns a
            status string this wrapper does not recognize.
        """
        payload = self._client.query(self.GET_MAP_STATUS, timeout_s=timeout_s)
        return self.parse_status(payload)

    @staticmethod
    def parse_status(payload: str) -> EdaxMappingStatus:
        """
        Convert a status payload into an :class:`EdaxMappingStatus`.

        Parameters
        ----------
        payload : str
            The payload returned by a map-status query.

        Returns
        -------
        EdaxMappingStatus
            The matching status, or ``UNKNOWN`` for unrecognized values.
        """
        normalized = payload.strip().lower().replace(" ", "").replace("_", "")
        try:
            return EdaxMappingStatus(normalized)
        except ValueError:
            return EdaxMappingStatus.UNKNOWN

    def map_duration_ticks(self, timeout_s: Optional[float] = None) -> float:
        """Return the expected map duration in .NET ticks."""
        return self._client.query_float(self.GET_MAP_DURATION, timeout_s=timeout_s)

    def map_duration_s(self, timeout_s: Optional[float] = None) -> float:
        """
        Return the expected map duration in seconds.

        Returns
        -------
        float
            Expected duration, converted from the ticks the IPAPI reports.
        """
        return self.map_duration_ticks(timeout_s=timeout_s) / TICKS_PER_SECOND

    # -- waiting -------------------------------------------------------------

    def wait_for_map_complete(
        self,
        timeout_s: float,
        poll_interval_s: float = 10.0,
        status_timeout_s: float = 120.0,
        progress_fn: Optional[Callable[[EdaxMappingStatus, float], None]] = None,
    ) -> EdaxMappingStatus:
        """
        Poll until map collection finishes, fails, or the timeout expires.

        Completion is detected two ways, because the IPAPI reports it through
        either channel and not reliably through both: a terminal map status, or
        a collection-complete event the client buffered while polling.

        The loop is built around one hard-won property of the IPAPI: **while
        the EDAX application finalizes a map it stops answering.** Finalization
        writes out the patterns, OIM data, and project database, so the pause
        scales with map size and can run far past any sensible per-command
        timeout. A status query that lands in that window simply waits.

        Two rules follow, and both are enforced here:

        1. A status query that times out is *not* an error and is *not*
           retried. The request stays outstanding and the loop keeps waiting
           for that same response via
           :meth:`~pytribeam.external_oem.edax.client.EdaxClient.await_response`.
           Sending a second command while one is in flight desynchronizes the
           single command socket, after which every reply answers the previous
           request.
        2. The response must be collected even when it arrives late. Abandoning
           it, or closing the socket under it, leaves the service writing to a
           dead connection.

        Parameters
        ----------
        timeout_s : float
            Maximum time to wait for completion, in seconds. Should be sized
            from the expected map duration, with headroom for finalization.
        poll_interval_s : float, optional
            Delay between status queries, in seconds.
        status_timeout_s : float, optional
            How long to wait on any single status response before checking the
            overall deadline again. Exceeding it is treated as "the application
            is still busy", not as a failure, so this can safely stay well
            below the finalization time of a large map.
        progress_fn : callable, optional
            Called after each answered poll with the current status and the
            elapsed seconds. Intended for logging.

        Returns
        -------
        EdaxMappingStatus
            The terminal status observed.

        Raises
        ------
        EdaxStateError
            If the map reports an error status.
        EdaxTimeoutError
            If no terminal status is reached before the overall timeout.
        """
        start_time = time.time()
        deadline = start_time + timeout_s

        # True while a status query has been sent but not yet answered, which
        # is the normal condition during map finalization.
        awaiting_status = False

        while True:
            # A completion event may have been buffered while another command
            # was in flight, in which case the map is already finished.
            if not awaiting_status:
                for event in self._client.drain_events():
                    if event.command == self.COLLECTION_COMPLETE_EVENT.value:
                        return EdaxMappingStatus.MAPPING_COMPLETE

            try:
                if awaiting_status:
                    # The request from a previous iteration is still in flight.
                    response = self._client.await_response(
                        self.GET_MAP_STATUS, timeout_s=status_timeout_s
                    )
                else:
                    response = self._client.send(
                        self.GET_MAP_STATUS, timeout_s=status_timeout_s
                    )
                awaiting_status = False
            except EdaxTimeoutError:
                # The application is finalizing and has stopped answering. Keep
                # the request outstanding and re-check the overall deadline.
                awaiting_status = True
                if time.time() >= deadline:
                    raise EdaxTimeoutError(
                        command=f"{self.DETECTOR_NAME} collection",
                        timeout_s=timeout_s,
                    )
                continue

            status = self.parse_status(response.payload)
            elapsed_s = time.time() - start_time

            if progress_fn is not None:
                progress_fn(status, elapsed_s)

            if status.is_error:
                raise EdaxStateError(
                    f"EDAX {self.DETECTOR_NAME} collection reported status "
                    f"'{status.value}' after {elapsed_s:.0f} s."
                )
            if status.is_terminal:
                return status

            # A completion event may have shared the read with this response.
            for event in self._client.drain_events():
                if event.command == self.COLLECTION_COMPLETE_EVENT.value:
                    return EdaxMappingStatus.MAPPING_COMPLETE

            if time.time() >= deadline:
                raise EdaxTimeoutError(
                    command=f"{self.DETECTOR_NAME} collection",
                    timeout_s=timeout_s,
                )

            time.sleep(min(poll_interval_s, max(deadline - time.time(), 0.0)))
