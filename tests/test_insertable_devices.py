## python standard libraries
from pathlib import Path
import platform
import time

# 3rd party libraries
import pytest


# Local
import pytribeam.constants as cs
from pytribeam.constants import Conversions
import pytribeam.insertable_devices as devices
import pytribeam.factory as factory
import pytribeam.image as img
import pytribeam.types as tbt
import pytribeam.utilities as ut
import pytribeam.stage as stage


@ut.hardware_movement
def test_connect_EBSD():
    assert devices.connect_EBSD() == tbt.RetractableDeviceState.RETRACTED


@ut.hardware_movement
def test_connect_EDS():
    assert devices.connect_EDS() == tbt.RetractableDeviceState.RETRACTED


def test_detector_insertable():
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    devices.device_access(microscope=microscope)
    valid_detectors = microscope.detector.type.available_values
    for detector in valid_detectors:
        detector = tbt.DetectorType(detector)  # overwrite
        img.detector_type(
            microscope=microscope,
            detector=detector,
        )
        insertable = devices.detector_insertable(
            microscope=microscope,
            detector=detector,
        )
        if detector == "CBS":
            assert insertable == True
            state = devices.detector_state(
                microscope=microscope,
                detector=detector,
            )
            assert state == tbt.RetractableDeviceState.RETRACTED.value
            continue
        if detector == "External":
            assert insertable == False
            state = devices.detector_state(
                microscope=microscope,
                detector=detector,
            )
            assert state == None
            continue
        if detector == "ETD":
            assert insertable == False
            state = devices.detector_state(
                microscope=microscope,
                detector=detector,
            )
            assert state == None
            continue

    microscope.disconnect()


@ut.hardware_movement
def test_detector_state():
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    devices.device_access(microscope=microscope)
    detector = tbt.DetectorType.CBS
    val = devices.detector_state(microscope=microscope, detector=detector)
    assert val != None

    detector_2 = tbt.DetectorType.ETD
    val_2 = devices.detector_state(microscope=microscope, detector=detector_2)
    assert val_2 == None


@ut.hardware_movement
def test_detectors_will_collide():
    # TODO enable no stage restrictions first
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    assert (
        devices.retract_all_devices(
            microscope=microscope,
            enable_EBSD=True,
            enable_EDS=True,
        )
        == True
    )

    stage.home_stage(microscope=microscope)

    devices.device_access(microscope=microscope)

    devices.retract_EDS(microscope=microscope)
    cbs = tbt.DetectorType.CBS
    devices.insert_detector(microscope=microscope, detector=cbs)
    val = devices.detectors_will_collide(
        microscope=microscope, detector_to_insert=tbt.DetectorType.EDS
    )
    devices.retract_device(microscope=microscope, detector=cbs)
    assert val == True

    devices.insert_EDS(microscope=microscope)
    val2 = devices.detectors_will_collide(
        microscope=microscope, detector_to_insert=tbt.DetectorType.CBS
    )
    assert val2 == True
    devices.retract_EDS(microscope=microscope)
    assert (
        devices.external.EDS_CameraStatus()
        == tbt.RetractableDeviceState.RETRACTED.value
    )
    microscope.disconnect()


@ut.hardware_movement
def test_insert_retract_EDS():
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    assert (
        devices.retract_all_devices(
            microscope=microscope,
            enable_EBSD=True,
            enable_EDS=True,
        )
        == True
    )

    stage.home_stage(microscope=microscope)

    devices.device_access(microscope=microscope)

    devices.retract_EDS(microscope=microscope)
    assert (
        devices.external.EDS_CameraStatus()
        == tbt.RetractableDeviceState.RETRACTED.value
    )

    devices.insert_EDS(microscope=microscope)
    assert (
        devices.external.EDS_CameraStatus() == tbt.RetractableDeviceState.INSERTED.value
    )

    devices.retract_EDS(microscope=microscope)
    assert (
        devices.external.EDS_CameraStatus()
        == tbt.RetractableDeviceState.RETRACTED.value
    )
    microscope.disconnect()


def prepare_stage_test_tilt(
    microscope: tbt.Microscope,
    stage_tolerance: tbt.StageTolerance,
    degree: float,
):
    """Helper function for hardware testing that homes stage and goes to requested tilt angle in degrees"""
    assert (
        devices.retract_all_devices(
            microscope=microscope,
            enable_EBSD=True,
            enable_EDS=True,
        )
        == True
    )
    stage.home_stage(microscope=microscope, stage_tolerance=stage_tolerance)

    # safe EBSD position
    tilt_pos = tbt.StagePositionUser(
        x_mm=0.0,
        y_mm=0.0,
        z_mm=0.0,
        r_deg=0.0,
        t_deg=degree,
        coordinate_system=tbt.StageCoordinateSystem.RAW,
    )
    stage.move_to_position(
        microscope=microscope,
        target_position=tilt_pos,
        stage_tolerance=stage_tolerance,
    )
    return


@ut.hardware_movement
def test_insert_retract_EBSD():
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    stage_tolerance = tbt.StageTolerance(
        translational_um=2.0,
        angular_deg=0.5,
    )

    stage.home_stage(microscope=microscope, stage_tolerance=stage_tolerance)
    
    prepare_stage_test_tilt(
        microscope=microscope,
        stage_tolerance=stage_tolerance,
        degree=30.0,
    )

    devices.device_access(microscope=microscope)

    devices.retract_EBSD(microscope=microscope)
    assert (
        devices.external.EBSD_CameraStatus()
        == tbt.RetractableDeviceState.RETRACTED.value
    )

    devices.insert_EBSD(microscope=microscope)
    assert (
        devices.external.EBSD_CameraStatus()
        == tbt.RetractableDeviceState.INSERTED.value
    )

    devices.retract_EBSD(microscope=microscope)
    assert (
        devices.external.EBSD_CameraStatus()
        == tbt.RetractableDeviceState.RETRACTED.value
    )

    stage.home_stage(microscope=microscope, stage_tolerance=stage_tolerance)

    microscope.disconnect()


@ut.hardware_movement
def test_insert_detector():
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    devices.device_access(microscope=microscope)

    stage_tolerance = tbt.StageTolerance(
        translational_um=2.0,
        angular_deg=0.5,
    )

    # go to 30 degrees to ensure CBS stage restrictions are off
    tilt_angle_deg = 30.0
    prepare_stage_test_tilt(
        microscope=microscope,
        stage_tolerance=stage_tolerance,
        degree=tilt_angle_deg,
    )

    with pytest.raises(ValueError) as err:
        devices.insert_detector(
            microscope=microscope,
            detector=tbt.DetectorType.ETD,
        )
    assert err.type == ValueError
    assert err.value.args[0] == "ETD detector is not insertable."

    devices.insert_detector(
        microscope=microscope,
        detector=tbt.DetectorType.CBS,
    )
    assert microscope.detector.state == tbt.RetractableDeviceState.INSERTED.value

    current_t_deg = factory.active_stage_position_settings(microscope=microscope).t_deg
    assert ut.in_interval(
        val=current_t_deg,
        limit=tbt.Limit(
            tilt_angle_deg - stage_tolerance.angular_deg,
            max=tilt_angle_deg + stage_tolerance.angular_deg,
        ),
        type=tbt.IntervalType.CLOSED,
    ), f"Stage should be at tilt of {tilt_angle_deg} +/-{stage_tolerance.angular_deg} degrees but is at a tilt of {current_t_deg} degrees. Please ensure stage restrictions are turned off for CBS insert, otherwise microscope will automatically tilt down to 0.5 degrees."

    devices.retract_device(microscope=microscope, detector=tbt.DetectorType.CBS)
    assert microscope.detector.state == tbt.RetractableDeviceState.RETRACTED.value

    stage.home_stage(
        microscope=microscope,
        stage_tolerance=stage_tolerance,
    )

    microscope.disconnect()


@ut.hardware_movement
def test_no_CBS_insert():
    """Test that CBS detector won't insert if EDS is in"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    assert (
        devices.retract_all_devices(
            microscope=microscope,
            enable_EBSD=True,
            enable_EDS=True,
        )
        == True
    )

    stage_tolerance = tbt.StageTolerance(
        translational_um=2.0,
        angular_deg=0.5,
    )
    stage.home_stage(microscope=microscope, stage_tolerance=stage_tolerance)

    devices.retract_EDS(microscope=microscope)
    assert (
        devices.external.EDS_CameraStatus()
        == tbt.RetractableDeviceState.RETRACTED.value
    )
    devices.insert_EDS(microscope=microscope)
    assert (
        devices.external.EDS_CameraStatus() == tbt.RetractableDeviceState.INSERTED.value
    )

    devices.device_access(microscope=microscope)
    with pytest.raises(SystemError) as err:
        devices.insert_detector(
            microscope=microscope,
            detector=tbt.DetectorType.CBS,
        )
    assert err.type == SystemError
    msg = "Error. Cannot insert CBS which may collide with another detector.\n                Disallowed detector combinations are: [[<DetectorType.CBS: 'CBS'>, <DetectorType.EDS: 'EDS'>], [<DetectorType.CBS: 'CBS'>, <DetectorType.EBSD: 'EBSD'>]]"
    assert err.value.args[0] == msg

    devices.retract_EDS(microscope=microscope)
    microscope.disconnect()


@ut.hardware_movement
def test_no_EDS_insert():
    """EDS detector should not insert on this"""
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    assert (
        devices.retract_all_devices(
            microscope=microscope,
            enable_EBSD=True,
            enable_EDS=True,
        )
        == True
    )

    stage_tolerance = tbt.StageTolerance(
        translational_um=2.0,
        angular_deg=0.5,
    )
    stage.home_stage(microscope=microscope, stage_tolerance=stage_tolerance)

    devices.device_access(microscope=microscope)
    devices.insert_detector(
        microscope=microscope,
        detector=tbt.DetectorType.CBS,
    )

    with pytest.raises(SystemError) as err:
        devices.insert_EDS(microscope=microscope)
    assert err.type == SystemError
    assert (
        err.value.args[0]
        == 'Error. Cannot insert EDS while CBS not in "Retracted" state. \n            CBS detector currently in "Inserted" state.'
    )
    devices.retract_device(
        microscope=microscope,
        detector=tbt.DetectorType.CBS,
    )
    microscope.disconnect()


@ut.hardware_movement
def test_retract_all_devices():
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    img.set_view(
        microscope=microscope,
        quad=tbt.ViewQuad.LOWER_RIGHT,
    )
    aa = devices.retract_all_devices(
        microscope=microscope,
        enable_EBSD=True,
        enable_EDS=True,
    )
    assert aa == True
    microscope.disconnect()


@ut.hardware_movement
def test_specimen_current():
    microscope = tbt.Microscope()
    microscope.connect("localhost")
    devices.device_access(microscope=microscope)
    current_na = devices.specimen_current(microscope=microscope)

    microscope.disconnect()

    assert current_na != pytest.approx(0.0)
