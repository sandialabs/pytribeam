## python standard libraries
from pathlib import Path
import platform
import time
import copy

# 3rd party libraries
import pytest
from schema import SchemaError
import numpy as np

# Local
import pytribeam.constants as cs
from pytribeam.constants import Conversions
import pytribeam.insertable_devices as devices
import pytribeam.factory as factory
import pytribeam.image as img
import pytribeam.stage as stage
import pytribeam.types as tbt
import pytribeam.utilities as ut


@pytest.fixture
def test_dir() -> str:
    """The relative path and file string locating the default yml test file."""

    return Path(__file__).parent.joinpath("files")


@ut.run_on_microscope_machine
def test_active_laser_settings():
    """tests reading of active laser settings and its component functions"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    factory.active_laser_settings(microscope=microscope)


@ut.run_on_standalone_machine
def test_active_image_settings():
    """tests active image settings and its component functions, including:
    factory.active_beam_with_settings()
    factory.active_detector_settings()
    factory.active_scan_settings()"""

    microscope = tbt.Microscope()
    microscope.connect("localhost")

    # beam
    microscope.imaging.set_active_device(tbt.Device.ELECTRON_BEAM.value)
    microscope.beams.electron_beam.high_voltage.value = 5.0 * Conversions.KV_TO_V
    microscope.beams.electron_beam.beam_current.value = 10.0 * Conversions.NA_TO_A
    microscope.beams.electron_beam.horizontal_field_width.value = (
        0.9 * Conversions.MM_TO_M
    )
    microscope.beams.electron_beam.working_distance.value = 4.1 * Conversions.MM_TO_M
    found_beam = factory.active_beam_with_settings(microscope=microscope)

    known_beam = tbt.ElectronBeam(
        settings=tbt.BeamSettings(
            voltage_kv=5.0,
            current_na=10.0,
            hfw_mm=0.9,
            working_dist_mm=4.1,
            voltage_tol_kv=cs.Constants().voltage_tol_ratio * 5.0,
            current_tol_na=cs.Constants().current_tol_ratio * 10.0,
        )
    )
    assert found_beam.settings.voltage_kv == pytest.approx(
        known_beam.settings.voltage_kv
    )
    assert found_beam.settings.current_na == pytest.approx(
        known_beam.settings.current_na
    )
    assert found_beam.settings.hfw_mm == pytest.approx(known_beam.settings.hfw_mm)
    assert found_beam.settings.working_dist_mm == pytest.approx(
        known_beam.settings.working_dist_mm
    )
    assert found_beam.settings.voltage_tol_kv == pytest.approx(
        known_beam.settings.voltage_tol_kv
    )
    assert found_beam.settings.current_tol_na == pytest.approx(
        known_beam.settings.current_tol_na
    )

    # detector
    microscope.detector.type.value = tbt.DetectorType.ETD.value
    microscope.detector.mode.value = tbt.DetectorMode.SECONDARY_ELECTRONS.value
    microscope.detector.brightness.value = 0.32
    microscope.detector.contrast.value = 0.21
    known_detector = tbt.Detector(
        type=tbt.DetectorType.ETD.value,
        mode=tbt.DetectorMode.SECONDARY_ELECTRONS.value,
        brightness=0.32,
        contrast=0.21,
        auto_cb_settings=tbt.ScanArea(
            left=None,
            top=None,
            width=None,
            height=None,
        ),
        custom_settings=None,
    )
    found_detector = factory.active_detector_settings(microscope=microscope)

    assert found_detector.type == pytest.approx(known_detector.type)
    assert found_detector.mode == pytest.approx(known_detector.mode)
    assert found_detector.brightness == pytest.approx(known_detector.brightness)
    assert found_detector.contrast == pytest.approx(known_detector.contrast)
    assert found_detector.auto_cb_settings.left == pytest.approx(
        known_detector.auto_cb_settings.left
    )

    # scanning
    microscope.beams.electron_beam.scanning.rotation.value = (
        30.0 * Conversions.DEG_TO_RAD
    )
    microscope.beams.electron_beam.scanning.dwell_time.value = 1.0 * Conversions.US_TO_S
    microscope.beams.electron_beam.scanning.resolution.value = (
        tbt.PresetResolution.PRESET_1024X884.value
    )
    known_scan = tbt.Scan(
        rotation_deg=30.0,
        dwell_time_us=1.0,
        resolution="1024x884",
        # mode=mode,
    )
    found_scan = factory.active_scan_settings(microscope=microscope)

    assert found_scan.rotation_deg == pytest.approx(known_scan.rotation_deg)
    assert found_scan.dwell_time_us == pytest.approx(known_scan.dwell_time_us)
    assert found_scan.dwell_time_us == pytest.approx(known_scan.dwell_time_us)

    # all together

    found_settings = factory.active_image_settings(microscope=microscope)
    assert found_settings.bit_depth.value == tbt.ColorDepth.BITS_8

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_active_stage_position():
    """tests active stage position"""

    microscope = tbt.Microscope()
    microscope.connect("localhost")
    stage.coordinate_system(microscope=microscope, mode=tbt.StageCoordinateSystem.RAW)

    microscope.specimen.stage.home()

    x_m, y_m, z_m = 0.0011, 0.0022, 0.0033
    r_rad, t_rad = np.pi / 2, np.pi / 6
    destination = tbt.StagePositionEncoder(
        x=x_m, y=y_m, z=z_m, r=r_rad, t=t_rad, coordinate_system="Raw"
    )
    microscope.specimen.stage.absolute_move(target_position=destination)

    found_pos = factory.active_stage_position_settings(microscope=microscope)

    known_pos = microscope.specimen.stage.current_position

    assert found_pos.x_mm == pytest.approx(known_pos.x * Conversions.M_TO_MM)
    assert found_pos.y_mm == pytest.approx(known_pos.y * Conversions.M_TO_MM)
    assert found_pos.z_mm == pytest.approx(known_pos.z * Conversions.M_TO_MM)
    assert found_pos.r_deg == pytest.approx(known_pos.r * Conversions.RAD_TO_DEG)
    assert found_pos.t_deg == pytest.approx(known_pos.t * Conversions.RAD_TO_DEG)

    large_r_pos = tbt.StagePositionUser(
        x_mm=0.0,
        y_mm=0.0,
        z_mm=0.0,
        t_deg=0.0,
        r_deg=181.0,
    )
    microscope.specimen.stage.absolute_move(
        target_position=stage.user_to_encoder_position(large_r_pos)
    )
    found_pos = factory.active_stage_position_settings(microscope=microscope)

    assert found_pos.r_deg == pytest.approx(-179.0)

    microscope.specimen.stage.home()
    microscope.disconnect()


def test_beam_object_type():
    assert factory.beam_object_type(tbt.BeamType.ELECTRON) == tbt.ElectronBeam
    assert factory.beam_object_type(tbt.BeamType.ION) == tbt.IonBeam


@pytest.mark.skipif(
    not any(
        platform.uname().node.lower() in machine.lower()
        for machine in (cs.Constants.offline_machines)
    ),
    reason="Run only on offline machines only",
)
def test_image(test_dir):
    # read config
    test_file = test_dir.joinpath("image_config.yml")
    # test_file = test_dir.joinpath("image_config_verbose.yml")
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
    ## create image object
    image_object = factory.image(
        microscope=microscope,
        step_settings=image_step_settings,
        step_name=image_step_name,
        yml_format=yml_format,
    )

    assert image_object.beam.type == tbt.BeamType.ELECTRON
    assert image_object.beam.settings.current_na == pytest.approx(5.0)
    assert image_object.beam.settings.current_tol_na == pytest.approx(0.5)
    assert image_object.bit_depth == tbt.ColorDepth.BITS_8
    assert image_object.bit_depth == 8
    assert image_object.detector.auto_cb_settings.height == None
    assert image_object.scan.resolution.value == "768x512"
    assert image_object.scan.resolution == tbt.PresetResolution.PRESET_768X512

    new_db = copy.deepcopy(image_step_settings)
    new_db["beam"]["voltage_kv"] = 900.0
    new_db["beam"]["voltage_tol_kv"] = -10

    with pytest.raises(SchemaError) as err:
        image_object = factory.image(
            microscope=microscope,
            step_settings=new_db,
            yml_format=yml_format,
            step_name=image_step_name,
        )
    assert err.type == SchemaError
    assert (
        err.value.args[0]
        == f"In step '{image_step_name}', requested voltage of '900.0' kV not within limits of 0.0 kV and 30.0 kV."
    )
    # overwrite
    voltage_tol_vals = [-10.0, 10, "str"]
    for val in voltage_tol_vals:
        new_db = copy.deepcopy(image_step_settings)
        new_db["beam"]["voltage_tol_kv"] = val
        with pytest.raises(SchemaError) as err:
            image_object = factory.image(
                microscope=microscope,
                step_settings=new_db,
                yml_format=yml_format,
                step_name=image_step_name,
            )
        assert err.type == SchemaError
        assert (
            err.value.args[0]
            == f"In step '{image_step_name}', requested voltage tolerance of '{val}' kV must be a positive float (greater than 0)."
        )

    microscope.disconnect()


@pytest.mark.skipif(
    not any(
        platform.uname().node.lower() in machine.lower()
        for machine in (cs.Constants.offline_machines)
    ),
    reason="Run only on offline machines only",
)
def test_ebsd(test_dir):
    # read config
    test_file = test_dir.joinpath("ebsd_config.yml")
    # test_file = test_dir.joinpath("image_config_verbose.yml")
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
    ## create image object
    ebsd_object = factory.ebsd(
        microscope=microscope,
        step_settings=image_step_settings,
        step_name=image_step_name,
        yml_format=yml_format,
    )

    assert ebsd_object.image.beam.settings.tilt_correction == True

    microscope.disconnect()


@pytest.mark.skipif(
    not any(
        platform.uname().node.lower() in machine.lower()
        for machine in (cs.Constants.offline_machines)
    ),
    reason="Run only on offline machines only",
)
def test_laser(test_dir):
    # read config
    test_file = test_dir.joinpath("laser_config.yml")
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
    laser_step_name, laser_step_settings = ut.step_settings(
        db,
        step_number_key="step_number",
        step_number_val=1,
        yml_format=yml_format,
    )

    # connect to microscope
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    ## create image object
    found_laser = factory.laser(
        microscope=microscope,
        step_settings=laser_step_settings,
        step_name=laser_step_name,
        yml_format=yml_format,
    )

    known_laser = tbt.LaserSettings(
        microscope=microscope,
        pulse=tbt.LaserPulse(
            wavelength_nm=tbt.LaserWavelength.NM_515,
            divider=2,
            energy_uj=5.0,
            polarization=tbt.LaserPolarization.VERTICAL,
        ),
        objective_position_mm=2.5,
        beam_shift_um=tbt.Point(
            x=0.0,
            y=0.0,
        ),
        pattern=tbt.LaserPattern(
            mode=tbt.LaserPatternMode.FINE,
            rotation_deg=0.0,
            pulses_per_pixel=2,
            geometry=tbt.LaserBoxPattern(
                passes=3,
                size_x_um=200.0,
                size_y_um=100.0,
                pitch_x_um=2.0,
                pitch_y_um=3.0,
                scan_type=tbt.LaserScanType.SERPENTINE,
                coordinate_ref=tbt.CoordinateReference.UPPER_CENTER,
            ),
        ),
    )

    # test pulse
    assert found_laser.pulse.wavelength_nm == known_laser.pulse.wavelength_nm
    assert found_laser.pulse.divider == known_laser.pulse.divider
    assert found_laser.pulse.energy_uj == pytest.approx(known_laser.pulse.energy_uj)
    assert found_laser.pulse.polarization == known_laser.pulse.polarization

    # test optics
    assert found_laser.objective_position_mm == pytest.approx(
        known_laser.objective_position_mm
    )
    assert found_laser.beam_shift_um.x == pytest.approx(known_laser.beam_shift_um.x)
    assert found_laser.beam_shift_um.y == pytest.approx(known_laser.beam_shift_um.y)

    # test pattern
    # general
    assert found_laser.pattern.rotation_deg == pytest.approx(
        known_laser.pattern.rotation_deg
    )
    assert found_laser.pattern.mode == known_laser.pattern.mode
    assert found_laser.pattern.pulses_per_pixel == pytest.approx(
        known_laser.pattern.pulses_per_pixel
    )
    assert found_laser.pattern.pixel_dwell_ms == pytest.approx(
        known_laser.pattern.pixel_dwell_ms
    )

    # box
    assert found_laser.pattern.geometry.passes == known_laser.pattern.geometry.passes
    assert found_laser.pattern.geometry.size_x_um == pytest.approx(
        known_laser.pattern.geometry.size_x_um
    )
    assert found_laser.pattern.geometry.size_y_um == pytest.approx(
        known_laser.pattern.geometry.size_y_um
    )
    assert found_laser.pattern.geometry.pitch_x_um == pytest.approx(
        known_laser.pattern.geometry.pitch_x_um
    )
    assert found_laser.pattern.geometry.pitch_y_um == pytest.approx(
        known_laser.pattern.geometry.pitch_y_um
    )
    assert (
        found_laser.pattern.geometry.scan_type == known_laser.pattern.geometry.scan_type
    )
    assert (
        found_laser.pattern.geometry.coordinate_ref
        == known_laser.pattern.geometry.coordinate_ref
    )

    microscope.disconnect()


@pytest.mark.skipif(
    not any(
        platform.uname().node.lower() in machine.lower()
        for machine in (cs.Constants.offline_machines)
    ),
    reason="Run only on offline machines only",
)
def test_fib(test_dir):
    # read config
    test_file = test_dir.joinpath("fib_config.yml")
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
    fib_step_name, fib_step_settings = ut.step_settings(
        db,
        step_number_key="step_number",
        step_number_val=1,
        yml_format=yml_format,
    )

    # connect to microscope
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    ## create image object
    found_fib = factory.fib(
        microscope=microscope,
        step_settings=fib_step_settings,
        step_name=fib_step_name,
        yml_format=yml_format,
    )

    known_fib = tbt.FIBSettings(
        microscope=microscope,
        image=tbt.ImageSettings(
            microscope=microscope,
            beam=tbt.IonBeam(
                settings=tbt.BeamSettings(
                    voltage_kv=5.0,
                    voltage_tol_kv=0.5,
                    current_na=5.0,
                    current_tol_na=0.5,
                    hfw_mm=0.75,
                    working_dist_mm=10.021,
                    dynamic_focus=False,
                    tilt_correction=False,
                ),
            ),
            detector=tbt.Detector(
                type=tbt.DetectorType.ETD,
                mode=tbt.DetectorMode.SECONDARY_ELECTRONS,
                brightness=0.2,
                contrast=0.3,
            ),
            scan=tbt.Scan(
                rotation_deg=0.0,
                dwell_time_us=1.0,
                resolution=tbt.PresetResolution.PRESET_768X512,
            ),
            bit_depth=tbt.ColorDepth.BITS_8,
        ),
        mill_beam=tbt.IonBeam(
            settings=tbt.BeamSettings(
                voltage_kv=30.0,
                voltage_tol_kv=1.0,
                current_na=12.0,
                current_tol_na=1.0,
                hfw_mm=0.75,
                working_dist_mm=15.001,
                dynamic_focus=False,
                tilt_correction=False,
            ),
        ),
        pattern=tbt.FIBPattern(
            application="Al",
            type=tbt.FIBPatternType.RECTANGLE,
            geometry=tbt.FIBRectanglePattern(
                center_um=tbt.Point(x=5.11, y=0.0),
                width_um=500.0,
                height_um=40.0,
                depth_um=5.0,
                scan_direction=tbt.FIBPatternScanDirection.BOTTOM_TO_TOP,
                scan_type=tbt.FIBPatternScanType.SERPENTINE,
            ),
        ),
    )
    microscope.disconnect()

    # image beam check
    assert found_fib.image.beam.settings.voltage_kv == pytest.approx(
        known_fib.image.beam.settings.voltage_kv
    )
    assert found_fib.image.beam.settings.voltage_tol_kv == pytest.approx(
        known_fib.image.beam.settings.voltage_tol_kv
    )
    assert found_fib.image.beam.settings.current_na == pytest.approx(
        known_fib.image.beam.settings.current_na
    )
    assert found_fib.image.beam.settings.current_tol_na == pytest.approx(
        known_fib.image.beam.settings.current_tol_na
    )

    # image scan scheck
    assert found_fib.image.scan.rotation_deg == pytest.approx(
        known_fib.image.scan.rotation_deg
    )
    assert found_fib.image.scan.dwell_time_us == pytest.approx(
        known_fib.image.scan.dwell_time_us
    )
    assert found_fib.image.scan.resolution == known_fib.image.scan.resolution

    # image detector check
    assert found_fib.image.detector.mode == pytest.approx(known_fib.image.detector.mode)
    assert found_fib.image.detector.type == pytest.approx(known_fib.image.detector.type)
    assert found_fib.image.detector.contrast == pytest.approx(
        known_fib.image.detector.contrast
    )
    assert found_fib.image.detector.brightness == pytest.approx(
        known_fib.image.detector.brightness
    )

    # mill beam check
    assert found_fib.mill_beam.settings.voltage_kv == pytest.approx(
        known_fib.mill_beam.settings.voltage_kv
    )
    assert found_fib.mill_beam.settings.voltage_tol_kv == pytest.approx(
        known_fib.mill_beam.settings.voltage_tol_kv
    )
    assert found_fib.mill_beam.settings.current_na == pytest.approx(
        known_fib.mill_beam.settings.current_na
    )
    assert found_fib.mill_beam.settings.current_tol_na == pytest.approx(
        known_fib.mill_beam.settings.current_tol_na
    )

    # pattern check
    assert found_fib.pattern.application == known_fib.pattern.application
    assert found_fib.pattern.type == known_fib.pattern.type
    assert found_fib.pattern.geometry.center_um.x == pytest.approx(
        known_fib.pattern.geometry.center_um.x
    )
    assert found_fib.pattern.geometry.center_um.y == pytest.approx(
        known_fib.pattern.geometry.center_um.y
    )
    assert found_fib.pattern.geometry.width_um == pytest.approx(
        known_fib.pattern.geometry.width_um
    )
    assert found_fib.pattern.geometry.height_um == pytest.approx(
        known_fib.pattern.geometry.height_um
    )
    assert found_fib.pattern.geometry.depth_um == pytest.approx(
        known_fib.pattern.geometry.depth_um
    )
    assert (
        found_fib.pattern.geometry.scan_direction
        == known_fib.pattern.geometry.scan_direction
    )
    assert found_fib.pattern.geometry.scan_type == known_fib.pattern.geometry.scan_type


def test_general(test_dir):
    # read config
    test_file = test_dir.joinpath("general_config.yml")
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

    general_db = ut.general_settings(db, yml_format=yml_format)

    with pytest.raises(ValueError) as err:
        general_settings = factory.general(
            general_db=general_db,
            yml_format=yml_format,
        )
    assert err.type == ValueError
    assert (
        err.value.args[0]
        == f'Requested experimental directory of "None", which is not a valid path.'
    )

    temp_dir = Path(__file__).parent.joinpath("temp_exp")
    general_db["exp_dir"] = str(temp_dir)

    general_settings = factory.general(
        general_db=general_db,
        yml_format=yml_format,
    )

    known_settings = tbt.GeneralSettings(
        yml_version=1.0,
        slice_thickness_um=2.0,
        max_slice_number=400,
        pre_tilt_deg=36.0,
        sectioning_axis=tbt.SectioningAxis.Z,
        stage_tolerance=tbt.StageTolerance(
            translational_um=0.5,
            angular_deg=0.02,
        ),
        connection=tbt.MicroscopeConnection(
            host="localhost",
            # port=None,
        ),
        EBSD_OEM=tbt.ExternalDeviceOEM.NONE,
        EDS_OEM=tbt.ExternalDeviceOEM.NONE,
        exp_dir=temp_dir,
        h5_log_name="log",
        step_count=1,
    )

    assert general_settings.slice_thickness_um == pytest.approx(
        known_settings.slice_thickness_um
    )
    assert general_settings.max_slice_number == known_settings.max_slice_number
    assert general_settings.pre_tilt_deg == pytest.approx(known_settings.pre_tilt_deg)
    assert general_settings.sectioning_axis == known_settings.sectioning_axis
    assert general_settings.stage_tolerance.translational_um == pytest.approx(
        known_settings.stage_tolerance.translational_um
    )
    assert general_settings.stage_tolerance.angular_deg == pytest.approx(
        known_settings.stage_tolerance.angular_deg
    )
    assert general_settings.connection.host == known_settings.connection.host
    assert general_settings.connection.port == known_settings.connection.port
    assert general_settings.EBSD_OEM == known_settings.EBSD_OEM
    assert general_settings.EDS_OEM == known_settings.EDS_OEM
    assert general_settings.exp_dir == known_settings.exp_dir
    assert general_settings.h5_log_name == known_settings.h5_log_name
    assert general_settings.step_count == known_settings.step_count

    ut.remove_directory(temp_dir)
