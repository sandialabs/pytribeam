#!/usr/bin/python3

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
        "S1099177",
    ]
    microscope_machines = ["HPN125v-MPC", "HPN276-MPC"]

    # error message display constants
    default_column_count = 3  # for printing large lists of values
    default_column_width = 20  # characters


class Conversions(NamedTuple):
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
