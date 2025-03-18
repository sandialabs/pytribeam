#!/usr/bin/python3

# Default python modules
from functools import singledispatch
import os
from pathlib import Path
import time
import warnings
import math
from typing import NamedTuple, List, Tuple
from functools import singledispatch
import subprocess

# Autoscript included modules
from PIL import Image as pil_img
import cv2
import numpy as np
from matplotlib import pyplot as plt
import h5py

# 3rd party module

# Local scripts
import pytribeam.constants as cs
from pytribeam.constants import Conversions
import pytribeam.insertable_devices as devices
import pytribeam.factory as factory
import pytribeam.types as tbt
import pytribeam.utilities as ut
import pytribeam.image as img


def application_files(microscope: tbt.Microscope) -> List[str]:
    """Gets application file list from the current microscope"""
    apps = microscope.patterning.list_all_application_files()

    # Remove "None" entry
    while "None" in apps:
        apps.remove("None")
    apps.sort(key=str.casefold)

    return apps


def shutter_control(microscope: tbt.Microscope) -> None:
    """Ensure auto control set on e-beam shutter. Manual control not currently offered."""
    shutter = microscope.beams.electron_beam.protective_shutter
    if not shutter.is_installed:
        warnings.warn("Protective E-beam shutter not installed on this system.")
        return
    status = shutter.mode.value
    if status != tbt.ProtectiveShutterMode.AUTOMATIC:
        shutter.mode.value = tbt.ProtectiveShutterMode.AUTOMATIC
    new_status = shutter.mode.value
    if new_status != tbt.ProtectiveShutterMode.AUTOMATIC:
        raise SystemError(
            "E-beam shutter for FIB milling is installed but cannot set control to 'Automatic' mode."
        )
    warnings.warn(
        "E-beam shutter for FIB milling operations is in auto-mode, which may not insert at certain tilt angles and stage positions. Manual control not available."
    )
    return


def prepare_milling(
    microscope: tbt.Microscope,
    application: str,
    patterning_device: tbt.Device = tbt.Device.ION_BEAM,
) -> bool:
    # TODO validation and error checking from TFS
    # TODO support e-beam patterning via the mill_beam settings
    """Clears old patterns, assigns patterning to ion beam by default, and loads application. No way to currently verify values have been set properly but can validate application by trying to make a pattern."""
    valid_devices = [tbt.Device.ELECTRON_BEAM, tbt.Device.ION_BEAM]
    if patterning_device not in valid_devices:
        raise ValueError(
            f"Invalid patterning device of '{patterning_device}' requested, only '{[i for i in valid_devices]}' are valid."
        )
    microscope.patterning.clear_patterns()
    microscope.patterning.set_default_beam_type(beam_index=patterning_device.value)
    if application not in microscope.patterning.list_all_application_files():
        raise ValueError(
            f"Invalid application file on this system, there is no patterning application with name: '{application}'."
        )
    else:
        microscope.patterning.set_default_application_file(application)

    return True


@singledispatch
def create_pattern(
    geometry,
    microscope: tbt.Microscope,
    **kwargs: dict,
) -> bool:  # FIBRectanglePattern
    """"""
    _ = geometry
    __ = microscope
    ___ = kwargs
    raise NotImplementedError(f"No handler for type {type(geometry)}")


@create_pattern.register
def _(
    geometry: tbt.FIBRectanglePattern,
    microscope: tbt.Microscope,
    **kwargs: dict,
) -> tbt.as_dynamics.RectanglePattern:
    pattern = microscope.patterning.create_rectangle(
        center_x=geometry.center_um.x * Conversions.UM_TO_M,
        center_y=geometry.center_um.y * Conversions.UM_TO_M,
        width=geometry.width_um * Conversions.UM_TO_M,
        height=geometry.height_um * Conversions.UM_TO_M,
        depth=geometry.depth_um * Conversions.UM_TO_M,
    )
    pattern.scan_direction = geometry.scan_direction.value
    pattern.scan_type = geometry.scan_type.value

    return pattern


@create_pattern.register
def _(
    geometry: tbt.FIBRegularCrossSection,
    microscope: tbt.Microscope,
    **kwargs: dict,
) -> tbt.as_dynamics.RegularCrossSectionPattern:
    pattern = microscope.patterning.create_regular_cross_section(
        center_x=geometry.center_um.x * Conversions.UM_TO_M,
        center_y=geometry.center_um.y * Conversions.UM_TO_M,
        width=geometry.width_um * Conversions.UM_TO_M,
        height=geometry.height_um * Conversions.UM_TO_M,
        depth=geometry.depth_um * Conversions.UM_TO_M,
    )
    pattern.scan_direction = geometry.scan_direction.value
    pattern.scan_type = geometry.scan_type.value

    return pattern


@create_pattern.register
def _(
    geometry: tbt.FIBCleaningCrossSection,
    microscope: tbt.Microscope,
    **kwargs: dict,
) -> tbt.as_dynamics.CleaningCrossSectionPattern:
    pattern = microscope.patterning.create_cleaning_cross_section(
        center_x=geometry.center_um.x * Conversions.UM_TO_M,
        center_y=geometry.center_um.y * Conversions.UM_TO_M,
        width=geometry.width_um * Conversions.UM_TO_M,
        height=geometry.height_um * Conversions.UM_TO_M,
        depth=geometry.depth_um * Conversions.UM_TO_M,
    )
    pattern.scan_direction = geometry.scan_direction.value
    pattern.scan_type = geometry.scan_type.value

    return pattern


@create_pattern.register
def _(
    geometry: tbt.FIBStreamPattern,
    microscope: tbt.Microscope,
    **kwargs: dict,
) -> tbt.StreamPattern:
    """Stream patterns are only supported at 16 bit depth now, but this is generally too many points, so we upscale images as if we were creting a 12 bit stream file and correct the offset mathematically."""

    # run image_processing and check that mask file is created
    input_image_path = kwargs["kwargs"]["input_image_path"]
    image_processing(
        geometry=geometry,
        input_image_path=input_image_path,
    )

    # get mask
    mask_path = geometry.mask_file
    with pil_img.open(mask_path) as mask_img:
        width, height = mask_img.size
        mask = np.asarray(mask_img).astype(int)

    stream_def = tbt.StreamPatternDefinition()
    stream_def.bit_depth = tbt.StreamDepth.BITS_16  # only supported bit depth now
    dwell_time = geometry.dwell_us * Conversions.US_TO_S

    scale_factor = cs.Constants.stream_pattern_scale / width
    point_img = cv2.resize(
        mask,
        dsize=(int(width * scale_factor), int(height * scale_factor)),
        interpolation=cv2.INTER_NEAREST,
    )
    idx = np.where(point_img == 1)
    num_points = (
        len(idx[0]) + 2
    )  # top right and bottom left corners each have a point to make sure pattern is centered

    # stream pattern is defined by 4 values for each point
    # [x, y, dwell_time, flags]
    # flags = 1 --> blank beam
    # flags = 0 --> use beam
    stream_def.points = np.zeros(shape=(num_points, 4), dtype=object)
    stream_def.points[0] = [
        1,  # x (top left)
        cs.Constants.stream_pattern_y_shift,  # y (top left)
        dwell_time,  # dwell
        1,  # flag (1 means blank the beam)
    ]
    flags = 0
    for i in range(1, num_points - 1):  # start at first point
        x = idx[1][i - 1] * 16 + 1
        y = (
            idx[0][i - 1] * 16 + cs.Constants.stream_pattern_y_shift
        )  # + (0.17 * (2**stream_def.bit_depth))
        stream_def.points[i] = [x, y, dwell_time, flags]
    stream_def.points[-1] = [
        2**stream_def.bit_depth,  # x (bottom right)
        2**stream_def.bit_depth
        - cs.Constants.stream_pattern_y_shift,  # y (bottom right)
        dwell_time,  # dwell
        1,  # flag
    ]

    stream_def.repeat_count = geometry.repeats

    stream_pattern = microscope.patterning.create_stream(
        center_x=0.0,
        center_y=0.0,
        stream_pattern_definition=stream_def,
    )

    return stream_pattern


def image_processing(
    geometry: tbt.FIBStreamPattern,
    input_image_path: Path,
) -> bool:
    output = subprocess.run(
        [
            "python",
            (geometry.recipe_file).as_posix(), # recipe_file
            input_image_path.as_posix(), # input path,
            (geometry.mask_file).as_posix(), # outputpath,
        ],
        capture_output=True,
    )
    if output.returncode != 0:
        raise ValueError(
            f"Subprocess call for script {geometry.recipe_file} using executable 'python' did not execute correctly."
        )
    # check for mask file
    if not geometry.mask_file.exists():
        raise ValueError(
            f"Mask file at location {geometry.mask_file} should have been created by image processing recipe but does not exist. Please check your recipe_file script."
        )
    # TODO
    # save masks

    return True


# TODO add more complex patterning behavior
def mill_operation(
    step: tbt.Step,
    fib_settings: tbt.FIBSettings,
    general_settings: tbt.GeneralSettings,
    slice_number: int,
) -> bool:
    microscope = fib_settings.microscope

    shutter_control(microscope=microscope)
    # prepare beam
    img.imaging_device(microscope=microscope, beam=fib_settings.mill_beam)
    # set milling application and device

    prepare_milling(
        microscope=microscope,
        application=fib_settings.pattern.application,
    )

    # get expected path of the fib image
    if fib_settings.pattern.type != tbt.FIBPatternType.SELECTED_AREA:
        input_image_path = None
    else:
        input_image_path = Path.join(
            general_settings.exp_dir,
            step.name,
            f"{slice_number:04}.tif",
        )
        if not input_image_path.exists():
            raise ValueError(
                f"Ion image for selected area milling was not found at '{input_image_path}'."
            )

    # make the pattern
    pattern = create_pattern(
        fib_settings.pattern.geometry,
        microscope=microscope,
        kwargs={"input_image_path": input_image_path},
    )

    microscope.patterning.run()

    return True
