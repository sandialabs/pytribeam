import sys
from pathlib import Path
from datetime import datetime
import traceback
import time


from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.ebsd import BrukerEBSDController
from pytribeam.external_oem.bruker.types import (
    BrukerSessionSettings,
    BrukerEDSMapSettings,
)

# Make local src/ available without requiring package installation
REPO_ROOT = Path(__file__).resolve().parents[5]  # check the number
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

OUT_DIR = Path(r"C:\Users\User\Documents\Polonsky\BrukerSandbox")
OUT_DIR.mkdir(parents=True, exist_ok=True)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_PATH = OUT_DIR / f"ebsd_hardware_sandbox_{STAMP}.log"

# txt looks unreadable, bcf made an output, trying h5 with and without patterns
OUT_PATH_EBSD = OUT_DIR.joinpath(f"ebsd_data_{STAMP}.h5")


def log(msg: str):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    log("=== Bruker EBSD hardware sandbox start ===")
    log(f"Log path: {LOG_PATH}")

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

        ebsd = BrukerEBSDController(session)

        status = ebsd.export_status()
        log("EBSD export status:")
        log(f"  has_get_profiles={status.has_get_profiles}")
        log(f"  has_select_profile={status.has_select_profile}")
        log(f"  has_start_acquisition={status.has_start_acquisition}")
        log(f"  has_start_with_profile={status.has_start_with_profile}")
        log(f"  has_stop_acquisition={status.has_stop_acquisition}")
        log(f"  has_get_state={status.has_get_state}")
        log(f"  has_save_to_file={status.has_save_to_file}")
        log(f"  has_export_data={status.has_export_data}")
        log(f"  has_get_detector_position={status.has_get_detector_position}")
        log(f"  has_set_detector_position={status.has_set_detector_position}")

        if status.has_get_detector_position:
            try:
                pos_mm = ebsd.get_detector_position_mm()
                log(f"EBSD detector position (mm): {pos_mm}")
            except Exception as exc:
                log(f"EBSD detector position query failed: {exc}")

        if status.has_get_detector_position:
            try:
                new_pos_mm = 10.0
                move_speed_mm_per_s = 2.0
                log(f"EBSD detector requested position (mm): {new_pos_mm}")
                ebsd.set_detector_position_mm(
                    position_mm=new_pos_mm,
                    speed_mm_per_s=move_speed_mm_per_s,
                )
                # get current pos after move
                pos_mm = ebsd.get_detector_position_mm()
                log(f"EBSD detector position (mm): {pos_mm}")
            except Exception as exc:
                log(f"EBSD detector position query failed: {exc}")

        if status.has_get_profiles:
            try:
                profiles = ebsd.get_profiles_raw()
                log("EBSD profiles raw:")
                for line in profiles.splitlines():
                    log(f"  {line}")
            except Exception as exc:
                log(f"EBSD profile query failed: {exc}")

        # if status.has_get_state:
        #     try:
        #         state = ebsd.get_acquisition_state()
        #         log(f"EBSD acquisition state: {state}")
        #     except Exception as exc:
        #         log(f"EBSD acquisition state query failed: {exc}")

        if status.has_get_state:
            # try small different area EBSD:

            log("Preparing small EDS map acquisition")
            map_settings = BrukerEDSMapSettings(
                name="hardware_sandbox_map",
                width_px=50,
                height_px=24,
                pixel_time_us=512,
                real_time_s=0,
                output_bcf_path=str(None),
                output_image_path=str(None),
                output_image_format="bmp",
                spu_device=1,
            )

            rc = session.dll.ImageSetConfiguration(
                session.cid,
                int(map_settings.width_px),
                int(map_settings.height_px),
                int(map_settings.pixel_time_us),
                True,
                False,
            )
            session._check(rc, "ImageSetConfiguration")

            try:
                # # this works:
                # ebsd.select_profile("default")
                # ebsd.start_acquisition()

                # # this won't work independently, you need to load a profile first
                # ebsd.start_acquisition_with_profile("default")

                # # THIS DOESN'T WORK, YOU NEED A PROFILE
                # ebsd.start_acquisition()

                # likely most robust method:
                ebsd.select_profile("default")
                ebsd.start_acquisition()

                log("EBSD acquisition running")
                state = ebsd.get_acquisition_state()
                log(f"EBSD acquisition state: {state}")
                # wait until scan is over
                while int(ebsd.get_acquisition_state().acquisition_percent) < 100:
                    time.sleep(2)  # check every 2 seconds
                    state = ebsd.get_acquisition_state()
                    log(f"EBSD acquisition state: {state}")
                log("EBSD acquisition complete")
                ebsd.stop_acquisition()
            except Exception as exc:
                log(f"EBSD acquisition start query failed: {exc}")

        # TRY SAVING OUT FILE:
        try:
            outpath = ebsd.save_to_file(
                output_path=OUT_PATH_EBSD,
                with_edx=False,
                with_patterns=True,
            )
            log(f"EBSD data saved to {OUT_PATH_EBSD.suffix} at {outpath}")
        except Exception as exc:
            log(f"EBSD file saving to {OUT_PATH_EBSD.suffix} format failed: {exc}")

        if status.has_get_detector_position:
            try:
                # overwrite, functionalize this better:
                new_pos_mm = 5.05  # NEED TO DEFINE HOME SAFE POSITION
                move_speed_mm_per_s = 2.0  # NEED to come up with safe speeds
                # fails a lot here, getting to 5.05 mm
                log(f"EBSD detector requested position (mm): {new_pos_mm}")
                ebsd.set_detector_position_mm(
                    position_mm=new_pos_mm,
                    speed_mm_per_s=move_speed_mm_per_s,
                )
            except Exception as exc:
                log(f"EBSD detector position set failed: {exc}")

        if status.has_get_detector_position:
            try:
                # get current pos after move
                pos_mm = ebsd.get_detector_position_mm()
                log(f"EBSD detector position (mm): {pos_mm}")
            except Exception as exc:
                log(f"EBSD detector position query failed: {exc}")

        log("EBSD sandbox complete")

    except Exception as exc:
        log(f"ERROR: {exc}")
        tb = traceback.format_exc()
        for line in tb.splitlines():
            log(line)

    finally:
        if session is not None:
            log("Leaving Esprit connection open (close_on_exit=False)")
        log("=== Bruker EBSD hardware sandbox end ===")


if __name__ == "__main__":
    main()
