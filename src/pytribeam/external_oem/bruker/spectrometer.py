"""
Bruker Spectrometer Status Module
=================================

Provides methods to query EDS spectrometer status, configuration, and
detector ranges from the Bruker ESPRIT API.

Useful for:
- Verifying detector health (count rate, temperature, cooling) before/after maps
- Logging spectrometer state for diagnostics
- Checking available energy ranges and throughput settings
"""

import ctypes as ct
from typing import Callable, Optional, Tuple

from pytribeam.external_oem.bruker.bindings import bind_spectrometer
from pytribeam.external_oem.bruker.ctypes_types import (
    TRTDetectorRanges,
    TRTSpectrometerStatus,
    c_i32,
    c_u32,
)
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.types import (
    BrukerDetectorRanges,
    BrukerSpectrometerDetectorStatus,
    BrukerSpectrometerStatus,
)


class BrukerSpectrometerController:
    """Controller for querying EDS spectrometer status and configuration.

    Parameters
    ----------
    session : BrukerSession
        An active, connected Bruker session.
    """

    def __init__(self, session: BrukerSession):
        self._session = session
        bind_spectrometer(self._session.dll)

    def get_spectrometer_status(self, spu: int = 1) -> BrukerSpectrometerStatus:
        """Query spectrometer and detector status.

        Parameters
        ----------
        spu : int
            Spectrometer number (1 in most cases).

        Returns
        -------
        BrukerSpectrometerStatus
            Status including per-detector count rate, temperature, and cooling.
        """
        status = TRTSpectrometerStatus()

        rc = self._session.dll.GetSpectrometerStatus(
            self._session.cid,
            int(spu),
            ct.byref(status),
        )
        self._session._check(rc, "GetSpectrometerStatus")

        detector_statuses = tuple(
            BrukerSpectrometerDetectorStatus(
                version=int(status.DetectorStatus[i].Version),
                status=int(status.DetectorStatus[i].Status),
                count_rate_cps=int(status.DetectorStatus[i].CountRate),
                temperature_c=int(status.DetectorStatus[i].Temperature),
                cooling_mode=int(status.DetectorStatus[i].CoolingMode),
            )
            for i in range(4)
        )

        return BrukerSpectrometerStatus(
            version=int(status.Version),
            detector_statuses=detector_statuses,
            status=int(status.Status),
            ready=bool(status.Ready),
        )

    def get_spectrometer_configuration(self, spu: int = 1) -> Tuple[int, int]:
        """Query current spectrometer configuration indices.

        Parameters
        ----------
        spu : int
            Spectrometer number (1 in most cases).

        Returns
        -------
        tuple of (max_energy_index, pulse_throughput_index)
            Index values for the current energy and throughput settings.
        """
        max_energy_idx = c_u32(0)
        pulse_throughput_idx = c_u32(0)

        rc = self._session.dll.GetSpectrometerConfiguration(
            self._session.cid,
            int(spu),
            ct.byref(max_energy_idx),
            ct.byref(pulse_throughput_idx),
        )
        self._session._check(rc, "GetSpectrometerConfiguration")

        return (int(max_energy_idx.value), int(pulse_throughput_idx.value))

    def get_spectrometer_ranges(
        self, spu: int = 1, det: int = 1
    ) -> BrukerDetectorRanges:
        """Query available energy ranges and throughput settings for a detector.

        Parameters
        ----------
        spu : int
            Spectrometer number (1 in most cases).
        det : int
            Detector number (1 in most cases).

        Returns
        -------
        BrukerDetectorRanges
            Available max energy and pulse throughput settings.
        """
        ranges = TRTDetectorRanges()

        rc = self._session.dll.GetSpectrometerRanges(
            self._session.cid,
            int(spu),
            int(det),
            ct.byref(ranges),
        )
        self._session._check(rc, "GetSpectrometerRanges")

        return BrukerDetectorRanges(
            max_energy=tuple(int(ranges.MaxEnergy[i]) for i in range(8)),
            pulse_throughput=tuple(int(ranges.PulseThroughPut[i]) for i in range(8)),
            energy_index_count=int(ranges.EnergyIndexCount),
            pulse_index_count=int(ranges.PulseIndexCount),
        )

    def log_status(
        self,
        spu: int = 1,
        log_fn: Optional[Callable[[str], None]] = None,
        label: str = "",
    ) -> BrukerSpectrometerStatus:
        """Query and log spectrometer status.

        Convenience method for logging spectrometer state before/after
        map acquisition.

        Parameters
        ----------
        spu : int
            Spectrometer number.
        log_fn : callable, optional
            Logging callback.
        label : str
            Label for the log entry (e.g., "pre-acquisition", "post-acquisition").

        Returns
        -------
        BrukerSpectrometerStatus
            The queried status.
        """
        status = self.get_spectrometer_status(spu=spu)

        if log_fn:
            prefix = f"[{label}] " if label else ""
            log_fn(
                f"{prefix}Spectrometer status: "
                f"version={status.version}, "
                f"status={status.status}, "
                f"ready={status.ready}"
            )
            for i, det in enumerate(status.detector_statuses):
                if det.status != -1:  # Only log present detectors
                    log_fn(
                        f"{prefix}  Detector {i}: "
                        f"status={det.status}, "
                        f"count_rate={det.count_rate_cps} cps, "
                        f"temp={det.temperature_c} C, "
                        f"cooling={det.cooling_mode}"
                    )

        return status
