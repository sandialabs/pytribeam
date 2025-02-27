#!/usr/bin/python3

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
    """Determines whether or not the built-in microscope detector is insertable and returns it state"""
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
    """Determine state of detector, only valid if detector is insertable"""
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
    """Determines if collision may occur"""
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
    """Switches to upper-left quad and assign electron beam as active device,
    which is the only device with access to insertable devices like the CBS/ABS detector
    Other devices, like ion-beam, CCD or Nav-Cam, do not have CBS/ABS access
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
    """inserts the selected detector"""
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
    """Retracts all insertable devices. First microscope detectors,
    then EBSD/EDS detectors if integrated. Must overwrite EBSD/EDS option to ignore
    these detectors

    microscope: microscope object for accessing autoscript API
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
    try:
        status = external.EBSD_CameraStatus()
    except:
        raise ConnectionError(
            """EBSD control not connected, "Laser Control" from ThermoFisher must be open. 
            Try closing Laser Control, restarting EBSD/EDS software, then opening Laser Control again."""
        )
    return tbt.RetractableDeviceState(status)


def retract_EBSD(microscope: tbt.Microscope) -> bool:
    # print(f"\t\tRetracting EBSD detector")
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
        minutes_to_wait = 5
        timeout = minutes_to_wait * 60  # seconds
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
    try:
        status = external.EDS_CameraStatus()
    except:
        raise ConnectionError(
            """EDS control not connected, "Laser Control" from ThermoFisher must be open. 
            Try closing Laser Control, restarting EBSD/EDS software, then opening Laser Control again."""
        )
    return tbt.RetractableDeviceState(status)


def retract_EDS(microscope: tbt.Microscope) -> bool:
    """Retract EDS dector"""
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
    """Pauses CCD, typically used after device or stage movement"""
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
    """visualizes detector or stage movement for the user using the CCD camera"""
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


def ebsd_operation(
    step: tbt.Step,
    general_settings: tbt.GeneralSettings,
    slice_number: int,
) -> bool:
    pass
    image_settings = step.operation_settings.image


def specimen_current(
    microscope: tbt.Microscope,
    hfw_mm=Constants.specimen_current_hfw_mm,
    delay_s=Constants.specimen_current_delay_s,
) -> float:
    """Measures specimen current using the electron beam"""
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

    return current_na
