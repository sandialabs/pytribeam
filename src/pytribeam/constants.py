#!/usr/bin/python3
"""
Constants Module
================

This module contains various constants and conversion factors used throughout the software. The constants are organized into two main classes: `Constants` and `Conversions`.

Classes
-------
Constants : NamedTuple
    A NamedTuple containing various constants related to software versions, log files, beam parameters, detector parameters, laser parameters, FIB parameters, stage parameters, mapping parameters, test suite parameters, and error message display parameters.

Conversions : NamedTuple
    A NamedTuple containing various conversion factors for length, time, voltage, current, and angle.
"""

# Default python modules
import os
from pathlib import Path
import time
import warnings
import math
from typing import Dict, NamedTuple, Tuple, List
import platform

import pytest
import numpy as np
import h5py

# import pytribeam.utilities as ut
import pytribeam.types as tbt


class Constants(NamedTuple):
    """
    A NamedTuple containing various constants used throughout the software.

    Attributes
    ----------
    module_short_name : str
        Short name of the module.
    autoscript_version : str
        Version of the AutoScript software.
    laser_api_version : str
        Version of the Laser API.
    yml_schema_version : str
        Maximum supported version of the YAML schema.

    logfile_extension : str
        Extension for log files.
    settings_dataset_name : str
        Name of the dataset for experiment settings.
    pre_position_dataset_name : str
        Name of the dataset for position before an event.
    post_position_dataset_name : str
        Name of the dataset for position after an event.
    pre_lasing_dataset_name : str
        Name of the dataset for laser power before an event.
    post_lasing_dataset_name : str
        Name of the dataset for laser power after an event.
    specimen_current_dataset_name : str
        Name of the dataset for specimen current.
    settings_dtype : np.dtype
        Data type for settings dataset.
    position_dtype : np.dtype
        Data type for position dataset.
    laser_power_dtype : np.dtype
        Data type for laser power dataset.
    specimen_current_dtype : np.dtype
        Data type for specimen current dataset.

    beam_types : list of str
        Types of beams (electron/ion).
    voltage_tol_ratio : float
        Tolerance ratio for voltage.
    current_tol_ratio : float
        Tolerance ratio for current.
    beam_dwell_tol_ratio : float
        Tolerance ratio for beam dwell time.
    default_color_depth : tbt.ColorDepth
        Default color depth.
    scan_resolution_limit : tbt.Limit
        Limit for scan resolution.

    contrast_brightness_tolerance : float
        Tolerance for contrast and brightness.

    image_scan_rotation_for_laser_deg : float
        Image scan rotation for laser in degrees.
    laser_objective_limit_mm : tbt.Limit
        Limit for laser objective in millimeters.
    laser_objective_retracted_mm : float
        Safe retracted position for laser objective in millimeters.
    laser_objective_tolerance_mm : float
        Tolerance for laser objective in millimeters.
    laser_beam_shift_tolerance_um : float
        Tolerance for laser beam shift in micrometers.
    laser_energy_tol_uj : float
        Tolerance for laser energy in microjoules.
    laser_delay_s : float
        Delay for measuring power and setting pulse divider/energy in seconds.

    default_fib_rectangle_pattern : tbt.FIBRectanglePattern
        Default FIB rectangle pattern.
    stream_pattern_scale : int
        Scale for stream pattern.
    stream_pattern_y_shift : int
        Y-axis shift for stream pattern.
    stream_pattern_base_dwell_us : float
        Base dwell time for stream pattern in microseconds.

    stage_move_delay_s : float
        Delay for stage movement in seconds.
    stage_move_attempts : int
        Number of attempts for stage movement.
    default_stage_tolerance : tbt.StageTolerance
        Default stage tolerance.
    slice_thickness_limit_um : tbt.Limit
        Limit for slice thickness in micrometers.
    pre_tilt_limit_deg_generic : tbt.Limit
        Generic limit for pre-tilt in degrees.
    pre_tilt_limit_deg_non_Z_sectioning : tbt.Limit
        Limit for pre-tilt in non-Z sectioning in degrees.
    home_position : tbt.StagePositionUser
        Home position of the stage.
    rotation_axis_limit_deg : tbt.Limit
        Limit for rotation axis in degrees.
    detector_collisions : list of list of tbt.DetectorType
        List of detector collisions.

    min_map_time_s : int
        Minimum mapping time in seconds.
    specimen_current_hfw_mm : float
        Specimen current high field width in millimeters.
    specimen_current_delay_s : float
        Delay for specimen current in seconds.

    test_hardware_movement : bool
        Flag for testing hardware movement.
    offline_machines : list of str
        List of offline machines.
    microscope_machines : list of str
        List of microscope machines.

    default_column_count : int
        Default number of columns for printing large lists of values.
    default_column_width : int
        Default width of columns in characters.
    """

    # Software versions
    module_short_name = "pyTriBeam"
    autoscript_version = "4.8.1"
    laser_api_version = "2.2.1"
    yml_schema_version = "1.0"  # max supported version #TODO convert to float

    # Log file constants
    logfile_extension = ".h5"
    settings_dataset_name = "Experiment Settings"
    pre_position_dataset_name = "Position Before"
    post_position_dataset_name = "Position After"
    pre_lasing_dataset_name = "Laser Power Before"
    post_lasing_dataset_name = "Laser Power After"
    specimen_current_dataset_name = "Specimen Current"
    settings_dtype = np.dtype(
        [
            ("Slice", "<u4"),
            ("Step", "<u4"),
            ("Config File", h5py.special_dtype(vlen=str)),
            ("Timestamp", h5py.special_dtype(vlen=str)),
            ("UNIX time", "<u8"),
        ]
    )
    position_dtype = np.dtype(
        [
            ("Slice", "<u4"),
            ("X", "<f8"),
            ("Y", "<f8"),
            ("Z", "<f8"),
            ("T", "<f8"),
            ("R", "<f8"),
            ("Timestamp", h5py.special_dtype(vlen=str)),
            ("UNIX time", "<u8"),
        ]
    )
    laser_power_dtype = np.dtype(
        [
            ("Slice", "<u4"),
            ("Power", "<f8"),
            ("Timestamp", h5py.special_dtype(vlen=str)),
            ("UNIX time", "<u8"),
        ]
    )
    specimen_current_dtype = np.dtype(
        [
            ("Slice", "<u4"),
            ("Current", "<f8"),
            ("Timestamp", h5py.special_dtype(vlen=str)),
            ("UNIX time", "<u8"),
        ]
    )

    # Beam (electron/ion) constants
    beam_types = [
        "electron",
        "ion",
    ]
    voltage_tol_ratio = 0.05
    current_tol_ratio = 0.05
    beam_dwell_tol_ratio = 0.001
    default_color_depth = tbt.ColorDepth.BITS_8
    scan_resolution_limit = tbt.Limit(min=12, max=65535)  # max of 2^16 - 1

    # Detector constants
    contrast_brightness_tolerance = 1.0e-4  # range is 0 to 1

    # Laser constants
    image_scan_rotation_for_laser_deg = 180.0  # requirement by TFS for laser milling
    laser_objective_limit_mm = tbt.Limit(min=2.0, max=29.0)
    laser_objective_retracted_mm = 2.5  # safe retracted position
    laser_objective_tolerance_mm = 0.005
    laser_beam_shift_tolerance_um = 0.5
    laser_energy_tol_uj = 0.05
    laser_delay_s = 3.0  # for measuring power and settings pulse divider/energy

    # FIB constants
    default_fib_rectangle_pattern = tbt.FIBRectanglePattern(
        center_um=tbt.Point(
            x=0.0,
            y=0.0,
        ),
        width_um=10.0,
        height_um=5.0,
        depth_um=0.1,
        scan_direction=tbt.FIBPatternScanDirection.TOP_TO_BOTTOM,
        scan_type=tbt.FIBPatternScanType.RASTER,
    )
    stream_pattern_scale = (
        2**12
    )  # upscales fib image to this value / width for higher density of points
    stream_pattern_y_shift = int(
        2**16 / 6
    )  # for correct centering of stream patterns, with scan control available only at 16 bit depth, must account for 3:2 aspect ratio for image length:width and cut off half the discrepancy on both top and bottom. Full equation: 2^16(1-(2/3)) / 2
    stream_pattern_base_dwell_us = 0.025  # can be 25 or 100 ns, defaults to 25ns

    # Stage constants
    stage_move_delay_s = 0.5
    stage_move_attempts = (
        2  # generally higher accuracy on movement with 2 attempts for non-piezo stages
    )
    default_stage_tolerance = tbt.StageTolerance(
        translational_um=0.5,
        angular_deg=0.02,
    )
    slice_thickness_limit_um = tbt.Limit(min=0.0, max=30.0)  # TODO revert to 0.5 micron
    pre_tilt_limit_deg_generic = tbt.Limit(min=-60.0, max=60.0)
    pre_tilt_limit_deg_non_Z_sectioning = tbt.Limit(min=0.0, max=0.0)
    home_position = tbt.StagePositionUser(
        x_mm=0.0, y_mm=0.0, z_mm=0.0, r_deg=0.0, t_deg=0.0
    )
    rotation_axis_limit_deg = tbt.Limit(
        min=-180.0, max=180.0
    )  # used as right-open internal: 180.0 is not valid and should be converted to -180.0
    detector_collisions = [
        [tbt.DetectorType.CBS, tbt.DetectorType.EDS],
        [tbt.DetectorType.CBS, tbt.DetectorType.EBSD],
    ]

    # Mapping (EBSD/EDS) constants
    min_map_time_s = 30
    specimen_current_hfw_mm = 1.0e-3
    specimen_current_delay_s = 2.0

    # Test suite constants
    test_hardware_movement = True
    offline_machines = [
        "S1099177", "S1125518"
    ]
    microscope_machines = ["HPN125v-MPC", "HPN276-MPC"]

    # error message display constants
    default_column_count = 3  # for printing large lists of values
    default_column_width = 20  # characters


class Conversions(NamedTuple):
    """
    A NamedTuple containing various conversion constants for length, time, voltage, current, and angle.

    Attributes
    ----------
    MM_TO_M : float
        Conversion factor from millimeters to meters.
    UM_TO_M : float
        Conversion factor from micrometers to meters.
    M_TO_MM : float
        Conversion factor from meters to millimeters.
    M_TO_UM : float
        Conversion factor from meters to micrometers.
    UM_TO_MM : float
        Conversion factor from micrometers to millimeters.
    MM_TO_UM : float
        Conversion factor from millimeters to micrometers.

    US_TO_S : float
        Conversion factor from microseconds to seconds.
    S_TO_US : float
        Conversion factor from seconds to microseconds.
    S_TO_NS : float
        Conversion factor from seconds to nanoseconds.
    NS_TO_S : float
        Conversion factor from nanoseconds to seconds.
    US_TO_NS : float
        Conversion factor from microseconds to nanoseconds.
    NS_TO_US : float
        Conversion factor from nanoseconds to microseconds.

    KV_TO_V : float
        Conversion factor from kilovolts to volts.
    V_TO_KV : float
        Conversion factor from volts to kilovolts.

    UA_TO_A : float
        Conversion factor from microamperes to amperes.
    NA_TO_A : float
        Conversion factor from nanoamperes to amperes.
    PA_TO_A : float
        Conversion factor from picoamperes to amperes.
    A_TO_UA : float
        Conversion factor from amperes to microamperes.
    A_TO_NA : float
        Conversion factor from amperes to nanoamperes.
    A_TO_PA : float
        Conversion factor from amperes to picoamperes.
    PA_TO_NA : float
        Conversion factor from picoamperes to nanoamperes.
    PA_TO_UA : float
        Conversion factor from picoamperes to microamperes.
    NA_TO_UA : float
        Conversion factor from nanoamperes to microamperes.
    NA_TO_PA : float
        Conversion factor from nanoamperes to picoamperes.
    UA_TO_NA : float
        Conversion factor from microamperes to nanoamperes.
    UA_TO_PA : float
        Conversion factor from microamperes to picoamperes.

    DEG_TO_RAD : float
        Conversion factor from degrees to radians.
    RAD_TO_DEG : float
        Conversion factor from radians to degrees.
    """

    # length
    MM_TO_M = 1.0e-3
    UM_TO_M = MM_TO_M / 1000.0
    M_TO_MM = 1.0 / MM_TO_M
    M_TO_UM = 1.0 / UM_TO_M
    UM_TO_MM = UM_TO_M * M_TO_MM
    MM_TO_UM = 1.0 / UM_TO_MM

    # time
    US_TO_S = 1.0e-6
    S_TO_US = 1.0 / US_TO_S
    S_TO_NS = S_TO_US * 1000.0
    NS_TO_S = 1.0 / S_TO_NS
    US_TO_NS = US_TO_S * S_TO_NS
    NS_TO_US = 1.0 / US_TO_NS

    # voltage
    KV_TO_V = 1.0e3
    V_TO_KV = 1.0 / KV_TO_V

    # current
    UA_TO_A = 1.0e-6
    NA_TO_A = UA_TO_A / 1000.0
    PA_TO_A = NA_TO_A / 1000.0
    A_TO_UA = 1.0 / UA_TO_A
    A_TO_NA = 1.0 / NA_TO_A
    A_TO_PA = 1.0 / PA_TO_A
    PA_TO_NA = PA_TO_A * A_TO_NA
    PA_TO_UA = PA_TO_A * A_TO_UA
    NA_TO_UA = NA_TO_A * A_TO_UA
    NA_TO_PA = 1.0 / PA_TO_NA
    UA_TO_NA = 1.0 / NA_TO_UA
    UA_TO_PA = 1.0 / PA_TO_UA

    # angle
    DEG_TO_RAD = math.pi / 180.0  # convert degrees to radians
    RAD_TO_DEG = 180.0 / math.pi
