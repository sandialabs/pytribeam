## python standard libraries
from pathlib import Path
import platform
import time
import warnings


# 3rd party libraries
import pytest
from PIL import Image as pil_img
import numpy as np

# Local
import pytribeam.constants as cs
from pytribeam.constants import Conversions, Constants
import pytribeam.insertable_devices as devices
import pytribeam.image as img
import pytribeam.factory as factory
import pytribeam.stage as stage
import pytribeam.types as tbt
import pytribeam.utilities as ut


@pytest.fixture
def test_dir() -> str:
    """The relative path and file string locating the default yml test file."""

    return Path(__file__).parent.joinpath("files")


#### tests ####


@ut.run_on_standalone_machine
def test_coordinate_system():
    """Test setting of default coordinate system"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    aa = stage.coordinate_system(microscope=microscope)
    assert aa == True

    # TODO CAPTURE WARNING
    mode = tbt.StageCoordinateSystem.SPECIMEN
    with pytest.warns(UserWarning) as warning:
        bb = stage.coordinate_system(
            microscope=microscope,
            mode=mode,
        )
    assert bb == True

    microscope.disconnect()
    # assert 4 == 2


@ut.run_on_standalone_machine
def test_encoder_to_user_position():
    """Tests conversion from microscope encoder position to user position"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    encoder_pos = tbt.StagePositionEncoder(
        x=0.005,
        y=0.002,
        z=0.003,
        r=np.pi / 2,
        t=np.pi / 6,
        coordinate_system=tbt.StageCoordinateSystem.RAW.value,
    )

    user_pos = stage.encoder_to_user_position(encoder_pos)
    assert user_pos.x_mm == pytest.approx(encoder_pos.x * Conversions.M_TO_MM)
    assert user_pos.y_mm == pytest.approx(encoder_pos.y * Conversions.M_TO_MM)
    assert user_pos.z_mm == pytest.approx(encoder_pos.z * Conversions.M_TO_MM)
    assert user_pos.r_deg == pytest.approx(encoder_pos.r * Conversions.RAD_TO_DEG)
    assert user_pos.t_deg == pytest.approx(encoder_pos.t * Conversions.RAD_TO_DEG)

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_user_to_encoder_position():
    """Tests conversion from microscope encoder position to user position"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    user_pos = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=3.0,
        r_deg=90.0,
        t_deg=30.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )

    encoder_pos = stage.user_to_encoder_position(user_pos)

    assert user_pos.x_mm == pytest.approx(encoder_pos.x * Conversions.M_TO_MM)
    assert user_pos.y_mm == pytest.approx(encoder_pos.y * Conversions.M_TO_MM)
    assert user_pos.z_mm == pytest.approx(encoder_pos.z * Conversions.M_TO_MM)
    assert user_pos.r_deg == pytest.approx(encoder_pos.r * Conversions.RAD_TO_DEG)
    assert user_pos.t_deg == pytest.approx(encoder_pos.t * Conversions.RAD_TO_DEG)

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_stop():
    """Test stopping of microscope stage"""
    # TODO asynchronous calls....
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    with pytest.raises(SystemError) as err:
        stage.stop(microscope=microscope)
    assert err.type == SystemError
    assert err.value.args[0] == "Microscope stage movement was halted."


def no_pretilt(microscope: tbt.Microscope) -> None:
    """helper function for test_target_position"""
    user_pos = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=3.0,
        r_deg=90.0,
        t_deg=30.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )
    slice_number = 11
    slice_thickness_um = 2.0

    stage_settings = tbt.StageSettings(
        microscope=microscope,
        initial_position=user_pos,
        pretilt_angle_deg=0.0,
        sectioning_axis=tbt.SectioningAxis.Z,
        rotation_side=tbt.RotationSide.FSL_MILL,
    )

    found_pos = stage.target_position(
        stage=stage_settings,
        slice_number=slice_number,
        slice_thickness_um=slice_thickness_um,
    )

    known_pos = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=3.020,
        r_deg=90.0,
        t_deg=30.0,
    )

    assert known_pos.x_mm == pytest.approx(found_pos.x_mm)
    assert known_pos.y_mm == pytest.approx(found_pos.y_mm)
    assert known_pos.z_mm == pytest.approx(found_pos.z_mm)
    assert known_pos.r_deg == pytest.approx(found_pos.r_deg)
    assert known_pos.t_deg == pytest.approx(found_pos.t_deg)


def pretilt(microscope: tbt.Microscope) -> None:
    """helper function for test_target_position"""
    user_pos = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=3.0,
        r_deg=90.0,
        t_deg=30.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )
    slice_number = 11
    slice_thickness_um = 2.0

    stage_settings = tbt.StageSettings(
        microscope=microscope,
        initial_position=user_pos,
        pretilt_angle_deg=30.0,
        sectioning_axis=tbt.SectioningAxis.Z,
        rotation_side=tbt.RotationSide.FSL_MILL,
    )

    found_pos = stage.target_position(
        stage=stage_settings,
        slice_number=slice_number,
        slice_thickness_um=slice_thickness_um,
    )

    known_pos = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=1.99,
        z_mm=3.01732,
        r_deg=90.0,
        t_deg=30.0,
    )

    assert known_pos.x_mm == pytest.approx(found_pos.x_mm)
    assert known_pos.y_mm == pytest.approx(found_pos.y_mm)
    assert known_pos.z_mm == pytest.approx(found_pos.z_mm)
    assert known_pos.r_deg == pytest.approx(found_pos.r_deg)
    assert known_pos.t_deg == pytest.approx(found_pos.t_deg)


def fib_mill_rotation_side(microscope: tbt.Microscope) -> None:
    """helper function for test_target_position"""
    user_pos = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=3.0,
        r_deg=90.0,
        t_deg=30.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )
    slice_number = 11
    slice_thickness_um = 2.0

    stage_settings = tbt.StageSettings(
        microscope=microscope,
        initial_position=user_pos,
        pretilt_angle_deg=30.0,
        sectioning_axis=tbt.SectioningAxis.Z,
        rotation_side=tbt.RotationSide.FIB_MILL,
    )

    found_pos = stage.target_position(
        stage=stage_settings,
        slice_number=slice_number,
        slice_thickness_um=slice_thickness_um,
    )

    known_pos = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.01,
        z_mm=3.01732,
        r_deg=90.0,
        t_deg=30.0,
    )

    assert known_pos.x_mm == pytest.approx(found_pos.x_mm)
    assert known_pos.y_mm == pytest.approx(found_pos.y_mm)
    assert known_pos.z_mm == pytest.approx(found_pos.z_mm)
    assert known_pos.r_deg == pytest.approx(found_pos.r_deg)
    assert known_pos.t_deg == pytest.approx(found_pos.t_deg)


def ebeam_normal_rotation_side(microscope: tbt.Microscope) -> None:
    """helper function for test_target_position"""
    user_pos = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=3.0,
        r_deg=90.0,
        t_deg=30.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )
    slice_number = 11
    slice_thickness_um = 2.0

    stage_settings = tbt.StageSettings(
        microscope=microscope,
        initial_position=user_pos,
        pretilt_angle_deg=30.0,
        sectioning_axis=tbt.SectioningAxis.Z,
        rotation_side=tbt.RotationSide.EBEAM_NORMAL,
    )

    found_pos = stage.target_position(
        stage=stage_settings,
        slice_number=slice_number,
        slice_thickness_um=slice_thickness_um,
    )

    known_pos = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.00,
        z_mm=3.01732,
        r_deg=90.0,
        t_deg=30.0,
    )

    assert known_pos.x_mm == pytest.approx(found_pos.x_mm)
    assert known_pos.y_mm == pytest.approx(found_pos.y_mm)
    assert known_pos.z_mm == pytest.approx(found_pos.z_mm)
    assert known_pos.r_deg == pytest.approx(found_pos.r_deg)
    assert known_pos.t_deg == pytest.approx(found_pos.t_deg)


@ut.run_on_standalone_machine
def test_target_position():
    """Test calculation of target position"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    no_pretilt(microscope=microscope)

    pretilt(microscope=microscope)

    fib_mill_rotation_side(microscope=microscope)

    ebeam_normal_rotation_side(microscope=microscope)

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_safe():
    """Test determination of safe position"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    good_pos = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=3.0,
        r_deg=90.0,
        t_deg=30.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )

    assert stage.safe(microscope=microscope, position=good_pos) == True

    bad_pos_x = tbt.StagePositionUser(
        x_mm=50000.0,
        y_mm=2.0,
        z_mm=5.0,
        r_deg=90.0,
        t_deg=30.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )

    assert stage.safe(microscope=microscope, position=bad_pos_x) == False

    bad_pos_y = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=200.0,
        z_mm=2.0,
        r_deg=90.0,
        t_deg=30.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )

    assert stage.safe(microscope=microscope, position=bad_pos_y) == False

    bad_pos_z = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=20.1,
        r_deg=90.0,
        t_deg=30.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )

    assert stage.safe(microscope=microscope, position=bad_pos_z) == False

    bad_pos_r = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=2.0,
        r_deg=190.0,
        t_deg=30.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )

    assert stage.safe(microscope=microscope, position=bad_pos_r) == False

    bad_pos_t = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=2.0,
        r_deg=90.0,
        t_deg=360.1,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )

    assert stage.safe(microscope=microscope, position=bad_pos_t) == False

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_axis_in_range():
    """Tests whether axis is within stage tolerance"""

    microscope = tbt.Microscope()
    microscope.connect("localhost")

    stage.home_stage(microscope=microscope)

    target_position = tbt.StagePositionUser(
        x_mm=0.0,
        y_mm=0.0005,
        z_mm=-0.2,
        r_deg=0.1,
        t_deg=3,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )
    stage_tolerance = tbt.StageTolerance(
        translational_um=0.5,
        angular_deg=0.1,
    )

    assert (
        stage.axis_in_range(
            microscope=microscope,
            axis=tbt.StageAxis.X,
            target_position=target_position,
            stage_tolerance=stage_tolerance,
        )
        == True
    )
    assert (
        stage.axis_in_range(
            microscope=microscope,
            axis=tbt.StageAxis.Y,
            target_position=target_position,
            stage_tolerance=stage_tolerance,
        )
        == True
    )
    assert (
        stage.axis_in_range(
            microscope=microscope,
            axis=tbt.StageAxis.Z,
            target_position=target_position,
            stage_tolerance=stage_tolerance,
        )
        == False
    )
    assert (
        stage.axis_in_range(
            microscope=microscope,
            axis=tbt.StageAxis.R,
            target_position=target_position,
            stage_tolerance=stage_tolerance,
        )
        == True
    )
    assert (
        stage.axis_in_range(
            microscope=microscope,
            axis=tbt.StageAxis.T,
            target_position=target_position,
            stage_tolerance=stage_tolerance,
        )
        == False
    )


@ut.run_on_standalone_machine
def test_move_axis():
    """Tests single axis movement"""

    microscope = tbt.Microscope()
    microscope.connect("localhost")

    stage.home_stage(microscope=microscope)

    position = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=3.0,
        r_deg=90.0,
        t_deg=30.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )
    stage_tolerance = tbt.StageTolerance(
        translational_um=0.5,
        angular_deg=0.02,
    )

    stage.move_axis(
        microscope=microscope,
        axis=tbt.StageAxis.X,
        target_position=position,
        num_attempts=1,
        stage_delay_s=0.0,
    )
    found_pos = factory.active_stage_position_settings(microscope=microscope)
    assert found_pos.x_mm == pytest.approx(position.x_mm)

    stage.move_axis(
        microscope=microscope,
        axis=tbt.StageAxis.Y,
        target_position=position,
        num_attempts=1,
        stage_delay_s=0.0,
    )
    found_pos = factory.active_stage_position_settings(microscope=microscope)
    assert found_pos.y_mm == pytest.approx(position.y_mm)

    stage.move_axis(
        microscope=microscope,
        axis=tbt.StageAxis.Z,
        target_position=position,
        num_attempts=1,
        stage_delay_s=0.0,
    )
    found_pos = factory.active_stage_position_settings(microscope=microscope)
    assert found_pos.z_mm == pytest.approx(position.z_mm)

    stage.move_axis(
        microscope=microscope,
        axis=tbt.StageAxis.R,
        target_position=position,
        num_attempts=1,
        stage_delay_s=0.0,
    )
    found_pos = factory.active_stage_position_settings(microscope=microscope)
    assert found_pos.r_deg == pytest.approx(position.r_deg)

    stage.move_axis(
        microscope=microscope,
        axis=tbt.StageAxis.T,
        target_position=position,
        num_attempts=1,
        stage_delay_s=0.0,
    )
    found_pos = factory.active_stage_position_settings(microscope=microscope)
    assert found_pos.t_deg == pytest.approx(position.t_deg)

    # assert found_pos.x_mm == pytest.approx(position.x_mm)
    # assert found_pos.y_mm == pytest.approx(position.y_mm)
    # assert found_pos.z_mm == pytest.approx(position.z_mm)
    # assert found_pos.r_deg == pytest.approx(position.r_deg)
    # assert found_pos.t_deg == pytest.approx(position.t_deg)

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_move_stage():
    """Tests movement of stage to requested position"""

    microscope = tbt.Microscope()
    microscope.connect("localhost")

    stage.home_stage(microscope=microscope)

    found_pos_0 = factory.active_stage_position_settings(microscope=microscope)
    assert found_pos_0.x_mm == pytest.approx(0.0)
    assert found_pos_0.y_mm == pytest.approx(0.0)
    assert found_pos_0.z_mm == pytest.approx(0.0)
    assert found_pos_0.r_deg == pytest.approx(0.0)
    assert found_pos_0.t_deg == pytest.approx(0.0)

    position = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=3.0,
        r_deg=90.0,
        t_deg=30.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )

    stage_tolerance = tbt.StageTolerance(
        translational_um=0.5,
        angular_deg=0.02,
    )

    stage.move_stage(
        microscope=microscope,
        target_position=position,
        stage_tolerance=stage_tolerance,
    )
    found_pos = factory.active_stage_position_settings(microscope=microscope)
    assert found_pos.x_mm == pytest.approx(position.x_mm)
    assert found_pos.y_mm == pytest.approx(position.y_mm)
    assert found_pos.z_mm == pytest.approx(position.z_mm)
    assert found_pos.r_deg == pytest.approx(position.r_deg)
    assert found_pos.t_deg == pytest.approx(position.t_deg)

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_move_completed():
    """tests move_completed function"""

    position = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=3.0,
        r_deg=90.0,
        t_deg=30.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )
    stage_tolerance = tbt.StageTolerance(
        translational_um=0.5,
        angular_deg=0.02,
    )

    microscope = tbt.Microscope()
    microscope.connect("localhost")

    stage.home_stage(microscope=microscope)

    completed = stage.move_completed(
        microscope=microscope,
        target_position=position,
        stage_tolerance=stage_tolerance,
    )

    assert completed == False

    microscope.disconnect()


@ut.run_on_standalone_machine
def test_move_to_position_simulator():
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    devices.retract_all_devices(
        microscope=microscope,
        enable_EBSD=False,
        enable_EDS=False,
    )
    stage.home_stage(microscope=microscope)

    # catch unsafe position error
    position = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=22.0,
        r_deg=10.0,
        t_deg=3.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )
    stage_tolerance = tbt.StageTolerance(
        translational_um=0.5,
        angular_deg=0.02,
    )
    with pytest.raises(ValueError) as err:
        stage.move_to_position(
            microscope=microscope,
            target_position=position,
            stage_tolerance=stage_tolerance,
        )
    assert err.type == ValueError
    err_msg = "Destination position of StagePositionUser(x_mm=5.0, y_mm=2.0, z_mm=22.0, r_deg=10.0, t_deg=3.0, coordinate_system=<StageCoordinateSystem.RAW: 'Raw'>) is unsafe. Stage limits are:\n\tStageLimits(x_mm=Limit(min=-55.0, max=55.0), y_mm=Limit(min=-55.0, max=55.0), z_mm=Limit(min=0.0, max=20.0), r_deg=Limit(min=-180.0, max=180.0), t_deg=Limit(min=0.0, max=360.0)). \nExiting now"
    assert err.value.args[0] == err_msg

    # good position
    position = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=2.0,
        r_deg=10.0,
        t_deg=3.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )
    stage_tolerance = tbt.StageTolerance(
        translational_um=0.5,
        angular_deg=0.02,
    )
    stage.move_to_position(
        microscope=microscope,
        target_position=position,
        stage_tolerance=stage_tolerance,
    )
    found_pos = factory.active_stage_position_settings(microscope=microscope)
    assert found_pos.x_mm == pytest.approx(position.x_mm)
    assert found_pos.y_mm == pytest.approx(position.y_mm)
    assert found_pos.z_mm == pytest.approx(position.z_mm)
    assert found_pos.r_deg == pytest.approx(position.r_deg)
    assert found_pos.t_deg == pytest.approx(position.t_deg)
    microscope.disconnect()


def test_home_stage():
    """tests move to home position"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    # retract all devices
    devices.retract_all_devices(
        microscope=microscope,
        enable_EBSD=True,
        enable_EDS=True,
    )

    stage_tolerance = tbt.StageTolerance(
        translational_um=0.5,
        angular_deg=0.02,
    )

    stage.home_stage(microscope=microscope, stage_tolerance=stage_tolerance)
    found_pos = factory.active_stage_position_settings(microscope=microscope)
    assert found_pos.x_mm == pytest.approx(
        cs.Constants.home_position.x_mm, abs=stage_tolerance.translational_um
    )
    assert found_pos.y_mm == pytest.approx(
        cs.Constants.home_position.y_mm, abs=stage_tolerance.translational_um
    )
    assert found_pos.z_mm == pytest.approx(
        cs.Constants.home_position.z_mm, abs=stage_tolerance.translational_um
    )
    assert found_pos.r_deg == pytest.approx(
        cs.Constants.home_position.r_deg, abs=stage_tolerance.angular_deg
    )
    assert found_pos.t_deg == pytest.approx(
        cs.Constants.home_position.t_deg, abs=stage_tolerance.angular_deg
    )

    microscope.disconnect()


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
def test_move_to_position_hardware():
    """tests move_to_position() on physical instrument"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    # retract all devices
    devices.retract_all_devices(
        microscope=microscope,
        enable_EBSD=True,
        enable_EDS=True,
    )
    stage.home_stage(microscope=microscope)

    position_1 = tbt.StagePositionUser(
        x_mm=5.0,
        y_mm=2.0,
        z_mm=3.0,
        r_deg=10.0,
        t_deg=3.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )
    stage_tolerance = tbt.StageTolerance(
        translational_um=0.75,
        angular_deg=0.02,
    )
    stage.move_to_position(
        microscope=microscope,
        target_position=position_1,
        stage_tolerance=stage_tolerance,
    )
    found_pos = factory.active_stage_position_settings(microscope=microscope)
    assert found_pos.x_mm == pytest.approx(
        position_1.x_mm, abs=stage_tolerance.translational_um
    )
    assert found_pos.y_mm == pytest.approx(
        position_1.y_mm, abs=stage_tolerance.translational_um
    )
    assert found_pos.z_mm == pytest.approx(
        position_1.z_mm, abs=stage_tolerance.translational_um
    )
    assert found_pos.r_deg == pytest.approx(
        position_1.r_deg, abs=stage_tolerance.angular_deg
    )
    assert found_pos.t_deg == pytest.approx(
        position_1.t_deg, abs=stage_tolerance.angular_deg
    )

    # ensure it tilts down first for change in r-axis
    # should then only move tilt axis back up after r-axis
    position_2 = tbt.StagePositionUser(
        x_mm=position_1.x_mm,
        y_mm=position_1.y_mm,
        z_mm=position_1.z_mm,
        r_deg=5.0,
        t_deg=3.0,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )
    stage_tolerance = tbt.StageTolerance(
        translational_um=0.5,
        angular_deg=0.02,
    )
    stage.move_to_position(
        microscope=microscope,
        target_position=position_2,
        stage_tolerance=stage_tolerance,
    )
    found_pos = factory.active_stage_position_settings(microscope=microscope)
    assert found_pos.x_mm == pytest.approx(
        position_2.x_mm, abs=stage_tolerance.translational_um
    )
    assert found_pos.y_mm == pytest.approx(
        position_2.y_mm, abs=stage_tolerance.translational_um
    )
    assert found_pos.z_mm == pytest.approx(
        position_2.z_mm, abs=stage_tolerance.translational_um
    )
    assert found_pos.r_deg == pytest.approx(
        position_2.r_deg, abs=stage_tolerance.angular_deg
    )
    assert found_pos.t_deg == pytest.approx(
        position_2.t_deg, abs=stage_tolerance.angular_deg
    )

    stage.home_stage(microscope=microscope)

    microscope.disconnect()
