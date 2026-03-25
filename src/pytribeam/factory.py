#!/usr/bin/python3
"""
Factory Module
==============

This module contains functions for creating and validating various settings and objects used in the microscope operations. The functions are organized to handle different step types, including EBSD, EDS, IMAGE, LASER, CUSTOM, and FIB.

Functions
---------
active_fib_applications(microscope: tbt.Microscope) -> list
    Retrieve a list of all active FIB (Focused Ion Beam) application files from the microscope.

active_beam_with_settings(microscope: tbt.Microscope) -> tbt.Beam
    Retrieve the current active beam and its settings from the microscope to create a beam object.

active_detector_settings(microscope: tbt.Microscope) -> tbt.Detector
    Retrieve the current active detector settings from the microscope to create a detector object.

active_image_settings(microscope: tbt.Microscope) -> tbt.ImageSettings
    Retrieve the current active image settings from the microscope to create an image settings object.

active_imaging_device(microscope: tbt.Microscope) -> tbt.Beam
    Determine the active imaging device and return the corresponding internal beam type object with null beam settings.

active_scan_settings(microscope: tbt.Microscope) -> tbt.Scan
    Retrieve the current active scan settings from the microscope to create a scan object.

active_stage_position_settings(microscope: tbt.Microscope) -> tbt.StagePositionUser
    Retrieve the current stage position in the raw coordinate system and user units [mm, deg].

active_laser_state() -> tbt.LaserState
    Retrieve the current state of the laser, including various properties that can be quickly read.

active_laser_settings(microscope: tbt.Microscope) -> tbt.LaserSettings
    Retrieve the current active laser settings from the microscope to create a laser settings object.

available_detector_types(microscope: tbt.Microscope) -> List[str]
    Retrieve the available detector types on the current microscope.

available_detector_modes(microscope: tbt.Microscope) -> List[str]
    Retrieve the available detector modes on the current microscope.

beam_object_type(type: tbt.BeamType) -> tbt.Beam
    Retrieve the beam object type based on the given beam type.

stage_limits(microscope: tbt.Microscope) -> tbt.StageLimits
    Retrieve the stage limits from the current microscope connection.

beam_limits(selected_beam: property, beam_type: tbt.BeamType) -> tbt.BeamLimits
    Retrieve the beam limits for the selected beam and beam type.

general(general_db: dict, yml_format: tbt.YMLFormatVersion) -> tbt.GeneralSettings
    Convert a general settings dictionary to a built-in type and perform schema checking.

laser_box_pattern(settings: dict) -> tbt.LaserBoxPattern
    Convert a dictionary of laser box pattern settings to a `LaserBoxPattern` object.

laser_line_pattern(settings: dict) -> tbt.LaserLinePattern
    Convert a dictionary of laser line pattern settings to a `LaserLinePattern` object.

laser(microscope: tbt.Microscope, step_settings: dict, step_name: str, yml_format: tbt.YMLFormatVersion) -> tbt.LaserSettings
    Convert a laser step from a .yml file to microscope settings for performing laser milling.

image(microscope: tbt.Microscope, step_settings: dict, step_name: str, yml_format: tbt.YMLFormatVersion) -> tbt.ImageSettings
    Convert an image step from a .yml file to microscope settings for capturing an image.

fib(microscope: tbt.Microscope, step_settings: dict, step_name: str, yml_format: tbt.YMLFormatVersion) -> tbt.FIBSettings
    Convert a FIB step from a .yml file to microscope settings for performing a FIB operation.

enforce_beam_type(beam_type, step_settings: dict, step_name: str, yml_format: tbt.YMLFormatVersion) -> bool
    Enforce a specific beam type is used for an operation based on a dictionary.

ebsd(microscope: tbt.Microscope, step_settings: dict, step_name: str, yml_format: tbt.YMLFormatVersion) -> tbt.EBSDSettings
    Convert an EBSD step from a .yml file to microscope settings for performing an EBSD operation.

eds(microscope: tbt.Microscope, step_settings: dict, step_name: str, yml_format: tbt.YMLFormatVersion) -> tbt.EDSSettings
    Convert an EDS step from a .yml file to microscope settings for performing an EDS operation.

custom(microscope: tbt.Microscope, step_settings: dict, step_name: str, yml_format: tbt.YMLFormatVersion) -> tbt.CustomSettings
    Convert a custom step from a .yml file to custom settings for the microscope.

scan_limits(selected_beam: property) -> tbt.ScanLimits
    Retrieve the scan settings limits for the selected beam.

string_to_res(input: str) -> tbt.Resolution
    Convert a string in the format "{{width}}x{{height}}" to a resolution object.

valid_string_resolution(string_resolution: str) -> bool
    Validate a string resolution.

validate_auto_cb_settings(settings: dict, yml_format: tbt.YMLFormatVersion, step_name: str) -> bool
    Perform schema checking for auto contrast/brightness setting dictionary.

validate_stage_position(microscope: tbt.Microscope, step_name: str, settings: dict, yml_format: tbt.YMLFormatVersion) -> bool
    Perform schema checking for stage position dictionary.

validate_beam_settings(microscope: tbt.Microscope, beam_type: tbt.BeamType, settings: dict, yml_format: tbt.YMLFormatVersion, step_name: str) -> bool
    Perform schema checking for beam setting dictionary.

validate_detector_settings(microscope: tbt.Microscope, beam_type: tbt.BeamType, settings: dict, yml_format: tbt.YMLFormatVersion, step_name: str) -> bool
    Perform schema checking for detector setting dictionary.

validate_EBSD_EDS_settings(yml_format: tbt.YMLFormatVersion, ebsd_oem: str, eds_oem: str, edax_settings: dict) -> bool
    Check EBSD and EDS OEM and connection for supported OEMs.

validate_general_settings(settings: dict, yml_format: tbt.YMLFormatVersion) -> bool
    Perform schema checking for general setting dictionary.

validate_scan_settings(microscope: tbt.Microscope, beam_type: tbt.BeamType, settings: dict, yml_format: tbt.YMLFormatVersion, step_name: str) -> bool
    Perform schema checking for scan setting dictionary.

stage_position_settings(microscope: tbt.Microscope, step_name: str, general_settings: tbt.GeneralSettings, step_stage_settings: dict, yml_format: tbt.YMLFormatVersion) -> tbt.StageSettings
    Create a StagePositionUser object from settings, including validation.

validate_pulse_settings(settings: dict, yml_format: tbt.YMLFormatVersion, step_name: str) -> bool
    Perform schema checking for pulse setting dictionary.

validate_laser_optics_settings(settings: dict, yml_format: tbt.YMLFormatVersion, step_name: str) -> bool
    Perform schema checking for laser optics setting dictionary.

validate_laser_box_settings(settings: dict, yml_format: tbt.YMLFormatVersion, step_name: str) -> bool
    Perform schema checking for laser box pattern setting dictionary.

validate_laser_line_settings(settings: dict, yml_format: tbt.YMLFormatVersion, step_name: str) -> bool
    Perform schema checking for laser line pattern setting dictionary.

validate_laser_mode_settings(settings: dict, yml_format: tbt.YMLFormatVersion, step_name: str) -> bool
    Perform schema checking for laser mode setting dictionary.

validate_laser_pattern_settings(settings: dict, yml_format: tbt.YMLFormatVersion, step_name: str) -> tbt.LaserPatternType
    Perform schema checking for laser pattern setting dictionary.

validate_fib_pattern_settings(microscope: tbt.Microscope, settings: dict, yml_format: tbt.YMLFormatVersion, step_name: str) -> Union[tbt.FIBRectanglePattern, tbt.FIBRegularCrossSection, tbt.FIBCleaningCrossSection, tbt.FIBStreamPattern]
    Perform schema checking for FIB pattern setting dictionary.

validate_fib_box_settings(settings: dict, yml_format: tbt.YMLFormatVersion, step_name: str, pattern_type: tbt.FIBPatternType) -> bool
    Perform schema checking for FIB box pattern setting dictionary.

validate_fib_selected_area_settings(settings: dict, yml_format: tbt.YMLFormatVersion, step_name: str, pattern_type: tbt.FIBPatternType) -> bool
    Perform schema checking for FIB selected area pattern setting dictionary.

step(microscope: tbt.Microscope, step_name: str, step_settings: dict, general_settings: tbt.GeneralSettings, yml_format: tbt.YMLFormatVersion) -> tbt.Step
    Create a step object for different step types, including validation.
"""
## python standard libraries
from pathlib import Path
import platform
import time
from typing import NamedTuple, List, Union
import warnings
from functools import singledispatch
import math


# 3rd party libraries
import pytest
from schema import And, Or, Schema, SchemaError
import jsonschema

# Local
import pytribeam.insertable_devices as devices
import pytribeam.image as img
import pytribeam.utilities as ut
import pytribeam.stage as stage
from pytribeam.constants import Conversions, Constants
from pytribeam.fib import application_files

try:
    import pytribeam.laser as fs_laser
except:
    pass
import pytribeam.types as tbt


def active_fib_applications(
    microscope: tbt.Microscope,
) -> list:
    """
    Retrieve a list of all active FIB (Focused Ion Beam) patterning application files from the microscope.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object from which to retrieve the application files.

    Returns
    -------
    list
        A list of active FIB patterning application files.
    """
    return microscope.patterning.list_all_application_files()


def active_beam_with_settings(
    microscope: tbt.Microscope,
) -> tbt.Beam:
    """
    Retrieve the current active beam and its settings from the microscope to create a beam object.

    This function grabs the current beam and its settings on the microscope to make a beam object. These settings fully depend on the currently active beam as determined by xTUI. Tolerance values for voltage and current are auto-populated as a ratio of current values predetermined in the `Constants` class.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object from which to retrieve the active beam and its settings.

    Returns
    -------
    tbt.Beam
        The active beam object with its settings.
    """
    selected_beam = active_imaging_device(microscope=microscope)
    beam = ut.beam_type(selected_beam, microscope)

    voltage_kv = round(beam.high_voltage.value * Conversions.V_TO_KV, 6)
    voltage_tol_kv = round(voltage_kv * Constants.voltage_tol_ratio, 6)

    current_na = round(beam.beam_current.value * Conversions.A_TO_NA, 6)
    current_tol_na = round(current_na * Constants.current_tol_ratio, 6)

    hfw_mm = round(beam.horizontal_field_width.value * Conversions.M_TO_MM, 6)

    working_dist_mm = round(beam.working_distance.value * Conversions.M_TO_MM, 6)

    active_settings = tbt.BeamSettings(
        voltage_kv=voltage_kv,
        current_na=current_na,
        hfw_mm=hfw_mm,
        working_dist_mm=working_dist_mm,
        voltage_tol_kv=voltage_tol_kv,
        current_tol_na=current_tol_na,
    )

    return type(selected_beam)(settings=active_settings)


def active_detector_settings(
    microscope: tbt.Microscope,
) -> tbt.Detector:
    """
    Retrieve the current active detector settings from the microscope to create a detector object.

    This function grabs the current detector settings on the microscope to make a detector object. These settings fully depend on the currently active detector as determined by xTUI.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object from which to retrieve the active detector settings.

    Returns
    -------
    tbt.Detector
        The active detector object with its settings.
    """

    detector_type = microscope.detector.type.value
    detector_mode = microscope.detector.mode.value
    brightness = microscope.detector.brightness.value
    contrast = microscope.detector.contrast.value
    auto_cb_settings = tbt.ScanArea(
        left=None,
        top=None,
        width=None,
        height=None,
    )
    custom_settings = None

    active_detector = tbt.Detector(
        type=detector_type,
        mode=detector_mode,
        brightness=brightness,
        contrast=contrast,
        auto_cb_settings=auto_cb_settings,
        custom_settings=custom_settings,
    )

    return active_detector


def active_image_settings(microscope: tbt.Microscope) -> tbt.ImageSettings:
    """
    Retrieve the current active image settings from the microscope to create an image settings object.

    This function grabs the current beam, detector, and scan settings on the microscope to make an image settings object. The bit depth is set to the default color depth defined in the `Constants` class.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object from which to retrieve the active image settings.

    Returns
    -------
    tbt.ImageSettings
        The active image settings object.
    """
    beam = active_beam_with_settings(microscope=microscope)
    detector = active_detector_settings(microscope=microscope)
    scan = active_scan_settings(microscope=microscope)
    bit_depth = Constants.default_color_depth

    active_image_settings = tbt.ImageSettings(
        microscope=microscope,
        beam=beam,
        detector=detector,
        scan=scan,
        bit_depth=bit_depth,
    )

    return active_image_settings


def active_imaging_device(microscope: tbt.Microscope) -> tbt.Beam:
    """
    Determine the active imaging device and return the corresponding internal beam type object with null beam settings.

    This function identifies the currently active imaging device on the microscope and returns the appropriate beam type object (electron or ion) with null beam settings.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object from which to determine the active imaging device.

    Returns
    -------
    tbt.Beam
        The active beam object with null beam settings.

    Raises
    ------
    ValueError
        If the currently selected device is neither an electron beam nor an ion beam.
    """
    curr_device = tbt.Device(microscope.imaging.get_active_device())
    if curr_device == tbt.Device.ELECTRON_BEAM:
        selected_beam = beam_object_type(type=tbt.BeamType.ELECTRON)(
            settings=tbt.BeamSettings()
        )
    elif curr_device == tbt.Device.ION_BEAM:
        selected_beam = beam_object_type(type=tbt.BeamType.ION)(
            settings=tbt.BeamSettings()
        )
    else:
        raise ValueError(
            f"Currently selected device {curr_device}, make sure a quadrant in xTUI with either an Electron beam or Ion beam active is selected."
        )
    return selected_beam


def active_scan_settings(
    microscope: tbt.Microscope,
) -> tbt.Scan:
    """
    Retrieve the current active scan settings from the microscope to create a scan object.

    This function grabs the current scan settings on the microscope to make a scan object. These settings fully depend on the currently active scan settings as determined by xTUI.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object from which to retrieve the active scan settings.

    Returns
    -------
    tbt.Scan
        The active scan object with its settings.
    """
    selected_beam = active_imaging_device(microscope=microscope)
    beam = ut.beam_type(selected_beam, microscope)

    rotation_deg = beam.scanning.rotation.value * Conversions.RAD_TO_DEG
    dwell_time_us = beam.scanning.dwell_time.value * Conversions.S_TO_US
    current_res = beam.scanning.resolution.value
    res = string_to_res(current_res)
    resolution = tbt.PresetResolution(res)

    active_scan = tbt.Scan(
        rotation_deg=rotation_deg,
        dwell_time_us=dwell_time_us,
        resolution=resolution,
        # mode=mode,
    )

    return active_scan


def active_stage_position_settings(microscope: tbt.Microscope) -> tbt.StagePositionUser:
    """
    Retrieve the current stage position in the raw coordinate system and user units [mm, deg].

    This function sets the stage coordinate system to RAW, retrieves the current stage position in encoder units (meters and radians), converts it to user units (millimeters and degrees), and ensures the r-axis is within the axis limit.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object from which to retrieve the current stage position.

    Returns
    -------
    tbt.StagePositionUser
        The current stage position in user units [mm, deg].
    """
    stage.coordinate_system(microscope=microscope, mode=tbt.StageCoordinateSystem.RAW)
    # encoder positions (pos) are in meters and radians
    direct_encoder_pos = microscope.specimen.stage.current_position
    x_m, y_m, z_m = direct_encoder_pos.x, direct_encoder_pos.y, direct_encoder_pos.z
    r_rad, t_rad = direct_encoder_pos.r, direct_encoder_pos.t
    coord_system_str = direct_encoder_pos.coordinate_system

    encoder_pos = tbt.StagePositionEncoder(
        x=x_m, y=y_m, z=z_m, r=r_rad, t=t_rad, coordinate_system=coord_system_str
    )
    user_pos = stage.encoder_to_user_position(encoder_pos)

    # ensure r-axis is kept in axis limit
    if not ut.in_interval(
        val=user_pos.r_deg,
        limit=Constants.rotation_axis_limit_deg,
        type=tbt.IntervalType.RIGHT_OPEN,
    ):
        # used as right-open internal: 180.0 is not valid and should be converted to -180.0
        while user_pos.r_deg >= Constants.rotation_axis_limit_deg.max:
            new_r_deg = user_pos.r_deg - 360.0
        while user_pos.r_deg < Constants.rotation_axis_limit_deg.min:
            new_r_deg = user_pos.r_deg + 360.0
        new_r_deg = round(new_r_deg, 6)
        user_pos = tbt.StagePositionUser(
            x_mm=user_pos.x_mm,
            y_mm=user_pos.y_mm,
            z_mm=user_pos.z_mm,
            r_deg=new_r_deg,
            t_deg=user_pos.t_deg,
        )

    return user_pos


def active_laser_state() -> tbt.LaserState:
    """
    Retrieve the current state of the laser, including various properties that can be quickly read.

    This function returns a dictionary object for all properties that can be quickly read from the laser (not exhaustive). Power can be read but has its own method and is more involved. Flipper configuration can only be set, not read.

    Returns
    -------
    tbt.LaserState
        The current state of the laser, including wavelength, frequency, pulse divider, pulse energy, objective position, beam shift, pattern, and expected pattern duration.

    Raises
    ------
    KeyError
        If an unsupported LaserPatternType is encountered.
    """
    vals = fs_laser.tfs_laser.Laser_ReadValues()
    vals["objective_position_mm"] = fs_laser.tfs_laser.LIP_GetZPosition()
    vals["beam_shift_um_x"] = fs_laser.tfs_laser.BeamShift_Get_X()
    vals["beam_shift_um_y"] = fs_laser.tfs_laser.BeamShift_Get_Y()
    vals["shutter_state"] = fs_laser.tfs_laser.Shutter_GetState()
    vals["pattern"] = fs_laser.tfs_laser.Patterning_ReadValues()
    vals["expected_pattern_duration_s"] = (
        fs_laser.tfs_laser.Patterning_GetExpectedDuration()
    )

    pattern_db = vals["pattern"]
    pattern_type = pattern_db["patternType"].lower()
    if not ut.valid_enum_entry(pattern_type, tbt.LaserPatternType):
        raise KeyError(
            f"Unsupported LaserPatternType of {pattern_type}, supported types include: {[i.value for i in tbt.LaserPatternType]}"
        )
    pattern_type = tbt.LaserPatternType(pattern_type)
    mode = tbt.LaserPatternMode(pattern_db["patterningMode"].lower())
    if mode == tbt.LaserPatternMode.COARSE:
        pixel_dwell_ms = pattern_db["dwellTime"]
        pulses_per_pixel = None
    elif mode == tbt.LaserPatternMode.FINE:
        pixel_dwell_ms = None
        pulses_per_pixel = pattern_db["pulsesPerPixel"]
    rotation_deg = pattern_db["patternRotation_deg"]

    if pattern_type == tbt.LaserPatternType.BOX:
        geometry = tbt.LaserBoxPattern(
            passes=pattern_db["passes"],
            size_x_um=pattern_db["xSize_um"],
            size_y_um=pattern_db["ySize_um"],
            pitch_x_um=pattern_db["xPitch_um"],
            pitch_y_um=pattern_db["yPitch_um"],
            scan_type=tbt.LaserScanType(pattern_db["scanningMode"].lower()),
            coordinate_ref=tbt.CoordinateReference(
                pattern_db["coordReference"].lower()
            ),
        )
    if pattern_type == tbt.LaserPatternType.LINE:
        geometry = tbt.LaserLinePattern(
            passes=pattern_db["passes"],
            size_um=pattern_db["xSize_um"],
            pitch_um=pattern_db["xPitch_um"],
            scan_type=tbt.LaserScanType(pattern_db["scanningMode"].lower()),
        )

    pattern = tbt.LaserPattern(
        mode=mode,
        rotation_deg=rotation_deg,
        geometry=geometry,
        pulses_per_pixel=pulses_per_pixel,
        pixel_dwell_ms=pixel_dwell_ms,
    )

    state = tbt.LaserState(
        wavelength_nm=vals["wavelength_nm"],
        frequency_khz=vals["frequency_kHz"],
        pulse_divider=vals["pulse_divider"],
        pulse_energy_uj=vals["pulse_energy_uJ"],
        objective_position_mm=vals["objective_position_mm"],
        beam_shift_um=tbt.Point(x=vals["beam_shift_um_x"], y=vals["beam_shift_um_y"]),
        pattern=pattern,
        expected_pattern_duration_s=vals["expected_pattern_duration_s"],
    )

    return state


def active_laser_settings(microscope: tbt.Microscope) -> tbt.LaserSettings:
    """
    Retrieve the current active laser settings from the microscope to create a laser settings object.

    This function grabs the current laser state and uses it to create a laser settings object. Some values cannot be read by Laser Control and can only be set. For example, polarization will default to "Vertical" as this value cannot be read.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object from which to retrieve the active laser settings.

    Returns
    -------
    tbt.LaserSettings
        The active laser settings object.
    """
    state = active_laser_state()

    settings = tbt.LaserSettings(
        microscope=microscope,
        pulse=tbt.LaserPulse(
            wavelength_nm=state.wavelength_nm,
            divider=state.pulse_divider,
            energy_uj=state.pulse_energy_uj,
            polarization=tbt.LaserPolarization.VERTICAL,  # TODO, can't read this, can only set it
        ),
        objective_position_mm=state.objective_position_mm,
        beam_shift_um=state.beam_shift_um,
        pattern=state.pattern,
    )

    return settings


def available_detector_types(microscope: tbt.Microscope) -> List[str]:
    """
    Retrieve the available detector types on the current microscope.

    This function returns a list of available detector types on the current microscope.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object from which to retrieve the available detector types.

    Returns
    -------
    List[str]
        A list of available detector types.
    """
    detectors = microscope.detector.type.available_values
    # available = [tbt.DetectorType(i) for i in detectors]
    return detectors


def available_detector_modes(microscope: tbt.Microscope) -> List[str]:
    """
    Retrieve the available detector modes on the current microscope.

    This function returns a list of available detector modes on the current microscope.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object from which to retrieve the available detector modes.

    Returns
    -------
    List[str]
        A list of available detector modes.
    """
    modes = microscope.detector.mode.available_values
    # available = [tbt.DetectorType(i) for i in modes]
    return modes


def beam_object_type(type: tbt.BeamType) -> tbt.Beam:
    """
    Retrieve the beam object type based on the given beam type.

    This function returns the appropriate beam object type (electron or ion) based on the provided beam type.

    Parameters
    ----------
    type : tbt.BeamType
        The type of the beam (electron or ion).

    Returns
    -------
    tbt.Beam
        The corresponding beam object type.

    Raises
    ------
    NotImplementedError
        If the provided beam type is unsupported.
    """
    if type.value == "electron":
        return tbt.ElectronBeam
    if type.value == "ion":
        return tbt.IonBeam
    raise NotImplementedError(f"Unsupported beam type {type.value}")


def stage_limits(microscope: tbt.Microscope) -> tbt.StageLimits:
    """
    Retrieve the stage limits from the current microscope connection.

    This function retrieves the stage limits for the X, Y, Z, R, and T axes from the current microscope connection and returns them as a `StageLimits` object.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object from which to retrieve the stage limits.

    Returns
    -------
    tbt.StageLimits
        The stage limits for the X, Y, Z, R, and T axes in user units (mm and degrees).
    """
    stage.coordinate_system(microscope=microscope)
    # x position
    min_x_mm = (
        microscope.specimen.stage.get_axis_limits(tbt.StageAxis.X).min
        * Conversions.M_TO_MM
    )
    max_x_mm = (
        microscope.specimen.stage.get_axis_limits(tbt.StageAxis.X).max
        * Conversions.M_TO_MM
    )
    # y position
    min_y_mm = (
        microscope.specimen.stage.get_axis_limits(tbt.StageAxis.Y).min
        * Conversions.M_TO_MM
    )
    max_y_mm = (
        microscope.specimen.stage.get_axis_limits(tbt.StageAxis.Y).max
        * Conversions.M_TO_MM
    )
    # z position
    min_z_mm = (
        microscope.specimen.stage.get_axis_limits(tbt.StageAxis.Z).min
        * Conversions.M_TO_MM
    )
    max_z_mm = (
        microscope.specimen.stage.get_axis_limits(tbt.StageAxis.Z).max
        * Conversions.M_TO_MM
    )
    # r position
    min_r_deg = Constants.rotation_axis_limit_deg.min
    max_r_deg = Constants.rotation_axis_limit_deg.max
    # t position
    min_t_deg = (
        microscope.specimen.stage.get_axis_limits(tbt.StageAxis.T).min
        * Conversions.RAD_TO_DEG
    )
    max_t_deg = (
        microscope.specimen.stage.get_axis_limits(tbt.StageAxis.T).max
        * Conversions.RAD_TO_DEG
    )

    return tbt.StageLimits(
        x_mm=tbt.Limit(min=min_x_mm, max=max_x_mm),
        y_mm=tbt.Limit(min=min_y_mm, max=max_y_mm),
        z_mm=tbt.Limit(min=min_z_mm, max=max_z_mm),
        r_deg=tbt.Limit(min=min_r_deg, max=max_r_deg),
        t_deg=tbt.Limit(min=min_t_deg, max=max_t_deg),
    )


def beam_limits(
    selected_beam: property,
    beam_type: tbt.BeamType,
) -> tbt.BeamLimits:
    """
    Retrieve the beam limits for the selected beam and beam type.

    This function retrieves the limits for voltage, current, horizontal field width (HFW), and working distance for the selected beam and beam type, and returns them as a `BeamLimits` object.

    Parameters
    ----------
    selected_beam : property
        The selected beam property from which to retrieve the limits.
    beam_type : tbt.BeamType
        The type of the beam (electron or ion).

    Returns
    -------
    tbt.BeamLimits
        The beam limits for voltage, current, HFW, and working distance in user units (kV, nA, mm).

    Raises
    ------
    ValueError
        If the beam type is unsupported.
    """
    # voltage range
    min_kv = selected_beam.high_voltage.limits.min * Conversions.V_TO_KV
    max_kv = selected_beam.high_voltage.limits.max * Conversions.V_TO_KV

    # current range
    if beam_type == tbt.BeamType.ELECTRON:
        min_na = selected_beam.beam_current.limits.min * Conversions.A_TO_NA
        max_na = selected_beam.beam_current.limits.max * Conversions.A_TO_NA
    if beam_type == tbt.BeamType.ION:
        available_currents = selected_beam.beam_current.available_values
        min_na = min(available_currents) * Conversions.A_TO_NA
        max_na = max(available_currents) * Conversions.A_TO_NA

    # hfw range
    min_hfw_mm = selected_beam.horizontal_field_width.limits.min * Conversions.M_TO_MM
    max_hfw_mm = selected_beam.horizontal_field_width.limits.max * Conversions.M_TO_MM

    # working_dist range
    min_wd_mm = selected_beam.working_distance.limits.min * Conversions.M_TO_MM
    max_wd_mm = selected_beam.working_distance.limits.max * Conversions.M_TO_MM

    return tbt.BeamLimits(
        voltage_kv=tbt.Limit(min=min_kv, max=max_kv),
        current_na=tbt.Limit(min=min_na, max=max_na),
        hfw_mm=tbt.Limit(min=min_hfw_mm, max=max_hfw_mm),
        working_distance_mm=tbt.Limit(min=min_wd_mm, max=max_wd_mm),
    )


def general(
    general_db: dict,
    yml_format: tbt.YMLFormatVersion,
) -> tbt.GeneralSettings:
    """
    Convert a general settings dictionary to a built-in type and perform schema checking.

    This function converts a general settings dictionary from a .yml file to a `GeneralSettings` object. It performs schema checking to ensure valid inputs are requested.

    Parameters
    ----------
    general_db : dict
        The general settings dictionary from the .yml file.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.

    Returns
    -------
    tbt.GeneralSettings
        The general settings object.

    Raises
    ------
    NotImplementedError
        If the provided yml format is unsupported.
    """

    if not yml_format in tbt.YMLFormatVersion:
        raise NotImplementedError(
            """Due to the complexity and number of variables, 
        image objects should only be constructed using a yml file."""
        )
    if not isinstance(yml_format, tbt.YMLFormatVersion):
        raise NotImplementedError(f"Unsupported yml format of {yml_format}.")

    validate_general_settings(
        settings=general_db,
        yml_format=yml_format,
    )

    if yml_format.version >= 1.0:
        # slice thickness
        slice_thickness_um = general_db["slice_thickness_um"]
        # max slice number
        max_slice_number = general_db["max_slice_num"]
        # pre tilt
        pre_tilt_deg = general_db["pre_tilt_deg"]
        # sectioning axis
        sectioning_axis = tbt.SectioningAxis(general_db["sectioning_axis"])
        # stage tolerance
        stage_tolerance = tbt.StageTolerance(
            translational_um=general_db["stage_translational_tol_um"],
            angular_deg=general_db["stage_angular_tol_deg"],
        )
        # connection
        connection = tbt.MicroscopeConnection(
            general_db["connection_host"], general_db["connection_port"]
        )
        # EBSD OEM
        ebsd_oem = tbt.ExternalDeviceOEM(general_db["EBSD_OEM"])
        # EDS OEM
        eds_oem = tbt.ExternalDeviceOEM(general_db["EDS_OEM"])
        # exp dir
        exp_dir = general_db["exp_dir"]
        # h5 log name
        h5_log_name = general_db["h5_log_name"]
        # remove log file extension if the user provided it
        log_extension = Constants.logfile_extension
        if h5_log_name.endswith(log_extension):
            h5_log_name = h5_log_name[: -len(log_extension)]
        # step count
        step_count = general_db["step_count"]
        EDAX_settings = None
        yml_version = 1.0

    if yml_format.version >= 1.1:
        edax_db = general_db["EDAX_settings"]
        EDAX_settings = tbt.EDAXConfig(
            save_directory=edax_db["save_directory"],
            project_name=edax_db["project_name"],
            connection=tbt.MicroscopeConnection(
                host=edax_db["connection"]["host"],
                port=edax_db["connection"]["port"],
            ),
        )
        yml_version = 1.1

    general_settings = tbt.GeneralSettings(
        yml_version=yml_version,
        slice_thickness_um=slice_thickness_um,
        max_slice_number=max_slice_number,
        pre_tilt_deg=pre_tilt_deg,
        sectioning_axis=sectioning_axis,
        stage_tolerance=stage_tolerance,
        connection=connection,
        EBSD_OEM=ebsd_oem,
        EDS_OEM=eds_oem,
        exp_dir=Path(exp_dir),
        h5_log_name=h5_log_name,
        EDAX_settings=EDAX_settings,
        step_count=step_count,
    )

    return general_settings


def laser_box_pattern(settings: dict) -> tbt.LaserBoxPattern:
    """
    Convert a dictionary of laser box pattern settings to a `LaserBoxPattern` object.

    This function takes a dictionary of laser box pattern settings and converts it to a `LaserBoxPattern` object.

    Parameters
    ----------
    settings : dict
        The dictionary containing laser box pattern settings.

    Returns
    -------
    tbt.LaserBoxPattern
        The laser box pattern object.
    """
    return tbt.LaserBoxPattern(
        passes=settings["passes"],
        size_x_um=settings["size_x_um"],
        size_y_um=settings["size_y_um"],
        pitch_x_um=settings["pitch_x_um"],
        pitch_y_um=settings["pitch_y_um"],
        scan_type=tbt.LaserScanType(settings["scan_type"]),
        coordinate_ref=tbt.CoordinateReference(settings["coordinate_ref"]),
    )


def laser_line_pattern(settings: dict) -> tbt.LaserBoxPattern:
    """
    Convert a dictionary of laser line pattern settings to a `LaserLinePattern` object.

    This function takes a dictionary of laser line pattern settings and converts it to a `LaserLinePattern` object.

    Parameters
    ----------
    settings : dict
        The dictionary containing laser line pattern settings.

    Returns
    -------
    tbt.LaserLinePattern
        The laser line pattern object.
    """
    return tbt.LaserLinePattern(
        passes=settings["passes"],
        size_um=settings["size_um"],
        pitch_um=settings["pitch_um"],
        scan_type=tbt.LaserScanType(settings["scan_type"]),
    )


def laser(
    microscope: tbt.Microscope,
    step_settings: dict,
    step_name: str,
    yml_format: tbt.YMLFormatVersion,
) -> tbt.LaserSettings:
    """
    Convert a laser step from a .yml file to microscope settings for performing laser milling.

    This function converts a laser step from a .yml file to `LaserSettings` for the microscope. It performs schema checking to ensure valid inputs are requested.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to set the laser settings.
    step_settings : dict
        The dictionary containing the laser step settings from the .yml file.
    step_name : str
        The name of the step in the .yml file.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.

    Returns
    -------
    tbt.LaserSettings
        The laser settings object.

    Raises
    ------
    KeyError
        If required settings are missing from the .yml file.
    """
    if yml_format.version >= 1.0:
        # pulse settings
        pulse_set_db = step_settings.get("pulse")
        if pulse_set_db is None:
            raise KeyError(
                f"Invalid .yml file, no 'pulse' settings found in 'laser' step_type for step '{step_name}'."
            )
        # laser optics settings
        optics_set_db = {
            "objective_position_mm": step_settings.get("objective_position_mm"),
            "beam_shift_um_x": step_settings.get("beam_shift").get("x_um"),
            "beam_shift_um_y": step_settings.get("beam_shift").get("y_um"),
        }
        # pattern settings
        pattern_set_db = step_settings.get("pattern")
        if pattern_set_db is None:
            raise KeyError(
                f"Invalid .yml file, no 'pattern' settings found in 'laser' step_type for step '{step_name}'."
            )
        line_pattern_db = pattern_set_db.get("type").get("line")
        box_pattern_db = pattern_set_db.get("type").get("box")

    validate_pulse_settings(
        settings=pulse_set_db,
        yml_format=yml_format,
        step_name=step_name,
    )
    pulse = tbt.LaserPulse(
        wavelength_nm=tbt.LaserWavelength(pulse_set_db["wavelength_nm"]),
        divider=pulse_set_db["divider"],
        energy_uj=pulse_set_db["energy_uj"],
        polarization=tbt.LaserPolarization(pulse_set_db["polarization"]),
    )

    validate_laser_optics_settings(
        settings=optics_set_db,
        yml_format=yml_format,
        step_name=step_name,
    )

    pattern_type = validate_laser_pattern_settings(
        settings=pattern_set_db,
        yml_format=yml_format,
        step_name=step_name,
    )
    if pattern_type == tbt.LaserPatternType.BOX:
        geometry = laser_box_pattern(box_pattern_db)
    if pattern_type == tbt.LaserPatternType.LINE:
        geometry = laser_line_pattern(line_pattern_db)
    pattern = tbt.LaserPattern(
        mode=tbt.LaserPatternMode(pattern_set_db["mode"]),
        rotation_deg=pattern_set_db["rotation_deg"],
        pulses_per_pixel=pattern_set_db["pulses_per_pixel"],
        pixel_dwell_ms=pattern_set_db["pixel_dwell_ms"],
        geometry=geometry,
    )

    laser_settings = tbt.LaserSettings(
        microscope=microscope,
        pulse=pulse,
        objective_position_mm=optics_set_db["objective_position_mm"],
        beam_shift_um=tbt.Point(
            x=optics_set_db["beam_shift_um_x"],
            y=optics_set_db["beam_shift_um_y"],
        ),
        pattern=pattern,
    )

    return laser_settings


def image(
    microscope: tbt.Microscope,
    step_settings: dict,
    step_name: str,
    yml_format: tbt.YMLFormatVersion,
) -> tbt.ImageSettings:
    """
    Convert an image step from a .yml file to microscope settings for capturing an image.

    This function converts an image step from a .yml file to `ImageSettings` for the microscope. It performs schema checking to ensure valid inputs are requested.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to set the image settings.
    step_settings : dict
        The dictionary containing the image step settings from the .yml file.
    step_name : str
        The name of the step in the .yml file.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.

    Returns
    -------
    tbt.ImageSettings
        The image settings object.

    Raises
    ------
    KeyError
        If required settings are missing from the .yml file.
    NotImplementedError
        If the provided beam type is unsupported.
    ValueError
        If invalid scan rotation is requested with dynamic focus or tilt correction, or if the bit depth is unsupported.
    """
    if yml_format.version >= 1.0:
        step_general = step_settings.get(yml_format.step_general_key)
        if step_general is None:
            raise KeyError(
                f"Invalid .yml file, no 'step_general' settings found in step '{step_name}'."
            )
        step_type = step_general.get(yml_format.step_type_key)
        if step_type is None:
            raise KeyError(
                f"Invalid .yml file, no 'step_type' settings found in step '{step_name}'."
            )
        # beam settings
        beam_set_db = step_settings.get("beam")
        if beam_set_db is None:
            raise KeyError(
                f"Invalid .yml file, no 'beam' settings found in '{step_type}' step_type for step '{step_name}'."
            )
        beam_type_value = beam_set_db.get("type")
        if not ut.valid_enum_entry(beam_type_value, tbt.BeamType):
            raise NotImplementedError(
                f"Unsupported beam type of '{beam_type_value}', supported beam types are: {[i.value for i in tbt.BeamType]}."
            )
        beam_type = tbt.BeamType(beam_set_db.get("type"))

        # detector settings
        detector_set_db = step_settings.get("detector")
        if detector_set_db is None:
            raise KeyError(
                f"Invalid .yml file, no 'detector' settings found in '{step_type}' step_type for step '{step_name}'."
            )
        auto_cb_set_db = detector_set_db.get("auto_cb")

        # scan settings
        scan_set_db = step_settings.get("scan")
        if scan_set_db is None:
            raise KeyError(
                f"Invalid .yml file, no 'scan' settings found in '{step_type}' step_type for step '{step_name}'."
            )
        scan_res = string_to_res(scan_set_db.get("resolution"))

        # misc settings
        bit_depth = step_settings.get("bit_depth")

    # TODO incorporate tile settings
    if yml_format.version >= 1.1:
        # tile settings
        tile_set_db = step_settings.get("tile_settings")

    validate_beam_settings(
        microscope=microscope,
        beam_type=beam_type,
        settings=beam_set_db,
        yml_format=yml_format,
        step_name=step_name,
    )
    beam_settings = tbt.BeamSettings(
        voltage_kv=beam_set_db["voltage_kv"],
        voltage_tol_kv=beam_set_db["voltage_tol_kv"],
        current_na=beam_set_db["current_na"],
        current_tol_na=beam_set_db["current_tol_na"],
        hfw_mm=beam_set_db["hfw_mm"],
        working_dist_mm=beam_set_db["working_dist_mm"],
        dynamic_focus=beam_set_db["dynamic_focus"],
        tilt_correction=beam_set_db["tilt_correction"],
    )

    validate_auto_cb_settings(
        settings=auto_cb_set_db,
        yml_format=yml_format,
        step_name=step_name,
    )
    auto_cb_settings = tbt.ScanArea(
        left=auto_cb_set_db["left"],
        top=auto_cb_set_db["top"],
        width=auto_cb_set_db["width"],
        height=auto_cb_set_db["height"],
    )

    validate_detector_settings(
        microscope=microscope,
        beam_type=beam_type,
        settings=detector_set_db,
        yml_format=yml_format,
        step_name=step_name,
    )
    detector_settings = tbt.Detector(
        type=tbt.DetectorType(detector_set_db["type"]),
        mode=tbt.DetectorMode(detector_set_db["mode"]),
        brightness=detector_set_db["brightness"],
        contrast=detector_set_db["contrast"],
        auto_cb_settings=auto_cb_settings,
        # custom_settings=None,
    )

    validate_scan_settings(
        microscope=microscope,
        beam_type=beam_type,
        settings=scan_set_db,
        yml_format=yml_format,
        step_name=step_name,
    )

    # cast resolution to preset if applicable
    if ut.valid_enum_entry(obj=scan_res, check_type=tbt.PresetResolution):
        scan_res = tbt.PresetResolution(scan_res)

    scan_settings = tbt.Scan(
        rotation_deg=scan_set_db["rotation_deg"],
        dwell_time_us=scan_set_db["dwell_time_us"],
        resolution=scan_res,
        # mode=tbt.ScanMode(scan_set_db["mode"]),
    )

    # make sure Scan rotation is 0 if dynamic focus or tilt correction is on (using auto mode only for angular correction)
    if beam_settings.dynamic_focus or beam_settings.tilt_correction:
        if not math.isclose(a=scan_settings.rotation_deg, b=0.0):
            raise ValueError(
                f"Invalid .yml for step '{step_name}'. Scan rotation of '{scan_settings.rotation_deg}' degrees requested with tilt_correction and/or dynamic focus set to 'True'. Cannot use dynamic focus or tilt correction for non-zero scan rotation."
            )

    # validate bit_depth
    if not ut.valid_enum_entry(bit_depth, tbt.ColorDepth):
        valid_bit_depths = [i.value for i in tbt.ColorDepth]
        raise ValueError(
            f"Unsupported bit depth of {bit_depth}, available depths are {valid_bit_depths}"
        )

    image_settings = tbt.ImageSettings(
        microscope=microscope,
        beam=beam_object_type(beam_type)(settings=beam_settings),
        detector=detector_settings,
        scan=scan_settings,
        bit_depth=bit_depth,
    )

    return image_settings


def fib(
    microscope: tbt.Microscope,
    step_settings: dict,
    step_name: str,
    yml_format: tbt.YMLFormatVersion,
) -> tbt.FIBSettings:
    """
    Convert a FIB step from a .yml file to microscope settings for performing a FIB operation.

    This function converts a FIB step from a .yml file to `FIBSettings` for the microscope. It performs schema checking to ensure valid inputs are requested.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to set the FIB settings.
    step_settings : dict
        The dictionary containing the FIB step settings from the .yml file.
    step_name : str
        The name of the step in the .yml file.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.

    Returns
    -------
    tbt.FIBSettings
        The FIB settings object.

    Raises
    ------
    KeyError
        If required settings are missing from the .yml file.
    ValueError
        If invalid beam type is requested.
    """
    ## create image_step_settings from this
    if yml_format.version >= 1.0:
        image_step_settings = step_settings.get("image")
        image_step_settings["step_general"] = step_settings.get("step_general")

        mill_step_settings = step_settings.get("mill")
        mill_beam_db = mill_step_settings.get("beam")
        mill_pattern_db = mill_step_settings.get("pattern")

    # ensure image is with an ion beam
    enforce_beam_type(
        tbt.IonBeam(settings=None),
        step_settings=image_step_settings,
        step_name=step_name,
        yml_format=yml_format,
    )
    image_settings = image(
        microscope=microscope,
        step_settings=image_step_settings,
        step_name=step_name,
        yml_format=yml_format,
    )

    ## fib mill settings
    # ensure milling is with an ion beam
    enforce_beam_type(
        tbt.IonBeam(settings=None),
        step_settings=mill_step_settings,
        step_name=step_name,
        yml_format=yml_format,
    )
    beam_type = tbt.BeamType(mill_beam_db.get("type"))
    # mill beam
    validate_beam_settings(
        microscope=microscope,
        beam_type=beam_type,
        settings=mill_beam_db,
        yml_format=yml_format,
        step_name=step_name,
    )
    mill_beam = tbt.IonBeam(
        settings=tbt.BeamSettings(
            voltage_kv=mill_beam_db["voltage_kv"],
            voltage_tol_kv=mill_beam_db["voltage_tol_kv"],
            current_na=mill_beam_db["current_na"],
            current_tol_na=mill_beam_db["current_tol_na"],
            hfw_mm=mill_beam_db["hfw_mm"],
            working_dist_mm=mill_beam_db["working_dist_mm"],
            dynamic_focus=mill_beam_db["dynamic_focus"],
            tilt_correction=mill_beam_db["tilt_correction"],
        )
    )

    # fib pattern settings
    pattern = validate_fib_pattern_settings(
        microscope=microscope,
        settings=mill_pattern_db,
        yml_format=yml_format,
        step_name=step_name,
    )

    fib_settings = tbt.FIBSettings(
        microscope=microscope,
        image=image_settings,
        mill_beam=mill_beam,
        pattern=pattern,
    )
    return fib_settings


@singledispatch
def enforce_beam_type(
    beam_type,
    step_settings: dict,
    step_name: str,
    yml_format: tbt.YMLFormatVersion,
) -> bool:
    """
    Enforce a specific beam type is used for an operation based on a dictionary.

    This function ensures that the specified beam type is used for an operation based on the provided settings dictionary. The dictionary must contain a sub-dictionary with the key 'beam'.

    Parameters
    ----------
    beam_type : Any
        The beam type to enforce.
    step_settings : dict
        The dictionary containing the step settings.
    step_name : str
        The name of the step in the .yml file.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.

    Returns
    -------
    bool
        True if the beam type is enforced successfully.

    Raises
    ------
    NotImplementedError
        If no handler is available for the provided type.
    """
    _ = beam_type
    __ = step_settings
    ___ = step_name
    ____ = yml_format
    raise NotImplementedError(f"No handler for type {type(step_settings)}")


@enforce_beam_type.register
def _(
    beam_type: tbt.ElectronBeam,
    step_settings: dict,
    step_name: str,
    yml_format: tbt.YMLFormatVersion,
) -> bool:
    """
    Enforce that an electron beam is used for an operation based on a dictionary.

    This function ensures that an electron beam is used for an operation based on the provided settings dictionary.

    Parameters
    ----------
    beam_type : tbt.ElectronBeam
        The electron beam type to enforce.
    step_settings : dict
        The dictionary containing the step settings.
    step_name : str
        The name of the step in the .yml file.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.

    Returns
    -------
    bool
        True if the electron beam type is enforced successfully.

    Raises
    ------
    KeyError
        If the 'beam' settings are missing from the .yml file.
    NotImplementedError
        If the beam type is unsupported or not an electron beam.
    """
    # beam must be electron
    if yml_format.version >= 1.0:
        beam_set_db = step_settings.get("beam")
        if beam_set_db is None:
            raise KeyError(
                f"Invalid .yml file, no 'beam' settings found in step '{step_name}'."
            )
        beam_type_value = beam_set_db.get("type")

        electron_beam_error_message = f"Unsupported beam type of '{beam_type_value}' in step '{step_name}'. '{tbt.BeamType.ELECTRON.value}' beam type must be used."
        if not ut.valid_enum_entry(beam_type_value, tbt.BeamType):
            raise NotImplementedError(electron_beam_error_message)
        if not tbt.BeamType(beam_type_value) == tbt.BeamType.ELECTRON:
            raise NotImplementedError(electron_beam_error_message)


@enforce_beam_type.register
def _(
    beam_type: tbt.IonBeam,
    step_settings: dict,
    step_name: str,
    yml_format: tbt.YMLFormatVersion,
) -> bool:
    """
    Enforce that an ion beam is used for an operation based on a dictionary.

    This function ensures that an ion beam is used for an operation based on the provided settings dictionary.

    Parameters
    ----------
    beam_type : tbt.IonBeam
        The ion beam type to enforce.
    step_settings : dict
        The dictionary containing the step settings.
    step_name : str
        The name of the step in the .yml file.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.

    Returns
    -------
    bool
        True if the ion beam type is enforced successfully.

    Raises
    ------
    KeyError
        If the 'beam' settings are missing from the .yml file.
    NotImplementedError
        If the beam type is unsupported or not an ion beam.
    """
    # beam must be ion
    if yml_format.version >= 1.0:
        beam_set_db = step_settings.get("beam")
        if beam_set_db is None:
            raise KeyError(
                f"Invalid .yml file, no 'beam' settings found in step '{step_name}'."
            )
        beam_type_value = beam_set_db.get("type")

        ion_beam_error_message = f"Unsupported beam type of '{beam_type_value}' for step '{step_name}'. '{tbt.BeamType.ION.value}' beam type must be used."
        if not ut.valid_enum_entry(beam_type_value, tbt.BeamType):
            raise NotImplementedError(ion_beam_error_message)
        if not tbt.BeamType(beam_type_value) == tbt.BeamType.ION:
            raise NotImplementedError(ion_beam_error_message)


def ebsd(
    microscope: tbt.Microscope,
    step_settings: dict,
    step_name: str,
    yml_format: tbt.YMLFormatVersion,
) -> tbt.EBSDSettings:
    """
    Convert an EBSD step from a .yml file to microscope settings for performing an EBSD operation.

    This function converts an EBSD step from a .yml file to `EBSDSettings` for the microscope. It performs schema checking to ensure valid inputs are requested.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to set the EBSD settings.
    step_settings : dict
        The dictionary containing the EBSD step settings from the .yml file.
    step_name : str
        The name of the step in the .yml file.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.

    Returns
    -------
    tbt.EBSDSettings
        The EBSD settings object.

    Raises
    ------
    KeyError
        If required settings are missing from the .yml file or if the 'concurrent_EDS' key is invalid.
    """
    enforce_beam_type(
        tbt.ElectronBeam(settings=None),
        step_settings=step_settings,
        step_name=step_name,
        yml_format=yml_format,
    )
    image_settings = image(
        microscope=microscope,
        step_settings=step_settings,
        step_name=step_name,
        yml_format=yml_format,
    )
    concurrent_EDS = step_settings.get("concurrent_EDS")
    if (concurrent_EDS is None) or (not concurrent_EDS):
        enable_eds = False
    elif concurrent_EDS == True:
        enable_eds = True
    else:
        raise KeyError(
            f"Invalid .yml file, for step '{step_name}', an EBSD type step. 'concurrent_EDS' key is '{concurrent_EDS}' of type {type(concurrent_EDS)} but must be boolean (True/False) or of NoneType (null in .yml)."
        )

    # TODO validate and check
    if yml_format.version >= 1.0:
        scan_box = None
        grid_type = None
        save_patterns = None
    if yml_format.version >= 1.1:
        edax_settings = step_settings.get("edax_settings")
        scan_db = edax_settings.get("scan_box")
        # We use brackets instead of parentheses here since grid type is the name not the value
        grid_type = tbt.EBSDGridType[edax_settings.get("grid_type")]
        save_patterns = edax_settings.get("save_patterns")
        x_start_um = scan_db.get("x_start_um")
        y_start_um = scan_db.get("y_start_um")
        x_size_um = scan_db.get("x_size_um")
        y_size_um = scan_db.get("y_size_um")
        step_size_um = scan_db.get("step_size_um")
        scan_box = tbt.EBSDScanBox(
            x_start_um=x_start_um,
            y_start_um=y_start_um,
            x_size_um=x_size_um,
            y_size_um=y_size_um,
            step_size_um=step_size_um,
        )
    ebsd_settings = tbt.EBSDSettings(
        image=image_settings,
        enable_eds=enable_eds,
        enable_ebsd=True,
        scan_box=scan_box,
        grid_type=grid_type,
        save_patterns=save_patterns,
    )
    return ebsd_settings


def eds(
    microscope: tbt.Microscope,
    step_settings: dict,
    step_name: str,
    yml_format: tbt.YMLFormatVersion,
) -> tbt.EDSSettings:
    """
    Convert an EDS step from a .yml file to microscope settings for performing an EDS operation.

    This function converts an EDS step from a .yml file to `EDSSettings` for the microscope. It performs schema checking to ensure valid inputs are requested.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to set the EDS settings.
    step_settings : dict
        The dictionary containing the EDS step settings from the .yml file.
    step_name : str
        The name of the step in the .yml file.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.

    Returns
    -------
    tbt.EDSSettings
        The EDS settings object.
    """
    enforce_beam_type(
        tbt.ElectronBeam(settings=None),
        step_settings=step_settings,
        step_name=step_name,
        yml_format=yml_format,
    )
    image_settings = image(
        microscope=microscope,
        step_settings=step_settings,
        step_name=step_name,
        yml_format=yml_format,
    )
    eds_settings = tbt.EDSSettings(
        image=image_settings,
        enable_eds=True,
    )
    return eds_settings


def custom(
    microscope: tbt.Microscope,
    step_settings: dict,
    step_name: str,
    yml_format: tbt.YMLFormatVersion,
) -> tbt.CustomSettings:
    """
    Convert a custom step from a .yml file to custom settings for the microscope.

    This function converts a custom step from a .yml file to `CustomSettings` for the microscope. It performs schema checking to ensure valid inputs are requested.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to set the custom settings.
    step_settings : dict
        The dictionary containing the custom step settings from the .yml file.
    step_name : str
        The name of the step in the .yml file.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.

    Returns
    -------
    tbt.CustomSettings
        The custom settings object.

    Raises
    ------
    KeyError
        If required settings are missing from the .yml file.
    ValueError
        If the specified script or executable path does not exist.
    """
    if yml_format.version >= 1.0:
        script_path = step_settings.get("script_path")
        if script_path is None:
            raise KeyError(
                f"Invalid .yml file, no 'script_path' found in custom step_type for step '{step_name}'."
            )
        if not Path(script_path).is_file():
            raise ValueError(
                f"Invalid location for script at location {script_path}. File does not exist."
            )

        executable_path = step_settings.get("executable_path")
        if executable_path is None:
            raise KeyError(
                f"Invalid .yml file, no 'executable_path' found in custom step_type for step '{step_name}'."
            )
        if not Path(executable_path).is_file():
            raise ValueError(
                f"Invalid location for executable at location {executable_path}. File does not exist."
            )

    custom_settings = tbt.CustomSettings(
        script_path=Path(script_path),
        executable_path=Path(executable_path),
    )
    return custom_settings


# def fib_pattern_type(
#     settings: tbt.FIBSettings,
# ) -> Union[tbt.FIBBoxPattern, tbt.FIBStreamPattern]:
#     """Returns specific pattern type settings for a properly formatted FIBSettings object"""


def scan_limits(
    selected_beam: property,
) -> tbt.ScanLimits:
    """
    Retrieve the scan settings limits for the selected beam.

    This function retrieves the limits for rotation and dwell time for the selected beam and returns them as a `ScanLimits` object.

    Parameters
    ----------
    selected_beam : property
        The selected beam property from which to retrieve the scan limits.

    Returns
    -------
    tbt.ScanLimits
        The scan limits for rotation (degrees) and dwell time (microseconds).
    """
    # rotation
    min_deg = selected_beam.scanning.rotation.limits.min * Conversions.RAD_TO_DEG
    max_deg = selected_beam.scanning.rotation.limits.max * Conversions.RAD_TO_DEG
    # dwell_time
    min_dwell_us = selected_beam.scanning.dwell_time.limits.min * Conversions.S_TO_US
    max_dwell_us = selected_beam.scanning.dwell_time.limits.max * Conversions.S_TO_US

    return tbt.ScanLimits(
        rotation_deg=tbt.Limit(min=min_deg, max=max_deg),
        dwell_us=tbt.Limit(min=min_dwell_us, max=max_dwell_us),
    )


def string_to_res(input: str) -> tbt.Resolution:
    """
    Convert a string in the format "{{width}}x{{height}}" to a resolution object.

    This function takes a string representing the resolution in the format "WIDTHxHEIGHT" and converts it to a `Resolution` object.

    Parameters
    ----------
    input : str
        The string representing the resolution in the format "WIDTHxHEIGHT".

    Returns
    -------
    tbt.Resolution
        The resolution object.

    Raises
    ------
    ValueError
        If the input string is not in the expected format.
    """
    try:
        split_res = (input.lower()).split("x")
        width, height = int(split_res[0]), int(split_res[1])
    except:
        raise ValueError(
            f"""Invalid string format, 
                            expected string format of "WIDTHxHEIGHT", 
                            but received the following: "{input}"."""
        )

    return tbt.Resolution(width=width, height=height)


def valid_string_resolution(string_resolution: str) -> bool:
    """
    Validate a string resolution.

    This function validates a string resolution by converting it to a `Resolution` object and checking if the width and height are within the specified limits.

    Parameters
    ----------
    string_resolution : str
        The string representing the resolution in the format "WIDTHxHEIGHT".

    Returns
    -------
    bool
        True if the resolution is valid, False otherwise.
    """
    res = string_to_res(string_resolution)
    width, height = res.width, res.height
    return (
        ut.in_interval(
            width,
            limit=Constants.scan_resolution_limit,
            type=tbt.IntervalType.CLOSED,
        )
    ) and (
        ut.in_interval(
            height,
            limit=Constants.scan_resolution_limit,
            type=tbt.IntervalType.CLOSED,
        )
    )


def validate_auto_cb_settings(
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
    step_name: str,
) -> bool:
    """
    Perform schema checking for auto contrast/brightness setting dictionary.

    This function validates the auto contrast/brightness settings dictionary based on the specified yml format.

    Parameters
    ----------
    settings : dict
        The dictionary containing the auto contrast/brightness settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.
    step_name : str
        The name of the step in the .yml file.

    Returns
    -------
    bool
        True if the settings are valid, False otherwise.

    Raises
    ------
    KeyError
        If required keys are missing from the settings dictionary.
    ValueError
        If the settings do not satisfy the specified schema.
    """

    if ut.none_value_dictionary(settings):
        return True

    if settings.get("left") is None or settings.get("top") is None:
        if settings.get("left") is None:
            missing_key = "left"
        else:
            missing_key = "top"
        raise KeyError(
            f"Missing or no value for '{missing_key}' key in 'auto_cb' sub-dictionary in step '{step_name}' All 'auto_cb' sub-dictionary values must be declared by the user to implement this capability."
        )

    origin_limit = tbt.Limit(min=0.0, max=1.0)  # reduced area limit for scan window
    width_limit = tbt.Limit(min=0.0, max=1.0 - settings["left"])
    height_limit = tbt.Limit(min=0.0, max=1.0 - settings["top"])

    if yml_format.version >= 1.0:
        schema = Schema(
            {
                "left": And(
                    float,
                    lambda x: ut.in_interval(
                        x,
                        limit=origin_limit,
                        type=tbt.IntervalType.RIGHT_OPEN,
                    ),
                    error=f"In step '{step_name}', requested auto contrast/brightness window setting 'left' of '{settings['left']}' must satisfy '0 <= left < {origin_limit.max}'. Origin is in top-left corner of the field of view.",
                ),
                "top": And(
                    float,
                    lambda x: ut.in_interval(
                        x,
                        limit=origin_limit,
                        type=tbt.IntervalType.RIGHT_OPEN,
                    ),
                    error=f"In step '{step_name}', requested auto contrast/brightness windows setting 'top' of '{settings['top']}' must satisfy '0.0 <= top < {origin_limit.max}'. Origin is in top-left corner of the field of view.",
                ),
                "width": And(
                    float,
                    lambda x: ut.in_interval(
                        x,
                        limit=width_limit,
                        type=tbt.IntervalType.LEFT_OPEN,
                    ),
                    error=f"In step '{step_name}', requested auto contrast/brightness windows setting 'width' of {settings['width']} must satisfy '0.0 < width <= {width_limit.max}' with 'left' setting of {settings['left']} as total width ('left' + 'width') cannot exceed 1.0",
                ),
                "height": And(
                    float,
                    lambda x: ut.in_interval(
                        x,
                        limit=height_limit,
                        type=tbt.IntervalType.LEFT_OPEN,
                    ),
                    error=f"In step '{step_name}', requested auto contrast/brightness windows setting 'height' of {settings['height']} must satisfy '0.0 < height <= {height_limit.max}' with 'top' setting of {settings['top']} as total height ('top' + 'height') cannot exceed 1.0",
                ),
            },
            ignore_extra_keys=True,
        )

    try:
        schema.validate(settings)
    except UnboundLocalError:
        raise ValueError(
            f"Error. Unsupported yml version {yml_format.version} provided."
        )
    return True


def validate_stage_position(
    microscope: tbt.Microscope,
    step_name: str,
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
) -> bool:
    """
    Perform schema checking for stage position dictionary.

    This function validates the stage position settings dictionary based on the specified yml format and the stage limits of the microscope.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to validate the stage position settings.
    step_name : str
        The name of the step in the .yml file.
    settings : dict
        The dictionary containing the stage position settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.

    Returns
    -------
    bool
        True if the settings are valid, False otherwise.

    Raises
    ------
    ValueError
        If the yml version is unsupported.
    """
    limits = stage_limits(microscope=microscope)

    if yml_format.version >= 1.0:
        schema = Schema(
            {
                "x_mm": And(
                    float,
                    lambda x: ut.in_interval(
                        x,
                        limit=limits.x_mm,
                        type=tbt.IntervalType.CLOSED,
                    ),
                    error=f"Requested x-axis position of {settings['x_mm']} mm for step '{step_name}' must satisfy '{limits.x_mm.min} <= x_mm <= {limits.x_mm.max}'",
                ),
                "y_mm": And(
                    float,
                    lambda x: ut.in_interval(
                        x,
                        limit=limits.y_mm,
                        type=tbt.IntervalType.CLOSED,
                    ),
                    error=f"Requested y-axis position of {settings['y_mm']} mm for step '{step_name}' must satisfy '{limits.y_mm.min} <= y_mm <= {limits.y_mm.max}'",
                ),
                "z_mm": And(
                    float,
                    lambda x: ut.in_interval(
                        x,
                        limit=limits.z_mm,
                        type=tbt.IntervalType.CLOSED,
                    ),
                    error=f"Requested z-axis position of {settings['z_mm']} mm for step '{step_name}' must satisfy '{limits.z_mm.min} <= z_mm <= {limits.z_mm.max}'",
                ),
                "r_deg": And(
                    float,
                    lambda x: ut.in_interval(
                        x,
                        limit=limits.r_deg,
                        type=tbt.IntervalType.RIGHT_OPEN,
                    ),
                    error=f"Requested r-axis position of {settings['r_deg']} degree for step '{step_name}' must satisfy '{limits.r_deg.min} <= r_deg < {limits.r_deg.max}'",
                ),
                "t_deg": And(
                    float,
                    lambda x: ut.in_interval(
                        x,
                        limit=limits.t_deg,
                        type=tbt.IntervalType.CLOSED,
                    ),
                    error=f"Requested r-axis position of {settings['t_deg']} degree for step '{step_name}' must satisfy '{limits.t_deg.min} <= t_deg <= {limits.t_deg.max}'",
                ),
            },
            ignore_extra_keys=True,
        )

    try:
        schema.validate(settings)
    except UnboundLocalError:
        raise ValueError(
            f"Error. Unsupported yml version {yml_format.version} provided."
        )


def validate_beam_settings(
    microscope: tbt.Microscope,
    beam_type: tbt.BeamType,
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
    step_name: str,
) -> bool:
    """
    Perform schema checking for beam setting dictionary.

    This function validates the beam settings dictionary based on the specified yml format and the beam limits of the microscope.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to validate the beam settings.
    beam_type : tbt.BeamType
        The type of the beam (electron or ion).
    settings : dict
        The dictionary containing the beam settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.
    step_name : str
        The name of the step in the .yml file.

    Returns
    -------
    bool
        True if the settings are valid, False otherwise.

    Raises
    ------
    ValueError
        If the yml version is unsupported or if the settings do not satisfy the specified schema.
    """
    specified_beam = beam_object_type(beam_type)(settings=tbt.BeamSettings())
    selected_beam = ut.beam_type(specified_beam, microscope)

    limits = beam_limits(selected_beam, beam_type)

    if yml_format.version >= 1.0:
        schema = Schema(
            {
                "voltage_kv": And(
                    float,
                    lambda x: ut.in_interval(
                        x,
                        limit=limits.voltage_kv,
                        type=tbt.IntervalType.CLOSED,
                    ),
                    error=f"In step '{step_name}', requested voltage of '{settings['voltage_kv']}' kV not within limits of {limits.voltage_kv.min} kV and {limits.voltage_kv.max} kV.",
                ),
                "voltage_tol_kv": And(
                    float,
                    lambda x: x > 0,
                    error=f"In step '{step_name}', requested voltage tolerance of '{settings['voltage_tol_kv']}' kV must be a positive float (greater than 0).",
                ),
                "current_na": And(
                    float,
                    lambda x: ut.in_interval(
                        x,
                        limit=limits.current_na,
                        type=tbt.IntervalType.CLOSED,
                    ),
                    error=f"In step '{step_name}', requested voltage of '{settings['current_na']}' nA not within limits of {limits.current_na.min} nA and {limits.current_na.max} nA",
                ),
                "current_tol_na": And(
                    float,
                    lambda x: x > 0,
                    error=f"In step '{step_name}', 'current_tol_na' must be a positive float (greater than 0)",
                ),
                "hfw_mm": And(
                    float,
                    lambda x: ut.in_interval(
                        x,
                        limits.hfw_mm,
                        type=tbt.IntervalType.CLOSED,
                    ),
                    error=f"In step '{step_name}', requested horizontal field width of '{settings['hfw_mm']}' mm not within limits of {limits.hfw_mm.min} mm and {limits.hfw_mm.max} mm",
                ),
                "working_dist_mm": And(
                    float,
                    lambda x: ut.in_interval(
                        x,
                        limit=limits.working_distance_mm,
                        type=tbt.IntervalType.CLOSED,
                    ),
                    error=f"In step '{step_name}', requested working distance of '{settings['working_dist_mm']}' mm not within limits of {limits.working_distance_mm.min} mm and {limits.working_distance_mm.max} mm",
                ),
            },
            ignore_extra_keys=True,
        )

        e_beam_schema = Schema(
            {
                "dynamic_focus": Or(
                    None,
                    bool,
                    error=f"In step '{step_name}' with 'electron' beam imaging, 'dynamic_focus' must be a boolean value but '{settings['dynamic_focus']}' of type {type(settings['dynamic_focus'])} was requested.",
                ),
                "tilt_correction": Or(
                    None,
                    bool,
                    error=f"In step '{step_name}' with 'electron' beam imaging, 'tilt_correction' must be a boolean value but '{settings['tilt_correction']}' of type {type(settings['tilt_correction'])} was requested.",
                ),
            },
            ignore_extra_keys=True,
        )
        i_beam_schema = Schema(
            {
                "dynamic_focus": Or(
                    None,
                    False,
                    error=f"In step '{step_name}' with 'ion' beam imaging, 'dynamic_focus' must be 'False' or 'None' but '{settings['dynamic_focus']}' of type {type(settings['dynamic_focus'])} was requested.",
                ),
                "tilt_correction": Or(
                    None,
                    False,
                    error=f"In step '{step_name}' with 'ion' beam imaging, 'tilt_correction' must be 'False' or 'None' but '{settings['tilt_correction']}' of type {type(settings['tilt_correction'])} was requested.",
                ),
            },
            ignore_extra_keys=True,
        )

    try:
        schema.validate(settings)
        if specified_beam.type == tbt.BeamType.ELECTRON:
            e_beam_schema.validate(settings)
        if specified_beam.type == tbt.BeamType.ION:
            i_beam_schema.validate(settings)
    except UnboundLocalError:
        raise ValueError(
            f"Error. Unsupported yml version {yml_format.version} provided."
        )


def validate_detector_settings(
    microscope: tbt.Microscope,
    beam_type: tbt.BeamType,
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
    step_name: str,
) -> bool:
    """
    Perform schema checking for detector setting dictionary.

    This function validates the detector settings dictionary based on the specified yml format and the detector capabilities of the microscope.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to validate the detector settings.
    beam_type : tbt.BeamType
        The type of the beam (electron or ion).
    settings : dict
        The dictionary containing the detector settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.
    step_name : str
        The name of the step in the .yml file.

    Returns
    -------
    bool
        True if the settings are valid, False otherwise.

    Raises
    ------
    KeyError
        If auto contrast/brightness settings conflict with fixed brightness/contrast values.
    ValueError
        If the yml version is unsupported, or if the settings do not satisfy the specified schema, or if the detector type or mode is unsupported.
    """

    # switch to top left quad, enable e-beam
    devices.device_access(microscope=microscope)

    # set specified beam to active imaging device
    specified_beam = beam_object_type(beam_type)(settings=tbt.BeamSettings())
    img.set_beam_device(
        microscope=microscope,
        device=specified_beam.device,
    )

    auto_cb_db = settings.get("auto_cb")
    use_auto_cb = not ut.none_value_dictionary(settings.get("auto_cb"))
    if use_auto_cb and (
        settings.get("brightness") is not None or settings.get("contrast") is not None
    ):
        raise KeyError(
            f"Auto contrast/brightness settings of {auto_cb_db} provided while settings of fixed brightness of '{settings.get('brightness')}' and fixed contrast of '{settings.get('contrast')}' were also provided. Users may use either fixed brightness/contrast values or auto contrast/brightness settings, but not both."
        )

    if yml_format.version >= 1.0:
        detector = settings.get("type")
        mode = settings.get("mode")
        cb_limit = tbt.Limit(min=0.0, max=1.0)
        schema = Schema(
            {
                "brightness": Or(
                    None,
                    And(
                        float,
                        lambda x: ut.in_interval(
                            x,
                            limit=cb_limit,
                            type=tbt.IntervalType.LEFT_OPEN,
                        ),
                    ),
                    error=f"In step '{step_name}', requested fixed brightness of '{settings['brightness']}'. This is not within limits of '>{cb_limit.min}' and '<={cb_limit.max}'.",
                ),
                "contrast": Or(
                    None,
                    And(
                        float,
                        lambda x: ut.in_interval(
                            x,
                            limit=cb_limit,
                            type=tbt.IntervalType.LEFT_OPEN,
                        ),
                    ),
                    error=f"In step '{step_name}', requested fixed contrast of '{settings['contrast']}'. This is either not within limits of '>{cb_limit.min}' and '<={cb_limit.max}'.",
                ),
            },
            ignore_extra_keys=True,
        )

    # check detector type
    if not ut.valid_enum_entry(detector, tbt.DetectorType):
        raise ValueError(
            f"Unsupported detector type of '{detector}' on step '{step_name}'."
        )
    detector_type = tbt.DetectorType(detector)
    microscope_detector_types = available_detector_types(microscope=microscope)
    if detector_type.value not in microscope_detector_types:
        raise ValueError(
            f"Requested detector of {detector_type.value} is unavailable on this tool. Available detectors are: {microscope_detector_types}"
        )
    # make sure to set this detector as the active one to access modes
    img.detector_type(
        microscope=microscope,
        detector=detector_type,
    )

    # check detector mode
    if not ut.valid_enum_entry(mode, tbt.DetectorMode):
        raise ValueError(
            f'Unsupported detector mode of "{mode}" for "{detector}" detector'
        )
    detector_mode = tbt.DetectorMode(mode)
    microscope_detector_modes = available_detector_modes(microscope=microscope)
    if detector_mode.value not in microscope_detector_modes:
        raise ValueError(
            f"Requested mode of {detector_mode.value} for {detector_type.value} detector is invalid. Valid mode types are: {microscope_detector_modes}"
        )

    # check detector settings
    try:
        schema.validate(settings)
    except UnboundLocalError:
        raise ValueError(
            f"Error. Unsupported yml version {yml_format.version} provided."
        )


def validate_EBSD_EDS_settings(
    yml_format: tbt.YMLFormatVersion,
    ebsd_oem: str,
    eds_oem: str,
    edax_settings: dict = None,
) -> bool:
    """
    Check EBSD and EDS OEM and connection for supported OEMs.

    This function ensures that the specified EBSD and EDS OEMs are supported and that the connection settings are valid.

    Parameters
    ----------
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.
    connection_host : str
        The host for the microscope connection.
    connection_port : str
        The port for the microscope connection.
    ebsd_oem : str
        The OEM for the EBSD device.
    eds_oem : str
        The OEM for the EDS device.

    Returns
    -------
    bool
        True if the settings are valid, False otherwise.

    Raises
    ------
    NotImplementedError
        If differing EBSD and EDS OEMs are requested.
    ValueError
        If the EBSD or EDS OEM is unsupported.
    SystemError
        If the Laser API is not accessible.
    """
    # ensure same manufacturer for both EBSD and EDS
    if (ebsd_oem is not None) and (eds_oem is not None) and (ebsd_oem != eds_oem):
        raise NotImplementedError(
            f"Differing EBSD and EDS OEMs are not supported. Requested EBSD OEM of '{ebsd_oem}' and EDS OEM of '{eds_oem}'."
        )

    # Check EBSD OEM
    if not ut.valid_enum_entry(ebsd_oem, tbt.ExternalDeviceOEM):
        raise ValueError(
            f"Unsupported EBSD OEM of '{ebsd_oem}'. Supported OEM types are: {[i.value for i in tbt.ExternalDeviceOEM]}"
        )
    ebsd_device = tbt.ExternalDeviceOEM(ebsd_oem)
    # Check EDS OEM
    if not ut.valid_enum_entry(eds_oem, tbt.ExternalDeviceOEM):
        raise ValueError(
            f"Unsupported EDS OEM of '{eds_oem}'. Supported OEM types are: {[i.value for i in tbt.ExternalDeviceOEM]}"
        )
    eds_device = tbt.ExternalDeviceOEM(eds_oem)

    # exit if both devices are none, no need for laser control
    if ebsd_device == eds_device == tbt.ExternalDeviceOEM.NONE:
        return True

    # check EBSD and EDS connection
    try:
        fs_laser.tfs_laser
    except:
        raise SystemError(
            "EBSD and/or EDS control requested, but Laser API not accessible, so cannot use EBSD and EDS control. Please restart Laser API, or if not installed, change OEM to 'null', or leave blank in settings file."
        )

    ###################### PROPOSED CHANGE ######################
    # Retracting devices here is unnecessary
    # This causes devices to retract during validation
    # Device retraction is needed only when startin/ending experiments
    # Both of which are outside the scope of validation and already handled elsewhere
    ###################### PROPOSED CHANGE ######################
    # microscope = tbt.Microscope()
    # ut.connect_microscope(
    #     microscope=microscope,
    #     quiet_output=True,
    #     connection_host=connection_host,
    #     connection_port=connection_port,
    # )
    # if tbt.ExternalDeviceOEM(eds_oem) != tbt.ExternalDeviceOEM.NONE:
    #     devices.retract_EDS(microscope=microscope)
    # if tbt.ExternalDeviceOEM(ebsd_oem) != tbt.ExternalDeviceOEM.NONE:
    #     devices.retract_EBSD(microscope=microscope)
    # ut.disconnect_microscope(
    #     microscope=microscope,
    #     quiet_output=True,
    # )

    if edax_settings is not None:
        schema = Schema(
            {
                "save_directory": And(
                    str,
                    error=f"Requested 'save_directory' of '{edax_settings['save_directory']}', which must be a string.",
                ),
                "project_name": And(
                    str,
                    error=f'Requested "project_name" of "{edax_settings["project_name"]}", which must be a string.',
                ),
            },
            ignore_extra_keys=True,
        )

        try:
            schema.validate(edax_settings)
        except UnboundLocalError:
            raise ValueError(
                f"Error. Unsupported yml version {yml_format.version} provided."
            )

        connection_db = edax_settings["connection"]
        schema_connection = Schema(
            {
                "host": And(
                    str,
                    error=f'Requested "host" of "{connection_db["host"]}", which must be a string.',
                ),
                "port": And(
                    int,
                    error=f'Requested "port" of "{connection_db["port"]}", which must be an int.',
                ),
            }
        )
        try:
            schema_connection.validate(connection_db)
        except UnboundLocalError:
            raise ValueError(
                f"Error. Unsupported yml version {yml_format.version} provided."
            )

        connection = fs_laser.connect_EDAX(
            ebsd_host=edax_settings["connection"]["host"],
            ebsd_port=edax_settings["connection"]["port"],
        )
        fs_laser.disconnect_EDAX(connection=connection)

    return True


def validate_general_settings(
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
) -> bool:
    """
    Perform schema checking for general setting dictionary.

    This function validates the general settings dictionary based on the specified yml format. It checks the microscope connection and EBSD/EDS connection if valid OEMs are specified.

    Parameters
    ----------
    settings : dict
        The dictionary containing the general settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.

    Returns
    -------
    bool
        True if the settings are valid, False otherwise.

    Raises
    ------
    ValueError
        If the general settings dictionary is empty, or if the settings do not satisfy the specified schema, or if the connection is invalid.
    NotImplementedError
        If the sectioning axis is unsupported.
    """

    if settings == {}:
        raise ValueError("General settings dictionary is empty.")

    slice_thickness_limit_um = Constants.slice_thickness_limit_um
    pre_tilt_limit_deg = Constants.pre_tilt_limit_deg_generic

    if yml_format.version >= 1.0:
        sectioning_axis = settings.get("sectioning_axis")
        connection_host = settings.get("connection_host")
        connection_port = settings.get("connection_port")
        ebsd_oem = settings.get("EBSD_OEM")
        eds_oem = settings.get("EDS_OEM")
        exp_dir = settings.get("exp_dir")
        h5_log_name = settings.get("h5_log_name")
        edax_settings = None
    if yml_format.version >= 1.1:
        edax_settings = settings.get("EDAX_settings")

    # Validate the non-numeric values
    # Check sectioning axis
    if not ut.valid_enum_entry(sectioning_axis, tbt.SectioningAxis):
        raise ValueError(f"Unsupported sectioning axis of {sectioning_axis}.")
    # TODO
    if tbt.SectioningAxis(sectioning_axis) != tbt.SectioningAxis.Z:
        raise NotImplementedError("Currently only Z-axis sectioning is supported.")
    if tbt.SectioningAxis(sectioning_axis) != tbt.SectioningAxis.Z:
        pre_tilt_limit_deg = Constants.pre_tilt_limit_deg_non_Z_sectioning  # overwrite
        warnings.warn(
            "Pre-tilt value must be zero (0.0) degrees when using a sectioning axis other than 'Z'"
        )
    # Check connection host and port
    if not ut.valid_microscope_connection(
        host=connection_host,
        port=connection_port,
    ):
        raise ValueError(
            f"Unsupported connection with host of {connection_host} and port of {connection_port}."
        )

    # check EBSD and EDS
    validate_EBSD_EDS_settings(
        yml_format=yml_format,
        ebsd_oem=ebsd_oem,
        eds_oem=eds_oem,
        edax_settings=edax_settings,
    )

    # Check exp dir
    try:
        Path(exp_dir).mkdir(
            parents=True,
            exist_ok=True,
        )
    except TypeError:
        raise ValueError(
            f'Requested experimental directory of "{exp_dir}", which is not a valid path.'
        )
    # Check h5 log name
    if not isinstance(h5_log_name, str):
        raise ValueError(f'Unsupported h5 log name of "{h5_log_name}"')

    schema = Schema(
        {
            "slice_thickness_um": And(
                float,
                lambda x: ut.in_interval(
                    x,
                    limit=slice_thickness_limit_um,
                    type=tbt.IntervalType.CLOSED,
                ),
                error=f"Requested slice thickness of {settings['slice_thickness_um']} um must satisfy '{slice_thickness_limit_um.min} <= slice_thickness_um <= {slice_thickness_limit_um.max}'",
            ),
            "max_slice_num": And(
                int,
                lambda x: x > 0,
                error=f"Requested max slice number of {settings['max_slice_num']} must satisfy '0 < max_slice_number'",
            ),
            "pre_tilt_deg": And(
                float,
                lambda x: ut.in_interval(
                    x,
                    limit=pre_tilt_limit_deg,
                    type=tbt.IntervalType.CLOSED,
                ),
                error=f"Requested pre tilt of {settings['pre_tilt_deg']} degrees must satisfy '{pre_tilt_limit_deg.min} <= pre_tilt_deg <= {pre_tilt_limit_deg.max}'",
            ),
            "stage_translational_tol_um": And(
                float,
                lambda x: x > 0,
                error=f"Requested stage translational tolerance of {settings['stage_translational_tol_um']} um must be a positive float (greater than 0)",
            ),
            "stage_angular_tol_deg": And(
                float,
                lambda x: x > 0,
                error=f"Requested stage angular tolerance of {settings['stage_angular_tol_deg']} degrees must be a positive float (greater than 0)",
            ),
            "step_count": And(
                int,
                lambda x: x > 0,
                error=f"Requested step count of {settings['step_count']} must be a positive int (greater than 0)",
            ),
        },
        ignore_extra_keys=True,
    )

    try:
        schema.validate(settings)
    except UnboundLocalError:
        raise ValueError(
            f"Error. Unsupported yml version {yml_format.version} provided."
        )


def validate_scan_settings(
    microscope: tbt.Microscope,
    beam_type: tbt.BeamType,
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
    step_name: str,
) -> bool:
    """
    Perform schema checking for scan setting dictionary.

    This function validates the scan settings dictionary based on the specified yml format and the scan limits of the microscope.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to validate the scan settings.
    beam_type : tbt.BeamType
        The type of the beam (electron or ion).
    settings : dict
        The dictionary containing the scan settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.
    step_name : str
        The name of the step in the .yml file.

    Returns
    -------
    bool
        True if the settings are valid, False otherwise.

    Raises
    ------
    ValueError
        If the yml version is unsupported or if the settings do not satisfy the specified schema.
    """
    specified_beam = beam_object_type(beam_type)(settings=tbt.BeamSettings())
    selected_beam = ut.beam_type(specified_beam, microscope)

    """Schema checking for scan setting dictionary, format specified by yml_format"""
    if yml_format.version >= 1.0:
        limits = scan_limits(selected_beam)
        resolution = settings["resolution"]
        rotation_limit = limits.rotation_deg
        dwell_limit = limits.dwell_us

    # check resolution
    res = string_to_res(resolution)

    schema = Schema(
        {
            "resolution": And(
                str,
                lambda x: valid_string_resolution(x),
                error=f"In '{step_name}', resolution provided was {settings['resolution']}, but must be an integer width and height in format '[width]x[height]'  with each dimension satisfying '{Constants.scan_resolution_limit.min} <= [value] <=  {Constants.scan_resolution_limit.max}",
            ),
            "rotation_deg": And(
                float,
                lambda x: ut.in_interval(
                    x,
                    limit=rotation_limit,
                    type=tbt.IntervalType.CLOSED,
                ),
                error=f"In '{step_name}', requested fixed rotation of '{settings['rotation_deg']}' degrees. This is not a float or not within limits of '>={rotation_limit.min}' and '<={rotation_limit.max}' degrees. Setting is of type {type(settings['rotation_deg'])}.",
            ),
            "dwell_time_us": And(
                float,
                lambda x: ut.in_interval(
                    x,
                    limit=dwell_limit,
                    type=tbt.IntervalType.CLOSED,
                ),
                error=f"In '{step_name}', requested fixed dwell_time of '{settings['dwell_time_us']}' microseconds. This is a float or not within limits of '>={dwell_limit.min}' and '<={dwell_limit.max}' microseconds. Settting is of type {type(settings['dwell_time_us'])}.",
            ),
        },
        ignore_extra_keys=True,
    )

    try:
        schema.validate(settings)
    except UnboundLocalError:
        raise ValueError(
            f"Error. Unsupported yml version {yml_format.version} provided."
        )


def stage_position_settings(
    microscope: tbt.Microscope,
    step_name: str,
    general_settings: tbt.GeneralSettings,
    step_stage_settings: dict,
    yml_format: tbt.YMLFormatVersion,
) -> tbt.StageSettings:
    """
    Create a StagePositionUser object from settings, including validation.

    This function creates a `StagePositionUser` object from the provided settings and performs validation.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to set the stage position.
    step_name : str
        The name of the step in the .yml file.
    general_settings : tbt.GeneralSettings
        The general settings object.
    step_stage_settings : dict
        The dictionary containing the stage position settings for the step.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.

    Returns
    -------
    tbt.StageSettings
        The stage settings object.

    Raises
    ------
    NotImplementedError
        If the rotation side value is unsupported.
    ValueError
        If the stage position settings do not satisfy the specified schema.
    """

    if yml_format.version >= 1.0:
        pos_db = step_stage_settings.get("initial_position")

        rotation_side = step_stage_settings["rotation_side"]
        if not ut.valid_enum_entry(rotation_side, tbt.RotationSide):
            raise NotImplementedError(
                f"Unsupported rotation_side value of '{rotation_side}' of type '{type(rotation_side)}' in step '{step_name}', supported rotation_side values are: {[i.value for i in tbt.RotationSide]}."
            )

    validate_stage_position(
        microscope=microscope,
        step_name=step_name,
        settings=pos_db,
        yml_format=yml_format,
    )

    initial_position = tbt.StagePositionUser(
        x_mm=pos_db["x_mm"],
        y_mm=pos_db["y_mm"],
        z_mm=pos_db["z_mm"],
        r_deg=pos_db["r_deg"],
        t_deg=pos_db["t_deg"],
    )

    pretilt_angle_deg = general_settings.pre_tilt_deg
    sectioning_axis = general_settings.sectioning_axis

    stage_settings = tbt.StageSettings(
        microscope=microscope,
        initial_position=initial_position,
        pretilt_angle_deg=pretilt_angle_deg,
        sectioning_axis=sectioning_axis,
        rotation_side=tbt.RotationSide(rotation_side),
        # movement_mode=tbt.StageMovementMode.OUT_OF_PLANE,
    )

    return stage_settings


def validate_pulse_settings(
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
    step_name: str,
) -> bool:
    """
    Perform schema checking for pulse setting dictionary.

    This function validates the pulse settings dictionary based on the specified yml format.

    Parameters
    ----------
    settings : dict
        The dictionary containing the pulse settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.
    step_name : str
        The name of the step in the .yml file.

    Returns
    -------
    bool
        True if the settings are valid, False otherwise.

    Raises
    ------
    NotImplementedError
        If the wavelength or polarization value is unsupported.
    ValueError
        If the yml version is unsupported or if the settings do not satisfy the specified schema.
    """
    if yml_format.version >= 1.0:
        wavelength_nm = settings.get("wavelength_nm")
        if not ut.valid_enum_entry(wavelength_nm, tbt.LaserWavelength):
            raise NotImplementedError(
                f"In 'laser' step_type for step '{step_name}', unsupported wavelength of '{wavelength_nm}' nm (data type {type(wavelength_nm)}), supported wavelengths are: {[i.value for i in tbt.LaserWavelength]}."
            )
        polarization = settings.get("polarization")
        if not ut.valid_enum_entry(polarization, tbt.LaserPolarization):
            raise NotImplementedError(
                f"In 'laser' step_type for step '{step_name}', unsupported laser polarization of '{polarization}', supported values are: {[i.value for i in tbt.LaserPolarization]}."
            )

        schema = Schema(
            {
                "divider": And(
                    int,
                    lambda x: x > 0,
                    error=f"In 'laser' step_type for step '{step_name}', 'divider' parameter must be a positive integer greater than 0 but '{settings['divider']}' was requested.",
                ),
                "energy_uj": And(
                    float,
                    lambda x: x > 0,
                    error=f"In 'laser' step_type for step '{step_name}', 'energy_uj' parameter must be a positive float greater than 0 but '{settings['energy_uj']}' was requested.",
                ),
            },
            ignore_extra_keys=True,
        )
    try:
        schema.validate(settings)
    except UnboundLocalError:
        raise ValueError(
            f"Error. Unsupported yml version {yml_format.version} provided."
        )


def validate_laser_optics_settings(
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
    step_name: str,
) -> bool:
    """
    Perform schema checking for laser optics setting dictionary.

    This function validates the laser optics settings dictionary based on the specified yml format.

    Parameters
    ----------
    settings : dict
        The dictionary containing the laser optics settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.
    step_name : str
        The name of the step in the .yml file.

    Returns
    -------
    bool
        True if the settings are valid, False otherwise.

    Raises
    ------
    ValueError
        If the yml version is unsupported or if the settings do not satisfy the specified schema.
    """
    if yml_format.version >= 1.0:
        schema = Schema(
            {
                "objective_position_mm": And(
                    float,
                    lambda x: ut.in_interval(
                        x,
                        limit=Constants.laser_objective_limit_mm,
                        type=tbt.IntervalType.CLOSED,
                    ),
                    error=f"In 'laser' step_type for step '{step_name}', 'objective_position_mm' parameter must be a float satisfying the following: {Constants.laser_objective_limit_mm.min} mm <= value <= {Constants.laser_objective_limit_mm.max} mm. '{settings['objective_position_mm']}' mm (of type {type(settings['objective_position_mm'])}) was requested.",
                ),
                "beam_shift_um_x": And(
                    float,
                    error=f"In 'laser' step_type for step '{step_name}', 'x' parameter for 'beam_shift_um' sub-dictioanry must be a float but '{settings['beam_shift_um_x']}' (of type {type(settings['beam_shift_um_x'])}) was requested.",
                ),
                "beam_shift_um_y": And(
                    float,
                    error=f"In 'laser' step_type for step '{step_name}', 'y' parameter for 'beam_shift_um' sub-dictioanry must be a float but '{settings['beam_shift_um_y']}' (of type {type(settings['beam_shift_um_y'])}) was requested.",
                ),
            },
            ignore_extra_keys=True,
        )
    try:
        schema.validate(settings)
    except UnboundLocalError:
        raise ValueError(
            f"Error. Unsupported yml version {yml_format.version} provided."
        )


def validate_laser_box_settings(
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
    step_name: str,
) -> bool:
    """
    Perform schema checking for laser box pattern setting dictionary.

    This function validates the laser box pattern settings dictionary based on the specified yml format.

    Parameters
    ----------
    settings : dict
        The dictionary containing the laser box pattern settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.
    step_name : str
        The name of the step in the .yml file.

    Returns
    -------
    bool
        True if the settings are valid, False otherwise.

    Raises
    ------
    NotImplementedError
        If the scan type or coordinate reference value is unsupported.
    ValueError
        If the yml version is unsupported or if the settings do not satisfy the specified schema.
    """
    if yml_format.version >= 1.0:
        # scan type
        scan_type = settings.get("scan_type")
        scan_types = [
            tbt.LaserScanType.RASTER,
            tbt.LaserScanType.SERPENTINE,
        ]
        scan_type_error_msg = f"In 'laser' step_type for step '{step_name}', unsupported scan type of '{scan_type}' for box pattern, supported scan types are: {[i.value for i in scan_types]}."
        if not ut.valid_enum_entry(scan_type, tbt.LaserScanType):
            raise NotImplementedError(scan_type_error_msg)
        if tbt.LaserScanType(scan_type) not in scan_types:
            raise NotImplementedError(scan_type_error_msg)

        # coordinate reference
        coordinate_ref = settings.get("coordinate_ref")
        coord_refs = [
            tbt.CoordinateReference.CENTER,
            tbt.CoordinateReference.UPPER_CENTER,
            tbt.CoordinateReference.UPPER_LEFT,
        ]
        coord_error_msg = f"In 'laser' step_type for step '{step_name}', unsupported coordinate reference of '{coordinate_ref}' for box pattern, supported coordinate references are: {[i.value for i in coord_refs]}."
        if not ut.valid_enum_entry(coordinate_ref, tbt.CoordinateReference):
            raise NotImplementedError(coord_error_msg)
        if tbt.CoordinateReference(coordinate_ref) not in coord_refs:
            raise NotImplementedError(coord_error_msg)

        schema = Schema(
            {
                "passes": And(
                    int,
                    lambda x: x > 0,
                    error=f"In 'laser' step_type for step '{step_name}', 'passes' parameter in 'box' type pattern must be a positive integer. '{settings['passes']}' (of type {type(settings['passes'])}) was requested.",
                ),
                "size_x_um": And(
                    float,
                    lambda x: x > 0,
                    error=f"In 'laser' step_type for step '{step_name}', 'size_x_um' parameter in 'box' type pattern must be a positive float. '{settings['size_x_um']}' mm (of type {type(settings['size_x_um'])}) was requested.",
                ),
                "size_y_um": And(
                    float,
                    lambda x: x > 0,
                    error=f"In 'laser' step_type for step '{step_name}', 'size_y_um' parameter in 'box' type pattern must be a positive float. '{settings['size_y_um']}' mm (of type {type(settings['size_y_um'])}) was requested.",
                ),
                "pitch_x_um": And(
                    float,
                    lambda x: x > 0,
                    error=f"In 'laser' step_type for step '{step_name}', 'pitch_x_um' parameter in 'box' type pattern must be a positive float. '{settings['pitch_x_um']}' mm (of type {type(settings['pitch_x_um'])}) was requested.",
                ),
                "pitch_y_um": And(
                    float,
                    lambda x: x > 0,
                    error=f"In 'laser' step_type for step '{step_name}', 'pitch_y_um' parameter in 'box' type pattern must be a positive float. '{settings['pitch_y_um']}' mm (of type {type(settings['pitch_y_um'])}) was requested.",
                ),
            },
            ignore_extra_keys=True,
        )
    try:
        schema.validate(settings)
    except UnboundLocalError:
        raise ValueError(
            f"Error. Unsupported yml version {yml_format.version} provided."
        )


def validate_laser_line_settings(
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
    step_name: str,
) -> bool:
    """
    Perform schema checking for laser line pattern setting dictionary.

    This function validates the laser line pattern settings dictionary based on the specified yml format.

    Parameters
    ----------
    settings : dict
        The dictionary containing the laser line pattern settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.
    step_name : str
        The name of the step in the .yml file.

    Returns
    -------
    bool
        True if the settings are valid, False otherwise.

    Raises
    ------
    NotImplementedError
        If the scan type value is unsupported.
    ValueError
        If the yml version is unsupported or if the settings do not satisfy the specified schema.
    """
    if yml_format.version >= 1.0:
        # scan type
        scan_type = settings.get("scan_type")
        scan_types = [
            tbt.LaserScanType.SINGLE,
            tbt.LaserScanType.LAP,
        ]
        scan_type_error_msg = f"In 'laser' step_type for step '{step_name}', unsupported scan type of '{scan_type}' for line pattern, supported scan types are: {[i.value for i in scan_types]}."
        if not ut.valid_enum_entry(scan_type, tbt.LaserScanType):
            raise NotImplementedError(scan_type_error_msg)
        if tbt.LaserScanType(scan_type) not in scan_types:
            raise NotImplementedError(scan_type_error_msg)

        schema = Schema(
            {
                "passes": And(
                    int,
                    lambda x: x > 0,
                    error=f"In 'laser' step_type for step '{step_name}', 'passes' parameter in 'line' type pattern must be a positive integer. '{settings['passes']}' (of type {type(settings['passes'])}) was requested.",
                ),
                "size_um": And(
                    float,
                    lambda x: x > 0,
                    error=f"In 'laser' step_type for step '{step_name}', 'size_um' parameter in 'line' type pattern must be a positive float. '{settings['size_um']}' mm (of type {type(settings['size_um'])}) was requested.",
                ),
                "pitch_um": And(
                    float,
                    lambda x: x > 0,
                    error=f"In 'laser' step_type for step '{step_name}', 'pitch_um' parameter in 'line' type pattern must be a positive float. '{settings['pitch_um']}' mm (of type {type(settings['pitch_um'])}) was requested.",
                ),
            },
            ignore_extra_keys=True,
        )
    try:
        schema.validate(settings)
    except UnboundLocalError:
        raise ValueError(
            f"Error. Unsupported yml version {yml_format.version} provided."
        )


def validate_laser_mode_settings(
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
    step_name: str,
) -> bool:
    """
    Perform schema checking for laser mode setting dictionary.

    This function validates the laser mode settings dictionary based on the specified yml format.

    Parameters
    ----------
    settings : dict
        The dictionary containing the laser mode settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.
    step_name : str
        The name of the step in the .yml file.

    Returns
    -------
    bool
        True if the settings are valid, False otherwise.

    Raises
    ------
    NotImplementedError
        If the laser pattern mode value is unsupported.
    ValueError
        If the yml version is unsupported or if the settings do not satisfy the specified schema.
    """
    if yml_format.version >= 1.0:
        mode = settings.get("mode")
        if not ut.valid_enum_entry(mode, tbt.LaserPatternMode):
            raise NotImplementedError(
                f"In 'laser' step_type for step '{step_name}', unsupported laser pattern mode of '{mode}', supported values are: {[i.value for i in tbt.LaserPatternMode]}."
            )

        schema = Schema(
            {
                "rotation_deg": And(
                    float,
                    error=f"In 'laser' step_type for step '{step_name}', 'rotation_deg' parameter must be a float. '{settings['rotation_deg']}' degrees (of type {type(settings['rotation_deg'])}) was requested.",
                ),
            },
            ignore_extra_keys=True,
        )
        schema_fine = Schema(
            {
                "pixel_dwell_ms": Or(
                    None,
                    "null",
                    "None",
                    error=f"In 'laser' step_type for step '{step_name}', 'pixel_dwell_ms' parameter does not apply to the selected 'fine' milling mode. Set 'pixel_dwell_ms' to 'null' 'None' or leave the entry blank to continue.",
                ),
                "pulses_per_pixel": And(
                    int,
                    lambda x: x > 0,
                    error=f"In 'laser' step_type for step '{step_name}', 'pulses_per_pixel' parameter is required for pattern type of 'fine'. 'pulses_per_pixel' must be a positive integer greater than 0. '{settings['pulses_per_pixel']}' (of type {type(settings['pulses_per_pixel'])}) was requested.",
                ),
            },
            ignore_extra_keys=True,
        )
        schema_coarse = Schema(
            {
                "pixel_dwell_ms": And(
                    float,
                    lambda x: x > 0.0,
                    error=f"In 'laser' step_type for step '{step_name}', 'pixel_dwell_ms' parameter is required for pattern type of 'coarse'. 'pixel_dwell_ms' must be a positive float greater than 0. '{settings['pixel_dwell_ms']}' (of type {type(settings['pixel_dwell_ms'])}) was requested.",
                ),
                "pulses_per_pixel": Or(
                    None,
                    "null",
                    "None",
                    error=f"In 'laser' step_type for step '{step_name}', 'pulses_per_pixel' parameter does not apply to the selected 'coarse' milling mode. Set 'pulses_per_pixel' to 'null' 'None' or leave the entry blank to continue.",
                ),
            },
            ignore_extra_keys=True,
        )
    try:
        schema.validate(settings)
        if mode == "fine":
            schema_fine.validate(settings)
        if mode == "coarse":
            schema_coarse.validate(settings)
    except UnboundLocalError:
        raise ValueError(
            f"Error. Unsupported yml version {yml_format.version} provided."
        )


def validate_laser_pattern_settings(
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
    step_name: str,
) -> tbt.LaserPatternType:
    """
    Perform schema checking for laser pattern setting dictionary.

    This function validates the laser pattern settings dictionary based on the specified yml format and determines the type of pattern (box or line).

    Parameters
    ----------
    settings : dict
        The dictionary containing the laser pattern settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.
    step_name : str
        The name of the step in the .yml file.

    Returns
    -------
    tbt.LaserPatternType
        The type of the laser pattern (box or line).

    Raises
    ------
    KeyError
        If required settings are missing from the .yml file or if multiple pattern types are specified.
    ValueError
        If the laser pattern settings are invalid.
    """
    if yml_format.version >= 1.0:
        # determine type of pattern (only one allowed)
        type_set_db = settings.get("type")
        if type_set_db is None:
            raise KeyError(
                f"Invalid .yml file, no 'type' settings sub-dictionary found in 'pattern' settings in 'laser' step_type for step '{step_name}'."
            )

        box_settings = type_set_db.get("box")
        line_settings = type_set_db.get("line")
        if box_settings is None:
            box_pattern = False
        else:
            box_pattern = not ut.none_value_dictionary(box_settings)
        if line_settings is None:
            line_pattern = False
        else:
            line_pattern = not ut.none_value_dictionary(line_settings)
        if box_pattern == line_pattern == False:
            raise KeyError(
                f"Invalid .yml file in 'laser' step_type for step '{step_name}'. No pattern type settings found."
            )
        if box_pattern == line_pattern == True:
            raise KeyError(
                f"Invalid .yml file in 'laser' step_type for step '{step_name}'. Pattern settings for one and only one type are allowed. Type settings found for both 'box' and 'line' type. Please leave one set of type settings completely blank, enter 'null' for each parameter, or remove the unused subdictionary completely from the .yml file."
            )
        validate_laser_mode_settings(
            settings=settings,
            yml_format=yml_format,
            step_name=step_name,
        )

        if box_pattern:
            validate_laser_box_settings(
                settings=box_settings,
                yml_format=yml_format,
                step_name=step_name,
            )
            return tbt.LaserPatternType.BOX
        elif line_pattern:
            validate_laser_line_settings(
                settings=line_settings,
                yml_format=yml_format,
                step_name=step_name,
            )
            return tbt.LaserPatternType.LINE
        else:
            raise ValueError(
                f"Invalid laser pattern settings for step {step_name}. Supported types are {[i.value for i in tbt.LaserPatternType]}"
            )


def validate_fib_pattern_settings(
    microscope: tbt.Microscope,
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
    step_name: str,
) -> Union[
    tbt.FIBRectanglePattern,
    tbt.FIBRegularCrossSection,
    tbt.FIBCleaningCrossSection,
    tbt.FIBStreamPattern,
]:
    """
    Perform schema checking for FIB pattern setting dictionary.

    This function validates the FIB pattern settings dictionary based on the specified yml format and determines the type of pattern (rectangle, regular cross section, cleaning cross section, or selected area).

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to validate the FIB pattern settings.
    settings : dict
        The dictionary containing the FIB pattern settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.
    step_name : str
        The name of the step in the .yml file.

    Returns
    -------
    Union[tbt.FIBRectanglePattern, tbt.FIBRegularCrossSection, tbt.FIBCleaningCrossSection, tbt.FIBStreamPattern]
        The validated FIB pattern object.

    Raises
    ------
    KeyError
        If required settings are missing from the .yml file or if multiple pattern types are specified.
    ValueError
        If the application file is unsupported or invalid for the specified pattern type.
    """

    if yml_format.version >= 1.0:
        application_file = settings.get("application_file")
        # determine type of pattern (only one allowed)
        type_set_db = settings.get("type")
        if type_set_db is None:
            raise KeyError(
                f"Invalid .yml file, no 'type' settings sub-dictionary found in 'pattern' settings in 'fib' step_type for step '{step_name}'."
            )
        rectangle_settings = type_set_db.get("rectangle")
        regular_cross_section_settings = type_set_db.get("regular_cross_section")
        cleaning_cross_section_settings = type_set_db.get("cleaning_cross_section")
        selected_area_settings = type_set_db.get("selected_area")

        pattern_settings = [
            rectangle_settings,
            regular_cross_section_settings,
            cleaning_cross_section_settings,
            selected_area_settings,
        ]
        (
            rectangle_pattern,
            regular_cross_section_pattern,
            cleaning_cross_section_pattern,
            selected_area_pattern,
        ) = (None, None, None, None)
        # pattern_names = [val.value for val in tbt.FIBPatternType]  # remembers order
        # assert pattern_names == [
        #     "rectangle",
        #     "regular_cross_section",
        #     "cleaning_cross_section",
        #     "selected_area",
        # ]
        pattern_names = [
            "rectangle",
            "regular_cross_section",
            "cleaning_cross_section",
            "selected_area",
        ]
        pattern_types = [
            rectangle_pattern,
            regular_cross_section_pattern,
            cleaning_cross_section_pattern,
            selected_area_pattern,
        ]

        for type in range(len(pattern_settings)):
            db = pattern_settings[type]
            if db is None:
                pattern_types[type] = False
            else:
                pattern_types[type] = not ut.none_value_dictionary(db)

        # one and only one type of pattern can have settings
        if sum(pattern_types) != 1:
            raise KeyError(
                f"Invalid .yml file in 'fib' step_type for step '{step_name}'. Pattern settings for one and only one type are allowed. Please provide settings for only one of the supported pattern types: {[name for name in pattern_names]}. For unused pattern types, leave the type settings completely blank, enter 'null' for each parameter, or remove the unused subdictionary completely from the .yml file."
            )
        pattern_type = tbt.FIBPatternType(pattern_names[pattern_types.index(True)])

    # check application file
    valid_applications = application_files(microscope=microscope)
    # TODO make this print out pretty
    # display_applications = ",".join(valid_applications)
    # display_applications = ut.tabular_list(data=valid_applications)
    if application_file not in valid_applications:
        raise ValueError(
            f"Unsupported FIB application file of '{application_file}' on step '{step_name}. Supported applications on this microscope are: \n{valid_applications}'"
        )

    if pattern_type == tbt.FIBPatternType.RECTANGLE:
        validate_fib_box_settings(
            settings=rectangle_settings,
            yml_format=yml_format,
            step_name=step_name,
            pattern_type=pattern_type,
        )

        pattern = tbt.FIBPattern(
            application=application_file,
            type=pattern_type,
            geometry=tbt.FIBRectanglePattern(
                center_um=tbt.Point(
                    x=rectangle_settings.get("center").get("x_um"),
                    y=rectangle_settings.get("center").get("y_um"),
                ),
                width_um=rectangle_settings.get("width_um"),
                height_um=rectangle_settings.get("height_um"),
                depth_um=rectangle_settings.get("depth_um"),
                scan_direction=tbt.FIBPatternScanDirection(
                    rectangle_settings.get("scan_direction")
                ),
                scan_type=tbt.FIBPatternScanType(rectangle_settings.get("scan_type")),
            ),
        )
        # make sure application file is valid for this pattern type:
        try:
            geometry = pattern.geometry
            microscope.patterning.set_default_application_file(pattern.application)
            microscope.patterning.create_rectangle(
                center_x=geometry.center_um.x * Conversions.UM_TO_M,
                center_y=geometry.center_um.y * Conversions.UM_TO_M,
                width=geometry.width_um * Conversions.UM_TO_M,
                height=geometry.height_um * Conversions.UM_TO_M,
                depth=geometry.depth_um * Conversions.UM_TO_M,
            )
            microscope.patterning.clear_patterns()
        except:
            raise ValueError(
                f'Invalid application file of "{pattern.application}" for Rectangle pattern type. Please select or create an appropriate application file.'
            )

        return pattern
    elif pattern_type == tbt.FIBPatternType.REGULAR_CROSS_SECTION:
        validate_fib_box_settings(
            settings=regular_cross_section_settings,
            yml_format=yml_format,
            step_name=step_name,
            pattern_type=pattern_type,
        )
        pattern = tbt.FIBPattern(
            application=application_file,
            type=pattern_type,
            geometry=tbt.FIBRegularCrossSection(
                center_um=tbt.Point(
                    x=regular_cross_section_settings.get("center").get("x_um"),
                    y=regular_cross_section_settings.get("center").get("y_um"),
                ),
                width_um=regular_cross_section_settings.get("width_um"),
                height_um=regular_cross_section_settings.get("height_um"),
                depth_um=regular_cross_section_settings.get("depth_um"),
                scan_direction=tbt.FIBPatternScanDirection(
                    regular_cross_section_settings.get("scan_direction")
                ),
                scan_type=tbt.FIBPatternScanType(
                    regular_cross_section_settings.get("scan_type")
                ),
            ),
        )
        # make sure application file is valid for this pattern type:
        try:
            geometry = pattern.geometry
            microscope.patterning.set_default_application_file(pattern.application)
            microscope.patterning.create_regular_cross_section(
                center_x=geometry.center_um.x * Conversions.UM_TO_M,
                center_y=geometry.center_um.y * Conversions.UM_TO_M,
                width=geometry.width_um * Conversions.UM_TO_M,
                height=geometry.height_um * Conversions.UM_TO_M,
                depth=geometry.depth_um * Conversions.UM_TO_M,
            )
            microscope.patterning.clear_patterns()
        except:
            raise ValueError(
                f'Invalid application file of "{pattern.application}" for Regular Cross Section pattern type. Please select or create an appropriate application file.'
            )
        return pattern
    elif pattern_type == tbt.FIBPatternType.CLEANING_CROSS_SECTION:
        validate_fib_box_settings(
            settings=cleaning_cross_section_settings,
            yml_format=yml_format,
            step_name=step_name,
            pattern_type=pattern_type,
        )
        pattern = tbt.FIBPattern(
            application=application_file,
            type=pattern_type,
            geometry=tbt.FIBCleaningCrossSection(
                center_um=tbt.Point(
                    x=cleaning_cross_section_settings.get("center").get("x_um"),
                    y=cleaning_cross_section_settings.get("center").get("y_um"),
                ),
                width_um=cleaning_cross_section_settings.get("width_um"),
                height_um=cleaning_cross_section_settings.get("height_um"),
                depth_um=cleaning_cross_section_settings.get("depth_um"),
                scan_direction=tbt.FIBPatternScanDirection(
                    cleaning_cross_section_settings.get("scan_direction")
                ),
                scan_type=tbt.FIBPatternScanType(
                    cleaning_cross_section_settings.get("scan_type")
                ),
            ),
        )
        # make sure application file is valid for this pattern type:
        try:
            geometry = pattern.geometry
            microscope.patterning.set_default_application_file(pattern.application)
            microscope.patterning.create_cleaning_cross_section(
                center_x=geometry.center_um.x * Conversions.UM_TO_M,
                center_y=geometry.center_um.y * Conversions.UM_TO_M,
                width=geometry.width_um * Conversions.UM_TO_M,
                height=geometry.height_um * Conversions.UM_TO_M,
                depth=geometry.depth_um * Conversions.UM_TO_M,
            )
            microscope.patterning.clear_patterns()
        except:
            raise ValueError(
                f'Invalid application file of "{pattern.application}" for Cleaning Cross Section pattern type. Please select or create an appropriate application file.'
            )
        return pattern
    elif pattern_type == tbt.FIBPatternType.SELECTED_AREA:
        validate_fib_selected_area_settings(
            settings=selected_area_settings,
            yml_format=yml_format,
            step_name=step_name,
            pattern_type=pattern_type,
        )
        pattern = tbt.FIBPattern(
            application=application_file,
            type=pattern_type,
            geometry=tbt.FIBStreamPattern(
                dwell_us=selected_area_settings.get("dwell_us"),
                repeats=selected_area_settings.get("repeats"),
                recipe=Path(selected_area_settings.get("recipe_file")),
                mask=Path(selected_area_settings.get("mask_file")),
            ),
        )

        # make sure application file is valid for this pattern type:
        try:
            microscope.patterning.set_default_application_file(pattern.application)
            microscope.patterning.create_rectangle(
                center_x=0.0,
                center_y=0.0,
                width=10.0e-6,
                height=10.0e-6,
                depth=1.0e-6,
            )
            microscope.patterning.clear_patterns()
        except:
            raise ValueError(
                f'Invalid application file of "{pattern.application}" for Selected Area pattern. Please use an application file for Rectangle milling.'
            )

        return pattern
    else:
        raise KeyError(
            f"Invalid pattern type of {pattern_type}. Supported pattern types are: {[i.value for i in tbt.FIBPatternType]}"
        )


def validate_fib_box_settings(
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
    step_name: str,
    pattern_type: tbt.FIBPatternType,
) -> bool:
    """
    Perform schema checking for FIB box pattern setting dictionary.

    This function validates the FIB box pattern settings dictionary based on the specified yml format.

    Parameters
    ----------
    settings : dict
        The dictionary containing the FIB box pattern settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.
    step_name : str
        The name of the step in the .yml file.
    pattern_type : tbt.FIBPatternType
        The type of the FIB pattern.

    Returns
    -------
    bool
        True if the settings are valid, False otherwise.

    Raises
    ------
    ValueError
        If the yml version is unsupported or if the settings do not satisfy the specified schema.
    """
    if yml_format.version >= 1.0:
        # flattens nested dictionary, adding "_" separator
        flat_settings = ut._flatten(settings)
        schema = Schema(
            {
                "center_x_um": And(
                    float,
                    error=f"In 'fib' step_type for step '{step_name}' and pattern type '{pattern_type.value}', 'x_um' parameter for pattern 'center' sub-dictionary must be a float. '{flat_settings['center_x_um']}' of type '{type(flat_settings['center_x_um'])}' was requested.",
                ),
                "center_y_um": And(
                    float,
                    error=f"In 'fib' step_type for step '{step_name}' and pattern type '{pattern_type.value}', 'y_um' parameter for pattern 'center' sub-dictionary must be a float. '{flat_settings['center_y_um']}' of type '{type(flat_settings['center_y_um'])}' was requested.",
                ),
                "width_um": And(
                    float,
                    lambda x: x > 0,
                    error=f"In 'fib' step_type for step '{step_name}' and pattern type '{pattern_type.value}', 'width_um' parameter must be a float. '{flat_settings['width_um']}' of type '{type(flat_settings['width_um'])}' was requested.",
                ),
                "height_um": And(
                    float,
                    lambda x: x > 0,
                    error=f"In 'fib' step_type for step '{step_name}' and pattern type '{pattern_type.value}', 'height_um' parameter must be a float. '{flat_settings['height_um']}' of type '{type(flat_settings['height_um'])}' was requested.",
                ),
                "depth_um": And(
                    float,
                    lambda x: x > 0,
                    error=f"In 'fib' step_type for step '{step_name}' and pattern type '{pattern_type.value}', 'depth_um' parameter must be a float. '{flat_settings['depth_um']}' of type '{type(flat_settings['depth_um'])}' was requested.",
                ),
                "scan_direction": And(
                    str,
                    lambda x: ut.valid_enum_entry(x, tbt.FIBPatternScanDirection),
                    error=f"In 'fib' step_type for step '{step_name}' and pattern type '{pattern_type.value}', 'scan_direction' parameter must be a valid scan direction type. '{flat_settings['scan_direction']}' was requested but supported values are: {[i.value for i in tbt.FIBPatternScanDirection]}",
                ),
                "scan_type": And(
                    str,
                    lambda x: ut.valid_enum_entry(x, tbt.FIBPatternScanType),
                    error=f"In 'fib' step_type for step '{step_name}' and pattern type '{pattern_type.value}', 'scan_type' parameter must be a valid scan type type. '{flat_settings['scan_type']}' was requested but supported values are: {[i.value for i in tbt.FIBPatternScanType]}",
                ),
            },
            ignore_extra_keys=True,
        )
    try:
        schema.validate(flat_settings)
    except UnboundLocalError:
        raise ValueError(
            f"Error. Unsupported yml version {yml_format.version} provided."
        )
    return True


def validate_fib_selected_area_settings(
    settings: dict,
    yml_format: tbt.YMLFormatVersion,
    step_name: str,
    pattern_type: tbt.FIBPatternType,
) -> bool:
    """
    Perform schema checking for FIB selected area pattern setting dictionary.

    This function validates the FIB selected area pattern settings dictionary based on the specified yml format.

    Parameters
    ----------
    settings : dict
        The dictionary containing the FIB selected area pattern settings.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.
    step_name : str
        The name of the step in the .yml file.
    pattern_type : tbt.FIBPatternType
        The type of the FIB pattern.

    Returns
    -------
    bool
        True if the settings are valid, False otherwise.

    Raises
    ------
    ValueError
        If the yml version is unsupported or if the settings do not satisfy the specified schema.
    """
    if yml_format.version >= 1.0:
        schema = Schema(
            {
                "dwell_us": And(
                    float,
                    lambda x: x > 0,
                    # check all float error versions of modulus
                    Or(
                        lambda x: math.isclose(
                            x % Constants.stream_pattern_base_dwell_us,
                            0,
                            abs_tol=Constants.stream_pattern_base_dwell_us / 1e5,
                        ),
                        lambda x: math.isclose(
                            x % Constants.stream_pattern_base_dwell_us,
                            Constants.stream_pattern_base_dwell_us,
                            abs_tol=Constants.stream_pattern_base_dwell_us / 1e5,
                        ),
                        lambda x: math.isclose(
                            x % Constants.stream_pattern_base_dwell_us,
                            -Constants.stream_pattern_base_dwell_us,
                            abs_tol=Constants.stream_pattern_base_dwell_us / 1e5,
                        ),
                    ),
                    error=f"In 'fib' step_type for step '{step_name}' and pattern type '{pattern_type.value}', 'dwell_us' parameter must be a positive float and an integer multiple of the base dwell time, { Constants.stream_pattern_base_dwell_us * Conversions.US_TO_NS} ns. '{settings['dwell_us']}' us of type '{type(settings['dwell_us'])}' was requested.",
                ),
                "repeats": And(
                    int,
                    lambda x: x > 0,
                    error=f"In 'fib' step_type for step '{step_name}' and pattern type '{pattern_type.value}', 'repeats' parameter must be a positive integer. '{settings['repeats']}' of type '{type(settings['repeats'])}' was requested.",
                ),
                "recipe_file": And(
                    str,
                    lambda x: Path(x).is_file(),
                    lambda x: Path(x).suffix == ".py",
                    error=f"In 'fib' step_type for step '{step_name}' and pattern type '{pattern_type.value}', 'recipe_file' parameter must be a valid file path string with the extension '.py' and must already exist. The recipe file '{settings['recipe_file']}' was requested.",
                ),
                "mask_file": And(
                    str,
                    lambda x: Path(x).suffix == ".tif",
                    error=f"In 'fib' step_type for step '{step_name}' and pattern type '{pattern_type.value}', 'mask' parameter must be a file path string with a file extension of '.tif'. '{settings['mask_file']}' of type '{type(settings['mask_file'])}' was requested.",
                ),
            },
            ignore_extra_keys=True,
        )
    try:
        schema.validate(settings)
    except UnboundLocalError:
        raise ValueError(
            f"Error. Unsupported yml version {yml_format.version} provided."
        )
    return True


def step(
    microscope: tbt.Microscope,
    # slice_number: str,
    step_name: str,
    step_settings: dict,
    general_settings: tbt.GeneralSettings,
    yml_format: tbt.YMLFormatVersion,
) -> tbt.Step:
    """
    Create a step object for different step types, including validation.

    This function creates a `Step` object for the specified step type and performs validation.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to create the step.
    step_name : str
        The name of the step in the .yml file.
    step_settings : dict
        The dictionary containing the step settings.
    general_settings : tbt.GeneralSettings
        The general settings object.
    yml_format : tbt.YMLFormatVersion
        The format specified by the version of the .yml file.

    Returns
    -------
    tbt.Step
        The step object.

    Raises
    ------
    NotImplementedError
        If the step type is unsupported.
    KeyError
        If required settings are missing or invalid.
    """

    # parsing settings
    step_type_value = step_settings[yml_format.step_general_key][
        yml_format.step_type_key
    ]
    if not ut.valid_enum_entry(step_type_value, tbt.StepType):
        raise NotImplementedError(
            f"Unsupported step type of '{step_type_value}', for step name '{step_name}' supported types are: {[i.value for i in tbt.StepType]}."
        )
    step_type = tbt.StepType(step_type_value)

    step_number = step_settings[yml_format.step_general_key][yml_format.step_number_key]
    if not isinstance(step_number, int) or (step_number < 1):
        raise KeyError(
            f"Invalid step number of '{step_number}', for step name '{step_name}'. Must be a positive integer greater than 0."
        )
    step_frequency = step_settings[yml_format.step_general_key][
        yml_format.step_frequency_key
    ]
    if not isinstance(step_frequency, int) or (step_frequency < 1):
        raise KeyError(
            f"Invalid step frequency of '{step_frequency}', for step name '{step_name}'. Must be a positive integer greater than 0."
        )
    stage_db = step_settings[yml_format.step_general_key][
        yml_format.step_stage_settings_key
    ]

    # check and validate stage
    stage_settings = stage_position_settings(
        microscope=microscope,
        step_name=step_name,
        general_settings=general_settings,
        step_stage_settings=stage_db,
        yml_format=yml_format,
    )

    # TODO
    # operation_settings, could use match statement in python >= 3.10
    if step_type == tbt.StepType.EBSD:
        operation_settings = ebsd(
            microscope=microscope,
            step_settings=step_settings,
            step_name=step_name,
            yml_format=yml_format,
        )
    if step_type == tbt.StepType.EDS:
        operation_settings = eds(
            microscope=microscope,
            step_settings=step_settings,
            step_name=step_name,
            yml_format=yml_format,
        )
    if step_type == tbt.StepType.IMAGE:
        operation_settings = image(
            microscope=microscope,
            step_settings=step_settings,
            step_name=step_name,
            yml_format=yml_format,
        )
    if step_type == tbt.StepType.LASER:
        operation_settings = laser(
            microscope=microscope,
            step_settings=step_settings,
            step_name=step_name,
            yml_format=yml_format,
        )
    if step_type == tbt.StepType.CUSTOM:
        operation_settings = custom(
            microscope=microscope,
            step_settings=step_settings,
            step_name=step_name,
            yml_format=yml_format,
        )
    if step_type == tbt.StepType.FIB:
        operation_settings = fib(
            microscope=microscope,
            step_settings=step_settings,
            step_name=step_name,
            yml_format=yml_format,
        )

    step_object = tbt.Step(
        type=step_type,
        name=step_name,
        number=step_number,
        frequency=step_frequency,
        stage=stage_settings,
        operation_settings=operation_settings,
    )

    return step_object
