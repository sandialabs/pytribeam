from pytribeam.external_oem.bruker.types import (
    BrukerSessionSettings,
    BrukerEDSMapSettings,
    BrukerDetectorMotionSettings,
)
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.detector_motion import BrukerDetectorMotionController


def main():
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

    map_settings = BrukerEDSMapSettings(
        name="test_map",
        width_px=32,
        height_px=24,
        pixel_time_us=1024,
        real_time_s=0,
        output_bcf_path=r"C:\Users\apolon\Bruker\Test\test_map.bcf",
        output_image_path=r"C:\Users\apolon\Bruker\Test\test_map.bmp",
        output_image_format="bmp",
        spu_device=1,
    )

    motion_settings = BrukerDetectorMotionSettings(
        detector_index=1,
        target_position="acquire",
        timeout_s=30.0,
        poll_interval_s=0.5,
    )

    session = BrukerSession(session_settings)
    info = session.connect()
    print(info)

    motion = BrukerDetectorMotionController(session)
    print(motion.get_eds_detector_position(1))
    print(motion.move_eds_detector(motion_settings))

    eds = BrukerEDSController(session)
    outputs = eds.acquire_map(map_settings)
    print(outputs)

    if session_settings.close_on_exit:
        session.close()


if __name__ == "__main__":
    main()
