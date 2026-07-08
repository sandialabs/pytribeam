import sys
import traceback
from datetime import datetime
from pathlib import Path

from pytribeam.external_oem.bruker.detector_motion import BrukerDetectorMotionController
from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.types import (
    BrukerDetectorMotionSettings,
    BrukerEDSMapSettings,
    BrukerSessionSettings,
)

# Make local src/ available without requiring package installation
REPO_ROOT = Path(__file__).resolve().parents[5]  # check the number
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

OUT_DIR = Path(r"C:\Users\User\Documents\Polonsky\BrukerSandbox")
OUT_DIR.mkdir(parents=True, exist_ok=True)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_PATH = OUT_DIR / f"eds_hardware_sandbox_{STAMP}.log"
BCF_PATH = OUT_DIR / f"eds_map_{STAMP}.bcf"  # bcf works
BMP_PATH = OUT_DIR / f"eds_map_{STAMP}.bmp"


def log(msg: str):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    log("=== Bruker EDS hardware sandbox start ===")
    log(f"Log path: {LOG_PATH}")
    log(f"BCF output: {BCF_PATH}")
    log(f"BMP output: {BMP_PATH}")

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

        motion = BrukerDetectorMotionController(session)
        eds = BrukerEDSController(session)

        log("Querying initial EDS detector position")
        initial_pos = motion.get_eds_detector_position(detector_index=1)
        log(f"Initial detector position: {initial_pos}")

        log("Attempting EDS detector move to acquire")
        acquire_motion = BrukerDetectorMotionSettings(
            detector_index=1,
            target_position="acquire",
            timeout_s=60.0,
            poll_interval_s=0.5,
        )
        acquire_state = motion.move_eds_detector(acquire_motion)
        log(f"Detector position after move-to-acquire: {acquire_state}")

        log("Preparing small EDS map acquisition")
        map_settings = BrukerEDSMapSettings(
            name="hardware_sandbox_map",
            width_px=32,
            height_px=24,
            pixel_time_us=1024,
            real_time_s=0,
            output_bcf_path=str(BCF_PATH),
            output_image_path=str(BMP_PATH),
            output_image_format="bmp",
            spu_device=1,
        )
        log(f"Map settings: {map_settings}")

        log("Starting EDS map acquisition")
        outputs = eds.acquire_map(
            settings=map_settings,
            poll_interval_s=0.2,
            max_wait_s=300.0,
        )
        log(f"Map acquisition finished. Outputs: {outputs}")

        if BCF_PATH.exists():
            log(f"BCF exists: {BCF_PATH} size={BCF_PATH.stat().st_size}")
        else:
            log("BCF file missing after acquisition")

        if BMP_PATH.exists():
            log(f"BMP exists: {BMP_PATH} size={BMP_PATH.stat().st_size}")
            with open(BMP_PATH, "rb") as f:
                magic = f.read(2)
            log(f"BMP magic bytes: {magic!r}")
        else:
            log("BMP file missing after acquisition")

        log("Querying final EDS detector position")
        final_pos = motion.get_eds_detector_position(detector_index=1)
        log(f"Final detector position: {final_pos}")

        log("Attempting EDS detector move back to park")
        park_motion = BrukerDetectorMotionSettings(
            detector_index=1,
            target_position="park",
            timeout_s=60.0,
            poll_interval_s=0.5,
        )
        park_state = motion.move_eds_detector(park_motion)
        log(f"Detector position after move-to-park: {park_state}")

        log("Sandbox complete")

    except Exception as exc:
        log(f"ERROR: {exc}")
        tb = traceback.format_exc()
        for line in tb.splitlines():
            log(line)

    finally:
        if session is not None:
            log("Leaving Esprit connection open (close_on_exit=False)")
        log("=== Bruker EDS hardware sandbox end ===")


if __name__ == "__main__":
    main()
