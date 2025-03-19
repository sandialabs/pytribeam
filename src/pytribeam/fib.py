#!/usr/bin/python3
"""
FIB Module
==========

This module contains functions for performing various operations related
to Focused Ion Beam (FIB) milling, including preparing the microscope
for milling, creating patterns, and performing milling operations.

Functions
---------
application_files(microscope: tbt.Microscope) -> List[str]
    Get the list of application files from the current microscope.

shutter_control(microscope: tbt.Microscope) -> None
    Ensure auto control is set on the e-beam shutter. Manual control is
    not currently offered.

prepare_milling(microscope: tbt.Microscope, application: str,
                patterning_device: tbt.Device = tbt.Device.ION_BEAM) -> bool
    Clear old patterns, assign patterning to ion beam by default,
    and load the application.

create_pattern(geometry, microscope: tbt.Microscope, **kwargs: dict) -> bool
    Create a pattern on the microscope based on the provided geometry.

create_pattern(geometry: tbt.FIBRectanglePattern,
               microscope: tbt.Microscope, **kwargs: dict) 
               -> tbt.as_dynamics.RectanglePattern
    Create a rectangle pattern on the microscope.

create_pattern(geometry: tbt.FIBRegularCrossSection, 
               microscope: tbt.Microscope, **kwargs: dict) 
               -> tbt.as_dynamics.RegularCrossSectionPattern
    Create a regular cross-section pattern on the microscope.

create_pattern(geometry: tbt.FIBCleaningCrossSection,
               microscope: tbt.Microscope, **kwargs: dict) 
               -> tbt.as_dynamics.CleaningCrossSectionPattern
    Create a cleaning cross-section pattern on the microscope.

create_pattern(geometry: tbt.FIBStreamPattern,
               microscope: tbt.Microscope, **kwargs: dict) 
               -> tbt.StreamPattern
    Create a stream pattern on the microscope.

image_processing(geometry: tbt.FIBStreamPattern,
                 input_image_path: Path) -> bool
    Perform image processing for FIB stream pattern.

mill_operation(step: tbt.Step, fib_settings: tbt.FIBSettings,
               general_settings: tbt.GeneralSettings,
               slice_number: int) -> bool
    Perform a milling operation based on the provided step and settings.
"""
# Default python modules
from functools import singledispatch
from pathlib import Path
import warnings
from typing import List
import subprocess

# Autoscript included modules
from PIL import Image as pil_img
import cv2
import numpy as np

# 3rd party module

# Local scripts
import pytribeam.constants as cs
from pytribeam.constants import Conversions
import pytribeam.types as tbt
import pytribeam.image as img


def application_files(microscope: tbt.Microscope) -> List[str]:
    """
    Get the list of application files from the current microscope.

    This function retrieves the list of application files available on
    the current microscope, removes any "None" entries, and sorts the
    list.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object from which to retrieve the application
        files.

    Returns
    -------
    List[str]
        A sorted list of application files available on the microscope.
    """
    apps = microscope.patterning.list_all_application_files()

    # Remove "None" entry
    while "None" in apps:
        apps.remove("None")
    apps.sort(key=str.casefold)

    return apps


def shutter_control(microscope: tbt.Microscope) -> None:
    """
    Ensure auto control is set on the e-beam shutter. Manual control is
    not currently offered.

    This function checks if the e-beam protective shutter is installed
    and sets its mode to automatic if it is not already set. If the
    shutter cannot be set to automatic mode, a SystemError is raised.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to control the e-beam shutter.

    Raises
    ------
    SystemError
        If the e-beam shutter is installed but cannot be set to
        automatic mode.

    Warnings
    --------
    UserWarning
        If the e-beam shutter is not installed or if it is set to
        automatic mode.
    """
    shutter = microscope.beams.electron_beam.protective_shutter
    if not shutter.is_installed:
        warnings.warn(
            "Protective E-beam shutter not installed on this system."
        )
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
    """
    Clear old patterns, assign patterning to ion beam by default, and
    load the application.

    This function clears old patterns, assigns the patterning device to
    the specified beam (ion beam by default), and loads the specified
    application. It validates the patterning device and application
    file.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object for which to prepare milling.
    application : str
        The name of the application file to load.
    patterning_device : tbt.Device, optional
        The device to use for patterning (default is
        tbt.Device.ION_BEAM).

    Returns
    -------
    bool
        True if the preparation is successful.

    Raises
    ------
    ValueError
        If the patterning device is invalid or if the application file
        is not found on the system.
    """
    valid_devices = [tbt.Device.ELECTRON_BEAM, tbt.Device.ION_BEAM]
    if patterning_device not in valid_devices:
        raise ValueError(
            f"Invalid patterning device of '{patterning_device}' requested, only '{[i for i in valid_devices]}' are valid."
        )
    microscope.patterning.clear_patterns()
    microscope.patterning.set_default_beam_type(
        beam_index=patterning_device.value
    )
    if application not in microscope.patterning.list_all_application_files():
        raise ValueError(
            f"Invalid application file on this system, there is no patterning application with name: '{application}'."
        )
    microscope.patterning.set_default_application_file(application)

    return True


@singledispatch
def create_pattern(
    geometry,
    microscope: tbt.Microscope,
    **kwargs: dict,
) -> bool:  # FIBRectanglePattern
    """
    Create a pattern on the microscope based on the provided geometry.

    This function creates a pattern on the microscope based on the
    provided geometry. It is a generic function that raises a
    NotImplementedError if no handler is available for the provided
    geometry type.

    Parameters
    ----------
    geometry : Any
        The geometry of the pattern to create.
    microscope : tbt.Microscope
        The microscope object on which to create the pattern.
    kwargs : dict
        Additional keyword arguments.

    Returns
    -------
    bool
        True if the pattern is created successfully.

    Raises
    ------
    NotImplementedError
        If no handler is available for the provided geometry type.
    """
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
    """
    Create a rectangle pattern on the microscope.

    Parameters
    ----------
    geometry : tbt.FIBRectanglePattern
        The geometry of the rectangle pattern to create.
    microscope : tbt.Microscope
        The microscope object on which to create the pattern.
    kwargs : dict
        Additional keyword arguments.

    Returns
    -------
    tbt.as_dynamics.RectanglePattern
        The created rectangle pattern.
    """
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
    """
    Create a regular cross-section pattern on the microscope.

    Parameters
    ----------
    geometry : tbt.FIBRegularCrossSection
        The geometry of the regular cross-section pattern to create.
    microscope : tbt.Microscope
        The microscope object on which to create the pattern.
    kwargs : dict
        Additional keyword arguments.

    Returns
    -------
    tbt.as_dynamics.RegularCrossSectionPattern
        The created regular cross-section pattern.
    """
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
    """
    Create a cleaning cross-section pattern on the microscope.

    Parameters
    ----------
    geometry : tbt.FIBCleaningCrossSection
        The geometry of the cleaning cross-section pattern to create.
    microscope : tbt.Microscope
        The microscope object on which to create the pattern.
    kwargs : dict
        Additional keyword arguments.

    Returns
    -------
    tbt.as_dynamics.CleaningCrossSectionPattern
        The created cleaning cross-section pattern.
    """
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
    """
    Create a stream pattern on the microscope.

    Parameters
    ----------
    geometry : tbt.FIBStreamPattern
        The geometry of the stream pattern to create.
    microscope : tbt.Microscope
        The microscope object on which to create the pattern.
    kwargs : dict
        Additional keyword arguments.

    Returns
    -------
    tbt.StreamPattern
        The created stream pattern.
    """

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
    stream_def.bit_depth = (
        tbt.StreamDepth.BITS_16
    )  # only supported bit depth now
    dwell_time = geometry.dwell_us * Conversions.US_TO_S

    scale_factor = cs.Constants.stream_pattern_scale / width
    point_img = cv2.resize(
        mask,
        dsize=(int(width * scale_factor), int(height * scale_factor)),
        interpolation=cv2.INTER_NEAREST,
    )
    idx = np.where(point_img == 1)
    # top right and bottom left corners each have a point to make sure
    # pattern is centered
    num_points = len(idx[0]) + 2

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
    """
    Perform image processing for FIB stream pattern.

    This function runs an image processing script specified by the
    `recipe_file` in the `geometry` object, using the input image path
    and outputting the mask file.

    Parameters
    ----------
    geometry : tbt.FIBStreamPattern
        The geometry of the FIB stream pattern, including the
        `recipe_file` and `mask_file`.
    input_image_path : Path
        The path to the input image.

    Returns
    -------
    bool
        True if the image processing is successful.

    Raises
    ------
    ValueError
        If the subprocess call for the script does not execute correctly
        or if the mask file is not created.
    """
    output = subprocess.run(
        [
            "python",
            (geometry.recipe_file).as_posix(),  # recipe_file
            input_image_path.as_posix(),  # input path,
            (geometry.mask_file).as_posix(),  # outputpath,
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
    """
    Perform a milling operation based on the provided step and settings.

    This function performs a milling operation using the specified step,
    FIB settings, general settings, and slice number.

    Parameters
    ----------
    step : tbt.Step
        The step object containing the operation settings.
    fib_settings : tbt.FIBSettings
        The FIB settings object containing the microscope and pattern
        settings.
    general_settings : tbt.GeneralSettings
        The general settings object.
    slice_number : int
        The slice number for the operation.

    Returns
    -------
    bool
        True if the milling operation is successful.

    Raises
    ------
    ValueError
        If the ion image for selected area milling is not found.
    """
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
        input_image_path = (general_settings.exp_dir).joinpath(
            step.name,
            f"{slice_number:04}.tif",
        )
        if not input_image_path.exists():
            raise ValueError(
                f"Ion image for selected area milling was not found at '{input_image_path}'."
            )

    # make the pattern
    create_pattern(
        fib_settings.pattern.geometry,
        microscope=microscope,
        kwargs={"input_image_path": input_image_path},
    )

    microscope.patterning.run()

    return True
