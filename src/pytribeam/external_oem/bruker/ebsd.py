import ctypes as ct
import time
from pathlib import Path
from typing import NamedTuple, Optional

from pytribeam.external_oem.bruker.ctypes_types import c_bool, c_dbl, c_i32
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.types import (
    BrukerEBSDAcquisitionSettings,
    BrukerEBSDDetectorMotionResult,
    BrukerEBSDDetectorMotionSettings,
    BrukerEBSDScanAreaSettings,
)


class BrukerEBSDExportStatus(NamedTuple):
    has_get_profiles: bool
    has_select_profile: bool
    has_start_acquisition: bool
    has_start_with_profile: bool
    has_stop_acquisition: bool
    has_get_state: bool
    has_save_to_file: bool
    has_export_data: bool
    has_get_detector_position: bool
    has_set_detector_position: bool
    has_image_set_configuration: bool


class BrukerEBSDProgress(NamedTuple):
    current_line: int
    acquisition_percent: int
    indexing_percent: int
    acquisition_running: bool
    indexing_running: bool


def _bind_if_present(dll, name, argtypes, restype):
    try:
        func = getattr(dll, name)
    except AttributeError:
        return None

    func.argtypes = argtypes
    func.restype = restype
    return func


class BrukerEBSDController:
    def __init__(self, session: BrukerSession):
        self._session = session
        self._dll = session.dll

        self._ImageSetConfiguration = _bind_if_present(
            self._dll,
            "ImageSetConfiguration",
            [ct.c_uint32, ct.c_uint32, ct.c_uint32, ct.c_uint32, c_bool, c_bool],
            ct.c_int32,
        )

        self._EBSDGetAcquisitionProfiles = _bind_if_present(
            self._dll,
            "EBSDGetAcquisitionProfiles",
            [ct.c_uint32, ct.c_char_p, ct.c_int32],
            ct.c_int32,
        )

        self._EBSDSelectAcquisitionProfile = _bind_if_present(
            self._dll,
            "EBSDSelectAcquisitionProfile",
            [ct.c_uint32, ct.c_char_p],
            ct.c_int32,
        )

        self._EBSDStartAcquisition = _bind_if_present(
            self._dll,
            "EBSDStartAcquisition",
            [ct.c_uint32],
            ct.c_int32,
        )

        self._EBSDStartAcquisitionWithProfile = _bind_if_present(
            self._dll,
            "EBSDStartAcquisitionWithProfile",
            [ct.c_uint32, ct.c_char_p],
            ct.c_int32,
        )

        self._EBSDStopAcquisition = _bind_if_present(
            self._dll,
            "EBSDStopAcquisition",
            [ct.c_uint32],
            ct.c_int32,
        )

        self._EBSDGetAcquisitionState = _bind_if_present(
            self._dll,
            "EBSDGetAcquisitionState",
            [
                ct.c_uint32,
                ct.POINTER(c_i32),
                ct.POINTER(c_i32),
                ct.POINTER(c_i32),
                ct.POINTER(c_bool),
                ct.POINTER(c_bool),
            ],
            ct.c_int32,
        )

        self._EBSDSaveToFile = _bind_if_present(
            self._dll,
            "EBSDSaveToFile",
            [ct.c_uint32, ct.c_char_p, c_bool, c_bool],
            ct.c_int32,
        )

        self._EBSDExportData = _bind_if_present(
            self._dll,
            "EBSDExportData",
            [ct.c_uint32, ct.c_char_p, c_i32],
            ct.c_int32,
        )

        self._EBSDGetDetectorPosition = _bind_if_present(
            self._dll,
            "EBSDGetDetectorPosition",
            [ct.c_uint32, ct.POINTER(c_dbl)],
            ct.c_int32,
        )

        self._EBSDSetDetectorPosition = _bind_if_present(
            self._dll,
            "EBSDSetDetectorPosition",
            [ct.c_uint32, c_dbl, c_dbl],
            ct.c_int32,
        )

    def export_status(self) -> BrukerEBSDExportStatus:
        return BrukerEBSDExportStatus(
            has_get_profiles=self._EBSDGetAcquisitionProfiles is not None,
            has_select_profile=self._EBSDSelectAcquisitionProfile is not None,
            has_start_acquisition=self._EBSDStartAcquisition is not None,
            has_start_with_profile=self._EBSDStartAcquisitionWithProfile is not None,
            has_stop_acquisition=self._EBSDStopAcquisition is not None,
            has_get_state=self._EBSDGetAcquisitionState is not None,
            has_save_to_file=self._EBSDSaveToFile is not None,
            has_export_data=self._EBSDExportData is not None,
            has_get_detector_position=self._EBSDGetDetectorPosition is not None,
            has_set_detector_position=self._EBSDSetDetectorPosition is not None,
            has_image_set_configuration=self._ImageSetConfiguration is not None,
        )

    def _require(self, func, name: str):
        if func is None:
            raise RuntimeError(f"EBSD function not exported: {name}")
        return func

    def configure_scan_area(self, settings: BrukerEBSDScanAreaSettings) -> None:
        """
        Configure scan/image area before EBSD acquisition.

        This follows the same ImageSetConfiguration pattern that worked for EDS.
        """
        func = self._require(self._ImageSetConfiguration, "ImageSetConfiguration")
        rc = func(
            self._session.cid,
            int(settings.width_px),
            int(settings.height_px),
            int(settings.pixel_time_us),
            True,
            False,
        )
        self._session._check(rc, "ImageSetConfiguration")

    def get_profiles_raw(self, bufsize: int = 16384) -> str:
        func = self._require(
            self._EBSDGetAcquisitionProfiles, "EBSDGetAcquisitionProfiles"
        )
        buf = ct.create_string_buffer(bufsize)
        rc = func(self._session.cid, buf, bufsize)
        self._session._check(rc, "EBSDGetAcquisitionProfiles")
        return buf.value.decode(errors="replace")

    def select_profile(self, profile_name: str) -> None:
        func = self._require(
            self._EBSDSelectAcquisitionProfile, "EBSDSelectAcquisitionProfile"
        )
        rc = func(self._session.cid, profile_name.encode())
        self._session._check(rc, "EBSDSelectAcquisitionProfile")

    def start_acquisition(self) -> None:
        func = self._require(self._EBSDStartAcquisition, "EBSDStartAcquisition")
        rc = func(self._session.cid)
        self._session._check(rc, "EBSDStartAcquisition")

    def start_acquisition_with_profile(self, profile_name: str) -> None:
        func = self._require(
            self._EBSDStartAcquisitionWithProfile, "EBSDStartAcquisitionWithProfile"
        )
        rc = func(self._session.cid, profile_name.encode())
        self._session._check(rc, "EBSDStartAcquisitionWithProfile")

    def stop_acquisition(self) -> None:
        func = self._require(self._EBSDStopAcquisition, "EBSDStopAcquisition")
        rc = func(self._session.cid)
        self._session._check(rc, "EBSDStopAcquisition")

    def get_acquisition_state(self) -> BrukerEBSDProgress:
        func = self._require(self._EBSDGetAcquisitionState, "EBSDGetAcquisitionState")

        current_line = c_i32(0)
        percent_ready = c_i32(0)
        indexing_percent = c_i32(0)
        acquisition_running = c_bool(False)
        indexing_running = c_bool(False)

        rc = func(
            self._session.cid,
            ct.byref(current_line),
            ct.byref(percent_ready),
            ct.byref(indexing_percent),
            ct.byref(acquisition_running),
            ct.byref(indexing_running),
        )
        self._session._check(rc, "EBSDGetAcquisitionState")

        return BrukerEBSDProgress(
            current_line=int(current_line.value),
            acquisition_percent=int(percent_ready.value),
            indexing_percent=int(indexing_percent.value),
            acquisition_running=bool(acquisition_running.value),
            indexing_running=bool(indexing_running.value),
        )

    def wait_for_acquisition_complete(
        self,
        poll_interval_s: float,
        timeout_s: float,
        log_fn=None,
    ) -> BrukerEBSDProgress:
        t0 = time.time()
        last_state = None

        while True:
            if (time.time() - t0) > timeout_s:
                raise TimeoutError(f"EBSD acquisition exceeded timeout_s={timeout_s}")

            state = self.get_acquisition_state()
            last_state = state

            if log_fn is not None:
                log_fn(f"EBSD acquisition state: {state}")

            if (
                not state.acquisition_running
                and not state.indexing_running
                and state.acquisition_percent >= 100
            ):
                return state

            if state.acquisition_percent >= 100 and not state.acquisition_running:
                return state

            time.sleep(poll_interval_s)

    def save_to_file(
        self, output_path, with_edx: bool = True, with_patterns: bool = True
    ) -> str:
        func = self._require(self._EBSDSaveToFile, "EBSDSaveToFile")
        out_path = str(Path(output_path))
        rc = func(
            self._session.cid, out_path.encode(), bool(with_edx), bool(with_patterns)
        )
        self._session._check(rc, "EBSDSaveToFile")
        return out_path

    def export_data(self, export_base_path, export_option: int) -> str:
        func = self._require(self._EBSDExportData, "EBSDExportData")
        out_path = str(Path(export_base_path))
        rc = func(self._session.cid, out_path.encode(), int(export_option))
        self._session._check(rc, "EBSDExportData")
        return out_path

    def get_detector_position_mm(self) -> float:
        func = self._require(self._EBSDGetDetectorPosition, "EBSDGetDetectorPosition")
        value = c_dbl(0.0)
        rc = func(self._session.cid, ct.byref(value))
        self._session._check(rc, "EBSDGetDetectorPosition")
        return float(value.value)

    def set_detector_position_mm(
        self, position_mm: float, speed_mm_per_s: float
    ) -> None:
        func = self._require(self._EBSDSetDetectorPosition, "EBSDSetDetectorPosition")
        rc = func(self._session.cid, float(position_mm), float(speed_mm_per_s))
        self._session._check(rc, "EBSDSetDetectorPosition")

    def move_detector_position_tolerant(
        self,
        settings: BrukerEBSDDetectorMotionSettings,
        log_fn=None,
    ) -> BrukerEBSDDetectorMotionResult:
        """
        Move EBSD detector and accept final position if within tolerance.

        Behavior:
        - issue EBSDSetDetectorPosition
        - if set call raises/fails, query current position anyway
        - if position is within tolerance, accept
        - otherwise poll until within tolerance and stable for N polls
        """
        func = self._require(self._EBSDSetDetectorPosition, "EBSDSetDetectorPosition")

        set_call_rc = None
        set_call_failed = False

        try:
            rc = func(
                self._session.cid,
                float(settings.target_position_mm),
                float(settings.speed_mm_per_s),
            )
            set_call_rc = int(rc)
            self._session._check(rc, "EBSDSetDetectorPosition")
        except Exception as exc:
            set_call_failed = True
            if log_fn is not None:
                log_fn(f"EBSDSetDetectorPosition raised/failure: {exc}")
                log_fn(
                    "Querying detector position after set failure to check tolerance"
                )

        t0 = time.time()
        stable_count = 0
        last_pos = None

        while True:
            pos = self.get_detector_position_mm()
            last_pos = pos
            error = abs(pos - settings.target_position_mm)
            within = error <= settings.tolerance_mm

            if log_fn is not None:
                log_fn(
                    "EBSD detector position poll: "
                    f"target={settings.target_position_mm:.4f} mm, "
                    f"pos={pos:.4f} mm, "
                    f"error={error:.4f} mm, "
                    f"within_tolerance={within}, "
                    f"stable_count={stable_count}"
                )

            if within:
                stable_count += 1
                if stable_count >= max(1, int(settings.stable_polls)):
                    return BrukerEBSDDetectorMotionResult(
                        requested_position_mm=float(settings.target_position_mm),
                        final_position_mm=float(pos),
                        error_mm=float(error),
                        within_tolerance=True,
                        set_call_rc=set_call_rc,
                    )
            else:
                stable_count = 0

            if (time.time() - t0) > settings.timeout_s:
                final_pos = float(last_pos) if last_pos is not None else float("nan")
                final_err = abs(final_pos - settings.target_position_mm)
                raise TimeoutError(
                    "EBSD detector did not reach target within tolerance: "
                    f"target={settings.target_position_mm}, "
                    f"final={final_pos}, "
                    f"error={final_err}, "
                    f"tolerance={settings.tolerance_mm}, "
                    f"set_call_failed={set_call_failed}"
                )

            time.sleep(settings.poll_interval_s)

    def run_profile_acquisition(
        self,
        settings: BrukerEBSDAcquisitionSettings,
        log_fn=None,
    ) -> Optional[str]:
        """
        Configure scan area, select profile, start EBSD acquisition, wait, stop, optionally save.

        This follows the hardware-sandbox finding that select_profile('default')
        then start_acquisition() worked more robustly than start_acquisition_with_profile().
        """
        self.configure_scan_area(settings.scan_area)

        if log_fn is not None:
            log_fn(f"Selecting EBSD profile: {settings.profile_name}")
        self.select_profile(settings.profile_name)

        if log_fn is not None:
            log_fn("Starting EBSD acquisition")
        self.start_acquisition()

        try:
            self.wait_for_acquisition_complete(
                poll_interval_s=settings.poll_interval_s,
                timeout_s=settings.timeout_s,
                log_fn=log_fn,
            )
        finally:
            try:
                if log_fn is not None:
                    log_fn("Stopping EBSD acquisition")
                self.stop_acquisition()
            except Exception as exc:
                if log_fn is not None:
                    log_fn(f"EBSD stop_acquisition failed/ignored: {exc}")

        if settings.output_path:
            if log_fn is not None:
                log_fn(f"Saving EBSD file: {settings.output_path}")
            return self.save_to_file(
                output_path=settings.output_path,
                with_edx=settings.with_edx,
                with_patterns=settings.with_patterns,
            )

        return None
