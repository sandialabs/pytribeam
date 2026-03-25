#!/usr/bin/python3
"""
Workflow Module
===============

This module contains functions for managing and executing the workflow of an experiment, including performing operations, setting up the experiment, and running the main experiment loop.

Functions
---------
perform_operation(step_settings, step: tbt.Step, general_settings: tbt.GeneralSettings, slice_number: int) -> bool
    Perform the operation for the specified step settings.

perform_operation(step_settings: tbt.ImageSettings, step: tbt.Step, general_settings: tbt.GeneralSettings, slice_number: int) -> bool
    Perform the image operation for the specified step settings.

perform_operation(step_settings: tbt.FIBSettings, step: tbt.Step, general_settings: tbt.GeneralSettings, slice_number: int) -> bool
    Perform the FIB operation for the specified step settings.

perform_operation(step_settings: tbt.CustomSettings, step: tbt.Step, general_settings: tbt.GeneralSettings, slice_number: int) -> bool
    Perform the custom operation for the specified step settings.

perform_operation(step_settings: tbt.EBSDSettings, step: tbt.Step, general_settings: tbt.GeneralSettings, slice_number: int) -> bool
    Perform the EBSD operation for the specified step settings.

perform_operation(step_settings: tbt.EDSSettings, step: tbt.Step, general_settings: tbt.GeneralSettings, slice_number: int) -> bool
    Perform the EDS operation for the specified step settings.

perform_operation(step_settings: tbt.LaserSettings, step: tbt.Step, general_settings: tbt.GeneralSettings, slice_number: int) -> bool
    Perform the laser operation for the specified step settings.

ebsd_eds_conflict_free(step_sequence: List[tbt.Step]) -> bool
    Check if the step sequence is free of EBSD and EDS conflicts.

pre_flight_check(yml_path: Path) -> tbt.ExperimentSettings
    Perform a pre-flight check for the experiment.

setup_experiment(yml_path: Path) -> tbt.ExperimentSettings
    Set up the experiment based on the YAML configuration.

perform_step(slice_number: int, step_number: int, experiment_settings: tbt.ExperimentSettings) -> bool
    Perform a step in the experiment.

run_experiment_cli(start_slice: int, start_step: int, yml_path: Path)
    Main loop for the experiment, accessed through the command line.
"""

# Default python modules
# from functools import singledispatch
import os
from pathlib import Path
import time
import warnings
import math
from typing import NamedTuple, List, Tuple
from functools import singledispatch
import subprocess

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
import pytribeam.stage as stage
import pytribeam.log as log
import pytribeam.laser as laser
import pytribeam.image as img
import pytribeam.fib as fib


@singledispatch
def perform_operation(
    step_settings,
    step: tbt.Step,
    general_settings: tbt.GeneralSettings,
    slice_number: int,
) -> bool:
    """
    Perform the operation for the specified step settings.

    This function performs the operation for the specified step settings, including validation.

    Parameters
    ----------
    step_settings : Any
        The step settings for the operation.
    step : tbt.Step
        The step object containing the operation settings.
    general_settings : tbt.GeneralSettings
        The general settings object.
    slice_number : int
        The slice number for the operation.

    Returns
    -------
    bool
        True if the operation is performed successfully.

    Raises
    ------
    NotImplementedError
        If no handler is available for the provided step settings type.
    """
    _ = step_settings
    __ = step
    ___ = general_settings
    ____ = slice_number
    raise NotImplementedError(f"No handler for type {type(step_settings)}")


@perform_operation.register
def _(
    step_settings: tbt.ImageSettings,
    step: tbt.Step,
    general_settings: tbt.GeneralSettings,
    slice_number: int,
) -> bool:
    """
    Perform the image operation for the specified step settings.

    Parameters
    ----------
    step_settings : tbt.ImageSettings
        The image settings for the operation.
    step : tbt.Step
        The step object containing the operation settings.
    general_settings : tbt.GeneralSettings
        The general settings object.
    slice_number : int
        The slice number for the operation.

    Returns
    -------
    bool
        True if the image operation is performed successfully.
    """
    return img.image_operation(
        step=step,
        image_settings=step.operation_settings,
        general_settings=general_settings,
        slice_number=slice_number,
    )


@perform_operation.register
def _(
    step_settings: tbt.FIBSettings,
    step: tbt.Step,
    general_settings: tbt.GeneralSettings,
    slice_number: int,
) -> bool:
    """
    Perform the FIB operation for the specified step settings.

    Parameters
    ----------
    step_settings : tbt.FIBSettings
        The FIB settings for the operation.
    step : tbt.Step
        The step object containing the operation settings.
    general_settings : tbt.GeneralSettings
        The general settings object.
    slice_number : int
        The slice number for the operation.

    Returns
    -------
    bool
        True if the FIB operation is performed successfully.
    """
    # collect image
    image_step = tbt.Step(
        type=tbt.StepType.IMAGE,
        name=step.name,
        number=step.number,
        frequency=step.frequency,
        stage=step.stage,
        operation_settings=step_settings.image,
    )
    type(image_step.operation_settings)
    perform_operation(
        image_step.operation_settings,
        step=image_step,
        general_settings=general_settings,
        slice_number=slice_number,
    )
    # mill pattern
    fib.mill_operation(
        step=step,
        fib_settings=step_settings,
        general_settings=general_settings,
        slice_number=slice_number,
    )

    return True


@perform_operation.register
def _(
    step_settings: tbt.CustomSettings,
    step: tbt.Step,
    general_settings: tbt.GeneralSettings,
    slice_number: int,
) -> bool:
    """
    Perform the custom operation for the specified step settings.

    Parameters
    ----------
    step_settings : tbt.CustomSettings
        The custom settings for the operation.
    step : tbt.Step
        The step object containing the operation settings.
    general_settings : tbt.GeneralSettings
        The general settings object.
    slice_number : int
        The slice number for the operation.

    Returns
    -------
    bool
        True if the custom operation is performed successfully.
    """
    # dump out .yml with experiment info
    slice_info_path = Path.joinpath(general_settings.exp_dir, "slice_info.yml")
    db = {"exp_dir": str(general_settings.exp_dir), "slice_number": slice_number}
    ut.dict_to_yml(db=db, file_path=slice_info_path)

    output = subprocess.run(
        [step_settings.executable_path, step_settings.script_path],
        capture_output=True,
    )
    stdout, stderr = output.stdout.decode("utf-8"), output.stderr.decode("utf-8")
    if stdout:
        print(f"\nCustom script output: {stdout}\n")

    if output.returncode != 0:
        if stderr:
            print(f"\nCustom script errors: {stderr}\n")
        raise ValueError(
            f"Subprocess call for script {step_settings.script_path} using executable {step_settings.executable_path} did not execute correctly."
        )

    slice_info_path.unlink()
    return True


@perform_operation.register
def _(
    step_settings: tbt.EBSDSettings,
    step: tbt.Step,
    general_settings: tbt.GeneralSettings,
    slice_number: int,
) -> bool:
    """
    Perform the EBSD operation for the specified step settings.

    Parameters
    ----------
    step_settings : tbt.EBSDSettings
        The EBSD settings for the operation.
    step : tbt.Step
        The step object containing the operation settings.
    general_settings : tbt.GeneralSettings
        The general settings object.
    slice_number : int
        The slice number for the operation.

    Returns
    -------
    bool
        True if the EBSD operation is performed successfully.
    """
    image_settings = step_settings.image
    microscope = image_settings.microscope

    # insert detector
    devices.insert_EBSD(microscope=microscope)
    if step_settings.enable_eds:
        devices.insert_EDS(microscope=microscope)

    # measure and log specimen current
    found_current_na = devices.specimen_current(microscope=microscope)
    log.specimen_current(
        step_number=step.number,
        step_name=step.name,
        slice_number=slice_number,
        log_filepath=general_settings.log_filepath,
        dataset_name=cs.Constants.specimen_current_dataset_name,
        specimen_current_na=found_current_na,
    )

    # take image
    img.image_operation(
        step=step,
        image_settings=image_settings,
        general_settings=general_settings,
        slice_number=slice_number,
    )

    # set dynamic focus/tilt correction
    dynamic_focus = image_settings.beam.settings.dynamic_focus
    tilt_correction = image_settings.beam.settings.tilt_correction
    img.beam_angular_correction(
        microscope=microscope,
        dynamic_focus=dynamic_focus,
        tilt_correction=tilt_correction,
    )

    # take map
    laser.map_ebsd(
        general_settings=general_settings,
        step_settings=step_settings,
        slice_number=slice_number,
        step=step,
    )

    # retract detector(s)
    devices.retract_EBSD(microscope=microscope)
    if step_settings.enable_eds:
        devices.retract_EDS(microscope=microscope)

    return True


@perform_operation.register
def _(
    step_settings: tbt.EDSSettings,
    step: tbt.Step,
    general_settings: tbt.GeneralSettings,
    slice_number: int,
) -> bool:
    """
    Perform the EDS operation for the specified step settings.

    Parameters
    ----------
    step_settings : tbt.EDSSettings
        The EDS settings for the operation.
    step : tbt.Step
        The step object containing the operation settings.
    general_settings : tbt.GeneralSettings
        The general settings object.
    slice_number : int
        The slice number for the operation.

    Returns
    -------
    bool
        True if the EDS operation is performed successfully.
    """
    image_settings = step_settings.image
    microscope = image_settings.microscope

    # insert detector
    devices.insert_EDS(microscope=microscope)

    # measure and log specimen current
    found_current_na = devices.specimen_current(microscope=microscope)
    log.specimen_current(
        step_number=step.number,
        step_name=step.name,
        slice_number=slice_number,
        log_filepath=general_settings.log_filepath,
        dataset_name=cs.Constants.specimen_current_dataset_name,
        specimen_current_na=found_current_na,
    )

    # take image
    img.image_operation(
        step=step,
        image_settings=image_settings,
        general_settings=general_settings,
        slice_number=slice_number,
    )

    # set dynamic focus/tilt correction
    dynamic_focus = image_settings.beam.settings.dynamic_focus
    tilt_correction = image_settings.beam.settings.tilt_correction
    img.beam_angular_correction(
        microscope=microscope,
        dynamic_focus=dynamic_focus,
        tilt_correction=tilt_correction,
    )

    # take map
    laser.map_eds()

    # retract detector
    devices.retract_EDS(microscope=microscope)

    return True


@perform_operation.register
def _(
    step_settings: tbt.LaserSettings,
    step: tbt.Step,
    general_settings: tbt.GeneralSettings,
    slice_number: int,
) -> bool:
    """
    Perform the laser operation for the specified step settings.

    Parameters
    ----------
    step_settings : tbt.LaserSettings
        The laser settings for the operation.
    step : tbt.Step
        The step object containing the operation settings.
    general_settings : tbt.GeneralSettings
        The general settings object.
    slice_number : int
        The slice number for the operation.

    Returns
    -------
    bool
        True if the laser operation is performed successfully.
    """
    return laser.laser_operation(
        step=step,
        general_settings=general_settings,
        slice_number=slice_number,
    )


# @perform_operation(tbt.StageSettings)
# def _(
#     step_settings,
#     step: tbt.Step,
#     log_filepath: Path,
# ) -> bool:
#     pass


def ebsd_eds_conflict_free(step_sequence: List[tbt.Step]) -> bool:
    """
    Check if the step sequence is free of EBSD and EDS conflicts.

    This function checks if the step sequence is free of EBSD and EDS conflicts.

    Parameters
    ----------
    step_sequence : List[tbt.Step]
        The step sequence to check.

    Returns
    -------
    bool
        True if the step sequence is free of EBSD and EDS conflicts.

    Raises
    ------
    ValueError
        If an EBSD or EDS conflict is found in the step sequence.
    """
    EBSD_EDS_conflict_msg = "Due to current limitations in 3rd party EBSD/EDS integration with the TriBeam, only one of these step types is allowed as only one map can be configured for an experiment, but EDS can be configured to be included with an EBSD type step. See User Guide for more details."

    found_EBSD = False
    found_EDS = False

    for step in step_sequence:
        if step.type == tbt.StepType.EBSD:
            if found_EDS == True:
                raise ValueError(
                    f"EBSD step found in sequence after EDS step was already defined. {EBSD_EDS_conflict_msg}"
                )
            found_EBSD = True

        if step.type == tbt.StepType.EDS:
            if found_EBSD == True:
                raise ValueError(
                    f"EDS step found in sequence after EBSD step was already defined. {EBSD_EDS_conflict_msg}"
                )
            found_EDS = True

    return True


def pre_flight_check(yml_path: Path) -> tbt.ExperimentSettings:
    """
    Perform a pre-flight check for the experiment.

    This function performs a pre-flight check for the experiment by validating the YAML configuration, connecting to the microscope, and validating the step sequence.

    Parameters
    ----------
    yml_path : Path
        The path to the YAML configuration file.

    Returns
    -------
    tbt.ExperimentSettings
        The validated experiment settings.

    Raises
    ------
    SystemError
        If there are issues with the EBSD or EDS camera, or if the laser control is not enabled.
    ValueError
        If the step sequence is not parsed correctly or if there are EBSD/EDS conflicts.
    """
    # get configuration from yml
    yml_version = ut.yml_version(yml_path)
    experiment_settings = ut.yml_to_dict(
        yml_path_file=yml_path,
        version=yml_version,
        required_keys=(
            "general",
            "config_file_version",
        ),
    )
    yml_format = ut.yml_format(version=yml_version)

    # get general settings and validate them
    general_db = ut.general_settings(
        exp_settings=experiment_settings, yml_format=yml_format
    )
    general_settings = factory.general(
        general_db=general_db,
        yml_format=yml_format,
    )

    # whether to enable EBSD and EDS control
    enable_EBSD = ut.enable_external_device(general_settings.EBSD_OEM)
    enable_EDS = ut.enable_external_device(general_settings.EDS_OEM)
    if enable_EBSD:
        status = devices.connect_EBSD()
        if status == tbt.RetractableDeviceState.ERROR:
            raise SystemError("EBSD camera is connected but in error state.")
        if (
            general_settings.EBSD_OEM == tbt.ExternalDeviceOEM.EDAX
            and general_settings.yml_version >= 1.1
        ):
            laser.ebsd_preflight(general_settings=general_settings)
    if enable_EDS:
        status = devices.connect_EDS()
        if status == tbt.RetractableDeviceState.ERROR:
            raise SystemError("EDS camera is connected but in error state.")

    # connect to microscope:
    connection = general_settings.connection
    microscope = tbt.Microscope()
    ut.connect_microscope(
        microscope=microscope,
        quiet_output=True,
        connection_host=connection.host,
        connection_port=connection.port,
    )

    # get step_count and validate settings
    num_steps = ut.step_count(exp_settings=experiment_settings, yml_format=yml_format)
    step_sequence = []  # empty list of tbt.Step type objects
    for step in range(1, num_steps + 1):
        step_name, step_settings = ut.step_settings(
            exp_settings=experiment_settings,
            step_number_key=yml_format.step_number_key,
            step_number_val=step,
            yml_format=yml_format,
        )
        if not step_name:
            raise KeyError(
                f"Step name for step {step} of {num_steps} is empty. Please provide a unique name for each step in your configuration."
            )
        step_type = ut.step_type(
            settings=step_settings,
            yml_format=yml_format,
        )

        # validate connections for specific step types
        if step_type == tbt.StepType.LASER:
            laser_enabled = laser.laser_connected()
            if not laser_enabled:
                raise SystemError(
                    f"Step name '{step_name}' is a Laser step type but Laser control is not currently enabled. Ensure TFS laser API is installed, Laser Control application is open."
                )
        if (step_type == tbt.StepType.EDS) and (not enable_EDS):
            raise SystemError(
                f"Step name '{step_name}' is an EDS step type but EDS control is not currently enabled."
            )
        if (step_type == tbt.StepType.EBSD) and (not enable_EBSD):
            raise SystemError(
                f"Step name '{step_name}' is an EDS step type but EDS control is not currently enabled."
            )
        # if (step_type == tbt.StepType.EBSD_EDS) and (
        #     (not enable_EBSD) or (not enable_EDS)
        # ):
        #     raise SystemError(
        #         f"Step name '{step_name}' is an EBSD_EDS step type but EBSD and EDS control are not both currently enabled."
        #     )
        # create the step settings
        step = factory.step(
            microscope=microscope,
            step_name=step_name,
            step_settings=step_settings,
            general_settings=general_settings,
            yml_format=yml_format,
        )

        step_sequence.append(step)

    if len(step_sequence) != num_steps:
        raise ValueError(
            f"Settings not parsed correctly, expected {num_steps} but only {len(step_sequence)} have been parsed."
        )

    # ensure only EBSD or EDS step type exists
    ebsd_eds_conflict_free(step_sequence=step_sequence)

    experiment_settings = tbt.ExperimentSettings(
        microscope=microscope,
        general_settings=general_settings,
        step_sequence=step_sequence,
        enable_EBSD=enable_EBSD,
        enable_EDS=enable_EDS,
    )
    # print("Pre-flight check complete.")
    return experiment_settings


def setup_experiment(
    yml_path: Path,
) -> tbt.ExperimentSettings:
    """
    Set up the experiment based on the YAML configuration.

    This function sets up the experiment by validating the YAML configuration, creating the log file, linking the stage, and retracting all devices.

    Parameters
    ----------
    yml_path : Path
        The path to the YAML configuration file.

    Returns
    -------
    tbt.ExperimentSettings
        The experiment settings.
    """
    # validate yml
    experiment_settings = pre_flight_check(yml_path=yml_path)

    log_filepath = experiment_settings.general_settings.log_filepath
    log.create_file(log_filepath)

    # link stage to free working distance
    experiment_settings.microscope.specimen.stage.link()

    # retract all devices
    print("\tRetracting all devices...")
    devices.retract_all_devices(
        microscope=experiment_settings.microscope,
        enable_EBSD=experiment_settings.enable_EBSD,
        enable_EDS=experiment_settings.enable_EDS,
    )

    return experiment_settings


def perform_step(
    slice_number: int,
    step_number: int,
    experiment_settings: tbt.ExperimentSettings,
):
    """
    Perform a step in the experiment.

    This function performs a step in the experiment based on the slice number, step number, and experiment settings.

    Parameters
    ----------
    slice_number : int
        The slice number for the step.
    step_number : int
        The step number for the experiment.
    experiment_settings : tbt.ExperimentSettings
        The experiment settings.

    Returns
    -------
    bool
        True if the step is performed successfully.
    """
    # # breakout experiment settings elements
    microscope = experiment_settings.microscope
    general_settings = experiment_settings.general_settings
    step_sequence = experiment_settings.step_sequence
    enable_EBSD = experiment_settings.enable_EBSD
    enable_EDS = experiment_settings.enable_EDS

    # get operation settings, execute operation.
    operation = step_sequence[step_number - 1]  # list is 0-indexed
    print(
        f"Slice {slice_number}, Step {step_number} of {general_settings.step_count}, '{operation.name}', a {operation.type.value} type step."
    )
    if (
        slice_number - 1
    ) % operation.frequency != 0:  # slices start at 1, perform all steps on slice 1.
        print(
            f"\tStep frequency is every {operation.frequency} slices, starting on slice 1. Skipping step on this slice.\n"
        )
        return

    # log step_start position
    log.position(
        step_number=step_number,
        step_name=operation.name,
        slice_number=slice_number,
        log_filepath=general_settings.log_filepath,
        dataset_name=cs.Constants.pre_position_dataset_name,
        current_position=factory.active_stage_position_settings(
            microscope=microscope,
        ),
    )

    # retract all devices
    print("\tRetracting all devices...")
    # with ut.nostdout():
    devices.retract_all_devices(
        microscope=microscope,
        enable_EBSD=enable_EBSD,
        enable_EDS=enable_EDS,
    )
    print("\tDevices retracted.")

    # move stage to starting position for slice
    stage.step_start_position(
        microscope=microscope,
        slice_number=slice_number,
        operation=operation,
        general_settings=general_settings,
    )

    # perform specific operation
    perform_operation(
        operation.operation_settings,
        step=operation,
        general_settings=general_settings,
        slice_number=slice_number,
    )

    # log step end position
    log.position(
        step_number=step_number,
        step_name=operation.name,
        slice_number=slice_number,
        log_filepath=general_settings.log_filepath,
        dataset_name=cs.Constants.post_position_dataset_name,
        current_position=factory.active_stage_position_settings(
            microscope=microscope,
        ),
    )

    # retract all devices
    print("\tRetracting all devices...")
    # with ut.nostdout():
    devices.retract_all_devices(
        microscope=microscope,
        enable_EBSD=enable_EBSD,
        enable_EDS=enable_EDS,
    )
    print("\tDevices retracted. Step Complete.\n")


def run_experiment_cli(
    start_slice: int,
    start_step: int,
    yml_path: Path,
):
    """
    Main loop for the experiment, accessed through the command line.

    This function runs the main loop for the experiment based on the specified start slice, start step, and YAML configuration file.

    Parameters
    ----------
    start_slice : int
        The starting slice number for the experiment.
    start_step : int
        The starting step number for the experiment.
    yml_path : Path
        The path to the YAML configuration file.

    Returns
    -------
    None
    """

    experiment_settings = setup_experiment(yml_path=yml_path)

    # warn user of any EBSD/EDS lack of control
    warning_text = """is not enabled, you will not have access to safety
    checking and these modalities during data collection. Please ensure 
    this detector is retracted before proceeding."""
    if not experiment_settings.enable_EBSD:
        print(f"\nWARNING: EBSD {warning_text}")
        if not ut.yes_no("Continue?"):
            print("\nExiting now...")
            exit()
    if not experiment_settings.enable_EDS:
        print(f"\nWARNING: EDS {warning_text}")
        if not ut.yes_no("Continue?"):
            print("\nExiting now...")
            exit()

    # main loop
    log.experiment_settings(
        slice_number=start_slice,
        step_number=start_step,
        log_filepath=experiment_settings.general_settings.log_filepath,
        yml_path=yml_path,
    )
    num_steps = len(experiment_settings.step_sequence)
    print(
        f"\n\nBeginning serial sectioning experiment on slice {start_slice}, step {start_step} of {num_steps}.\n"
    )

    for slice_number in range(
        start_slice, experiment_settings.general_settings.max_slice_number + 1
    ):  # inclusive of max slice number
        for step_number in range(start_step, num_steps + 1):  # list is 1-indexed
            perform_step(
                slice_number=slice_number,
                step_number=step_number,
                experiment_settings=experiment_settings,
            )

        # reset start_step to 1 at end of slice
        start_step = 1

    ut.disconnect_microscope(
        microscope=experiment_settings.microscope,
        quiet_output=True,
    )

    print("\n\nExperiment complete.")


if __name__ == "__main__":
    pass
