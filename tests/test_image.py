## python standard libraries
from pathlib import Path
import platform
import time

# 3rd party libraries
import pytest
from PIL import Image as pil_img

# Local
import pytribeam.constants as cs
from pytribeam.constants import Conversions, Constants
import pytribeam.insertable_devices as devices
import pytribeam.factory as factory
import pytribeam.image as img
import pytribeam.types as tbt
import pytribeam.utilities as ut


@pytest.fixture
def test_dir() -> str:
    """The relative path and file string locating the default yml test file."""

    return Path(__file__).parent.joinpath("files")


#### tests ####


@ut.run_on_standalone_machine
def test_beam_current():
    """Tests if beam currents can be correctly adjusted"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    settings = tbt.BeamSettings()

    microscope.beams.electron_beam.beam_current.value = 5.0 * Conversions.NA_TO_A
    current_target_na = 40.0

    bb = microscope.beams.electron_beam.beam_current.value
    print(bb)
    img.beam_current(
        tbt.ElectronBeam(settings=settings),
        microscope=microscope,
        current_na=current_target_na,
        current_tol_na=2.0,
        delay_s=0,
    )
    cc = microscope.beams.electron_beam.beam_current.value
    print(cc)
    assert cc == current_target_na * Conversions.NA_TO_A

    current_target_na = 15.0  # overwrite
    microscope.beams.ion_beam.beam_current.value = 5.0 * Conversions.NA_TO_A
    dd = microscope.beams.ion_beam.beam_current.value
    print(dd)
    img.beam_current(
        tbt.IonBeam(settings=settings),
        microscope=microscope,
        current_na=current_target_na,
        current_tol_na=2.0,
        delay_s=0,
    )
    ee = microscope.beams.ion_beam.beam_current.value
    print(ee)
    assert ee == current_target_na * Conversions.NA_TO_A

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_beam_dwell_time():
    """Tests if beam dwell time can be correctly adjusted"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    settings = tbt.BeamSettings()

    e_beam = tbt.ElectronBeam(settings=settings)
    dwell_us = 0.120
    img.beam_dwell_time(
        beam=e_beam,
        microscope=microscope,
        dwell_us=dwell_us,
        delay_s=0.0,
    )
    assert (
        microscope.beams.electron_beam.scanning.dwell_time.value
        == dwell_us * Conversions.US_TO_S
    )

    i_beam = tbt.IonBeam(settings=settings)
    dwell_us = 20.2  # overwrite
    img.beam_dwell_time(
        beam=i_beam,
        microscope=microscope,
        dwell_us=dwell_us,
        delay_s=0.0,
    )

    assert (
        microscope.beams.ion_beam.scanning.dwell_time.value
        == dwell_us * Conversions.US_TO_S
    )

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_beam_hfw():
    """Tests if beam horizontal field widths can be correctly adjusted"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    settings = tbt.BeamSettings()

    microscope.beams.electron_beam.horizontal_field_width.value == 0.8
    e_beam = tbt.ElectronBeam(settings=settings)
    hfw_mm = 0.5
    img.beam_hfw(
        beam=e_beam,
        microscope=microscope,
        hfw_mm=hfw_mm,
        delay_s=0.0,
    )
    assert (
        microscope.beams.electron_beam.horizontal_field_width.value
        == hfw_mm * Conversions.MM_TO_M
    )

    microscope.beams.ion_beam.horizontal_field_width.value == 0.5
    i_beam = tbt.IonBeam(settings=settings)
    hfw_mm = 0.275  # overwrite
    img.beam_hfw(
        beam=i_beam,
        microscope=microscope,
        hfw_mm=hfw_mm,
        delay_s=0.0,
    )

    assert (
        microscope.beams.ion_beam.horizontal_field_width.value
        == hfw_mm * Conversions.MM_TO_M
    )

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_beam_ready():
    """Tests if beam can be turned on and unblanked correctly"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    settings = tbt.BeamSettings()

    microscope.imaging.set_active_device(tbt.Device.ELECTRON_BEAM.value)
    e_beam = factory.active_beam_with_settings(
        microscope=microscope,
    )  # generates beam with current settings

    microscope.beams.electron_beam.blank()
    microscope.beams.electron_beam.turn_off()
    assert (
        not microscope.beams.electron_beam.is_on
        and microscope.beams.electron_beam.is_blanked
    )

    img.beam_ready(e_beam, microscope, delay_s=0)

    assert (
        microscope.beams.electron_beam.is_on
        and not microscope.beams.electron_beam.is_blanked
    )

    # check we skip through code correctly when beam already on and unblanked
    img.beam_ready(e_beam, microscope, delay_s=0)
    assert (
        microscope.beams.electron_beam.is_on
        and not microscope.beams.electron_beam.is_blanked
    )

    i_beam = tbt.IonBeam(settings=settings)
    microscope.beams.ion_beam.blank()
    microscope.beams.ion_beam.turn_off()
    assert not microscope.beams.ion_beam.is_on and microscope.beams.ion_beam.is_blanked

    img.beam_ready(i_beam, microscope, delay_s=0)

    assert microscope.beams.ion_beam.is_on and not microscope.beams.ion_beam.is_blanked

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_beam_scan_resolution():
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    settings = tbt.BeamSettings()

    e_beam = tbt.ElectronBeam(settings=settings)
    microscope.beams.electron_beam.scanning.resolution.value = (
        tbt.PresetResolution.PRESET_1536X1024.value
    )
    img.beam_scan_resolution(
        beam=e_beam,
        microscope=microscope,
        resolution=tbt.PresetResolution.PRESET_1024X884,
    )
    current_res = microscope.beams.electron_beam.scanning.resolution.value
    assert current_res == "1024x884"

    i_beam = tbt.IonBeam(settings=settings)
    microscope.beams.ion_beam.scanning.resolution.value = (
        tbt.PresetResolution.PRESET_2048X1768.value
    )
    img.beam_scan_resolution(
        beam=i_beam,
        microscope=microscope,
        resolution=tbt.PresetResolution.PRESET_1536X1024,
    )
    current_res = microscope.beams.ion_beam.scanning.resolution.value
    assert current_res == "1536x1024"

    e_beam = tbt.ElectronBeam(settings=settings)
    microscope.beams.electron_beam.scanning.resolution.value = (
        tbt.PresetResolution.PRESET_1536X1024.value
    )
    target_res = tbt.Resolution(
        width=4,
        height=3,
    )
    with pytest.raises(ValueError) as err:
        img.beam_scan_resolution(
            beam=e_beam,
            microscope=microscope,
            resolution=target_res,
        )
    bb = 4
    assert err.type == ValueError
    assert (
        err.value.args[0]
        == "Requested a custom resolution of 4x3. Only preset resolutions allowed."
    )

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_beam_scan_rotation():
    """Tests if beam scan rotation can be correctly adjusted"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    settings = tbt.BeamSettings()

    e_beam = tbt.ElectronBeam(settings=settings)
    rotation_deg = 33.4
    img.beam_scan_rotation(
        beam=e_beam,
        microscope=microscope,
        rotation_deg=rotation_deg,
        delay_s=0.0,
    )
    assert (
        microscope.beams.electron_beam.scanning.rotation.value
        == rotation_deg * Conversions.DEG_TO_RAD
    )

    i_beam = tbt.IonBeam(settings=settings)
    rotation_deg = 53.1  # overwrite
    img.beam_scan_rotation(
        beam=i_beam,
        microscope=microscope,
        rotation_deg=rotation_deg,
        delay_s=0.0,
    )

    assert (
        microscope.beams.ion_beam.scanning.rotation.value
        == rotation_deg * Conversions.DEG_TO_RAD
    )

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_beam_voltage():
    """Tests if beam voltages can be correctly adjusted"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    settings = tbt.BeamSettings()

    microscope.beams.electron_beam.high_voltage.value = 5.0 * Conversions.KV_TO_V
    voltage_target_kv = 10.0

    bb = microscope.beams.electron_beam.high_voltage.value
    print(bb)
    img.beam_voltage(
        tbt.ElectronBeam(settings=settings),
        microscope=microscope,
        voltage_kv=voltage_target_kv,
        voltage_tol_kv=1.0,
        delay_s=0,
    )
    cc = microscope.beams.electron_beam.high_voltage.value
    print(cc)
    assert cc == voltage_target_kv * Conversions.KV_TO_V

    microscope.beams.ion_beam.high_voltage.value = 2.0 * Conversions.KV_TO_V
    voltage_target_kv = 10.0  # overwrite

    bb = microscope.beams.ion_beam.high_voltage.value
    print(bb)
    img.beam_voltage(
        tbt.IonBeam(settings=settings),
        microscope=microscope,
        voltage_kv=voltage_target_kv,
        voltage_tol_kv=1.0,
        delay_s=0,
    )
    cc = microscope.beams.ion_beam.high_voltage.value
    print(cc)
    assert cc == voltage_target_kv * Conversions.KV_TO_V


@ut.run_on_standalone_machine
def test_beam_working_dist():
    """Tests if beam working distance can be correctly adjusted"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    settings = tbt.BeamSettings()

    e_beam = tbt.ElectronBeam(settings=settings)
    wd_mm = 4.3
    img.beam_working_distance(
        beam=e_beam, microscope=microscope, wd_mm=wd_mm, delay_s=0.0
    )
    assert (
        microscope.beams.electron_beam.working_distance.value
        == wd_mm * Conversions.MM_TO_M
    )

    i_beam = tbt.IonBeam(settings=settings)
    wd_mm = 5.35  # overwrite
    img.beam_working_distance(
        beam=i_beam,
        microscope=microscope,
        wd_mm=wd_mm,
        delay_s=0.0,
    )

    assert (
        microscope.beams.ion_beam.working_distance.value == wd_mm * Conversions.MM_TO_M
    )

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_detector_cb():
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    microscope.imaging.set_active_device(tbt.Device.ELECTRON_BEAM.value)
    e_beam = factory.active_beam_with_settings(
        microscope=microscope,
    )

    ebeam = tbt.ElectronBeam(
        settings=tbt.BeamSettings(
            voltage_kv=5.0,
            current_tol_na=92.0,
            voltage_tol_kv=0.1,
            working_dist_mm=100.0,
        )
    )

    etd = tbt.Detector(
        type=tbt.DetectorType.ETD,
        mode=tbt.DetectorMode.BACKSCATTER_ELECTRONS,
        brightness=0.48,
        contrast=0.52,
    )
    microscope.detector.type.value = tbt.DetectorType.ETD.value
    microscope.detector.brightness.value = 0.3
    microscope.detector.contrast.value = 0.2

    img.detector_cb(
        microscope=microscope,
        detector_settings=etd,
        beam=ebeam,
    )

    assert microscope.detector.brightness.value == pytest.approx(0.48)
    assert microscope.detector.contrast.value == pytest.approx(0.52)

    etd2 = tbt.Detector(
        type=tbt.DetectorType.ETD,
        mode=tbt.DetectorMode.BACKSCATTER_ELECTRONS,
        brightness=None,
        contrast=None,
        auto_cb_settings=tbt.ScanArea(
            left=0.2,
            top=0.2,
            width=0.6,
            height=0.6,
        ),
    )

    img.detector_cb(
        microscope=microscope,
        detector_settings=etd2,
        beam=ebeam,
    )

    aa = microscope.detector.brightness.value
    bb = microscope.detector.contrast.value

    assert aa == pytest.approx(0.48)
    assert bb == pytest.approx(0.52)


def test_detector_mode():
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    devices.device_access(microscope=microscope)

    valid_detectors = microscope.detector.type.available_values
    for detector in valid_detectors:
        img.detector_type(
            microscope=microscope,
            detector=tbt.DetectorType(detector),
        )
        assert microscope.detector.type.value == detector
        valid_modes = microscope.detector.mode.available_values
        for mode in valid_modes:
            img.detector_mode(
                microscope=microscope,
                detector_mode=tbt.DetectorMode(mode),
            )
            assert microscope.detector.mode.value == mode

    microscope.disconnect()


def test_detector_type():
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    devices.device_access(microscope=microscope)

    valid_detectors = microscope.detector.type.available_values
    for detector in valid_detectors:
        img.detector_type(
            microscope=microscope,
            detector=tbt.DetectorType(detector),
        )
        # custom = detector.custom_settings
        assert microscope.detector.type.value == detector

    microscope.disconnect()


def test_set_beam_device():
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    devices.device_access(microscope=microscope)
    microscope.imaging.set_active_device(tbt.Device.ELECTRON_BEAM.value)
    assert microscope.imaging.get_active_device() == tbt.Device.ELECTRON_BEAM.value

    img.set_beam_device(
        microscope=microscope,
        device=tbt.Device.ION_BEAM,
    )
    assert microscope.imaging.get_active_device() == tbt.Device.ION_BEAM.value


def test_set_view():
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    settings = tbt.BeamSettings()

    microscope.imaging.set_active_view(2)

    e_beam = tbt.ElectronBeam(settings=settings)
    img.set_view(microscope=microscope, quad=e_beam.default_view)
    assert microscope.imaging.get_active_view() == tbt.ElectronBeam.default_view

    i_beam = tbt.IonBeam(settings=settings)
    img.set_view(microscope=microscope, quad=i_beam.default_view)
    assert microscope.imaging.get_active_view() == tbt.IonBeam.default_view

    img.set_view(microscope=microscope, quad=tbt.ViewQuad.LOWER_RIGHT)
    assert microscope.imaging.get_active_view() == 4

    microscope.disconnect()


def test_set_device():
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    devices.device_access(microscope=microscope)
    img.set_beam_device(microscope=microscope, device=tbt.Device.ELECTRON_BEAM)
    assert microscope.imaging.get_active_device() == tbt.Device.ELECTRON_BEAM.value

    img.set_beam_device(microscope=microscope, device=tbt.Device.ION_BEAM)
    assert microscope.imaging.get_active_device() == tbt.Device.ION_BEAM.value


### the main methods of the file
@pytest.mark.skipif(
    not any(
        platform.uname().node.lower() in machine.lower()
        for machine in (cs.Constants.offline_machines)
    ),
    reason="Run only on offline machines only",
)
def test_collect_single_image(test_dir):
    ## Preset resolution

    # read config
    test_file = test_dir.joinpath("image_config.yml")
    yml_version = 1.0
    yml_format = ut.yml_format(version=yml_version)
    db = ut.yml_to_dict(
        yml_path_file=test_file,
        version=yml_version,
        required_keys=(
            "general",
            "config_file_version",
        ),
    )
    # get image step settings
    image_step_name, image_step_settings = ut.step_settings(
        db,
        step_number_key="step_number",
        step_number_val=1,
        yml_format=yml_format,
    )

    # connect to microscope
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    # create image object
    image_object = factory.image(
        microscope=microscope,
        step_settings=image_step_settings,
        yml_format=yml_format,
        step_name=image_step_name,
    )
    # check test_file doesn't exist
    temp_path = test_dir.joinpath("preset_image_test.tif")
    try:
        temp_path.unlink()  # delete the temp.yml if it exists aready
    except FileNotFoundError:
        pass

    # call the function
    img.collect_single_image(
        save_path=temp_path,
        img_settings=image_object,
    )

    # get dims of image to check
    assert microscope.detector.type.value == tbt.DetectorType.ETD.value
    assert microscope.detector.mode.value == tbt.DetectorMode.SECONDARY_ELECTRONS.value
    assert microscope.beams.electron_beam.scanning.rotation.value == pytest.approx(
        180.0 * Conversions.DEG_TO_RAD
    )

    with pil_img.open(str(temp_path)) as stnd_img:
        assert stnd_img.width == 768
        assert stnd_img.height == 512

    try:
        temp_path.unlink()
    except FileNotFoundError:
        pass

    microscope.disconnect()

    ## Custom resolution

    # read config
    test_file = test_dir.joinpath("image_config_custom_resolution.yml")
    yml_version = 1.0
    yml_format = ut.yml_format(version=yml_version)
    db = ut.yml_to_dict(
        yml_path_file=test_file,
        version=yml_version,
        required_keys=(
            "general",
            "config_file_version",
        ),
    )
    # get image step settings
    image_step_name, image_step_settings = ut.step_settings(
        db,
        step_number_key="step_number",
        step_number_val=1,
        yml_format=yml_format,
    )

    # connect to microscope
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    # create image object
    image_object = factory.image(
        microscope=microscope,
        step_settings=image_step_settings,
        yml_format=yml_format,
        step_name=image_step_name,
    )
    # check test_file doesn't exist
    temp_path = test_dir.joinpath("custom_image_test.tif")
    try:
        temp_path.unlink()  # delete the temp.yml if it exists aready
    except FileNotFoundError:
        pass

    # call the function
    img.collect_single_image(
        save_path=temp_path,
        img_settings=image_object,
    )

    # get dims of image to check
    assert microscope.detector.type.value == tbt.DetectorType.ETD.value
    assert microscope.detector.mode.value == tbt.DetectorMode.SECONDARY_ELECTRONS.value
    assert microscope.beams.electron_beam.scanning.rotation.value == pytest.approx(
        180.0 * Conversions.DEG_TO_RAD
    )

    with pil_img.open(str(temp_path)) as stnd_img:
        assert stnd_img.width == 400
        assert stnd_img.height == 800

    try:
        temp_path.unlink()
    except FileNotFoundError:
        pass

    microscope.disconnect()


### the main methods of the file
@pytest.mark.skipif(
    (
        not any(
            platform.uname().node.lower() in machine.lower()
            for machine in (cs.Constants.microscope_machines)
        )
    )
    or (not Constants.test_hardware_movement),
    reason="Run on hardware machines only",
)
def test_collect_single_image_insertable(test_dir):
    # read config
    test_file = test_dir.joinpath("image_insertable_config.yml")
    yml_version = 1.0
    yml_format = ut.yml_format(version=yml_version)
    db = ut.yml_to_dict(
        yml_path_file=test_file,
        version=yml_version,
        required_keys=(
            "general",
            "config_file_version",
        ),
    )
    # get image step settings
    image_step_name, image_step_settings = ut.step_settings(
        db,
        step_number_key="step_number",
        step_number_val=1,
        yml_format=yml_format,
    )

    # connect to microscope
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    # create image object
    image_object = factory.image(
        microscope=microscope,
        step_settings=image_step_settings,
        step_name=image_step_name,
        yml_format=yml_format,
    )
    # check test_file doesn't exist
    temp_path = test_dir.joinpath("stnd_image_test_insertable.tif")
    try:
        temp_path.unlink()  # delete the temp.yml if it exists aready
    except FileNotFoundError:
        pass

    devices.retract_all_devices(
        microscope=microscope, enable_EBSD=False, enable_EDS=False
    )

    # call the function
    img.collect_single_image(
        save_path=temp_path,
        img_settings=image_object,
    )

    # check correct detector settings were used
    assert microscope.detector.type.value == tbt.DetectorType.CBS.value
    assert microscope.detector.mode.value == tbt.DetectorMode.ALL.value
    assert microscope.beams.electron_beam.scanning.rotation.value == pytest.approx(
        0.0 * Conversions.DEG_TO_RAD
    )
    devices.retract_all_devices(
        microscope=microscope, enable_EBSD=False, enable_EDS=False
    )

    # get dims of image to check
    with pil_img.open(str(temp_path)) as stnd_img:
        assert stnd_img.width == 3072
        assert stnd_img.height == 2048

    try:
        temp_path.unlink()  # delete the temp.yml if it exists aready
    except FileNotFoundError:
        pass

    microscope.disconnect()


# TODO this test
def test_collect_multiple_images():
    pass
