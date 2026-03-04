"""
Microscope Imaging Module
=========================

This module provides a set of functions for configuring and operating the microscope for imaging purposes.
It includes functions for setting beam parameters, detector settings, and capturing images with custom
or preset resolutions.

Functions
---------
beam_angular_correction(microscope, dynamic_focus, tilt_correction, delay_s=0.5)
    Uses auto mode to set tilt correction and dynamic focus.

beam_current(beam, microscope, current_na, current_tol_na, delay_s=5.0)
    Sets the current for the selected beam type, with inputs in units of nanoamps.

beam_dwell_time(beam, microscope, dwell_us, delay_s=0.1)
    Sets the dwell time for the selected beam, with inputs in units of microseconds.

beam_hfw(beam, microscope, hfw_mm, delay_s=0.1)
    Sets the horizontal field width for the selected beam, with inputs in units of millimeters.

beam_ready(beam, microscope, delay_s=5.0, attempts=2)
    Checks if the beam is on or blanked, and tries to turn it on and unblank it if possible.

beam_scan_full_frame(beam, microscope)
    Sets the beam scan mode to full frame.

beam_scan_resolution(beam, microscope, resolution, delay_s=0.1)
    Sets the scan resolution for the selected beam, with inputs in units of preset resolutions.

beam_scan_rotation(beam, microscope, rotation_deg, delay_s=0.1)
    Sets the scan rotation for the selected beam, with inputs in units of degrees.

beam_voltage(beam, microscope, voltage_kv, voltage_tol_kv, delay_s=5.0)
    Sets the voltage for a given beam type, with inputs in units of kilovolts.

beam_working_dist(beam, microscope, wd_mm, delay_s=0.1)
    Sets the working distance for the selected beam, with inputs in units of millimeters.

collect_multiple_images(multiple_img_settings, num_frames)
    Sets up scanning for multiple frames.

collect_single_image(save_path, img_settings)
    Collects a single frame image with defined image settings.

detector_auto_cb(microscope, beam, settings, delay_s=0.1)
    Runs the detector auto contrast-brightness function.

detector_brightness(microscope, brightness, delay_s=0.1)
    Sets the detector brightness with input from 0 to 1.

detector_cb(microscope, detector_settings, beam)
    Sets detector contrast and brightness.

detector_contrast(microscope, contrast, delay_s=0.1)
    Sets the detector contrast with input from 0 to 1.

detector_mode(microscope, detector_mode, delay_s=0.1)
    Sets the detector mode.

detector_type(microscope, detector, delay_s=0.1)
    Sets the detector type.

grab_custom_resolution_frame(img_settings, save_path)
    Captures a single frame image using custom resolutions and saves it to the specified path.

grab_preset_resolution_frame(img_settings)
    Captures a single frame image using preset resolutions.

image_operation(step, image_settings, general_settings, slice_number)
    Performs an image operation based on the specified settings.

imaging_detector(img_settings)
    Prepares the detector and inserts it if applicable.

imaging_device(microscope, beam)
    Prepares the imaging beam, viewing quad, and the beam voltage and current.

imaging_scan(img_settings)
    Sets all scan settings except for the resolution.

prepare_imaging(img_settings)
    Prepares various imaging settings.

set_beam_device(microscope, device, delay_s=0.1)
    Sets the active imaging device.

set_view(microscope, quad)
    Sets the active view to the specified quad.

"""

# Default python modules
# from functools import singledispatch
from pathlib import Path
import time
import warnings
from typing import List
import math

# Local scripts
import pytribeam.constants as cs
import pytribeam.insertable_devices as devices
import pytribeam.types as tbt
import pytribeam.utilities as ut


def beam_angular_correction(
    microscope: tbt.Microscope,
    dynamic_focus: bool,
    tilt_correction: bool,
    # correction_angle_deg: float = None,
    delay_s: float = 0.5,
) -> bool:
    """
    Uses auto mode to set tilt correction and dynamic focus.

    This function configures the electron beam's angular correction mode to automatic,
    sets the scan rotation to zero, and enables or disables dynamic focus and tilt correction
    based on the provided parameters.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object to configure.
    dynamic_focus : bool
        If True, dynamic focus will be turned on. If False, dynamic focus will be turned off.
    tilt_correction : bool
        If True, tilt correction will be turned on. If False, tilt correction will be turned off.
    delay_s : float, optional
        The delay in seconds to wait after turning dynamic focus or tilt correction on or off (default is 0.5).

    Returns
    -------
    bool
        True if the configuration is successful, False otherwise.

    Raises
    ------
    SystemError
        If unable to turn dynamic focus or tilt correction on or off.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> success = beam_angular_correction(microscope, dynamic_focus=True, tilt_correction=False)
    >>> print(success)
    True
    """
    angular_correction = microscope.beams.electron_beam.angular_correction
    angular_correction.mode = tbt.AngularCorrectionMode.AUTOMATIC
    # scan rotation must be zero for auto mode
    microscope.beams.electron_beam.scanning.rotation.value = 0.0

    # manual adjustment not implemented yet, only works at zero scan rotation
    # if correction_angle_deg is not None:
    #     angular_correction.mode = tbt.AngularCorrectionMode.MANUAL
    if dynamic_focus:
        angular_correction.dynamic_focus.turn_on()
        time.sleep(delay_s)
        if not angular_correction.dynamic_focus.is_on:
            raise SystemError("Unable to turn dynamic focus on.")
    if (not dynamic_focus) or (dynamic_focus is None):
        angular_correction.dynamic_focus.turn_off()
        time.sleep(delay_s)
        if angular_correction.dynamic_focus.is_on:
            raise SystemError("Unable to turn dynamic focus off.")

    if tilt_correction:
        angular_correction.tilt_correction.turn_on()
        time.sleep(delay_s)
        if not angular_correction.tilt_correction.is_on:
            raise SystemError("Unable to turn tilt correction on.")
    if (not tilt_correction) or (tilt_correction is None):
        angular_correction.tilt_correction.turn_off()
        time.sleep(delay_s)
        if angular_correction.tilt_correction.is_on:
            raise SystemError("Unable to turn tilt correction off.")


def beam_current(
    beam: tbt.Beam,
    microscope: tbt.Microscope,
    current_na: float,
    current_tol_na: float,
    delay_s: float = 5.0,
) -> bool:
    """
    Sets the current for the selected beam type, with inputs in units of nanoamps.

    This function sets the beam current for the specified beam type on the microscope.
    If the current difference exceeds the tolerance, it adjusts the beam current and
    waits for the specified delay.

    Parameters
    ----------
    beam : tbt.Beam
        The beam type to configure.
    microscope : tbt.Microscope
        The microscope object to configure.
    current_na : float
        The desired beam current in nanoamps.
    current_tol_na : float
        The tolerance for the beam current in nanoamps.
    delay_s : float, optional
        The delay in seconds to wait after adjusting the beam current (default is 5.0).

    Returns
    -------
    bool
        True if the beam current is set successfully, False otherwise.

    Raises
    ------
    ValueError
        If the beam current cannot be adjusted within the specified tolerance.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> beam = tbt.ElectronBeam(settings=None)
    >>> success = beam_current(beam, microscope, current_na=1.0, current_tol_na=0.1)
    >>> print(success)
    True
    """
    selected_beam = ut.beam_type(beam, microscope)

    exisiting_current_a = selected_beam.beam_current.value  # amps
    delta_current_na = abs(
        exisiting_current_a * cs.Conversions.A_TO_NA - current_na
    )  # nanoamps
    if delta_current_na > current_tol_na:
        warnings.warn(
            "Requested beam current is not the current setting, imaging conditions may be non-ideal."
        )
        print("Adjusting beam current...")
        selected_beam.beam_current.value = current_na * cs.Conversions.NA_TO_A
        time.sleep(delay_s)

        new_current_na = selected_beam.beam_current.value * cs.Conversions.A_TO_NA
        current_diff_na = abs(new_current_na - current_na)
        if current_diff_na > current_tol_na:
            raise ValueError(
                f"""Could not correctly adjust beam voltage,
                requested {current_na} nA, current beam current is
                {new_current_na} nA"""
            )

    return True


def beam_dwell_time(
    beam: tbt.Beam,
    microscope: tbt.Microscope,
    dwell_us: float,
    delay_s: float = 0.1,
) -> bool:
    """
    Sets the dwell time for the selected beam, with inputs in units of microseconds.

    This function sets the dwell time for the specified beam type on the microscope.
    It converts the dwell time from microseconds to seconds, sets the dwell time, and
    waits for the specified delay.

    Parameters
    ----------
    beam : tbt.Beam
        The beam type to configure.
    microscope : tbt.Microscope
        The microscope object to configure.
    dwell_us : float
        The desired dwell time in microseconds.
    delay_s : float, optional
        The delay in seconds to wait after adjusting the dwell time (default is 0.1).

    Returns
    -------
    bool
        True if the dwell time is set successfully, False otherwise.

    Raises
    ------
    ValueError
        If the dwell time cannot be adjusted correctly.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> beam = tbt.ElectronBeam(settings=None)
    >>> success = beam_dwell_time(beam, microscope, dwell_us=10.0)
    >>> print(success)
    True
    """
    selected_beam = ut.beam_type(beam, microscope)
    dwell_s = dwell_us * cs.Conversions.US_TO_S
    selected_beam.scanning.dwell_time.value = dwell_s
    time.sleep(delay_s)
    if not math.isclose(
        selected_beam.scanning.dwell_time.value,
        dwell_s,
        rel_tol=cs.Constants.beam_dwell_tol_ratio,
    ):
        raise ValueError(
            f"""Could not correctly adjust dwell time,
            requested {dwell_s} seconds, current dwell time is
            {selected_beam.scanning.dwell_time.value} seconds"""
        )

    return True


def beam_hfw(
    beam: tbt.Beam,
    microscope: tbt.Microscope,
    hfw_mm: float,
    delay_s: float = 0.1,
    hfw_tol_mm: float = 1e-6,  # 1 nm of tolerance
) -> bool:
    """
    Sets the horizontal field width for the selected beam, with inputs in units of millimeters.

    This function sets the horizontal field width (HFW) for the specified beam type on the microscope.
    It converts the HFW from millimeters to meters, sets the HFW, and waits for the specified delay.
    This should be done after adjusting the working distance.

    Parameters
    ----------
    beam : tbt.Beam
        The beam type to configure.
    microscope : tbt.Microscope
        The microscope object to configure.
    hfw_mm : float
        The desired horizontal field width in millimeters.
    delay_s : float, optional
        The delay in seconds to wait after adjusting the HFW (default is 0.1).

    Returns
    -------
    bool
        True if the HFW is set successfully, False otherwise.

    Raises
    ------
    ValueError
        If the HFW cannot be adjusted correctly.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> beam = tbt.ElectronBeam(settings=None)
    >>> success = beam_hfw(beam, microscope, hfw_mm=1.0)
    >>> print(success)
    True
    """
    selected_beam = ut.beam_type(beam, microscope)
    hfw_m = hfw_mm * cs.Conversions.MM_TO_M
    selected_beam.horizontal_field_width.value = hfw_m
    time.sleep(delay_s)
    if not math.isclose(
        selected_beam.horizontal_field_width.value,
        hfw_m,
        abs_tol=hfw_tol_mm
        * cs.Conversions.MM_TO_M,  # convert to meters for autoscript calls
    ):
        raise ValueError(
            f"""Could not correctly adjust horizontal field width,
            requested {hfw_mm} millimeters, current field with is
            {selected_beam.horizontal_field_width.value*cs.Conversions.M_TO_MM} millimeters"""
        )

    return True


def beam_ready(
    beam: tbt.Beam,
    microscope: tbt.Microscope,
    delay_s: float = 5.0,
    attempts: int = 2,
) -> bool:
    """
    Checks if the beam is on or blanked, and tries to turn it on and unblank it if possible.

    This function checks the vacuum state, ensures the beam is on, and unblanks the beam if it is blanked.
    It makes multiple attempts to turn on and unblank the beam, waiting for the specified delay between attempts.

    Parameters
    ----------
    beam : tbt.Beam
        The beam type to check.
    microscope : tbt.Microscope
        The microscope object to check.
    delay_s : float, optional
        The delay in seconds to wait between attempts (default is 5.0).
    attempts : int, optional
        The number of attempts to turn on and unblank the beam (default is 2).

    Returns
    -------
    bool
        True if the beam is ready (on and unblanked), False otherwise.

    Raises
    ------
    ValueError
        If the vacuum is not pumped.
        If the beam cannot be turned on after the specified number of attempts.
        If the beam cannot be unblanked after the specified number of attempts.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> beam = tbt.ElectronBeam(settings=None)
    >>> success = beam_ready(beam, microscope)
    >>> print(success)
    True
    """
    selected_beam = ut.beam_type(beam, microscope)

    # check vaccum
    vacuum = microscope.vacuum.chamber_state
    if vacuum != tbt.VacuumState.PUMPED.value:
        raise ValueError(f'Vacuum is not pumped, current state is "{vacuum}"')

    # check beam on
    count: int = 0
    while count < attempts:
        beam_on = selected_beam.is_on
        if not beam_on:
            selected_beam.turn_on()
            time.sleep(delay_s)
        count += 1
    if not beam_on:
        raise ValueError(
            f"Unable to turn on {beam.type} beam after {attempts} attempts."
        )

    # check beam blank
    count: int = 0
    while count < attempts:
        beam_blank = selected_beam.is_blanked
        if beam_blank:
            selected_beam.unblank()
            time.sleep(delay_s)
        count += 1
    if beam_blank:
        raise ValueError(
            f"Unable to unblank {beam.type} beam after {attempts} attempts."
        )

    return True


def beam_scan_full_frame(
    beam: tbt.Beam,
    microscope: tbt.Microscope,
) -> bool:
    """
    Set beam scan mode to full frame.

    This function sets the scanning mode of the specified beam to full frame on the microscope.

    Parameters
    ----------
    beam : tbt.Beam
        The beam type to configure.
    microscope : tbt.Microscope
        The microscope object to configure.

    Returns
    -------
    bool
        True if the scan mode is set to full frame successfully, False otherwise.

    Raises
    ------
    SystemError
        If unable to set the scan mode to full frame.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> beam = tbt.ElectronBeam(settings=None)
    >>> success = beam_scan_full_frame(beam, microscope)
    >>> print(success)
    True
    """
    selected_beam = ut.beam_type(beam, microscope)
    selected_beam.scanning.mode.set_full_frame()
    scan_mode = selected_beam.scanning.mode.value
    if not scan_mode == tbt.ScanMode.FULL_FRAME.value:
        raise SystemError(
            f"Unable to set imaging to full frame. Current scan mode is {scan_mode}."
        )
    return True


def beam_scan_resolution(
    beam: tbt.Beam,
    microscope: tbt.Microscope,
    resolution: tbt.Resolution,
    delay_s: float = 0.1,
) -> bool:
    """
    Sets the scan resolution for the selected beam, with inputs in units of preset resolutions.

    This function sets the scan resolution for the specified beam type on the microscope.
    It only works for preset resolutions and waits for the specified delay after setting the resolution.

    Parameters
    ----------
    beam : tbt.Beam
        The beam type to configure.
    microscope : tbt.Microscope
        The microscope object to configure.
    resolution : tbt.Resolution
        The desired scan resolution (must be a preset resolution).
    delay_s : float, optional
        The delay in seconds to wait after adjusting the resolution (default is 0.1).

    Returns
    -------
    bool
        True if the scan resolution is set successfully, False otherwise.

    Raises
    ------
    ValueError
        If a custom resolution is requested or if the resolution cannot be adjusted correctly.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> import pytribeam.utility as ut
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> beam = tbt.ElectronBeam(settings=None)
    >>> resolution = tbt.PresetResolution.HIGH
    >>> success = beam_scan_resolution(beam, microscope, resolution)
    >>> print(success)
    True
    """
    if not isinstance(resolution, tbt.PresetResolution):
        raise ValueError(
            f"Requested a custom resolution of {resolution.value}. Only preset resolutions allowed."
        )

    selected_beam = ut.beam_type(beam, microscope)
    selected_beam.scanning.resolution.value = resolution.value
    time.sleep(delay_s)
    if selected_beam.scanning.resolution.value != resolution.value:
        raise ValueError(
            f"""Could not correctly adjust scan resolution,
            requested {resolution}, current resolution is
            {selected_beam.scanning.resolution.value}"""
        )

    return True


def beam_scan_rotation(
    beam: tbt.Beam,
    microscope: tbt.Microscope,
    rotation_deg: float,
    delay_s: float = 0.1,
) -> bool:
    """
    Sets the scan rotation for the selected beam, with inputs in units of degrees.

    This function sets the scan rotation for the specified beam type on the microscope.
    It converts the rotation from degrees to radians, sets the scan rotation, and waits for the specified delay.

    Parameters
    ----------
    beam : tbt.Beam
        The beam type to configure.
    microscope : tbt.Microscope
        The microscope object to configure.
    rotation_deg : float
        The desired scan rotation in degrees.
    delay_s : float, optional
        The delay in seconds to wait after adjusting the scan rotation (default is 0.1).

    Returns
    -------
    bool
        True if the scan rotation is set successfully, False otherwise.

    Raises
    ------
    ValueError
        If the scan rotation cannot be adjusted correctly.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> beam = tbt.ElectronBeam(settings=None)
    >>> success = beam_scan_rotation(beam, microscope, rotation_deg=45.0)
    >>> print(success)
    True
    """
    selected_beam = ut.beam_type(beam, microscope)
    rotation_rad = rotation_deg * cs.Conversions.DEG_TO_RAD
    selected_beam.scanning.rotation.value = rotation_rad
    time.sleep(delay_s)
    if selected_beam.scanning.rotation.value != rotation_rad:
        raise ValueError(
            f"""Could not correctly adjust scan rotation,
            requested {rotation_rad} radians, current scan rotation is
            {selected_beam.scanning.rotation.value} radians"""
        )

    return True


def beam_voltage(
    beam: tbt.Beam,
    microscope: tbt.Microscope,
    voltage_kv: float,
    voltage_tol_kv: float,
    delay_s: float = 5.0,
) -> bool:
    """
    Sets the voltage for a given beam type, with inputs in units of kilovolts.

    This function sets the beam voltage for the specified beam type on the microscope.
    If the voltage difference exceeds the tolerance, it adjusts the beam voltage and waits for the specified delay.

    Parameters
    ----------
    beam : tbt.Beam
        The beam type to configure.
    microscope : tbt.Microscope
        The microscope object to configure.
    voltage_kv : float
        The desired beam voltage in kilovolts.
    voltage_tol_kv : float
        The tolerance for the beam voltage in kilovolts.
    delay_s : float, optional
        The delay in seconds to wait after adjusting the beam voltage (default is 5.0).

    Returns
    -------
    bool
        True if the beam voltage is set successfully, False otherwise.

    Raises
    ------
    ValueError
        If the beam voltage cannot be adjusted within the specified tolerance.
        If the beam is not controllable.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> beam = tbt.ElectronBeam(settings=None)
    >>> success = beam_voltage(beam, microscope, voltage_kv=15.0, voltage_tol_kv=0.5)
    >>> print(success)
    True
    """
    selected_beam = ut.beam_type(beam, microscope)

    exisiting_voltage_v = selected_beam.high_voltage.value  # volts
    delta_voltage_kv = abs(
        exisiting_voltage_v * cs.Conversions.V_TO_KV - voltage_kv
    )  # kilovolts
    if delta_voltage_kv > voltage_tol_kv:
        warnings.warn(
            "Requested beam current is not the current setting, imaging conditions may be non-ideal."
        )
        beam_controllable = selected_beam.high_voltage.is_controllable

        if not beam_controllable:
            raise ValueError(
                f"Unable to modify beam voltage, beam is not currently controllable."
            )
        print("Adjusting beam voltage...")
        selected_beam.high_voltage.value = voltage_kv * cs.Conversions.KV_TO_V
        time.sleep(delay_s)
        new_voltage_kv = selected_beam.high_voltage.value * cs.Conversions.V_TO_KV
        voltage_diff_kv = abs(new_voltage_kv - voltage_kv)
        if voltage_diff_kv > voltage_tol_kv:
            raise ValueError(
                f"""Could not correctly adjust beam voltage,
                requested {voltage_kv} kV, current beam voltage is
                {new_voltage_kv} kV"""
            )

    return True


def beam_working_distance(
    beam: tbt.Beam,
    microscope: tbt.Microscope,
    wd_mm: float,
    delay_s: float = 0.1,
) -> bool:
    """
    Sets the working distance for the selected beam, with inputs in units of millimeters.

    This function sets the working distance (WD) for the specified beam type on the microscope.
    It converts the WD from millimeters to meters, sets the WD, and waits for the specified delay.
    This should be done before adjusting the horizontal field width.

    Parameters
    ----------
    beam : tbt.Beam
        The beam type to configure.
    microscope : tbt.Microscope
        The microscope object to configure.
    wd_mm : float
        The desired working distance in millimeters.
    delay_s : float, optional
        The delay in seconds to wait after adjusting the working distance (default is 0.1).

    Returns
    -------
    bool
        True if the working distance is set successfully, False otherwise.

    Raises
    ------
    ValueError
        If the working distance cannot be adjusted correctly.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> beam = tbt.ElectronBeam(settings=None)
    >>> success = beam_working_dist(beam, microscope, wd_mm=5.0)
    >>> print(success)
    True
    """
    selected_beam = ut.beam_type(beam, microscope)
    wd_m = wd_mm * cs.Conversions.MM_TO_M
    selected_beam.working_distance.value = wd_m
    time.sleep(delay_s)
    if selected_beam.working_distance.value != wd_m:
        raise ValueError(
            f"""Could not correctly adjust working distance,
            requested {wd_m} meters, current working distance is
            {selected_beam.working_distance.value} meters"""
        )

    return True


def detector_auto_cb(
    microscope: tbt.Microscope,
    beam: tbt.Beam,
    settings: tbt.ScanArea,
    delay_s: float = 0.1,
) -> bool:
    """
    Detector auto contrast brightness. Currently only reduced scan area option is supported.

    This function sets the scanning mode to reduced area, runs the auto contrast-brightness function,
    and then sets the scanning mode back to full frame.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object to configure.
    beam : tbt.Beam
        The beam type to configure.
    settings : tbt.ScanArea
        The scan area settings for the reduced area.
    delay_s : float, optional
        The delay in seconds to wait after each operation (default is 0.1).

    Returns
    -------
    bool
        True if the auto contrast-brightness is completed successfully, False otherwise.

    Raises
    ------
    SystemError
        If unable to set the scan mode to reduced area or full frame.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> beam = tbt.ElectronBeam(settings=None)
    >>> auto_cb_settings = tbt.ScanArea(left=0.1, top=0.1, width=0.8, height=0.8)
    >>> success = detector_auto_cb(microscope, beam, auto_cb_settings)
    >>> print(success)
    True
    """
    selected_beam = ut.beam_type(beam, microscope)
    selected_beam.scanning.mode.set_reduced_area(
        left=settings.left,
        top=settings.top,
        width=settings.width,
        height=settings.height,
    )
    scan_mode = selected_beam.scanning.mode.value
    if not scan_mode == tbt.ScanMode.REDUCED_AREA.value:
        raise SystemError(
            f"Unable to set imaging to reduced area before auto contrast-brightness. Current scan mode is {scan_mode}."
        )
    microscope.auto_functions.run_auto_cb()
    time.sleep(delay_s)
    selected_beam.scanning.mode.set_full_frame()
    time.sleep(delay_s)

    new_scan_mode = selected_beam.scanning.mode.value
    if new_scan_mode != tbt.ScanMode.FULL_FRAME.value:
        raise SystemError(
            f"Unable to set imaging back to full frame after auto contrast-brightness. Current scan mode is {new_scan_mode}."
        )
    return True


def detector_brightness(
    microscope: tbt.Microscope,
    brightness: float,
    delay_s: float = 0.1,
) -> bool:
    """
    Sets the detector brightness with input from 0 to 1.

    This function sets the brightness for the detector on the microscope and waits for the specified delay.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object to configure.
    brightness : float
        The desired brightness value (from 0 to 1).
    delay_s : float, optional
        The delay in seconds to wait after adjusting the brightness (default is 0.1).

    Returns
    -------
    bool
        True if the brightness is set successfully, False otherwise.

    Raises
    ------
    ValueError
        If the brightness cannot be adjusted correctly.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> success = detector_brightness(microscope, brightness=0.5)
    >>> print(success)
    True
    """
    microscope.detector.brightness.value = brightness
    current_detector = microscope.detector.type.value
    time.sleep(delay_s)
    if not math.isclose(
        microscope.detector.brightness.value,
        brightness,
        abs_tol=cs.Constants.contrast_brightness_tolerance,
    ):
        raise ValueError(
            f"""Could not correctly adjust detector brightness,
            requested {brightness} on {current_detector} detector, 
            current brightness is {microscope.detector.brightness.value}"""
        )
    return True


def detector_contrast(
    microscope: tbt.Microscope,
    contrast: float,
    delay_s: float = 0.1,
) -> bool:
    """
    Sets the detector contrast with input from 0 to 1.

    This function sets the contrast for the detector on the microscope and waits for the specified delay.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object to configure.
    contrast : float
        The desired contrast value (from 0 to 1).
    delay_s : float, optional
        The delay in seconds to wait after adjusting the contrast (default is 0.1).

    Returns
    -------
    bool
        True if the contrast is set successfully, False otherwise.

    Raises
    ------
    ValueError
        If the contrast cannot be adjusted correctly.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> success = detector_contrast(microscope, contrast=0.5)
    >>> print(success)
    True
    """
    microscope.detector.contrast.value = contrast
    current_detector = microscope.detector.type.value
    time.sleep(delay_s)
    if not math.isclose(
        microscope.detector.contrast.value,
        contrast,
        abs_tol=cs.Constants.contrast_brightness_tolerance,
    ):
        raise ValueError(
            f"""Could not correctly adjust detector contrast,
            requested {contrast} on {current_detector} detector, 
            current contrast is {microscope.detector.contrast.value}"""
        )
    return True


def detector_cb(
    microscope: tbt.Microscope,
    detector_settings: tbt.Detector,
    beam: tbt.Beam,
) -> bool:
    """
    Sets detector contrast and brightness.

    This function sets the contrast and brightness for the detector on the microscope.
    It also runs the auto contrast-brightness function if specified in the detector settings.
    Supports initial settings of contrast and brightness with fixed values before auto adjustment.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object to configure.
    detector_settings : tbt.Detector
        The detector settings, including contrast, brightness, and auto contrast-brightness settings.
    beam : tbt.Beam
        The beam type to configure.

    Returns
    -------
    bool
        True if the contrast and brightness are set successfully, False otherwise.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> beam = tbt.ElectronBeam(settings=None)
    >>> detector_settings = tbt.Detector(contrast=None, brightness=None, auto_cb_settings=tbt.ScanArea(left=0.1, top=0.1, width=0.8, height=0.8))
    >>> success = detector_cb(microscope, detector_settings, beam)
    >>> print(success)
    True

    >>> detector_settings = tbt.Detector(contrast=0.2, brightness=0.3, auto_cb_settings=None)
    >>> success = detector_cb(microscope, detector_settings, beam)
    >>> print(success)
    True
    >>> beam_brightness = microscope.detector.brightness.value
    >>> print(beam_brightness)
    0.3
    >>> beam_contrast = microscope.detector.contrast.value
    >>> print(beam_contrast)
    0.2
    """
    ### cannot ensure detector is the active one, will overwrite mode settings, so following line is not used
    # microscope.detector.type.value = detector_settings.type.value
    contrast = detector_settings.contrast
    brightness = detector_settings.brightness
    if contrast is not None:
        detector_contrast(microscope=microscope, contrast=contrast)
    if brightness is not None:
        detector_brightness(microscope=microscope, brightness=brightness)

    null_scan = tbt.ScanArea(left=None, top=None, width=None, height=None)
    if not null_scan == detector_settings.auto_cb_settings:
        detector_auto_cb(
            microscope=microscope,
            settings=detector_settings.auto_cb_settings,
            beam=beam,
        )
    return True


def detector_mode(
    microscope: tbt.Microscope,
    detector_mode: tbt.DetectorMode,
    delay_s: float = 0.1,
) -> bool:
    """
    Sets the detector mode.

    This function sets the mode for the detector on the microscope and waits for the specified delay.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object to configure.
    detector_mode : tbt.DetectorMode
        The desired detector mode.
    delay_s : float, optional
        The delay in seconds to wait after setting the detector mode (default is 0.1).

    Returns
    -------
    bool
        True if the detector mode is set successfully, False otherwise.

    Raises
    ------
    ValueError
        If the detector mode cannot be set correctly.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> mode = tbt.DetectorMode.SECONDARY_ELECTRONS
    >>> success = detector_mode(microscope, mode)
    >>> print(success)
    True
    """
    microscope.detector.mode.value = detector_mode.value
    time.sleep(delay_s)
    if microscope.detector.mode.value != detector_mode.value:
        raise ValueError(
            f"""Could not correctly set detector mode,
            requested {detector_mode}, current mode is
            {microscope.detector.mode.value}"""
        )
    return True


def detector_type(
    microscope: tbt.Microscope,
    detector: tbt.DetectorType,
    delay_s: float = 0.1,
) -> bool:
    """
    Sets the detector type.

    This function sets the type for the detector on the microscope and waits for the specified delay.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object to configure.
    detector : tbt.DetectorType
        The desired detector type.
    delay_s : float, optional
        The delay in seconds to wait after setting the detector type (default is 0.1).

    Returns
    -------
    bool
        True if the detector type is set successfully, False otherwise.

    Raises
    ------
    ValueError
        If the detector type cannot be set correctly.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> detector = tbt.DetectorType.ETD
    >>> success = detector_type(microscope, detector)
    >>> print(success)
    True
    """
    microscope.detector.type.value = detector.value
    time.sleep(delay_s)
    if microscope.detector.type.value != detector.value:
        raise ValueError(
            f"""Could not correctly set detector type,
            requested {detector}, current detector is
            {microscope.detector.type.value}"""
        )
    return True


def grab_custom_resolution_frame(
    img_settings: tbt.ImageSettings,
    save_path: Path,
) -> bool:
    """
    Method for single frame imaging used with custom resolutions.

    This function captures a single frame image using custom resolutions and saves it to the specified path.

    Parameters
    ----------
    img_settings : tbt.ImageSettings
        The image settings, including the microscope and scan resolution.
    save_path : Path
        The path to save the captured image.

    Returns
    -------
    bool
        True if the image is captured and saved successfully, False otherwise.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> from pathlib import Path
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> img_settings = tbt.ImageSettings(
    ...     microscope=microscope,
    ...     beam=tbt.ElectronBeam(settings=None),
    ...     detector=tbt.Detector(),
    ...     scan=tbt.Scan(resolution=tbt.Resolution(width=1024, height=768)),
    ...     bit_depth=tbt.ColorDepth.BITS_8,
    ... )
    >>> save_path = Path("/path/to/save/image.tif")
    >>> success = grab_custom_resolution_frame(img_settings, save_path)
    >>> print(success)
    True
    """
    microscope = img_settings.microscope
    resolution = img_settings.scan.resolution
    microscope.imaging.grab_frame_to_disk(
        save_path.absolute().as_posix(),
        file_format=tbt.ImageFileFormat.TIFF.value,
        settings=tbt.GrabFrameSettings(
            resolution=f"{resolution.width}x{resolution.height}"
        ),
    )
    return True


def grab_preset_resolution_frame(
    img_settings: tbt.ImageSettings,
) -> tbt.AdornedImage:
    """
    Method for single frame imaging used with preset resolutions.

    This function captures a single frame image using preset resolutions.

    Parameters
    ----------
    img_settings : tbt.ImageSettings
        The image settings, including the microscope, beam, detector, and scan resolution.

    Returns
    -------
    tbt.AdornedImage
        The captured image.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> img_settings = tbt.ImageSettings(
    ...     microscope=microscope,
    ...     beam=tbt.ElectronBeam(settings=None),
    ...     detector=tbt.Detector(),
    ...     scan=tbt.Scan(resolution=tbt.PresetResolution.PRESET_768X512),
    ...     bit_depth=tbt.ColorDepth.BITS_8,
    ... )
    >>> image = grab_preset_resolution_frame(img_settings)
    >>> print(image)
    AdornedImage(width=768, height=512, bit_depth=8)
    """
    beam = img_settings.beam
    microscope = img_settings.microscope
    beam_scan_resolution(
        beam=beam,
        microscope=microscope,
        resolution=img_settings.scan.resolution,
    )
    return microscope.imaging.grab_frame(
        tbt.GrabFrameSettings(bit_depth=img_settings.bit_depth)
    )


def imaging_detector(img_settings: tbt.ImageSettings) -> bool:
    """
    Prepares the detector and inserts it if applicable.

    This function sets the detector type, inserts the detector if necessary, sets the detector mode,
    and adjusts the contrast and brightness settings. It is important to set detector mode settings
    right before contrast and brightness as any subsequent calls to a detector type can overwrite the mode.

    Parameters
    ----------
    img_settings : tbt.ImageSettings
        The image settings, including the microscope, beam, and detector settings.

    Returns
    -------
    bool
        True if the detector is prepared successfully, False otherwise.

    Examples
    --------
    >>> import pytribeam.types as tbt
    >>> microscope = tbt.Microscope()
    >>> microscope.connect("localhost")
    Client connecting to [localhost:7520]...
    Client connected to [localhost:7520]
    >>> img_settings = tbt.ImageSettings(
    ...     microscope=microscope,
    ...     beam=tbt.ElectronBeam(settings=None),
    ...     detector=tbt.Detector(
    ...         type=tbt.DetectorType.ETD,
    ...         mode=tbt.DetectorMode.SECONDARY_ELECTRONS,
    ...         brightness=0.4,
    ...         contrast=0.2,
    ...     ),
    ...     scan=tbt.Scan(resolution=tbt.PresetResolution.PRESET_768X512),
    ...     bit_depth=tbt.ColorDepth.BITS_8,
    ... )
    >>> success = imaging_detector(img_settings)
    >>> print(success)
    True
    """
    microscope = img_settings.microscope
    detector = img_settings.detector.type
    detector_type(
        microscope=microscope,
        detector=detector,
    )
    detector_state = devices.detector_state(
        microscope=microscope,
        detector=detector,
    )
    if detector_state is not None:
        devices.insert_detector(
            microscope=microscope,
            detector=detector,
        )
    detector_mode(
        microscope=microscope,
        detector_mode=img_settings.detector.mode,
    )
    detector_cb(
        microscope=microscope,
        detector_settings=img_settings.detector,
        beam=img_settings.beam,
    )
    return True


def imaging_device(
    microscope: tbt.Microscope,
    beam: tbt.Beam,
) -> bool:
    """
    Prepares the imaging beam, viewing quad, and the beam voltage and current.

    This function sets the beam device, ensures the beam is ready, sets the beam voltage and current,
    and applies angular correction if the beam type is electron.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object to configure.
    beam : tbt.Beam
        The beam type to configure, including its settings.

    Returns
    -------
    bool
        True if the imaging device is prepared successfully, False otherwise.
    """
    set_beam_device(microscope=microscope, device=beam.device)
    beam_ready(beam=beam, microscope=microscope)
    beam_voltage(
        beam=beam,
        microscope=microscope,
        voltage_kv=beam.settings.voltage_kv,
        voltage_tol_kv=beam.settings.voltage_tol_kv,
    )
    beam_current(
        beam=beam,
        microscope=microscope,
        current_na=beam.settings.current_na,
        current_tol_na=beam.settings.current_tol_na,
    )
    if beam.type == tbt.BeamType.ELECTRON:
        beam_angular_correction(
            microscope=microscope,
            dynamic_focus=beam.settings.dynamic_focus,
            tilt_correction=beam.settings.tilt_correction,
        )
    return True


def imaging_scan(img_settings: tbt.ImageSettings) -> bool:
    """
    Sets all scan settings except for the resolution.

    This function configures the scan settings for the specified image settings, including
    setting the scan mode to full frame, scan rotation, working distance, horizontal field width,
    and dwell time.

    Parameters
    ----------
    img_settings : tbt.ImageSettings
        The image settings, including the microscope, beam, and scan settings.

    Returns
    -------
    bool
        True if the scan settings are configured successfully, False otherwise.
    """
    microscope = img_settings.microscope
    beam = img_settings.beam
    beam_scan_full_frame(
        beam=beam,
        microscope=microscope,
    )
    beam_scan_rotation(
        beam=beam, microscope=microscope, rotation_deg=img_settings.scan.rotation_deg
    )
    beam_working_distance(
        beam=beam,
        microscope=microscope,
        wd_mm=img_settings.beam.settings.working_dist_mm,
    )
    beam_hfw(beam=beam, microscope=microscope, hfw_mm=img_settings.beam.settings.hfw_mm)
    beam_dwell_time(
        beam=beam, microscope=microscope, dwell_us=img_settings.scan.dwell_time_us
    )
    return True


def prepare_imaging(img_settings: tbt.ImageSettings) -> bool:
    """
    Prepares various imaging settings.

    This function prepares the imaging device, scan settings, and detector settings
    based on the specified image settings.

    Parameters
    ----------
    img_settings : tbt.ImageSettings
        The image settings, including the microscope, beam, scan, and detector settings.

    Returns
    -------
    bool
        True if the imaging settings are prepared successfully, False otherwise.
    """
    imaging_device(microscope=img_settings.microscope, beam=img_settings.beam)
    imaging_scan(img_settings=img_settings)
    imaging_detector(img_settings=img_settings)
    return True


def set_view(
    microscope: tbt.Microscope,
    quad: tbt.ViewQuad,
) -> bool:
    """
    Sets the active view to the specified quad.

    This function sets the active imaging view to the specified quad on the microscope.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object to configure.
    quad : tbt.ViewQuad
        The imaging view to select:
        - 1 is upper left
        - 2 is upper right
        - 3 is lower left
        - 4 is lower right

    Returns
    -------
    bool
        True if the active view is set successfully, False otherwise.
    """
    microscope.imaging.set_active_view(quad.value)


def set_beam_device(
    microscope: tbt.Microscope,
    device: tbt.Device,
    delay_s: float = 0.1,
) -> bool:
    """
    Sets the active imaging device.

    This function sets the active imaging device on the microscope and waits for the specified delay.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object to configure.
    device : tbt.Device
        The desired imaging device.
    delay_s : float, optional
        The delay in seconds to wait after setting the device (default is 0.1).

    Returns
    -------
    bool
        True if the active device is set successfully, False otherwise.

    Raises
    ------
    ValueError
        If the active device cannot be set correctly.
    """
    microscope.imaging.set_active_device(device)
    time.sleep(delay_s)
    curr_device = tbt.Device(microscope.imaging.get_active_device())
    if curr_device != device.value:
        raise ValueError(
            f"""Could not set active device,
            requested device {device.value} but current device is {curr_device}.
            Device list:
                {tbt.Device.ELECTRON_BEAM.value}: Electron Beam
                {tbt.Device.ION_BEAM.value}: Ion Beam
                {tbt.Device.CCD_CAMERA.value}: CCD Camera
                {tbt.Device.IR_CAMERA.value}: IR Camera
                {tbt.Device.NAV_CAM.value}: Nav Cam"""
        )
    return True


#################


def collect_single_image(
    save_path: Path,
    img_settings: tbt.ImageSettings,
) -> bool:
    """
    Collects a single frame image with defined image settings.

    This function prepares the imaging settings, sets the view, and captures a single frame image.
    It saves the image to the specified path. If a non-preset resolution is requested, the image
    will be saved at 8-bit color depth.

    Parameters
    ----------
    save_path : Path
        The path to save the captured image.
    img_settings : tbt.ImageSettings
        The image settings, including the microscope, beam, scan, and detector settings.

    Returns
    -------
    bool
        True if the image is captured and saved successfully, False otherwise.
    """
    beam = img_settings.beam
    microscope = img_settings.microscope
    set_view(microscope=microscope, quad=beam.default_view)
    prepare_imaging(img_settings=img_settings)

    resolution = img_settings.scan.resolution
    if isinstance(resolution, tbt.PresetResolution):
        img = grab_preset_resolution_frame(img_settings=img_settings)
        img.save(str(save_path))
        return True
    warnings.warn(
        f'Warning, non-preset resolution of "{img_settings.scan.resolution}" requested. Image will automatically be saved at 8-bit color depth'
    )
    if img_settings.bit_depth != tbt.ColorDepth.BITS_8:
        warnings.warn(
            f"Warning, non-preset resolution necessitates images be stored at 8-bit color depth, requested bit-depth of {img_settings.bit_depth.value} will be ignored."
        )
    grab_custom_resolution_frame(
        img_settings=img_settings,
        save_path=save_path,
    )
    return True


def collect_multiple_images(
    multiple_img_settings: List[tbt.ImageSettings], num_frames: int
) -> List[tbt.AdornedImage]:
    """
    Sets up scanning for multiple frames.

    This function is best used for collecting multiple segments on a single detector simultaneously.
    It is limited to preset resolutions only.

    Parameters
    ----------
    multiple_img_settings : List[tbt.ImageSettings]
        The list of image settings for each frame, including the microscope, beam, scan, and detector settings.
    num_frames : int
        The number of frames to collect.

    Returns
    -------
    List[tbt.AdornedImage]
        The list of captured images.

    Raises
    ------
    ValueError
        If a non-preset resolution is requested for simultaneous multiple frame imaging.

    Notes
    -----
    This method has not yet been tested.

    """
    # TODO test this

    # Ensure that an insertable detector is done first so that inserting the detector doesn't interfere with other detectors
    # Will need to make sure that only one insertable detector at a time
    insertable_detector = [
        devices.detector_state(
            microscope=_set.microscope,
            detector=_set.detector,
        )
        is not None
        for _set in multiple_img_settings
    ]
    if any(insertable_detector):
        start = multiple_img_settings[insertable_detector.index(True)]
        multiple_img_settings = [start] + multiple_img_settings

    warnings.warn("Method not yet tested")
    views = []
    for quad in range(1, num_frames + 1):
        img_settings = multiple_img_settings[quad - 1]
        resolution = img_settings.scan.resolution
        if not isinstance(resolution, tbt.PresetResolution):
            raise ValueError(
                f'Only preset resolutions allowed for simultaneous multiple frame imaging, but resolution of "{resolution.width}x{resolution.height}" was requested.'
            )

        microscope = img_settings.microscope
        beam = img_settings.beam
        views.append(quad)
        set_view(microscope=microscope, quad=img_settings.beam.default_view)
        prepare_imaging(microscope=microscope, beam=beam, img_settings=img_settings)
    frames = microscope.imaging.grab_multiple_frames(
        tbt.GrabFrameSettings(bit_depth=img_settings.bit_depth, views=views)
    )
    return frames


# TODO
# def image_method(dict):
#     """determine imaging method and return associated function"""
#     pass

# TODO
# def collect_tiling_image():
#     for loop
#         collect_standard_image
#         #stage move


# TODO add more complex imaging behavior, determine method in this function
def image_operation(
    step: tbt.Step,
    image_settings: tbt.ImageSettings,
    general_settings: tbt.GeneralSettings,
    slice_number: int,
) -> bool:
    """
    Performs an image operation based on the specified settings.

    This function collects an image, saves it to the specified directory, and turns off tilt correction and dynamic focus.

    Parameters
    ----------
    step : tbt.Step
        The step information, including the name of the step.
    image_settings : tbt.ImageSettings
        The image settings, including the microscope, beam, scan, and detector settings.
    general_settings : tbt.GeneralSettings
        The general settings, including the experimental directory.
    slice_number : int
        The slice number for naming the saved image file.

    Returns
    -------
    bool
        True if the image operation is performed successfully, False otherwise.
    """
    print("\tCollecting image")
    # create folder in same directory as experimental directory
    image_directory = Path(general_settings.exp_dir).joinpath(step.name)
    image_directory.mkdir(parents=True, exist_ok=True)

    # TODO
    # determine_image_method()
    # collect_multiple_images()

    # single image process:
    save_path = image_directory.joinpath(f"{slice_number:04}.tif")
    collect_single_image(save_path=save_path, img_settings=image_settings)
    print(f"\tImage saved to {save_path}")

    # turn off tilt correction and dynamic focus
    beam_angular_correction(
        microscope=image_settings.microscope,
        dynamic_focus=False,
        tilt_correction=False,
    )

    return True
