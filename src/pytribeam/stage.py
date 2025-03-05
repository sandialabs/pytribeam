#!/usr/bin/python3

# Default python modules
# from functools import singledispatch
import os
from pathlib import Path
import time
import warnings
import math
from typing import NamedTuple, List, Tuple
import sys

# Autoscript included modules
import numpy as np
from matplotlib import pyplot as plt

# 3rd party module

# Local scripts
import pytribeam.constants as cs
from pytribeam.constants import Conversions
import pytribeam.insertable_devices as devices
import pytribeam.factory as factory
import pytribeam.types as tbt
import pytribeam.utilities as ut


def coordinate_system(
    microscope: tbt.Microscope,
    mode: tbt.StageCoordinateSystem = tbt.StageCoordinateSystem.RAW,
) -> bool:
    """Sets stage mode. Default is "SPECIMEN" which is not recommended"""
    if mode != tbt.StageCoordinateSystem.RAW:
        warnings.warn(
            f"""Warning. {mode.value} coordinate system requested
                      instead of "RAW" stage coordinate system. This can lead
                      to inaccurate stage movements and increases collision risk."""
        )
        # TODO ask for yes no continue
    microscope.specimen.stage.set_default_coordinate_system(mode.value)
    return True


def stop(microscope: tbt.Microscope) -> None:
    """Immediately stop all stage movement and exit"""
    microscope.specimen.stage.stop()
    microscope.disconnect()

    raise SystemError("Microscope stage movement was halted.")
    # sys.exit("Microscope stage movement was halted.")


def encoder_to_user_position(pos: tbt.StagePositionEncoder) -> tbt.StagePositionUser:
    """Converts from user position (mm/deg units) to encoder position (m/radian units)"""
    if not isinstance(pos, tbt.StagePositionEncoder):
        raise TypeError(
            f"provided position is not of type '<class pytribeam.types.StagePositionEncoder>', but instead of type '{type(pos)}'. Did you mean to use the function 'user_to_encoder_position'?"
        )
    user_pos = tbt.StagePositionUser(
        x_mm=round(pos.x * Conversions.M_TO_MM, 6),
        y_mm=round(pos.y * Conversions.M_TO_MM, 6),
        z_mm=round(pos.z * Conversions.M_TO_MM, 6),
        r_deg=round(pos.r * Conversions.RAD_TO_DEG, 6),
        t_deg=round(pos.t * Conversions.RAD_TO_DEG, 6),
        coordinate_system=tbt.StageCoordinateSystem(pos.coordinate_system),
    )
    return user_pos


def user_to_encoder_position(pos: tbt.StagePositionUser) -> tbt.StagePositionEncoder:
    """Converts from user position (mm/deg units) to encoder position (m/radian units)"""
    if not isinstance(pos, tbt.StagePositionUser):
        raise TypeError(
            f"Provided position is not of type '<class pytribeam.types.StagePositionUser>', but instead of type '{type(pos)}'. Did you mean to use the function 'encoder_to_user_position'?"
        )
    encoder_pos = tbt.StagePositionEncoder(
        x=pos.x_mm * Conversions.MM_TO_M,
        y=pos.y_mm * Conversions.MM_TO_M,
        z=pos.z_mm * Conversions.MM_TO_M,
        r=pos.r_deg * Conversions.DEG_TO_RAD,
        t=pos.t_deg * Conversions.DEG_TO_RAD,
        coordinate_system=pos.coordinate_system.value,
    )
    return encoder_pos


# TODO not yet implemented, below example works on Z-sectioning
def rotation_side_adjustment(
    rotation_side: tbt.RotationSide,
    initial_position_m: float,
    delta_pos_m: float,
) -> float:
    """Takes rotation side variable into accound to determine translation stage destination"""
    if rotation_side == tbt.RotationSide.FSL_MILL:
        target_m = (
            initial_position_m - delta_pos_m
        )  # absolute negative direction (towards laser)
    elif rotation_side == tbt.RotationSide.FIB_MILL:
        target_m = (
            initial_position_m + delta_pos_m
        )  # absolute positive direction (towards FIB)
    elif rotation_side == tbt.RotationSide.EBEAM_NORMAL:
        target_m = initial_position_m  # no adjustment needed
    else:
        raise NotImplementedError(
            f"Unsupported RotationSide enumeration of '{rotation_side}'"
        )
    return target_m


def target_position(
    stage: tbt.StageSettings,
    slice_number: int,
    slice_thickness_um: float,
) -> tbt.StagePositionUser:
    """Calculates target position for the movement based off of
    sectioning axis, slice number, and slice thickness.

    For Z-axis sectioning:
        Z will always incrememnt toward pole piece (positive direction)
        Y will increment with slice number if a non-zero pre-tilt is used
        Y increment direction depends on rotation of the stage relative to machining operations

    For X-axis sectioning (not yet implemented, need to determine rotation_side_adjustment)
    For Y-axis sectioning (not yet implemented, need to determine rotation_side_adjustment)
    """

    initial_pos_user = stage.initial_position
    initial_pos_encoder = user_to_encoder_position(initial_pos_user)
    slice_thickness_m = slice_thickness_um * Conversions.UM_TO_M
    pre_tilt_rad = stage.pretilt_angle_deg * Conversions.DEG_TO_RAD
    sectioning_axis = stage.sectioning_axis
    rotation_side = stage.rotation_side
    increment_factor_m = slice_thickness_m * (slice_number - 1)  # slices are 1-indexed

    # only modify needed axes for each case, so initialize with original position
    target_x_m = initial_pos_encoder.x
    target_y_m = initial_pos_encoder.y
    target_z_m = initial_pos_encoder.z
    target_r_rad = initial_pos_encoder.r
    target_t_rad = initial_pos_encoder.t

    if sectioning_axis == tbt.SectioningAxis.Z:
        delta_z_m = math.cos(pre_tilt_rad) * increment_factor_m
        # Z always increments in positive direction
        target_z_m = initial_pos_encoder.z + delta_z_m

        # Y axis depends on rotation_side
        delta_y_m = math.sin(pre_tilt_rad) * increment_factor_m

        if rotation_side == tbt.RotationSide.FSL_MILL:
            target_y_m = (
                initial_pos_encoder.y - delta_y_m
            )  # absolute negative direction (towards laser)
        elif rotation_side == tbt.RotationSide.FIB_MILL:
            target_y_m = (
                initial_pos_encoder.y + delta_y_m
            )  # absolute positive direction (towards FIB)
        elif rotation_side == tbt.RotationSide.EBEAM_NORMAL:
            target_y_m = initial_pos_encoder.y  # no adjustment needed
        else:
            raise NotImplementedError(
                f"Unsupported RotationSide enumeration of '{rotation_side}'"
            )

    # TODO
    elif sectioning_axis == tbt.SectioningAxis.X_POS:
        raise NotImplementedError("Currently only Z-axis sectioning is supported.")
        delta_x_m = increment_factor_m
        pass
    elif sectioning_axis == tbt.SectioningAxis.X_NEG:
        raise NotImplementedError("Currently only Z-axis sectioning is supported.")
        delta_x_m = increment_factor_m
        pass
    elif sectioning_axis == tbt.SectioningAxis.Y_POS:
        raise NotImplementedError("Currently only Z-axis sectioning is supported.")
        delta_x_m = increment_factor_m
        pass
    elif sectioning_axis == tbt.SectioningAxis.Y_NEG:
        raise NotImplementedError("Currently only Z-axis sectioning is supported.")
        delta_x_m = increment_factor_m
        pass

    target_pos_encoder = tbt.StagePositionEncoder(
        x=target_x_m,
        y=target_y_m,
        z=target_z_m,
        r=target_r_rad,
        t=target_t_rad,
        coordinate_system=tbt.StageCoordinateSystem.RAW.value,
    )
    target_pos_user = encoder_to_user_position(target_pos_encoder)
    return target_pos_user


def safe(
    microscope: tbt.Microscope,
    position: tbt.StagePositionUser,
) -> bool:
    # returns in user units (mm, deg)
    stage_limits = factory.stage_limits(microscope=microscope)

    if not ut.in_interval(
        position.x_mm, stage_limits.x_mm, type=tbt.IntervalType.CLOSED
    ):
        return False
    if not ut.in_interval(
        position.y_mm, stage_limits.y_mm, type=tbt.IntervalType.CLOSED
    ):
        return False
    if not ut.in_interval(
        position.z_mm, stage_limits.z_mm, type=tbt.IntervalType.CLOSED
    ):
        return False
    if not ut.in_interval(
        position.t_deg, stage_limits.t_deg, type=tbt.IntervalType.CLOSED
    ):
        return False
    if not ut.in_interval(
        position.r_deg, stage_limits.r_deg, type=tbt.IntervalType.CLOSED
    ):
        return False

    return True


def axis_translational_in_range(
    current_pos_mm: float,
    target_pos_mm: float,
    stage_tolerance_um: float,
) -> bool:
    """Determines whether translation axis needs to be moved"""
    return ut.in_interval(
        current_pos_mm,
        limit=tbt.Limit(
            min=target_pos_mm - (stage_tolerance_um * Conversions.UM_TO_MM),
            max=target_pos_mm + (stage_tolerance_um * Conversions.UM_TO_MM),
        ),
        type=tbt.IntervalType.CLOSED,
    )


def axis_angular_in_range(
    current_pos_deg: float,
    target_pos_deg: float,
    stage_tolerance_deg: float,
) -> bool:
    """Determines whether angular axis needs to be moved"""
    return ut.in_interval(
        current_pos_deg,
        limit=tbt.Limit(
            min=target_pos_deg - (stage_tolerance_deg * Conversions.DEG_TO_RAD),
            max=target_pos_deg + (stage_tolerance_deg * Conversions.DEG_TO_RAD),
        ),
        type=tbt.IntervalType.CLOSED,
    )


def axis_in_range(
    microscope: tbt.Microscope,
    axis: tbt.StageAxis,
    target_position: tbt.StagePositionUser,
    stage_tolerance: tbt.StageTolerance = cs.Constants.default_stage_tolerance,
) -> bool:
    """Checks whether position of specified axis is within stage tolerance"""
    current_position = factory.active_stage_position_settings(
        microscope=microscope
    )  # user units [mm_deg]

    # TODO convert to match statements at python >=3.10
    match_db = {
        tbt.StageAxis.X: {
            "current_position": current_position.x_mm,
            "target_position": target_position.x_mm,
            "tolerance": stage_tolerance.translational_um * Conversions.UM_TO_MM,
        },
        tbt.StageAxis.Y: {
            "current_position": current_position.y_mm,
            "target_position": target_position.y_mm,
            "tolerance": stage_tolerance.translational_um * Conversions.UM_TO_MM,
        },
        tbt.StageAxis.Z: {
            "current_position": current_position.z_mm,
            "target_position": target_position.z_mm,
            "tolerance": stage_tolerance.translational_um * Conversions.UM_TO_MM,
        },
        tbt.StageAxis.R: {
            "current_position": current_position.r_deg,
            "target_position": target_position.r_deg,
            "tolerance": stage_tolerance.angular_deg,
        },
        tbt.StageAxis.T: {
            "current_position": current_position.t_deg,
            "target_position": target_position.t_deg,
            "tolerance": stage_tolerance.angular_deg,
        },
    }

    return ut.in_interval(
        val=match_db[axis]["current_position"],
        limit=tbt.Limit(
            min=match_db[axis]["target_position"] - match_db[axis]["tolerance"],
            max=match_db[axis]["target_position"] + match_db[axis]["tolerance"],
        ),
        type=tbt.IntervalType.CLOSED,
    )


def move_axis(
    microscope: tbt.Microscope,
    axis: tbt.StageAxis,
    target_position: tbt.StagePositionUser,
    num_attempts: int = cs.Constants.stage_move_attempts,
    stage_delay_s: float = cs.Constants.stage_move_delay_s,
) -> bool:
    """Moves single specified stage axis to the requested user target position"""
    encoder_position = user_to_encoder_position(target_position)
    # TODO convert to match statements at python >=3.10
    match_db = {
        tbt.StageAxis.X: tbt.StagePositionEncoder(x=encoder_position.x),
        tbt.StageAxis.Y: tbt.StagePositionEncoder(y=encoder_position.y),
        tbt.StageAxis.Z: tbt.StagePositionEncoder(z=encoder_position.z),
        tbt.StageAxis.R: tbt.StagePositionEncoder(r=encoder_position.r),
        tbt.StageAxis.T: tbt.StagePositionEncoder(t=encoder_position.t),
    }
    for _ in range(num_attempts):
        microscope.specimen.stage.absolute_move(match_db[axis])
        time.sleep(stage_delay_s)
    return True


def move_stage(
    microscope: tbt.Microscope,
    target_position: tbt.StagePositionUser,
    stage_tolerance: tbt.StageTolerance,
) -> bool:
    """Moves stage axis if outside of tolerance
    Stage axes are moved one at a time in the following sequence:
        R-axis: if needed, tilt will be adjusted to 0 degrees first for safety
        X-axis
        Y-axis
        Z-axis
        T-axis
    """

    # ensure RAW specimen coordiantes
    coordinate_system(microscope=microscope, mode=tbt.StageCoordinateSystem.RAW)

    # r-axis first for safety
    if not axis_in_range(
        microscope=microscope,
        axis=tbt.StageAxis.R,
        target_position=target_position,
        stage_tolerance=stage_tolerance,
    ):
        # move t-axis to 0 deg (home position) first if needed
        if not axis_in_range(
            microscope=microscope,
            axis=tbt.StageAxis.T,
            target_position=cs.Constants.home_position,
            stage_tolerance=stage_tolerance,
        ):
            move_axis(
                microscope=microscope,
                axis=tbt.StageAxis.T,
                target_position=cs.Constants.home_position,
            )

        move_axis(
            microscope=microscope,
            axis=tbt.StageAxis.R,
            target_position=target_position,
        )

    # remaining axes are independent, but sequential
    remaining_axes = [
        tbt.StageAxis.X,
        tbt.StageAxis.Y,
        tbt.StageAxis.Z,
        tbt.StageAxis.T,
    ]
    for axis in remaining_axes:
        if not axis_in_range(
            microscope=microscope,
            axis=axis,
            target_position=target_position,
            stage_tolerance=stage_tolerance,
        ):
            move_axis(
                microscope=microscope,
                axis=axis,
                target_position=target_position,
            )

    return True


def move_completed(
    microscope: tbt.Microscope,
    target_position: tbt.StagePositionUser,
    stage_tolerance: tbt.StageTolerance,
) -> bool:
    """Checks whether the stage is at the target position"""

    # ensure RAW specimen coordiantes
    coordinate_system(microscope=microscope, mode=tbt.StageCoordinateSystem.RAW)

    axes = [
        tbt.StageAxis.X,
        tbt.StageAxis.Y,
        tbt.StageAxis.Z,
        tbt.StageAxis.R,
        tbt.StageAxis.T,
    ]
    for axis in axes:
        if not axis_in_range(
            microscope=microscope,
            axis=axis,
            target_position=target_position,
            stage_tolerance=stage_tolerance,
        ):
            # handle -179.9 degrees of rotation being very close equivalently to 180.0 degrees, for example
            if axis == tbt.StageAxis.R:
                equivalent_position_pos = tbt.StagePositionUser(
                    x_mm=target_position.x_mm,
                    y_mm=target_position.y_mm,
                    z_mm=target_position.z_mm,
                    r_deg=target_position.r_deg + 360.0,
                    t_deg=target_position.t_deg,
                )
                equivalent_position_neg = tbt.StagePositionUser(
                    x_mm=target_position.x_mm,
                    y_mm=target_position.y_mm,
                    z_mm=target_position.z_mm,
                    r_deg=target_position.r_deg - 360.0,
                    t_deg=target_position.t_deg,
                )
                if axis_in_range(
                    microscope=microscope,
                    axis=axis,
                    target_position=equivalent_position_pos,
                    stage_tolerance=stage_tolerance,
                ) or axis_in_range(
                    microscope=microscope,
                    axis=axis,
                    target_position=equivalent_position_neg,
                    stage_tolerance=stage_tolerance,
                ):
                    continue
            return False
    return True


## main methods
def home_stage(
    microscope: tbt.Microscope,
    stage_tolerance: tbt.StageTolerance = cs.Constants.default_stage_tolerance,
) -> bool:
    """Moves the stage to home position defined in pytribeam.constants, a special case of the move_to_position function"""
    target_position = cs.Constants.home_position
    move_to_position(
        microscope=microscope,
        target_position=target_position,
        stage_tolerance=stage_tolerance,
    )
    return True


def move_to_position(
    microscope: tbt.Microscope,
    target_position: tbt.StagePositionUser,
    stage_tolerance: tbt.StageTolerance = cs.Constants.default_stage_tolerance,
) -> bool:
    """main method for moving stage, with error checking"""

    # check if safe
    if not safe(microscope=microscope, position=target_position):
        raise ValueError(
            f"Destination position of {target_position} is unsafe. Stage limits are:\n\t{factory.stage_limits(microscope=microscope)}. \nExiting now"
        )

    # visualize movement on CCD
    devices.CCD_view(microscope=microscope)

    # move the stage
    move_stage(
        microscope=microscope,
        target_position=target_position,
        stage_tolerance=stage_tolerance,
    )

    # stop visualization on CCD
    devices.CCD_pause(microscope=microscope)

    # check if completed #TODO clean this with a loop
    if not move_completed(
        microscope=microscope,
        target_position=target_position,
        stage_tolerance=stage_tolerance,
    ):
        # Try again
        move_stage(
            microscope=microscope,
            target_position=target_position,
            stage_tolerance=stage_tolerance,
        )
        # check if completed
        if not move_completed(
            microscope=microscope,
            target_position=target_position,
            stage_tolerance=stage_tolerance,
        ):
            current_position = factory.active_stage_position_settings(
                microscope=microscope
            )
            error_message = _bad_axes_message(
                target_position, current_position, stage_tolerance
            )
            raise SystemError(error_message)

    return True


def _bad_axes_message(
    target_position: tbt.StagePositionUser,
    current_position: tbt.StagePositionUser,
    stage_tolerance: tbt.StageTolerance,
) -> str:
    error_msg = "Error: Stage move did not execute correctly.\n"
    x_error_um = np.around(
        abs(target_position.x_mm - current_position.x_mm) * Conversions.MM_TO_UM, 3
    )
    y_error_um = np.around(
        abs(target_position.y_mm - current_position.y_mm) * Conversions.MM_TO_UM, 3
    )
    z_error_um = np.around(
        abs(target_position.z_mm - current_position.z_mm) * Conversions.MM_TO_UM, 3
    )

    translation_errors = [x_error_um, y_error_um, z_error_um]
    translation_axes = ["X", "Y", "Z"]
    for axis in range(0, len(translation_axes)):
        if translation_errors[axis] > stage_tolerance.translational_um:
            error_msg += f"\t {translation_axes[axis]} axis error: {translation_errors[axis]} micron, stage tolerance is {stage_tolerance.translational_um} micron\n"

    t_error_deg = np.around(abs(target_position.t_deg - current_position.t_deg), 3)
    r_error_deg = np.around(abs(target_position.r_deg - current_position.r_deg), 3)
    angular_errors = [t_error_deg, r_error_deg]
    angular_axes = ["T", "R"]
    for axis in range(0, len(angular_axes)):
        if angular_errors[axis] > stage_tolerance.translational_um:
            error_msg += f"\t {angular_axes[axis]} axis error: {angular_errors[axis]} degrees, stage tolerance is {stage_tolerance.angular_deg} degrees\n"

    return error_msg


def step_start_position(
    microscope: tbt.Microscope,
    slice_number: int,
    operation: tbt.Step,
    general_settings: tbt.GeneralSettings,
) -> bool:
    """Moves stage to starting position for the step"""
    position = target_position(
        operation.stage,
        slice_number=slice_number,
        slice_thickness_um=general_settings.slice_thickness_um,
    )
    print("\tMoving to following position:")
    space = " "
    print(
        f"\t\t{'X [mm]' + space:<10}{'Y [mm]' + space:<10}{'Z [mm]' + space:<10}{'R [deg]' + space:<10}{'T [deg]' + space:<10}"
    )
    print(
        f"\t\t{round(position.x_mm,4):<10}{round(position.y_mm,4):<10}{round(position.z_mm,4):<10}{round(position.r_deg,3):<10}{round(position.t_deg,3):<10}"
    )
    move_to_position(
        microscope=microscope,
        target_position=position,
        stage_tolerance=general_settings.stage_tolerance,
    )
