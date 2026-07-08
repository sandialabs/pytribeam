import sys
import traceback
from datetime import datetime
from pathlib import Path

# Make local src/ available without requiring package installation
REPO_ROOT = Path(__file__).resolve().parents[5]  # adjust if needed
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from pytribeam.external_oem.bruker.ebsd import BrukerEBSDController
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.types import (
    BrukerEBSDAcquisitionSettings,
    BrukerEBSDDetectorMotionSettings,
    BrukerEBSDScanAreaSettings,
    BrukerSessionSettings,
)

HARDWARE_TEST = False

OUT_DIR = Path(r"C:\Users\apolon\Documents\Polonsky\BrukerSandbox")
if HARDWARE_TEST:
    OUT_DIR = Path(r"C:\Users\User\Documents\Polonsky\BrukerSandbox")

OUT_DIR.mkdir(parents=True, exist_ok=True)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_PATH = OUT_DIR / f"ebsd_hardware_sandbox_{STAMP}.log"

EBSD_OUTPUT_PATH = OUT_DIR / f"ebsd_data_{STAMP}.bcf"

# Hardware-specific values to refine
EBSD_ACQUIRE_POSITION_MM = 0.0
EBSD_SAFE_PARK_POSITION_MM = 0.0
if HARDWARE_TEST:
    EBSD_ACQUIRE_POSITION_MM = 10.0
    EBSD_SAFE_PARK_POSITION_MM = 5.05
EBSD_MOVE_SPEED_MM_PER_S = 2.0
EBSD_POSITION_TOLERANCE_MM = 0.10
EBSD_POSITION_TIMEOUT_S = 4.0
if HARDWARE_TEST:
    EBSD_POSITION_TIMEOUT_S = 90.0
EBSD_POSITION_POLL_INTERVAL_S = 0.5
EBSD_STABLE_POLLS = 2

EBSD_PROFILE_NAME = "default"

SCAN_WIDTH_PX = 50
SCAN_HEIGHT_PX = 24
SCAN_PIXEL_TIME_US = 512

ACQ_POLL_INTERVAL_S = 2.0
ACQ_TIMEOUT_S = 600.0


def log(msg: str):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    log("=== Bruker EBSD hardware sandbox start ===")
    log(f"Log path: {LOG_PATH}")
    log(f"EBSD output path: {EBSD_OUTPUT_PATH}")

    session_settings = BrukerSessionSettings(
        dll_dir=r"C:\Program Files\Bruker\Esprit API",
        mode="local",
        server="Lokaler Server",
        user="edx",
        password="edx",
        host=None,
        port=None,
        close_on_exit=False,
        keep_connection_open=True,
    )

    session = None
    ebsd = None

    try:
        log("Creating BrukerSession")
        session = BrukerSession(session_settings)

        log("Connecting to Esprit")
        info = session.connect()
        log(f"Connected with CID={info.cid}")
        log("QueryInfo follows:")
        for line in info.query_info.splitlines():
            log(f"  {line}")

        log("Checking connection")
        session.check_connection()
        log("CheckConnection passed")

        ebsd = BrukerEBSDController(session)

        status = ebsd.export_status()
        log("EBSD export status:")
        for field_name, value in zip(status._fields, status):
            log(f"  {field_name}={value}")

        if status.has_get_detector_position:
            try:
                pos_mm = ebsd.get_detector_position_mm()
                log(f"Initial EBSD detector position (mm): {pos_mm}")
            except Exception as exc:
                log(f"Initial EBSD detector position query failed: {exc}")

        if status.has_get_profiles:
            try:
                profiles = ebsd.get_profiles_raw()
                log("EBSD profiles raw:")
                for line in profiles.splitlines():
                    log(f"  {line}")
            except Exception as exc:
                log(f"EBSD profile query failed: {exc}")

        if status.has_set_detector_position and status.has_get_detector_position:
            log(
                f"Moving EBSD detector to acquire-ish position: {EBSD_ACQUIRE_POSITION_MM} mm"
            )
            acquire_motion = BrukerEBSDDetectorMotionSettings(
                target_position_mm=EBSD_ACQUIRE_POSITION_MM,
                speed_mm_per_s=EBSD_MOVE_SPEED_MM_PER_S,
                tolerance_mm=EBSD_POSITION_TOLERANCE_MM,
                timeout_s=EBSD_POSITION_TIMEOUT_S,
                poll_interval_s=EBSD_POSITION_POLL_INTERVAL_S,
                stable_polls=EBSD_STABLE_POLLS,
            )
            result = ebsd.move_detector_position_tolerant(acquire_motion, log_fn=log)
            log(f"EBSD detector acquire motion result: {result}")

        if (
            status.has_select_profile
            and status.has_start_acquisition
            and status.has_get_state
        ):
            acq_settings = BrukerEBSDAcquisitionSettings(
                profile_name=EBSD_PROFILE_NAME,
                scan_area=BrukerEBSDScanAreaSettings(
                    width_px=SCAN_WIDTH_PX,
                    height_px=SCAN_HEIGHT_PX,
                    pixel_time_us=SCAN_PIXEL_TIME_US,
                ),
                output_path=str(EBSD_OUTPUT_PATH),
                with_edx=False,
                with_patterns=True,
                poll_interval_s=ACQ_POLL_INTERVAL_S,
                timeout_s=ACQ_TIMEOUT_S,
            )

            try:
                log(f"Running EBSD profile acquisition with settings: {acq_settings}")
                saved_path = ebsd.run_profile_acquisition(acq_settings, log_fn=log)
                log(f"EBSD acquisition saved_path={saved_path}")
            except Exception as exc:
                log(f"EBSD acquisition failed: {exc}")

        if status.has_set_detector_position and status.has_get_detector_position:
            log(
                f"Moving EBSD detector to safe park position: {EBSD_SAFE_PARK_POSITION_MM} mm"
            )
            park_motion = BrukerEBSDDetectorMotionSettings(
                target_position_mm=EBSD_SAFE_PARK_POSITION_MM,
                speed_mm_per_s=EBSD_MOVE_SPEED_MM_PER_S,
                tolerance_mm=EBSD_POSITION_TOLERANCE_MM,
                timeout_s=EBSD_POSITION_TIMEOUT_S,
                poll_interval_s=EBSD_POSITION_POLL_INTERVAL_S,
                stable_polls=EBSD_STABLE_POLLS,
            )
            result = ebsd.move_detector_position_tolerant(park_motion, log_fn=log)
            log(f"EBSD detector park motion result: {result}")

        if status.has_get_detector_position:
            try:
                pos_mm = ebsd.get_detector_position_mm()
                log(f"Final EBSD detector position (mm): {pos_mm}")
            except Exception as exc:
                log(f"Final EBSD detector position query failed: {exc}")

        log("EBSD sandbox complete")

    except Exception as exc:
        log(f"ERROR: {exc}")
        tb = traceback.format_exc()
        for line in tb.splitlines():
            log(line)

    finally:
        # Last-resort park attempt if something failed mid-run.
        # Keep this conservative and logged.
        if ebsd is not None:
            try:
                log("Final safety attempt: query EBSD detector position")
                pos_mm = ebsd.get_detector_position_mm()
                log(f"Safety final position query: {pos_mm}")
            except Exception as exc:
                log(f"Safety final position query failed: {exc}")

        if session is not None:
            log("Leaving Esprit connection open (close_on_exit=False)")
        log("=== Bruker EBSD hardware sandbox end ===")


if __name__ == "__main__":
    main()
