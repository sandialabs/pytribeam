#!/usr/bin/python3
"""
Insertable Devices Module
==========================

This module contains functions for managing and controlling insertable devices in the microscope, including detectors, EBSD, and EDS systems.

Functions
---------
detector_insertable(microscope: tbt.Microscope, detector: tbt.DetectorType) -> bool
    Determine whether or not the built-in microscope detector is insertable and return its state.

detector_state(microscope: tbt.Microscope, detector: tbt.DetectorType) -> tbt.RetractableDeviceState
    Determine the state of the detector, only valid if the detector is insertable.

detectors_will_collide(microscope: tbt.Microscope, detector_to_insert: tbt.DetectorType) -> bool
    Determine if a collision may occur when inserting the specified detector.

device_access(microscope: tbt.Microscope) -> tbt.ViewQuad
    Switch to the upper-left quadrant and assign the electron beam as the active device.

insert_EBSD(microscope: tbt.Microscope) -> bool
    Insert the EBSD camera into the microscope.

insert_EDS(microscope: tbt.Microscope) -> bool
    Insert the EDS camera into the microscope.

insert_detector(microscope: tbt.Microscope, detector: tbt.DetectorType, time_delay_s: float = 0.5) -> bool
    Insert the selected detector into the microscope.

retract_all_devices(microscope: tbt.Microscope, enable_EBSD: bool, enable_EDS: bool) -> bool
    Retract all insertable devices, including microscope detectors and EBSD/EDS detectors if integrated.

connect_EBSD() -> tbt.RetractableDeviceState
    Connect to the EBSD system and retrieve the camera status.

retract_EBSD(microscope: tbt.Microscope) -> bool
    Retract the EBSD camera from the microscope.

connect_EDS() -> tbt.RetractableDeviceState
    Connect to the EDS system and retrieve the camera status.

retract_EDS(microscope: tbt.Microscope) -> bool
    Retract the EDS detector from the microscope.

retract_device(microscope: tbt.Microscope, detector: tbt.DetectorType) -> bool
    Retract the specified detector from the microscope.

CCD_pause(microscope: tbt.Microscope, quad: tbt.ViewQuad = tbt.ViewQuad.LOWER_RIGHT) -> bool
    Pause the CCD camera, typically used after device or stage movement.

CCD_view(microscope: tbt.Microscope, quad: tbt.ViewQuad = tbt.ViewQuad.LOWER_RIGHT) -> bool
    Visualize detector or stage movement for the user using the CCD camera.

specimen_current(microscope: tbt.Microscope, hfw_mm=Constants.specimen_current_hfw_mm, delay_s=Constants.specimen_current_delay_s) -> float
    Measure the specimen current using the electron beam and return the value in nA.
"""
# Default python modules
# from functools import singledispatch
import os
from pathlib import Path
import time
import warnings
import math
from typing import NamedTuple, List, Tuple
from types import ModuleType

# Autoscript included modules
import numpy as np
from matplotlib import pyplot as plt

# 3rd party module

# Local scripts
import pytribeam.utilities as ut
import pytribeam.constants as cs
from pytribeam.constants import Constants
import pytribeam.image as img

try:
    from pytribeam.laser import tfs_laser as external
except:
    pass
import pytribeam.types as tbt


def detector_insertable(
    microscope: tbt.Microscope,
    detector: tbt.DetectorType,
) -> bool:
    """
    Determine whether or not the built-in microscope detector is insertable and return its state.

    This function checks if the specified detector is being read by Autoscript and if it is insertable.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to check the detector.
    detector : tbt.DetectorType
        The type of the detector to check.

    Returns
    -------
    bool
        True if the detector is insertable, False otherwise.

    Warnings
    --------
    UserWarning
        If the detector type is invalid for the currently selected device or if the detector is not found on the system.
    """
    # check if the detector is being read by Autoscript
    try:
        # make requested detector the active detector
        microscope.detector.type.value = detector.value
    except:
        warnings.warn(
            f"""Warning. Invalid detector type of "{detector.value}" for currently selected device 
            of "{tbt.Device(microscope.imaging.get_active_device()).value}" or detector not found on this system.
            Detector will be assumed to not be insertable."""
        )
        return False

    # check if it is insertable
    try:
        microscope.detector.state
        return True
    except Exception:
        return False


def detector_state(
    microscope: tbt.Microscope,
    detector: tbt.DetectorType,
) -> tbt.RetractableDeviceState:
    """
    Determine the state of the detector, only valid if the detector is insertable.

    This function checks if the specified detector is insertable and returns its state.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to check the detector state.
    detector : tbt.DetectorType
        The type of the detector to check.

    Returns
    -------
    tbt.RetractableDeviceState
        The state of the detector if it is insertable, None otherwise.
    """
    # check if the detector is being read by Autoscriptdevice_access(microscope)
    if not detector_insertable(
        microscope=microscope,
        detector=detector,
    ):
        return None
    return tbt.RetractableDeviceState(microscope.detector.state)


def detectors_will_collide(
    microscope: tbt.Microscope,
    detector_to_insert: tbt.DetectorType,
) -> bool:
    """
    Determine if a collision may occur when inserting the specified detector.

    This function checks if inserting the specified detector will cause a collision with any other detectors.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to check for potential collisions.
    detector_to_insert : tbt.DetectorType
        The type of the detector to insert.

    Returns
    -------
    bool
        True if a collision may occur, False otherwise.
    """
    device_retracted = tbt.RetractableDeviceState.RETRACTED.value
    for detector_combo in Constants.detector_collisions:
        if detector_to_insert in detector_combo:
            for detector in detector_combo:
                if detector == detector_to_insert:
                    continue
                if detector == tbt.DetectorType.EDS:
                    if external.EDS_CameraStatus() != device_retracted:
                        return True
                elif detector == tbt.DetectorType.EBSD:
                    if external.EBSD_CameraStatus() != device_retracted:
                        return True
                else:
                    state = detector_state(microscope=microscope, detector=detector)
                    if state.value != device_retracted:
                        return True
    return False


def device_access(microscope: tbt.Microscope) -> tbt.ViewQuad:
    """
    Switch to the upper-left quadrant and assign the electron beam as the active device.

    This function switches the view to the upper-left quadrant and assigns the electron beam as the active device, which is the only device with access to insertable devices like the CBS/ABS detector. Other devices, like the ion beam, CCD, or Nav-Cam, do not have CBS/ABS access.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to switch the view and assign the active device.

    Returns
    -------
    tbt.ViewQuad
        The upper-left quadrant view.
    """
    img.set_view(
        microscope=microscope,
        quad=tbt.ViewQuad.UPPER_LEFT,
    )
    img.set_beam_device(
        microscope=microscope,
        device=tbt.Device.ELECTRON_BEAM,
    )
    return True


def insert_EBSD(
    microscope: tbt.Microscope,
) -> bool:
    """
    Insert the EBSD camera into the microscope.

    This function connects to the EBSD system, checks for potential collisions with other detectors, and inserts the EBSD camera if it is not already inserted. It raises an error if the EBSD camera cannot be inserted.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to insert the EBSD camera.

    Returns
    -------
    bool
        True if the EBSD camera is successfully inserted.

    Raises
    ------
    SystemError
        If a collision may occur with another detector, if the EBSD camera is in an error state, if the EBSD mapping is not idle, or if the EBSD camera cannot be inserted.
    """
    connect_EBSD()
    if detectors_will_collide(
        microscope=microscope,
        detector_to_insert=tbt.DetectorType.EBSD,
    ):
        raise SystemError(
            f"""Error. Cannot insert EBSD which may collide with another detector.
            Disallowed detector combinations are: {Constants.detector_collisions}"""
        )
    ebsd_cam_status = tbt.RetractableDeviceState(external.EBSD_CameraStatus())
    map_status = tbt.MapStatus(external.EBSD_MappingStatus())
    if ebsd_cam_status == tbt.RetractableDeviceState.ERROR:
        raise SystemError("Error, EDS Camera in error state, workflow stopped.")
    if map_status != tbt.MapStatus.IDLE:
        raise SystemError(
            f'Error, EBSD mapping not in "{tbt.MapStatus.IDLE.value}" state.'
        )
    if ebsd_cam_status != tbt.RetractableDeviceState.INSERTED:
        print("\tInserting EBSD Camera...")
        # TODO change to constants
        minutes_to_wait = 3
        timeout = minutes_to_wait * 60  # seconds
        waittime = 4  # seconds
        CCD_view(microscope=microscope)
        # Oxford Inst requires 2 inserts
        while True:
            external.EBSD_InsertCamera()  # inserted state
            if (
                external.EBSD_CameraStatus()
                == tbt.RetractableDeviceState.INSERTED.value
            ):
                break
            time.sleep(waittime)
            timeout = timeout - waittime
            if timeout < 1:
                warnings.warn("Warning: EBSD insert timeout. Trying to continue...")
                break
        CCD_pause(microscope=microscope)

    new_ebsd_cam_status = tbt.RetractableDeviceState(external.EBSD_CameraStatus())
    if new_ebsd_cam_status == tbt.RetractableDeviceState.INSERTED:
        print("\tEBSD Camera inserted")
        return True
    raise SystemError(
        f'EBSDS Camera is not inserted, currently in "{new_ebsd_cam_status}" state'
    )


def insert_EDS(
    microscope: tbt.Microscope,
) -> bool:
    """
    Insert the EDS camera into the microscope.

    This function connects to the EDS system, checks for potential collisions with other detectors, and inserts the EDS camera if it is not already inserted. It raises an error if the EDS camera cannot be inserted.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to insert the EDS camera.

    Returns
    -------
    bool
        True if the EDS camera is successfully inserted.

    Raises
    ------
    SystemError
        If a collision may occur with another detector, if the EDS camera is in an error state, if the EDS mapping is not idle, or if the EDS camera cannot be inserted.
    """
    connect_EDS()
    if detectors_will_collide(
        microscope=microscope,
        detector_to_insert=tbt.DetectorType.EDS,
    ):
        raise SystemError(
            f"""Error. Cannot insert EDS while CBS not in "Retracted" state. 
            CBS detector currently in "{detector_state(microscope=microscope, detector=tbt.DetectorType.CBS).value}" state."""
        )
    eds_cam_status = tbt.RetractableDeviceState(external.EDS_CameraStatus())
    map_status = tbt.MapStatus(external.EDS_MappingStatus())
    if eds_cam_status == tbt.RetractableDeviceState.ERROR:
        raise SystemError("Error, EDS Camera in error state, workflow stopped.")
    if map_status != tbt.MapStatus.IDLE:
        raise SystemError(
            f'Error, EDS mapping not in "{tbt.MapStatus.IDLE.value}" state.'
        )
    if eds_cam_status != tbt.RetractableDeviceState.INSERTED:
        print("\tInserting EDS Camera...")
        CCD_view(microscope=microscope)
        external.EDS_InsertCamera()
        CCD_pause(microscope=microscope)

    new_eds_cam_status = tbt.RetractableDeviceState(external.EDS_CameraStatus())
    if new_eds_cam_status == tbt.RetractableDeviceState.INSERTED:
        print("\tEDS Camera inserted")
        return True
    raise SystemError(
        f'EDS Camera is not inserted, currently in "{new_eds_cam_status}" state'
    )


def insert_detector(
    microscope: tbt.Microscope,
    detector: tbt.DetectorType,
    time_delay_s: float = 0.5,
) -> bool:
    """
    Insert the selected detector into the microscope.

    This function ensures the specified detector is the active one, confirms it is insertable, and inserts it if it is not already inserted. It raises an error if the detector cannot be inserted.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to insert the detector.
    detector : tbt.DetectorType
        The type of the detector to insert.
    time_delay_s : float, optional
        The time delay in seconds after inserting the detector (default is 0.5 seconds).

    Returns
    -------
    bool
        True if the detector is successfully inserted.

    Raises
    ------
    ValueError
        If the detector is not insertable.
    SystemError
        If a collision may occur with another detector or if the detector cannot be inserted.
    """
    # ensure detector is the active one
    microscope.detector.type.value = detector.value
    # confirm detector is insertable
    try:
        state = microscope.detector.state
    except:
        raise ValueError(f"{detector.value} detector is not insertable.")
    if state == tbt.RetractableDeviceState.RETRACTED.value:
        if detectors_will_collide(
            microscope=microscope,
            detector_to_insert=detector,
        ):
            raise SystemError(
                f"""Error. Cannot insert {detector.value} which may collide with another detector.
                Disallowed detector combinations are: {Constants.detector_collisions}"""
            )

        print(f"\tInserting {detector.value} detector...")
        CCD_view(microscope=microscope)
        microscope.detector.insert()
        time.sleep(time_delay_s)
        CCD_pause(microscope=microscope)
        if microscope.detector.state == tbt.RetractableDeviceState.INSERTED.value:
            print(f"\t\t{detector.value} detector inserted.")
            return True
    elif state == tbt.RetractableDeviceState.INSERTED.value:
        print(f"\t{detector.value} detector is already inserted.")
        return True
    raise SystemError(
        f'Cannot insert {detector.value} detector, current detector state is "{state}".'
    )


def retract_all_devices(
    microscope: tbt.Microscope,
    enable_EBSD: bool,
    enable_EDS: bool,
) -> bool:
    # TODO come up with better system for enable_EBSD_EDS
    """
    Retract all insertable devices, including microscope detectors and EBSD/EDS detectors if integrated.

    This function retracts all insertable devices, first retracting microscope detectors and then retracting EBSD/EDS detectors if they are integrated and enabled.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for accessing the Autoscript API.
    enable_EBSD : bool
        Whether to enable retraction of the EBSD detector.
    enable_EDS : bool
        Whether to enable retraction of the EDS detector.

    Returns
    -------
    bool
        True if all devices are successfully retracted.

    Raises
    ------
    None
    """
    print("\tRetracting devices, do not interact with xTUI during this process...")
    initial_view = tbt.ViewQuad(microscope.imaging.get_active_view())
    device_access(microscope)

    for detector in microscope.detector.type.available_values:
        detector = tbt.DetectorType(detector)  # overwrite
        state = detector_state(
            microscope=microscope,
            detector=detector,
        )
        if (state is not None) and (state != tbt.RetractableDeviceState.RETRACTED):
            retract_device(
                microscope=microscope,
                detector=detector,
            )

    # EBSD/EDS detectors:
    try:
        external
    except NameError:
        pass
        print("\t\tLaser API not imported, EBSD and EDS detectors are unavailable")
    else:
        if enable_EBSD:
            retract_EBSD(microscope=microscope)
        if enable_EDS:
            retract_EDS(microscope=microscope)
        # else:
        #     warnings.warn(
        #         "\t\tWarning: EBSD and EDS device control API is available but not being used."
        #     )

    # reset initial settings:
    img.set_view(
        microscope=microscope,
        quad=initial_view,
    )
    print("\t\tAll available and enabled devices retracted.")
    return True


def connect_EBSD() -> tbt.RetractableDeviceState:
    """
    Connect to the EBSD system and retrieve the camera status.

    This function attempts to connect to the EBSD system and retrieve the camera status. It raises a ConnectionError if the connection fails.

    Returns
    -------
    tbt.RetractableDeviceState
        The status of the EBSD camera.

    Raises
    ------
    ConnectionError
        If the EBSD control is not connected.
    """
    try:
        status = external.EBSD_CameraStatus()
    except:
        raise ConnectionError(
            """EBSD control not connected, "Laser Control" from ThermoFisher must be open. 
            Try closing Laser Control, restarting EBSD/EDS software, then opening Laser Control again."""
        )
    return tbt.RetractableDeviceState(status)


def retract_EBSD(microscope: tbt.Microscope) -> bool:
    """
    Retract the EBSD camera from the microscope.

    This function connects to the EBSD system, checks the camera status, and retracts the EBSD camera if it is not already retracted. It raises an error if the EBSD camera cannot be retracted.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to retract the EBSD camera.

    Returns
    -------
    bool
        True if the EBSD camera is successfully retracted.

    Raises
    ------
    SystemError
        If the EBSD camera is in an error state, if the EBSD mapping is not completed, or if the EBSD camera retraction fails.
    """
    connect_EBSD()
    ebsd_status = tbt.RetractableDeviceState(external.EBSD_CameraStatus())
    if ebsd_status == tbt.RetractableDeviceState.ERROR:
        raise SystemError(
            "EBSD Camera in error state, workflow stopped. Check EBSD/EDS software or restart laser control"
        )
    if ebsd_status != tbt.RetractableDeviceState.RETRACTED:
        print(
            '\t\t\tEBSD Camera Retraction requested, please wait for "mapping complete" verification...'
        )
        map_status = tbt.MapStatus(external.EBSD_MappingStatus())
        # first check if mapping is finished properly
        minutes_to_wait = 5  # TODO set constant
        timeout = minutes_to_wait * 60  # seconds #TODO
        cameraokconfirmations = 3  # synchronization issue with EDAX, try to get map completed 3x before continuing
        waittime = 10  # seconds
        if map_status == tbt.MapStatus.ACTIVE:
            print("\t\t\tEBSD mapping currently active, waiting for mapping to finish")
        while True:
            current_map_status = tbt.MapStatus(external.EBSD_MappingStatus())
            if current_map_status != tbt.MapStatus.ACTIVE:
                cameraokconfirmations = cameraokconfirmations - 1
                waittime = 3  # shorten wait time, polling 3x to see if mapping was really completed.
            time.sleep(waittime)
            timeout = timeout - waittime
            if cameraokconfirmations < 1:
                delay = minutes_to_wait * 60 - timeout
                print(f"\t\t\t\tEBSD mapping finished. Delay of {delay} seconds")
                break
            if timeout < 1:
                warnings.warn(
                    "\t\t\tWarning, EBSD mapping timeout. Trying to continue..."
                )
                break
        CCD_view(microscope=microscope)
        print("\t\t\tEBSD Camera retracting...")
        external.EBSD_RetractCamera()
        time.sleep(1)
        CCD_pause(microscope=microscope)
        current_ebsd_status = tbt.RetractableDeviceState(external.EBSD_CameraStatus())
        if current_ebsd_status != tbt.RetractableDeviceState.RETRACTED:
            raise SystemError("Error, EBSD Camera retraction failed, workflow stopped.")
        print("\t\tEBSD Camera retracted")
    return True


def connect_EDS() -> tbt.RetractableDeviceState:
    """
    Connect to the EDS system and retrieve the camera status.

    This function attempts to connect to the EDS system and retrieve the camera status. It raises a ConnectionError if the connection fails.

    Returns
    -------
    tbt.RetractableDeviceState
        The status of the EDS camera.

    Raises
    ------
    ConnectionError
        If the EDS control is not connected.
    """
    try:
        status = external.EDS_CameraStatus()
    except:
        raise ConnectionError(
            """EDS control not connected, "Laser Control" from ThermoFisher must be open. 
            Try closing Laser Control, restarting EBSD/EDS software, then opening Laser Control again."""
        )
    return tbt.RetractableDeviceState(status)


def retract_EDS(microscope: tbt.Microscope) -> bool:
    """
    Retract the EDS detector from the microscope.

    This function connects to the EDS system, checks the camera status, and retracts the EDS camera if it is not already retracted. It raises an error if the EDS camera cannot be retracted.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to retract the EDS camera.

    Returns
    -------
    bool
        True if the EDS camera is successfully retracted.

    Raises
    ------
    SystemError
        If the EDS camera is in an error state or if the EDS camera retraction fails.
    """
    # print(f"\t\tRetracting EDS detector")
    connect_EDS()
    eds_status = tbt.RetractableDeviceState(external.EDS_CameraStatus())
    if eds_status == tbt.RetractableDeviceState.ERROR:
        raise SystemError(
            "EDS Camera in error state, workflow stopped. Check EBSD/EDS software or restart laser control"
        )
    if eds_status != tbt.RetractableDeviceState.RETRACTED:
        print("\t\t\tEDS Camera retracting...")
        CCD_view(microscope=microscope)
        external.EDS_RetractCamera()
        time.sleep(1)
        if (
            tbt.RetractableDeviceState(external.EDS_CameraStatus())
            != tbt.RetractableDeviceState.RETRACTED
        ):
            raise SystemError("Error, EDS Camera retraction failed, workflow stopped.")
        CCD_pause(microscope=microscope)
        print("\t\tEDS Camera retracted")
    return True


def retract_device(microscope: tbt.Microscope, detector: tbt.DetectorType) -> bool:
    """
    Retract the specified detector from the microscope.

    This function ensures the specified detector is the active one, retracts it, and checks its state. It raises an error if the detector cannot be retracted.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to retract the detector.
    detector : tbt.DetectorType
        The type of the detector to retract.

    Returns
    -------
    bool
        True if the detector is successfully retracted.

    Raises
    ------
    SystemError
        If the detector cannot be retracted.
    """
    CCD_view(microscope=microscope)
    print(f"\t\tRetracting {detector.value} detector")
    microscope.detector.type.value = detector.value
    microscope.detector.retract()
    state = tbt.RetractableDeviceState(microscope.detector.state)
    if state != tbt.RetractableDeviceState.RETRACTED:
        raise SystemError(
            f"{detector.value} detector not retracted, current detector state is {detector_state.value}"
        )
    print(f"\t\t{detector.value} detector retracted")
    CCD_pause(microscope=microscope)

    return True


def CCD_pause(
    microscope: tbt.Microscope,
    quad: tbt.ViewQuad = tbt.ViewQuad.LOWER_RIGHT,
) -> bool:
    """
    Pause the CCD camera, typically used after device or stage movement.

    This function pauses the CCD camera by switching to the specified quadrant, setting the beam device to the CCD camera, and stopping the acquisition. It restores the initial view afterward.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to pause the CCD camera.
    quad : tbt.ViewQuad, optional
        The quadrant to switch to before pausing the CCD camera (default is tbt.ViewQuad.LOWER_RIGHT).

    Returns
    -------
    bool
        True if the CCD camera is successfully paused.

    Warnings
    --------
    UserWarning
        If the CCD camera is not installed on the microscope.
    """
    initial_view = tbt.ViewQuad(microscope.imaging.get_active_view())
    img.set_view(microscope=microscope, quad=quad)
    try:
        img.set_beam_device(microscope=microscope, device=tbt.Device.CCD_CAMERA)
    except:
        warnings.warn("CCD camera is not installed on this microscope.")
    else:
        microscope.imaging.stop_acquisition()
    finally:
        microscope.imaging.set_active_view(initial_view.value)
        return True


def CCD_view(
    microscope: tbt.Microscope,
    quad: tbt.ViewQuad = tbt.ViewQuad.LOWER_RIGHT,
) -> bool:
    """
    Visualize detector or stage movement for the user using the CCD camera.

    This function visualizes detector or stage movement by switching to the specified quadrant, setting the beam device to the CCD camera, and starting the acquisition. It restores the initial view afterward.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to visualize the movement.
    quad : tbt.ViewQuad, optional
        The quadrant to switch to before visualizing the movement (default is tbt.ViewQuad.LOWER_RIGHT).

    Returns
    -------
    bool
        True if the CCD camera is successfully used for visualization.

    Warnings
    --------
    UserWarning
        If the CCD camera is not installed on the microscope.
    """
    initial_view = tbt.ViewQuad(microscope.imaging.get_active_view())
    img.set_view(microscope=microscope, quad=quad)
    try:
        img.set_beam_device(microscope=microscope, device=tbt.Device.CCD_CAMERA)
    except:
        warnings.warn("CCD camera is not installed on this microscope.")
    else:
        microscope.imaging.start_acquisition()
    finally:
        microscope.imaging.set_active_view(initial_view.value)
        return True


def specimen_current(
    microscope: tbt.Microscope,
    hfw_mm=Constants.specimen_current_hfw_mm,
    delay_s=Constants.specimen_current_delay_s,
) -> float:
    """
    Measure the specimen current using the electron beam and return the value in nA.

    This function sets the beam device to the electron beam, adjusts the horizontal field width (HFW) and detector, starts the acquisition, and measures the specimen current. It then resets the detector and HFW to their initial values.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to measure the specimen current.
    hfw_mm : float, optional
        The horizontal field width in millimeters (default is Constants.specimen_current_hfw_mm).
    delay_s : float, optional
        The delay in seconds before measuring the specimen current (default is Constants.specimen_current_delay_s).

    Returns
    -------
    float
        The measured specimen current in nA.
    """
    img.set_beam_device(
        microscope=microscope,
        device=tbt.Device.ELECTRON_BEAM,
    )
    initial_hfw_m = microscope.beams.electron_beam.horizontal_field_width.value
    initial_detector = tbt.DetectorType(microscope.detector.type.value)

    img.detector_type(microscope=microscope, detector=tbt.DetectorType.ETD)
    img.beam_hfw(
        beam=tbt.ElectronBeam(settings=tbt.BeamSettings()),
        microscope=microscope,
        hfw_mm=hfw_mm,
    )
    microscope.imaging.start_acquisition()
    time.sleep(delay_s)
    current_na = microscope.state.specimen_current.value * cs.Conversions.A_TO_NA
    microscope.imaging.stop_acquisition()

    # reset detector and hfw
    microscope.beams.electron_beam.horizontal_field_width.value = initial_hfw_m
    img.detector_type(microscope=microscope, detector=initial_detector)
    img.beam_hfw(
        beam=tbt.ElectronBeam(settings=tbt.BeamSettings()),
        microscope=microscope,
        hfw_mm=initial_hfw_m * cs.Conversions.M_TO_MM,
    )

    return current_na
