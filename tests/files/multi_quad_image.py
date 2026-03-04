import imageio
import yaml
from pathlib import Path

import pytribeam.factory as factory
import pytribeam.types as tbt
import pytribeam.utilities as ut
import pytribeam.image as img


if __name__ == "__main__":
    with open("slice_info.yml", mode="r") as stream:
        db = yaml.load(stream, Loader=yaml.Safe)
    slice_number = db["slice_number"]
    exp_dir = Path(db["exp_dir"])

    microscope = tbt.Microscope()
    microscope.connect("localhost")

    beam = tbt.BeamSettings(
        voltage_kv=8.0,
        current_na=0.8,
        hfw_mm=2.0,
        working_dist_mm=4.299303,
        voltage_tol_kv=0.4,
        current_tol_na=0.04,
        dynamic_focus=False,
        tilt_correction=False,
    )
    scan = tbt.Scan(
        rotation_deg=0.0,
        dwell_time_us=5.0,
        resolution=tbt.Resolution(
            width=10002,
            height=6668,
        ),
    )

    # Create image settings
    ebeam_etd = tbt.ElectronBeam(
        type=tbt.BeamType.ELECTRON,
        default_view=tbt.ViewQuad.UPPER_LEFT,
        device=tbt.Device.ELECTRON_BEAM,
        settings=beam,
    )
    ebeam_cbs = tbt.ElectronBeam(
        type=tbt.BeamType.ELECTRON,
        default_view=tbt.ViewQuad.LOWER_LEFT,
        device=tbt.Device.ELECTRON_BEAM,
        settings=beam,
    )

    cbs_detector = tbt.Detector(
        type=tbt.DetectorType.CBS,
        mode=tbt.DetectorMode.BACKSCATTER_ELECTRONS,
        brightness=None,
        contrast=None,
        auto_cb_settings=tbt.ScanArea(
            left=0.4,
            top=0.2,
            width=0.2,
            height=0.6,
        ),
    )
    etd_detector = tbt.Detector(
        type=tbt.DetectorType.ETD,
        mode=tbt.DetectorMode.SECONDARY_ELECTRONS,
        brightness=None,
        contrast=None,
        auto_cb_settings=tbt.ScanArea(
            left=0.4,
            top=0.2,
            width=0.2,
            height=0.6,
        ),
    )

    etd_settings = tbt.ImageSettings(
        microscope=microscope,
        beam=ebeam_etd,
        detector=etd_detector,
        scan=scan,
        bit_depth=8,
    )
    cbs_settings = tbt.ImageSettings(
        microscope=microscope,
        beam=ebeam_cbs,
        detector=cbs_detector,
        scan=scan,
        bit_depth=8,
    )

    print("\tCollecting image")

    # Grab multiple frames
    multiple_img_settings = [cbs_settings, etd_settings]
    views = [1, 3]
    for i in range(len(multiple_img_settings)):
        img_settings = multiple_img_settings[i]
        resolution = img_settings.scan.resolution
        if not isinstance(resolution, tbt.PresetResolution):
            raise ValueError(
                f'Only preset resolutions allowed for simultaneous multiple frame imaging, but resolution of "{resolution.width}x{resolution.height}" was requested.'
            )

        microscope = img_settings.microscope
        beam = img_settings.beam
        img.set_view(microscope=microscope, quad=img_settings.beam.default_view)
        img.prepare_imaging(microscope=microscope, beam=beam, img_settings=img_settings)
    
    for i in range(len(multiple_img_settings)):
        
    frames = microscope.imaging.grab_multiple_frames(
        tbt.GrabFrameSettings(bit_depth=img_settings.bit_depth, views=views)
    )
    


    # Export images
    # Create folder in same directory as experimental directory
    cbs_image_directory = exp_dir.joinpath("CBS_image")
    etd_image_directory = exp_dir.joinpath("ETD_image")
    cbs_image_directory.mkdir(parents=True, exist_ok=True)
    etd_image_directory.mkdir(parents=True, exist_ok=True)
    
    cbs_save_path = cbs_image_directory.joinpath(f"{slice_number:04}.tif")
    imageio.imwrite(cbs_save_path, imgs[0])
    print(f"\tImage saved to {cbs_save_path}")

    etd_save_path = etd_image_directory.joinpath(f"{slice_number:04}.tif")
    imageio.imwrite(etd_save_path, imgs[1])
    print(f"\tImage saved to {etd_save_path}")

    # turn off tilt correction and dynamic focus
    img.beam_angular_correction(
        microscope=microscope,
        dynamic_focus=False,
        tilt_correction=False,
    )
