#!/usr/bin/python3
"""
Laser Module
============

This module contains functions for managing and controlling the laser in the microscope, including setting laser parameters, checking laser connections, and performing laser operations.

Functions
---------
laser_state_to_db(state: tbt.LaserState) -> dict
    Convert a laser state object into a flattened dictionary.

laser_connected() -> bool
    Check if the laser is connected.

_device_connections() -> tbt.DeviceStatus
    Check the connection status of the laser and associated external devices.

pattern_mode(mode: tbt.LaserPatternMode) -> bool
    Set the laser pattern mode.

pulse_energy_uj(energy_uj: float, energy_tol_uj: float = Constants.laser_energy_tol_uj, delay_s: float = 3.0) -> bool
    Set the pulse energy on the laser.

pulse_divider(divider: int, delay_s: float = Constants.laser_delay_s) -> bool
    Set the pulse divider on the laser.

set_wavelength(wavelength: tbt.LaserWavelength, frequency_khz: float = 60, timeout_s: int = 20, num_attempts: int = 2, delay_s: int = 5) -> bool
    Set the wavelength and frequency of the laser.

read_power(delay_s: float = Constants.laser_delay_s) -> float
    Measure the laser power in watts.

insert_shutter(microscope: tbt.Microscope) -> bool
    Insert the laser shutter.

retract_shutter(microscope: tbt.Microscope) -> bool
    Retract the laser shutter.

pulse_polarization(polarization: tbt.LaserPolarization, wavelength: tbt.LaserWavelength) -> bool
    Configure the polarization of the laser light.

pulse_settings(pulse: tbt.LaserPulse) -> bool
    Apply the pulse settings to the laser.

retract_laser_objective() -> bool
    Retract the laser objective to a safe position.

objective_position(position_mm: float, tolerance_mm=Constants.laser_objective_tolerance_mm) -> bool
    Move the laser objective to the requested position.

beam_shift(shift_um: tbt.Point, shift_tolerance_um: float = Constants.laser_beam_shift_tolerance_um) -> bool
    Adjust the laser beam shift to the specified values.

create_pattern(pattern: tbt.LaserPattern) -> bool
    Create a laser pattern and check that it is set correctly.

apply_laser_settings(image_beam: tbt.Beam, settings: tbt.LaserSettings) -> bool
    Apply the laser settings to the current patterning.

execute_patterning() -> bool
    Execute the laser patterning.

mill_region(settings: tbt.LaserSettings) -> bool
    Perform laser milling on a specified region.

laser_operation(step: tbt.Step, general_settings: tbt.GeneralSettings, slice_number: int) -> bool
    Perform a laser operation based on the specified step and settings.

map_ebsd() -> bool
    Start an EBSD map and ensure it takes the minimum expected time.

map_eds() -> bool
    Start an EDS map and ensure it takes the minimum expected time.
"""

# Default python modules
import os
from pathlib import Path
import time
import warnings
import contextlib, io
import math
import socket

try:
    import Laser.PythonControl as tfs_laser

    print("Laser PythonControl API imported.")
except:
    print("WARNING: Laser API not imported!")
    print("\tLaser control, as well as EBSD and EDS control are unavailable.")

# 3rd party .whl modules
import h5py

# Local scripts
from pytribeam.constants import Conversions, Constants
import pytribeam.factory as factory
import pytribeam.types as tbt
import pytribeam.utilities as ut
import pytribeam.insertable_devices as devices
import pytribeam.image as img
import pytribeam.log as log


def laser_state_to_db(state: tbt.LaserState) -> dict:
    """
    This function converts a `LaserState` object into a flattened dictionary representation.

    Parameters
    ----------
    state : tbt.LaserState
        The laser state object to convert.

    Returns
    -------
    dict
        A flattened dictionary representation of the laser state.
    """
    db = {}

    db["wavelength_nm"] = state.wavelength_nm
    db["frequency_khz"] = state.frequency_khz
    db["pulse_divider"] = state.pulse_divider
    db["pulse_energy_uj"] = state.pulse_energy_uj
    db["objective_position_mm"] = state.objective_position_mm
    db["expected_pattern_duration_s"] = state.expected_pattern_duration_s

    beam_shift = state.beam_shift_um
    db["beam_shift_um_x"] = beam_shift.x
    db["beam_shift_um_y"] = beam_shift.y

    # we can name these differently depending on the needs of the GUI
    pattern = state.pattern
    db["laser_pattern_mode"] = pattern.mode.value
    db["laser_pattern_rotation_deg"] = pattern.rotation_deg
    db["laser_pattern_pulses_per_pixel"] = pattern.pulses_per_pixel
    db["laser_pattern_pixel_dwell_ms"] = pattern.pixel_dwell_ms

    geometry = pattern.geometry
    db["passes"] = geometry.passes
    db["laser_scan_type"] = geometry.scan_type.value
    db["geometry_type"] = geometry.type.value

    if geometry.type == tbt.LaserPatternType.BOX:
        db["size_x_um"] = geometry.size_x_um
        db["size_y_um"] = geometry.size_y_um
        db["pitch_x_um"] = geometry.pitch_x_um
        db["pitch_y_um"] = geometry.pitch_y_um
        db["coordinate_ref"] = geometry.coordinate_ref

    if geometry.type == tbt.LaserPatternType.LINE:
        db["size_um"] = geometry.size_um
        db["pitch_um"] = geometry.pitch_um

    return db


def laser_connected() -> bool:
    """
    Check if the laser is connected.

    This function tests the connection to the laser and returns True if the connection is successful.

    Returns
    -------
    bool
        True if the laser is connected, False otherwise.
    """
    connect_msg = "Connection test successful.\n"
    laser_status = io.StringIO()
    try:
        with contextlib.redirect_stdout(laser_status):
            tfs_laser.TestConnection()
    except:
        return False
    else:
        if laser_status.getvalue() == connect_msg:
            return True
    return False


def _device_connections() -> tbt.DeviceStatus:
    """
    Check the connection status of the laser and associated external devices.

    This function checks the connection status of the laser, EBSD, and EDS devices. It is meant to be a quick tool for the GUI and does not provide additional information for troubleshooting.

    Returns
    -------
    tbt.DeviceStatus
        The connection status of the laser, EBSD, and EDS devices.
    """
    # laser must be connected to connect with other devices:
    if not laser_connected():
        laser = tbt.RetractableDeviceState.ERROR
        ebsd = tbt.RetractableDeviceState.ERROR
        eds = tbt.RetractableDeviceState.ERROR
    else:
        laser = tbt.RetractableDeviceState.CONNECTED
        ebsd = devices.connect_EBSD()  # retractable device state
        eds = devices.connect_EDS()  # retractable device state

    return tbt.DeviceStatus(
        laser=laser,
        ebsd=ebsd,
        eds=eds,
    )


def pattern_mode(mode: tbt.LaserPatternMode) -> bool:
    """
    Set the laser pattern mode.

    This function sets the laser pattern mode and verifies that it has been set correctly.

    Parameters
    ----------
    mode : tbt.LaserPatternMode
        The laser pattern mode to set.

    Returns
    -------
    bool
        True if the pattern mode is set correctly.

    Raises
    ------
    SystemError
        If the pattern mode cannot be set correctly.
    """
    tfs_laser.Patterning_Mode(mode.value)
    laser_state = factory.active_laser_state()
    if laser_state.pattern.mode != mode:
        raise SystemError("Unable to correctly set pattern mode.")
    return True


def pulse_energy_uj(
    energy_uj: float,
    energy_tol_uj: float = Constants.laser_energy_tol_uj,
    delay_s: float = 3.0,
) -> bool:
    """
    Set the pulse energy on the laser.

    This function sets the pulse energy on the laser and verifies that it has been set correctly. It should be done after setting the pulse divider.

    Parameters
    ----------
    energy_uj : float
        The pulse energy to set in microjoules.
    energy_tol_uj : float, optional
        The tolerance for the pulse energy in microjoules (default is Constants.laser_energy_tol_uj).
    delay_s : float, optional
        The delay in seconds after setting the pulse energy (default is 3.0 seconds).

    Returns
    -------
    bool
        True if the pulse energy is set correctly.

    Raises
    ------
    ValueError
        If the pulse energy cannot be set correctly.
    """
    tfs_laser.Laser_SetPulseEnergy_MicroJoules(energy_uj)
    time.sleep(delay_s)
    laser_state = factory.active_laser_state()
    if not ut.in_interval(
        val=laser_state.pulse_energy_uj,
        limit=tbt.Limit(
            min=energy_uj - energy_tol_uj,
            max=energy_uj + energy_tol_uj,
        ),
        type=tbt.IntervalType.CLOSED,
    ):
        raise ValueError(
            f"Could not properly set pulse energy, requested '{energy_uj}' uJ",
            f"Current settings is {round(laser_state.pulse_energy_uj,3)} uJ",
        )
    return True


def pulse_divider(
    divider: int,
    delay_s: float = Constants.laser_delay_s,
) -> bool:
    """
    Set the pulse divider on the laser.

    This function sets the pulse divider on the laser and verifies that it has been set correctly.

    Parameters
    ----------
    divider : int
        The pulse divider to set.
    delay_s : float, optional
        The delay in seconds after setting the pulse divider (default is Constants.laser_delay_s).

    Returns
    -------
    bool
        True if the pulse divider is set correctly.

    Raises
    ------
    ValueError
        If the pulse divider cannot be set correctly.
    """
    tfs_laser.Laser_PulseDivider(divider)
    time.sleep(delay_s)
    laser_state = factory.active_laser_state()
    if laser_state.pulse_divider != divider:
        raise ValueError(
            f"Could not properly set pulse divider, requested '{divider}'",
            f"Current settings have a divider of {laser_state.pulse_divider}.",
        )
    return True


def set_wavelength(
    wavelength: tbt.LaserWavelength,
    frequency_khz: float = 60,  # make constnat
    timeout_s: int = 20,  # 120,  # make constant
    num_attempts: int = 2,  # TODO make a constant
    delay_s: int = 5,  # make a constant
) -> bool:
    """
    Set the wavelength and frequency of the laser.

    This function sets the wavelength and frequency of the laser and verifies that they have been set correctly.

    Parameters
    ----------
    wavelength : tbt.LaserWavelength
        The wavelength to set.
    frequency_khz : float, optional
        The frequency to set in kHz (default is 60 kHz).
    timeout_s : int, optional
        The timeout in seconds for each attempt (default is 20 seconds).
    num_attempts : int, optional
        The number of attempts to set the wavelength and frequency (default is 2).
    delay_s : int, optional
        The delay in seconds between checks (default is 5 seconds).

    Returns
    -------
    bool
        True if the wavelength and frequency are set correctly, False otherwise.
    """

    def correct_preset(laser_state: tbt.LaserState):
        if laser_state.wavelength_nm == wavelength:
            return math.isclose(laser_state.frequency_khz, frequency_khz, rel_tol=0.05)
            # TODO use constant for tolerance):
        return False

    for _ in range(num_attempts):
        if correct_preset(factory.active_laser_state()):
            return True
        print("Adjusting preset...")
        tfs_laser.Laser_SetPreset(
            wavelength_nm=wavelength.value, frequency_kHz=frequency_khz
        )
        time_remaining = timeout_s
        while time_remaining > 0:
            laser_state = factory.active_laser_state()
            # print(time_remaining, laser_state.frequency_khz)
            if correct_preset(laser_state=laser_state):
                return True
            time.sleep(delay_s)
            time_remaining -= delay_s

    return False


def read_power(delay_s: float = Constants.laser_delay_s) -> float:
    """
    Measure the laser power in watts.

    This function measures the laser power using an external power meter.

    Parameters
    ----------
    delay_s : float, optional
        The delay in seconds before reading the power (default is Constants.laser_delay_s).

    Returns
    -------
    float
        The measured laser power in watts.
    """
    tfs_laser.Laser_ExternalPowerMeter_PowerMonitoringON()
    tfs_laser.Laser_ExternalPowerMeter_SetZeroOffset()
    tfs_laser.Laser_FireContinuously_Start()
    time.sleep(delay_s)
    power = tfs_laser.Laser_ExternalPowerMeter_ReadPower()
    tfs_laser.Laser_FireContinuously_Stop()
    tfs_laser.Laser_ExternalPowerMeter_PowerMonitoringOFF()
    return power


def insert_shutter(microscope: tbt.Microscope) -> bool:
    """
    Insert the laser shutter.

    This function inserts the laser shutter and verifies that it has been inserted correctly.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to insert the laser shutter.

    Returns
    -------
    bool
        True if the laser shutter is successfully inserted.

    Raises
    ------
    SystemError
        If the laser shutter cannot be inserted.
    """
    devices.CCD_view(microscope=microscope)
    if tfs_laser.Shutter_GetState() != "Inserted":
        tfs_laser.Shutter_Insert()
    state = tfs_laser.Shutter_GetState()
    if state != "Inserted":
        raise SystemError(
            f"Could not insert laser shutter, current laser shutter state is '{state}'."
        )
    devices.CCD_pause(microscope=microscope)
    return True


def retract_shutter(microscope: tbt.Microscope) -> bool:
    """
    Retract the laser shutter.

    This function retracts the laser shutter and verifies that it has been retracted correctly.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to retract the laser shutter.

    Returns
    -------
    bool
        True if the laser shutter is successfully retracted.

    Raises
    ------
    SystemError
        If the laser shutter cannot be retracted.
    """
    devices.CCD_view(microscope=microscope)
    if tfs_laser.Shutter_GetState() != "Retracted":
        tfs_laser.Shutter_Retract()
    state = tfs_laser.Shutter_GetState()
    if state != "Retracted":
        raise SystemError(
            f"Could not retract laser shutter, current laser shutter state is '{state}'."
        )
    devices.CCD_pause(microscope=microscope)
    return True


def pulse_polarization(
    polarization: tbt.LaserPolarization, wavelength: tbt.LaserWavelength
) -> bool:
    """
    Configure the polarization of the laser light.

    This function sets the polarization of the laser light based on the specified polarization and wavelength. The polarization is controlled via "FlipperConfiguration", which takes the following values:
        - Waveplate_None switches to Vert. (P)
        - Waveplate_1030 switches to Horiz. (S)
        - Waveplate_515 switches to Horiz. (S)

    Parameters
    ----------
    polarization : tbt.LaserPolarization
        The desired polarization of the laser light.
    wavelength : tbt.LaserWavelength
        The wavelength of the laser light.

    Returns
    -------
    bool
        True if the polarization is set correctly.

    Raises
    ------
    KeyError
        If the laser wavelength or pulse polarization is invalid.
    """
    if polarization == tbt.LaserPolarization.VERTICAL:
        tfs_laser.FlipperConfiguration("Waveplate_None")
        return True
    elif polarization == tbt.LaserPolarization.HORIZONTAL:
        match_db = {
            tbt.LaserWavelength.NM_1030: "Waveplate_1030",
            tbt.LaserWavelength.NM_515: "Waveplate_515",
        }
        try:
            tfs_laser.FlipperConfiguration(match_db[wavelength])
        except KeyError:
            raise KeyError(
                f"Invalid laser wavelength, valid options are {[i.value for i in tbt.LaserWavelength]}"
            )
        return True
    else:
        raise KeyError(
            f"Invalid pulse polarization, valid options are {[i.value for i in tbt.LaserPolarization]}"
        )


def pulse_settings(pulse: tbt.LaserPulse) -> True:
    """
    Apply the pulse settings to the laser.

    This function applies the specified pulse settings to the laser, including wavelength, pulse divider, pulse energy, and polarization.

    Parameters
    ----------
    pulse : tbt.LaserPulse
        The pulse settings to apply.

    Returns
    -------
    bool
        True if the pulse settings are applied correctly.
    """
    active_state = factory.active_laser_state()
    if pulse.wavelength_nm != active_state.wavelength_nm:
        # wavelength settings
        set_wavelength(wavelength=pulse.wavelength_nm)
    pulse_divider(divider=pulse.divider)
    pulse_energy_uj(energy_uj=pulse.energy_uj)
    pulse_polarization(polarization=pulse.polarization, wavelength=pulse.wavelength_nm)
    return True


def retract_laser_objective() -> bool:
    """
    Retract the laser objective to a safe position.

    This function retracts the laser objective to a predefined safe position.

    Returns
    -------
    bool
        True if the laser objective is successfully retracted.
    """
    objective_position(position_mm=Constants.laser_objective_retracted_mm)
    return True


def objective_position(
    position_mm: float,
    tolerance_mm=Constants.laser_objective_tolerance_mm,
) -> bool:
    """
    Move the laser objective to the requested position.

    This function moves the laser objective to the specified position and verifies that it has been moved correctly.

    Parameters
    ----------
    position_mm : float
        The desired position of the laser objective in millimeters.
    tolerance_mm : float, optional
        The tolerance for the laser objective position in millimeters (default is Constants.laser_objective_tolerance_mm).

    Returns
    -------
    bool
        True if the laser objective is moved to the requested position correctly.

    Raises
    ------
    ValueError
        If the requested position is out of range.
    SystemError
        If the laser objective cannot be moved to the requested position.
    """
    tfs_laser.LIP_UnlockZ()

    if not ut.in_interval(
        val=position_mm,
        limit=Constants.laser_objective_limit_mm,
        type=tbt.IntervalType.CLOSED,
    ):
        raise ValueError(
            f"Requested laser objective position of {position_mm} mm is out of range. Laser objective can travel from {Constants.laser_objective_limit_mm.min} to {Constants.laser_objective_limit_mm.max} mm."
        )

    for _ in range(2):
        if ut.in_interval(
            val=tfs_laser.LIP_GetZPosition(),
            limit=tbt.Limit(
                min=position_mm - tolerance_mm, max=position_mm + tolerance_mm
            ),
            type=tbt.IntervalType.CLOSED,
        ):
            return True
        tfs_laser.LIP_SetZPosition(position_mm, asynchronously=False)

    raise SystemError(
        f"Unable to move laser injection port objective to requested position of {position_mm} +/- {tolerance_mm} mm.",
        f"Currently at {tfs_laser.LIP_GetZPosition()} mm.",
    )


def _shift_axis(
    target: float,
    current: float,
    tolerance: float,
    axis: str,
) -> bool:
    """
    Helper function for beam shift.

    This function adjusts the beam shift for the specified axis to the target value within the given tolerance.

    Parameters
    ----------
    target : float
        The target value for the beam shift.
    current : float
        The current value of the beam shift.
    tolerance : float
        The tolerance for the beam shift.
    axis : str
        The axis to adjust ("X" or "Y").

    Returns
    -------
    bool
        True if the beam shift is adjusted to the target value correctly, False otherwise.
    """
    for _ in range(2):
        if ut.in_interval(
            val=current,
            limit=tbt.Limit(
                min=target - tolerance,
                max=target + tolerance,
            ),
            type=tbt.IntervalType.CLOSED,
        ):
            return True
        if axis == "X":
            tfs_laser.BeamShift_Set_X(value=target)
            current = tfs_laser.BeamShift_Get_X()
        if axis == "Y":
            tfs_laser.BeamShift_Set_Y(value=target)
            current = tfs_laser.BeamShift_Get_Y()

    return False


def beam_shift(
    shift_um: tbt.Point,
    shift_tolerance_um: float = Constants.laser_beam_shift_tolerance_um,
) -> bool:
    """
    Adjust the laser beam shift to the specified values.

    This function adjusts the laser beam shift to the specified x and y values within the given tolerance.

    Parameters
    ----------
    shift_um : tbt.Point
        The target beam shift values in micrometers.
    shift_tolerance_um : float, optional
        The tolerance for the beam shift in micrometers (default is Constants.laser_beam_shift_tolerance_um).

    Returns
    -------
    bool
        True if the beam shift is adjusted to the target values correctly.

    Raises
    ------
    ValueError
        If the beam shift cannot be adjusted to the target values.
    """
    current_shift_x = tfs_laser.BeamShift_Get_X()
    current_shift_y = tfs_laser.BeamShift_Get_Y()

    if not (
        _shift_axis(
            target=shift_um.x,
            current=current_shift_x,
            tolerance=shift_tolerance_um,
            axis="X",
        )
        and _shift_axis(
            target=shift_um.y,
            current=current_shift_y,
            tolerance=shift_tolerance_um,
            axis="Y",
        )
    ):
        raise ValueError(
            f"Unable to set laser beam shift. Requested beam shift of (x,y) = ({shift_um.x} um,{shift_um.y} um,), but current beam shift is ({tfs_laser.BeamShift_Get_X()} um, {tfs_laser.BeamShift_Get_Y()} um)."
        )
    return True


def create_pattern(pattern: tbt.LaserPattern):
    """
    Create a laser pattern and check that it is set correctly.

    This function creates a laser pattern based on the specified pattern settings and verifies that it has been set correctly.

    Parameters
    ----------
    pattern : tbt.LaserPattern
        The laser pattern settings to create.

    Returns
    -------
    bool
        True if the pattern is created and set correctly.

    Raises
    ------
    ValueError
        If the pattern geometry type is unsupported.
    SystemError
        If the pattern cannot be set correctly.
    """
    pattern_mode(mode=pattern.mode)

    # check if pattern is empty or not
    if isinstance(pattern.geometry, tbt.LaserBoxPattern):
        box = pattern.geometry
        tfs_laser.Patterning_CreatePattern_Box(
            sizeX_um=box.size_x_um,
            sizeY_um=box.size_y_um,
            pitchX_um=box.pitch_x_um,
            pitchY_um=box.pitch_y_um,
            dwellTime_ms=pattern.pixel_dwell_ms,
            passes_int=box.passes,
            pulsesPerPixel_int=pattern.pulses_per_pixel,
            scanrotation_degrees=pattern.rotation_deg,
            scantype_string=box.scan_type.value,  # cast enum to string
            coordinateReference_string=box.coordinate_ref.value,  # cast enum to string
        )
    elif isinstance(pattern.geometry, tbt.LaserLinePattern):
        line = pattern.geometry
        tfs_laser.Patterning_CreatePattern_Line(
            sizeX_um=line.size_um,
            pitchX_um=line.pitch_um,
            dwellTime_ms=pattern.pixel_dwell_ms,
            passes_int=line.passes,
            pulsesPerPixel_int=pattern.pulses_per_pixel,
            scanrotation_degrees=pattern.rotation_deg,
            scantype_string=line.scan_type.value,  # cast enum to string
        )
    else:
        raise ValueError(
            f"Unsupported pattern geometry of type '{type(pattern.geometry)}'. Supported types are {tbt.LaserLinePattern, tbt.LaserBoxPattern}"
        )
    laser_state = factory.active_laser_state()
    if laser_state.pattern != pattern:
        raise SystemError("Unable to correctly set Pattern.")
    return True


def apply_laser_settings(image_beam: tbt.Beam, settings: tbt.LaserSettings) -> bool:
    """
    Apply the laser settings to the current patterning.

    This function applies the specified laser settings to the current patterning, including beam scan rotation, pulse settings, objective position, beam shift, and patterning settings.

    Parameters
    ----------
    image_beam : tbt.Beam
        The beam settings for the image.
    settings : tbt.LaserSettings
        The laser settings to apply.

    Returns
    -------
    bool
        True if the laser settings are applied correctly.
    """
    microscope = settings.microscope

    # forces rotation of electron beam for laser (TFS required)
    img.beam_scan_rotation(
        beam=image_beam,
        microscope=microscope,
        rotation_deg=Constants.image_scan_rotation_for_laser_deg,
    )
    # pulse settings
    pulse_settings(pulse=settings.pulse)

    # objective position
    objective_position(settings.objective_position_mm)

    # beam shift
    beam_shift(settings.beam_shift_um)

    # apply patterning settings
    create_pattern(pattern=settings.pattern)

    return True


def execute_patterning() -> bool:
    """
    Execute the laser patterning.

    This function starts the laser patterning process.

    Returns
    -------
    bool
        True if the patterning process is started successfully.
    """
    tfs_laser.Patterning_Start()

    return True


### main methods


def mill_region(
    settings: tbt.LaserSettings,
) -> bool:
    """
    Perform laser milling on a specified region.

    This function performs laser milling on a specified region using the provided laser settings. It checks the laser connection, applies the laser settings, inserts the shutter, executes the patterning, retracts the shutter, and resets the scan rotation.

    Parameters
    ----------
    settings : tbt.LaserSettings
        The laser settings to use for milling.

    Returns
    -------
    bool
        True if the milling process is completed successfully.

    Raises
    ------
    SystemError
        If the laser is not connected.
    """
    # check connection
    if not laser_connected():
        raise SystemError("Laser is not connected")

    microscope = settings.microscope
    # initial_scan_rotation of ebeam
    devices.device_access(microscope=microscope)
    active_beam = factory.active_beam_with_settings(microscope=microscope)
    scan_settings = factory.active_scan_settings(microscope=microscope)
    initial_scan_rotation_deg = scan_settings.rotation_deg

    # apply laser settings
    apply_laser_settings(
        image_beam=active_beam,
        settings=settings,
    )

    # insert shutter
    insert_shutter(microscope=microscope)

    # execute patterning
    execute_patterning()

    # retract shutter
    retract_shutter(microscope=microscope)
    time.sleep(1)

    # reset scan rotation
    img.beam_scan_rotation(
        beam=active_beam,
        microscope=microscope,
        rotation_deg=initial_scan_rotation_deg,
    )

    return True


def laser_operation(
    step: tbt.Step, general_settings: tbt.GeneralSettings, slice_number: int
) -> bool:
    """
    Perform a laser operation based on the specified step and settings.

    This function performs a laser operation using the provided step and general settings. It logs the laser power before and after the operation, and performs the milling process.

    Parameters
    ----------
    step : tbt.Step
        The step object containing the operation settings.
    general_settings : tbt.GeneralSettings
        The general settings object.
    slice_number : int
        The slice number for the operation.

    Returns
    -------
    bool
        True if the laser operation is completed successfully.
    """
    # log laser power before
    laser_power_w = read_power()
    log.laser_power(
        step_number=step.number,
        step_name=step.name,
        slice_number=slice_number,
        log_filepath=general_settings.log_filepath,
        dataset_name=Constants.pre_lasing_dataset_name,
        power_w=laser_power_w,
    )

    mill_region(settings=step.operation_settings)

    # log laser power after
    laser_power_w = read_power()
    log.laser_power(
        step_number=step.number,
        step_name=step.name,
        slice_number=slice_number,
        log_filepath=general_settings.log_filepath,
        dataset_name=Constants.post_lasing_dataset_name,
        power_w=laser_power_w,
    )

    return True


def socket_command(
    connection: socket.socket,
    command: str,
    pause_s: float = 0.2,
    timeout_s: float = 10.0,
    expected_response: str = None,
) -> str:
    """
    EDAX socket commands always (with the exception of edax_unlock) return '[command_sent] response "[response]"'.
    Therefore by default, we check if the response contains the command sent and the string "response", provided it is not the unlock command.
    Assuming the response is valid, one can specify the expected response in '[command_sent] response "[expected response]"'.
    If the expected response is not equal to the actual response, then a ValueError is raised.
    Assuming all checks pass, the returned value is the [response] part of the returned string (the command and the strin "resposne" are removed).

    Note that some commands return a meaningful response and not just success/failure (such as get_map_status). In this case, we set the expected response to None
    so that we can read the return value.
    """
    connection.sendall(command.lower().encode("ascii"))
    time.sleep(pause_s)
    found_response = socket_response(connection=connection, timeout_s=timeout_s)

    if expected_response is not None:
        expected_response = expected_response.lower()
        if found_response != expected_response:
            raise RuntimeError(
                f"EDAX IPAPI command '{command}' returned an invalid response. Expected '{expected_response}' but received '{found_response}'"
            )

    return found_response


def socket_response(connection: socket.socket, timeout_s: float = 10.0) -> str:
    """Checks the socket for a message."""
    connection.settimeout(timeout_s)
    try:
        found_response = connection.recv(4096).decode("ascii").lower()
    except socket.timeout:
        found_response = None
    return found_response


def parse_socket_response(response: str, sent_command: str) -> str:
    """Parses a response from the EDAX IPAPI server."""
    if response is None:
        return None
    response = (
        response.replace(sent_command.lower(), "")
        .replace("response", "")
        .replace('"', "")
        .replace(" ", "")
        .strip()
    )
    return response


def configure_scan(connection: socket.socket, settings: tbt.EBSDSettings) -> bool:
    # patterns
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_savepatterns "{settings.save_patterns}"',
        expected_response='set_ebsd_params_savepatterns response "execution successful"',
    )
    # grid type
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_grid "{settings.grid_type}"',
        expected_response='set_ebsd_params_grid response "execution successful"',
    )
    # resolution
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_resolution "3"',
        expected_response='set_ebsd_params_resolution response "execution successful"',
    )
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_customstepsize "{settings.scan_box.step_size_um}"',
        expected_response='set_ebsd_params_customstepsize response "execution successful"',
    )
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_stepsize "{settings.scan_box.step_size_um}"',
        expected_response='set_ebsd_params_stepsize response "execution successful"',
    )
    # simulataneous EDS
    if settings.enable_eds:
        socket_command(
            connection=connection,
            command=f'set_ebsd_params_savespectra "{settings.enable_eds}"',
            expected_response='set_ebsd_params_savespectra response "execution successful"',
        )

    # start x and Y
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_ystart "{settings.scan_box.y_start_um}"',
        expected_response='set_ebsd_params_ystart response "execution successful"',
    )
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_xstart "{settings.scan_box.x_start_um}"',
        expected_response='set_ebsd_params_xstart response "execution successful"',
    )

    # size x and Y
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_ysize "{settings.scan_box.y_size_um}"',
        expected_response='set_ebsd_params_ysize response "execution successful"',
    )
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_xsize "{settings.scan_box.x_size_um}"',
        expected_response='set_ebsd_params_xsize response "execution successful"',
    )


def ebsd_preflight(
    general_settings: tbt.GeneralSettings,
) -> bool:
    """EDAX only for now"""
    # TODO confirm the user is done befopre continuing

    edax_settings = general_settings.EDAX_settings

    connection = connect_EDAX(
        edax_settings.connection.host,
        edax_settings.connection.port,
    )

    folder = edax_settings.save_directory
    project_name = edax_settings.project_name
    guid = Constants.EDAX_GUID
    max_slice_number = general_settings.max_slice_number
    slice_thickness_um = general_settings.slice_thickness_um

    # EBSD preflight
    # folder locations and mapping
    socket_command(
        connection=connection,
        command='set_system_remoteaccesstype_ebsd "1"',
        expected_response='set_system_remoteaccesstype_ebsd response "execution successful"',
        timeout_s=5.0,
    )
    socket_command(
        connection=connection,
        command=f'set_ebsd_params_folderpath "{folder}"',
        expected_response='set_ebsd_params_folderpath response "execution successful"',
        pause_s=0.0,
    )
    socket_command(
        connection=connection,
        command=f'set_system_projectinfo_ext_ebsd "{guid}","{project_name}","{max_slice_number}","{slice_thickness_um}"',
        expected_response='set_system_projectinfo_ext_ebsd response "execution successful"',
        pause_s=0.0,
        timeout_s=120.0,
    )
    # socket_command(
    #     connection=connection,
    #     command=f"do_map_setup_start_ebsd",
    #     expected_response='do_map_setup_start_ebsd response "execution successful"',
    #     pause_s=0.0,
    #     timeout_s=60.0,
    # )
    disconnect_EDAX(connection=connection)
    return True


def connect_EDAX(ebsd_host: str, ebsd_port: int) -> socket.socket:
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host = ebsd_host
    port = ebsd_port
    connection.connect((host, port))
    print(f"\tConnected to {host}:{port}")
    # unlock and enable remote access
    socket_command(
        connection=connection,
        command="edax_unlock",
        expected_response="client connection accepted",
    )
    return connection


def disconnect_EDAX(connection: socket.socket) -> bool:
    connection.close()
    return True


def edax_camera_saturation(
    microscope: tbt.Microscope,
    connection: socket.socket,
    hfw_mm=Constants.ebsd_camera_saturation_hfw_mm,
    delay_s=Constants.ebsd_camera_saturation_delay_s,
) -> float:
    """Measures the (EDAX) EBSD detector saturation. Returns in range [0,1]"""
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
    command = "get_camera_saturation"
    camera_saturation = socket_command(
        connection=connection,
        command=command,
        expected_response=None,
    )
    microscope.imaging.stop_acquisition()

    # reset detector and hfw
    img.detector_type(microscope=microscope, detector=initial_detector)
    img.beam_hfw(
        beam=tbt.ElectronBeam(settings=tbt.BeamSettings()),
        microscope=microscope,
        hfw_mm=initial_hfw_m * Conversions.M_TO_MM,
    )
    microscope.imaging.start_acquisition()
    time.sleep(delay_s)
    microscope.imaging.stop_acquisition()

    camera_saturation = float(parse_socket_response(camera_saturation, command))

    return float(camera_saturation)


def edax_average_ci(connection: socket.socket) -> float:
    """Get the average confidence of the most recent scan."""
    command = "get_map_avg_ci"
    average_ci = socket_command(
        connection=connection,
        command=command,
        expected_response=None,
        timeout_s=60.0,
    )
    average_ci = float(parse_socket_response(average_ci, command))
    return average_ci


def edax_insert_camera(connection=socket.socket):
    camera_status = socket_command(
        connection=connection,
        command="get_camera_status",
        expected_response=None,
        timeout_s=60.0,
    )
    if "slidein" in camera_status:
        # print("Slide is already in")
        return True
    print("\tInserting EDAX EBSD camera...")
    socket_command(
        connection=connection,
        command="do_map_insert_camera",
        expected_response='do_map_insert_camera response "execution successful"',
    )
    time.sleep(10.0)
    while True:
        response = socket_command(
            connection=connection,
            command="get_camera_status",
            expected_response=None,
            timeout_s=60.0,
        )
        # print("Camera status:", response)
        if response is None:
            pass
        elif "slidein" in response:
            break
        time.sleep(2.0)
    print("\tEDAX EBSD camera inserted")
    return True


def edax_retract_camera(connection=socket.socket):
    camera_status = socket_command(
        connection=connection,
        command="get_camera_status",
        expected_response=None,
        timeout_s=60.0,
    )
    if "slideout" in camera_status:
        # print("Slide is already out")
        return True
    print("\tRetracting EDAX EBSD camera...")
    socket_command(
        connection=connection,
        command="do_map_retract_camera",
        expected_response='do_map_retract_camera response "execution successful"',
    )
    time.sleep(10.0)
    while True:
        response = socket_command(
            connection=connection,
            command="get_camera_status",
            expected_response=None,
            timeout_s=60.0,
        )
        # print("Camera status:", response)
        if response is None:
            pass
        elif "slideout" in response:
            break
        elif "slidemovewdog" in response:
            socket_command(
                connection=connection,
                command="do_map_retract_camera",
                expected_response='do_map_retract_camera response "execution successful"',
                timeout_s=60.0,
            )
        elif "slidewatchdog" in response:
            raise RuntimeError(
                "EBSD camera is in indeterminate state. Please manually adjust and restart."
            )
        time.sleep(2.0)
    print("\tEDAX EBSD camera retracted")
    return True


def map_ebsd(
    general_settings: tbt.GeneralSettings,
    step_settings: tbt.EBSDSettings,
    slice_number: int,
    step: tbt.Step,
) -> bool:
    ebsd_oem = general_settings.EBSD_OEM
    yml_version = general_settings.yml_version
    start_time = time.time()

    if ebsd_oem == tbt.ExternalDeviceOEM.EDAX and yml_version >= 1.1:
        # Make connection
        connection = connect_EDAX(
            general_settings.EDAX_settings.connection.host,
            general_settings.EDAX_settings.connection.port,
        )

        # Set APEX variables properly
        configure_scan(
            connection=connection,
            settings=step_settings,
        )
        # Grab the camera saturation and log it
        cam_sat_p = edax_camera_saturation(
            microscope=step_settings.image.microscope,
            connection=connection,
        )
        log.ebsd_camera_saturation(
            step_number=step.number,
            step_name=step.name,
            slice_number=slice_number,
            log_filepath=general_settings.log_filepath,
            dataset_name=Constants.ebsd_camera_saturation_dataset_name,
            cam_sat_p=cam_sat_p,
        )

        # Predict duration
        n_ticks = socket_command(
            connection=connection,
            command="get_map_duration_ebsd",
            expected_response=None,
        )
        n_ticks = float(parse_socket_response(n_ticks, "get_map_duration_ebsd"))
        expected_duration_s = n_ticks / 10000000 + Constants.edax_map_start_delay_s

        # Start scan and wait for expected duration
        socket_command(
            connection=connection,
            command=f'do_map_collection_start_ebsd "Slice_{slice_number:04}"',
            expected_response='do_map_collection_start_ebsd response "execution successful"',
        )
        scan_start_time = time.time()
        print(f"\tEBSD map started...")
        time.sleep(Constants.edax_map_start_delay_s)

        # Check map status every second to see when it finishes
        timeout = expected_duration_s * Constants.edax_timeout_scalar
        while True:
            map_status = socket_command(
                connection=connection,
                command=f"get_map_status_ebsd",
                expected_response=None,
                pause_s=1.0,
                timeout_s=120.0,
            )
            # map_status should return a string with "get_map_status_ebsd", the command that was originally sent
            # however, it is possible for it to return "event_map_collection_complete_ebsd mapping complete" instead due to the scan finishing
            # check to make sure it is one of those two
            if "get_map_status_ebsd" in map_status:
                map_status = parse_socket_response(map_status, "get_map_status_ebsd")
            elif "event_map_collection_complete_ebsd" in map_status:
                map_status = parse_socket_response(
                    map_status, "event_map_collection_complete_ebsd"
                )
            else:
                raise RuntimeError(
                    f"EDAX IPAPI returned an unexpected response. Please make sure the software is operating properly. Response: {map_status}"
                )

            # Check if the map status command is timed out (None) or if the map collection did not finish in time
            if map_status is None:
                # The IPAPI server did not respond in time. Try again.
                pass
            elif time.time() - scan_start_time > timeout:
                disconnect_EDAX(connection=connection)
                raise RuntimeError(
                    f"EDAX EBSD Map did not complete within {timeout:.0f} seconds, aborting."
                )

            # We received a valid response, check the status
            map_status = tbt.EdaxMappingStatus(map_status)
            if map_status == tbt.EdaxMappingStatus.READY:
                # The map finished successfully
                print("\t\tMapping complete")
                break
            elif map_status == tbt.EdaxMappingStatus.MAPPING_COMPLETE:
                # The map finished successfully, but there might be a second message of "ready" coming"
                print("\t\tMapping complete")
                socket_response(
                    connection=connection,
                    timeout_s=10.0,
                )
                break
            time.sleep(Constants.edax_map_status_interval_s)

        # Record end time
        end_time = time.time()

        # Grab the average CI value and put in log
        avg_ci_p = edax_average_ci(connection=connection)
        log.ebsd_average_ci(
            step_number=step.number,
            step_name=step.name,
            slice_number=slice_number,
            log_filepath=general_settings.log_filepath,
            dataset_name=Constants.ebsd_average_ci_dataset_name,
            avg_ci_p=avg_ci_p,
        )
        time.sleep(1.0)

        # Retract the EBSD camera
        edax_retract_camera(connection=connection)

        # Disconnect socket to EDAX IPAPI
        disconnect_EDAX(connection=connection)

        # Check if the map was too quick
        actual_duration_s = end_time - scan_start_time
        if actual_duration_s < expected_duration_s:
            raise RuntimeError(
                f"EDAX EBSD map finished unexpectedly quickly. Expected duration was {expected_duration_s:.0f} seconds (actual duration was {actual_duration_s:.0f} seconds). Please check the EDAX software."
            )

    else:
        # Run map through LaserControl API
        tfs_laser.EBSD_StartMap()

        # Check if the map was too quick
        end_time = time.time()
        map_time = end_time - start_time
        if map_time < Constants.min_map_time_s:
            raise ValueError(
                f"Mapping did not take minimum expected time of {Constants.min_map_time_s} seconds, please reset EBSD mapping software"
            )
        print(f"\t\tMapping Complete in {int(map_time)} seconds.")

    return True


def map_eds() -> bool:
    """
    Start an EDS map and ensure it takes the minimum expected time.

    This function starts an EDS map and checks that the mapping process takes at least the minimum expected time. If the mapping process is too short, it raises an error.

    Returns
    -------
    bool
        True if the EDS mapping is completed successfully.

    Raises
    ------
    ValueError
        If the mapping process does not take the minimum expected time.
    """
    start_time = time.time()
    tfs_laser.EDS_StartMap()
    time.sleep(1)
    end_time = time.time()
    map_time = end_time - start_time
    if map_time < Constants.min_map_time_s:
        raise ValueError(
            f"Mapping did not take minimum expected time of {Constants.min_map_time_s} seconds, please reset EDS mapping software"
        )
    print(f"\t\tMapping Complete in {int(map_time)} seconds.")
    return True
