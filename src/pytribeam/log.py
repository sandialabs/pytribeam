#!/usr/bin/python3

# Default python modules
# from functools import singledispatch
import os
from pathlib import Path
import warnings
import math
from typing import NamedTuple, List, Tuple
from functools import singledispatch
import time
import datetime

# Autoscript included modules
import numpy as np
from matplotlib import pyplot as plt
import h5py
import pandas as pd

# 3rd party module

# Local scripts
from pytribeam.constants import Constants
import pytribeam.types as tbt


def create_file(path: Path) -> bool:
    if not path.is_file():
        log = h5py.File(path, "w")
        log.close()
        if path.is_file():
            print(f'Logfile created at "{path}".')
    if path.is_file():
        return True
    raise ValueError(f'Unable to create log file at location "{path}".')


def current_time() -> tbt.TimeStamp:
    now = datetime.datetime.now()
    human_readable = now.strftime("%m/%d/%Y %H:%M:%S")
    unix_time = int(now.timestamp())
    time = tbt.TimeStamp(human_readable=human_readable, unix=unix_time)
    return time


def yml_from_log(
    log_path_h5: Path,
    output_path_yml: Path,
    row: int,
    config_field: str = "Config File",
) -> bool:
    # TODO enforce file formats on inputs
    with h5py.File(log_path_h5, "r") as file:
        data = np.array(file[Constants.settings_dataset_name][:])
    settings = data[row][Constants.settings_dtype.names.index(config_field)].decode(
        "utf-8"
    )

    with open(output_path_yml, "w") as file:
        file.write(settings)

    return True


def experiment_settings(
    slice_number: int,
    step_number: int,
    log_filepath: Path,
    yml_path: Path,
) -> bool:
    dataset_name = Constants.settings_dataset_name
    settings_dtype = Constants.settings_dtype
    time = current_time()

    with open(yml_path, "r") as yml_file:
        yml_lines = yml_file.readlines()

    yml_data = " ".join([line for line in yml_lines])

    if not log_filepath.exists():
        log_filepath.touch()

    with h5py.File(log_filepath, "r+") as log:
        if not dataset_name in log:
            settings = log.create_dataset(
                dataset_name,
                (0,),
                settings_dtype,
                maxshape=(None,),
            )
        dataset = log[dataset_name]
        settings_data = np.array(
            [
                (
                    slice_number,
                    step_number,
                    yml_data,
                    time.human_readable,
                    time.unix,
                )
            ],
            settings_dtype,
        )
        # add one row to table
        dataset.resize(dataset.shape[0] + 1, axis=0)
        dataset[-1:] = settings_data

    return True


def position(
    step_number: int,
    step_name: str,
    slice_number: int,
    log_filepath: Path,
    dataset_name: str,
    current_position: tbt.StagePositionUser,
) -> bool:
    print("\tLogging current position...")
    dataset_location = f"{step_number:02d}_{step_name}/{dataset_name}"
    time = current_time()

    with h5py.File(log_filepath, "r+") as file:
        if not dataset_location in file:
            position = file.create_dataset(
                dataset_location,
                (0,),
                Constants.position_dtype,
                maxshape=(None,),
            )
            position.attrs["X Units"] = np.string_("[mm]")
            position.attrs["Y Units"] = np.string_("[mm]")
            position.attrs["Z Units"] = np.string_("[mm]")
            position.attrs["T Units"] = np.string_("[degrees]")
            position.attrs["R Units"] = np.string_("[degrees]")

        dataset = file[dataset_location]
        position_data = np.array(
            [
                (
                    slice_number,
                    round(current_position.x_mm, 6),
                    round(current_position.y_mm, 6),
                    round(current_position.z_mm, 6),
                    round(current_position.t_deg, 6),
                    round(current_position.r_deg, 6),
                    time.human_readable,
                    time.unix,
                )
            ],
            Constants.position_dtype,
        )
        # add one row to table
        dataset.resize(dataset.shape[0] + 1, axis=0)
        dataset[-1:] = position_data

    return True


def laser_power(
    step_number: int,
    step_name: str,
    slice_number: int,
    log_filepath: Path,
    dataset_name: str,
    power_w: float,
) -> bool:
    print("\tLogging laser power...")
    dataset_location = f"{step_number:02d}_{step_name}/{dataset_name}"
    time = current_time()

    with h5py.File(log_filepath, "r+") as file:
        if not dataset_location in file:
            laser_power = file.create_dataset(
                dataset_location,
                (0,),
                Constants.laser_power_dtype,
                maxshape=(None,),
            )
            laser_power.attrs["Units"] = np.string_("[W]")

        dataset = file[dataset_location]
        laser_power_data = np.array(
            [
                (
                    slice_number,
                    round(power_w, 6),
                    time.human_readable,
                    time.unix,
                )
            ],
            Constants.laser_power_dtype,
        )
        # add one row to table
        dataset.resize(dataset.shape[0] + 1, axis=0)
        dataset[-1:] = laser_power_data


def specimen_current(
    step_number: int,
    step_name: str,
    slice_number: int,
    log_filepath: Path,
    dataset_name: str,
    specimen_current_na: float,
) -> bool:
    print("\tLogging sample current...")
    dataset_location = f"{step_number:02d}_{step_name}/{dataset_name}"
    time = current_time()

    with h5py.File(log_filepath, "r+") as file:
        if not dataset_location in file:
            specimen_current = file.create_dataset(
                dataset_location,
                (0,),
                Constants.specimen_current_dtype,
                maxshape=(None,),
            )
            specimen_current.attrs["Units"] = np.string_("[nA]")

        dataset = file[dataset_location]
        specimen_current_data = np.array(
            [
                (
                    slice_number,
                    round(specimen_current_na, 6),
                    time.human_readable,
                    time.unix,
                )
            ],
            Constants.specimen_current_dtype,
        )
        # add one row to table
        dataset.resize(dataset.shape[0] + 1, axis=0)
        dataset[-1:] = specimen_current_data
    print("\tLogging sample current complete...")


if __name__ == "__main__":
    pass
