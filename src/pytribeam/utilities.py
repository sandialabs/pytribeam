#!/usr/bin/python3

# Default python modules
import os
from pathlib import Path
import time
import warnings
import math
from typing import Dict, NamedTuple, Tuple, Any, List
from enum import Enum, IntEnum
import platform
import pytest
from functools import singledispatch
import shutil

# # Autoscript modules
import yaml
import contextlib
import sys
from pandas import json_normalize

# # # 3rd party module
# from schema import Schema, And, Use, Optional, SchemaError

# # Local scripts
import pytribeam.types as tbt

# import pytribeam.constants as cs
from pytribeam.constants import Constants


@singledispatch
def beam_type(beam) -> property:
    """Returns beam property object as ion and electron beams have same internal hierarchy"""
    _ = beam  # no operation
    raise NotImplementedError()


@beam_type.register
def _(beam: tbt.ElectronBeam, microscope: tbt.Microscope) -> property:
    """Returns electron beam property object"""
    return microscope.beams.electron_beam


@beam_type.register
def _(beam: tbt.IonBeam, microscope: tbt.Microscope) -> property:
    """Returns ion beam property object"""
    return microscope.beams.ion_beam


def connect_microscope(
    microscope: tbt.Microscope,
    quiet_output: bool = True,
    connection_host: str = None,
    connection_port: int = None,
):
    """Connects to the microscope with option to suppress printout"""

    # TODO clean up inner function
    def connect(
        microscope: tbt.Microscope,
        connection_host: str = None,
        connection_port: int = None,
    ) -> bool:
        if connection_port is not None:
            microscope.connect(connection_host, connection_port)
        elif connection_host is not None:
            microscope.connect(connection_host)
        else:
            microscope.connect()

    if quiet_output:
        with nostdout():
            connect(
                microscope=microscope,
                connection_host=connection_host,
                connection_port=connection_port,
            )
    else:
        connect(
            microscope=microscope,
            connection_host=connection_host,
            connection_port=connection_port,
        )

    if microscope.server_host is not None:
        return True
    else:
        raise ConnectionError(
            f"Connection failed with connection_host of '{connection_host}' and  connection_port of '{connection_port}' microscope not connected."
        )


def dict_to_yml(db: dict, file_path: Path) -> Path:
    """
    Converts dict to yaml
    """
    with open(file_path, "w", encoding="utf-8") as out_file:
        yaml.dump(
            db,
            out_file,
            default_flow_style=False,
            sort_keys=False,
        )

    return file_path


def disconnect_microscope(
    microscope: tbt.Microscope,
    quiet_output: bool = True,
):
    """Disconnects from the microscope with option to suppress printout"""
    if quiet_output:
        with nostdout():
            microscope.disconnect()
    else:
        microscope.disconnect()

    if microscope.server_host is None:
        return True
    else:
        raise ConnectionError("Disconnection failed, microscope still connected")


def general_settings(exp_settings: dict, yml_format: tbt.YMLFormat) -> dict:
    """Grabs general experiment settings from a .yml and returns them as a dictionary"""
    general_key = yml_format.general_section_key
    return exp_settings[general_key]


def step_type(settings: dict, yml_format: tbt.YMLFormat) -> tbt.StepType:
    """determine step type for an specific step settings dictioanry"""
    step_type = tbt.StepType(
        settings[yml_format.step_general_key][yml_format.step_type_key]
    )

    return step_type


def in_interval(val: float, limit: tbt.Limit, type: tbt.IntervalType) -> bool:
    """Tests where a value is within an interval, with interval type (close, open, half-open, etc. defined by enumerated IntervalType)

    Args:
        val: The input value to be compared to against min and max.
        limit: The bounds of the interval
        type: The type of interval

    Returns
        True if winthin interval, False otherwise"""
    if type == tbt.IntervalType.OPEN:
        return (val > limit.min) and (val < limit.max)
    if type == tbt.IntervalType.CLOSED:
        return (val >= limit.min) and (val <= limit.max)
    if type == tbt.IntervalType.LEFT_OPEN:
        return (val > limit.min) and (val <= limit.max)
    if type == tbt.IntervalType.RIGHT_OPEN:
        return (val >= limit.min) and (val < limit.max)


def gen_dict_extract(key, var):
    if hasattr(var, "items"):
        for k, v in var.items():
            if k == key:
                yield v
            if isinstance(v, dict):
                for result in gen_dict_extract(key, v):
                    yield result
            elif isinstance(v, list):
                for d in v:
                    for result in gen_dict_extract(key, d):
                        yield result
    # return v, result


# def list_enum_to_string(list: List[Enum]) -> List[str]:
#     """Converts list of enum to strings"""
#     return [str(i.value) for i in list]


def nested_dictionary_location(d: dict, key: str, value: Any) -> List[str]:
    """Finds nested location of key-value pair in dictionary, returns a list of key values
    from highest to lowest level of nested dictionaries. Checks if key value pair is found
    """
    nesting = nested_find_key_value_pair(d=d, key=key, value=value)
    if nesting is None:
        raise KeyError(
            f'Key : value pair of "{key} : {value}" not found in the provided dictionary.'
        )
    return nesting


def nested_find_key_value_pair(d: dict, key: str, value: Any) -> List[str]:
    """Finds key value pair in nested dictionary, returns a list of key
    values from highest to lowest level of nested dictionaries"""
    for k, v in d.items():
        if k == key:
            if v == value:
                return [k]
        if isinstance(v, dict):
            p = nested_find_key_value_pair(v, key, value)
            if p:
                return [k] + p


def _flatten(dictionary: dict) -> dict:
    """Flattens a dictionary using pandas, which can be slow on large dictionaries.

    From https://stackoverflow.com/questions/6027558/flatten-nested-dictionaries-compressing-keys
    """
    data_frame = json_normalize(dictionary, sep="_")
    db_flat = data_frame.to_dict(orient="records")[0]
    return db_flat


def none_value_dictionary(dictionary: dict) -> bool:
    """Return true if all values in dictionary are None, false otherwise."""
    # flatten the dictionary first
    db_flat = _flatten(dictionary)
    return all([v is None for v in db_flat.values()])


@contextlib.contextmanager
def nostdout():
    """Creates dummy file to suppress output"""
    save_stdout = sys.stdout
    sys.stdout = tbt.DummyFile()
    yield
    sys.stdout = save_stdout


def step_count(
    exp_settings: dict,
    yml_format: tbt.YMLFormatVersion,
):
    """Determine maximum step number from a settings dictionary, as specified by the step_number_key"""

    step_number_key = yml_format.step_number_key
    non_step_sections = yml_format.non_step_section_count

    # make sure dict from yml has correct section count
    # (steps should all be in one section)
    total_sections = len(exp_settings)
    if total_sections != non_step_sections + 1:
        raise ValueError(
            f"Invalid .yml file, {total_sections} sections were found but the input .yml should have {non_step_sections + 1} sections. Please verify that all top-level keys in the .yml have unique strings and that all steps are contained in a single top-level section."
        )

    expected_step_count = exp_settings[yml_format.general_section_key][
        yml_format.step_count_key
    ]

    found_step_count = 0
    while True:
        try:
            nested_dictionary_location(
                d=exp_settings,
                key=step_number_key,
                value=found_step_count + 1,
            )
        except KeyError:
            break
        found_step_count += 1

    # validate number of steps found with steps read by YAML loader
    # TODO YAML safeloader will ignore duplicate top level keys, so this check relies on unique step numbers in ascending order (no gaps) to be found.

    if expected_step_count != found_step_count:
        raise ValueError(
            f"Invalid .yml file, {found_step_count} steps were found but the input .yml should have {expected_step_count} steps from the general setting key '{yml_format.step_count_key}' within the '{yml_format.general_section_key}' section. Please verify that all step_name keys in the .yml have unique strings and that step numbers are continuously-increasing positive integers starting at 1."
        )

    return found_step_count


def step_settings(
    exp_settings: dict,
    step_number_key: str,
    step_number_val: int,
    yml_format: tbt.YMLFormatVersion,
) -> Tuple[str, dict]:
    """Grabs specific step settings from an experimental dictionary and
    returns them as a dictionary along with the user-defined step name"""

    nested_locations = nested_dictionary_location(
        d=exp_settings,
        key=step_number_key,
        value=step_number_val,
    )
    ### top level dictionary key name is first index, need key name nested within it (second level, index = 1)
    step_name = nested_locations[1]
    step_section_key = yml_format.step_section_key
    return step_name, exp_settings[step_section_key][step_name]


def valid_microscope_connection(host: str, port: str) -> bool:
    """Determines if microscope connection can be made, disconnects if a connection can be made"""
    microscope = tbt.Microscope()
    if connect_microscope(
        microscope=microscope,
        quiet_output=True,
        connection_host=host,
        connection_port=port,
    ):
        if disconnect_microscope(
            microscope=microscope,
            quiet_output=True,
        ):
            return True
    return False


def enable_external_device(oem: tbt.ExternalDeviceOEM) -> bool:
    """Determines whether to enable External Device Control.
    Device must be a member of the ExternalDeviceOEM enum and not equal to ExternalDeviceOEM.NONE to enable control
    """
    if not isinstance(oem, tbt.ExternalDeviceOEM):
        raise NotImplementedError(
            f"Unsupported type of {type(oem)}, only 'ExternalDeviceOEM' types are supported."
        )
    if oem != tbt.ExternalDeviceOEM.NONE:
        return True
    return False


def valid_enum_entry(obj: Any, check_type: Enum) -> bool:
    """Determines if object is member of an Enum class"""
    return obj in check_type._value2member_map_


def yml_format(version: float) -> tbt.YMLFormatVersion:
    """returns YMLFile format for a given version"""
    supported_versions = [file.version for file in tbt.YMLFormatVersion]
    if not version in supported_versions:
        raise NotImplementedError(
            f'Unsupported YML file version for version "{version}". Valid formats include: {[i.value for i in tbt.YMLFormatVersion]}'
        )
    yml_file_idx = supported_versions.index(version)
    yml_format = list(tbt.YMLFormatVersion)[yml_file_idx]
    return yml_format


def yml_to_dict(
    *, yml_path_file: Path, version: float, required_keys: Tuple[str, ...]
) -> Dict:
    """Given a valid Path to a yml input file, read it in and return the
    result as a dictionary.

    Args:
        yml_path_file: The fully pathed location to the input file.
        version: The version of the yml in x.y format.
        required_keys: The key(s) that must be in the yml file for conversion
            to a dictionary to occur.

    Returns:
        The .yml file represented as a dictionary.
    """

    # Compared to the lower() method, the casefold() method is stronger.
    # It will convert more characters into lower case, and will find more
    # matches on comparison of two strings that are both are converted
    # using the casefold() method.
    file_type = yml_path_file.suffix.casefold()

    supported_types = (".yaml", ".yml")

    if file_type not in supported_types:
        raise TypeError("Only file types .yaml, and .yml are supported.")

    try:
        with open(file=yml_path_file, mode="r", encoding="utf-8") as stream:
            # See deprecation warning for plain yaml.load(input) at
            # https://github.com/yaml/pyyaml/wiki/PyYAML-yaml.load(input)-Deprecation
            db = yaml.load(stream, Loader=yaml.SafeLoader)
    except yaml.YAMLError as error:
        print(f"Error with YAML file: {error}")
        # print(f"Could not open: {self.self.path_file_in}")
        print(f"Could not open or decode: {yml_path_file}")
        # raise yaml.YAMLError
        raise OSError from error

    # check keys found in input file against required keys
    found_keys = tuple(db.keys())
    keys_exist = tuple(map(lambda x: x in found_keys, required_keys))
    has_required_keys = all(keys_exist)
    if not has_required_keys:
        raise KeyError(f"Input files must have these keys defined: {required_keys}")

    version_specified = db["config_file_version"]
    version_requested = version

    if version_specified != version_requested:
        ee = f"Version mismatch: specified in file was {version_specified},"
        ee += f"requested is {version_requested}"
        raise ValueError(ee)

    return db


def yml_version(
    file: Path,
    key_name="config_file_version",
) -> float:
    """Returns version of yml file if proper key exists"""
    with open(file, "r") as stream:
        data = yaml.load(stream, Loader=yaml.SafeLoader)

    try:
        version = data[key_name]
    except KeyError:
        # print(f"Error with version key: {error}")
        raise KeyError(f"Error with version key, '{key_name}' key not found in {file}.")
    try:
        version = float(version)
    except ValueError:
        raise ValueError(
            f"Could not find valid version in {file} for key {key_name}, found '{version}' which is not a float."
        )
    return version


def yes_no(question):
    """Simple Yes/No Function."""
    prompt = f"{question} (y/n): "
    ans = input(prompt).strip().lower()
    if ans not in ["y", "n"]:
        print(f"{ans} is invalid, please try again...")
        return yes_no(question)
    if ans == "y":
        return True
    return False


def remove_directory(directory: Path):
    """Recursively remove a directory"""
    shutil.rmtree(directory)


def split_list(data: List, chunk_size: int) -> List:
    """split list into equal sized chunks"""
    result = []
    for i in range(0, len(data), chunk_size):
        result.append(data[i : i + chunk_size])
    return result


def tabular_list(
    data: List,
    num_columns: int = Constants.default_column_count,
    column_width: int = Constants.default_column_width,
) -> str:
    rows = split_list(data, chunk_size=num_columns)
    result = ""
    for sublist in rows:
        result += "\n"
        for item in sublist:
            result += f"{item:^{column_width}}"
    return result


### Custom Decorators ###


def hardware_movement(func):
    @run_on_microscope_machine
    def wrapper_func():
        if not Constants.test_hardware_movement:
            pytest.skip("Run only when hardware testing is enabled")
        func()

    return wrapper_func


def run_on_standalone_machine(func):
    def wrapper_func():
        current_machine = platform.uname().node.lower()
        test_machines = [machine.lower() for machine in Constants().offline_machines]
        if current_machine not in test_machines:
            pytest.skip("Run on Offline License Machine Only.")
        func()

    return wrapper_func


def run_on_microscope_machine(func):
    def wrapper_func():
        current_machine = platform.uname().node.lower()
        test_machines = [machine.lower() for machine in Constants().microscope_machines]
        if current_machine not in test_machines:
            pytest.skip("Run on Microscope Machine Only.")
        func()

    return wrapper_func
