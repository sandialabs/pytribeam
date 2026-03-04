#!/usr/bin/python3
"""
Utilities Module
================

This module contains various utility functions and decorators for managing and controlling the microscope, handling YAML files, and performing other common tasks.

Functions
---------
beam_type(beam) -> property
    Return the beam property object as ion and electron beams have the same internal hierarchy.

connect_microscope(microscope: tbt.Microscope, quiet_output: bool = True, connection_host: str = None, connection_port: int = None) -> bool
    Connect to the microscope with the option to suppress printout.

dict_to_yml(db: dict, file_path: Path) -> Path
    Convert a dictionary to a YAML file.

disconnect_microscope(microscope: tbt.Microscope, quiet_output: bool = True) -> bool
    Disconnect from the microscope with the option to suppress printout.

general_settings(exp_settings: dict, yml_format: tbt.YMLFormat) -> dict
    Grab general experiment settings from a .yml file and return them as a dictionary.

step_type(settings: dict, yml_format: tbt.YMLFormat) -> tbt.StepType
    Determine the step type for a specific step settings dictionary.

in_interval(val: float, limit: tbt.Limit, type: tbt.IntervalType) -> bool
    Test whether a value is within an interval, with the interval type defined by an enumerated IntervalType.

gen_dict_extract(key, var)
    Extract values from a nested dictionary by key.

nested_dictionary_location(d: dict, key: str, value: Any) -> List[str]
    Find the nested location of a key-value pair in a dictionary.

nested_find_key_value_pair(d: dict, key: str, value: Any) -> List[str]
    Find a key-value pair in a nested dictionary.

_flatten(dictionary: dict) -> dict
    Flatten a dictionary using pandas.

none_value_dictionary(dictionary: dict) -> bool
    Check if all values in a dictionary are None.

nostdout()
    Create a dummy file to suppress output.

step_count(exp_settings: dict, yml_format: tbt.YMLFormatVersion) -> int
    Determine the maximum step number from a settings dictionary.

step_settings(exp_settings: dict, step_number_key: str, step_number_val: int, yml_format: tbt.YMLFormatVersion) -> Tuple[str, dict]
    Grab specific step settings from an experimental dictionary and return them as a dictionary along with the user-defined step name.

valid_microscope_connection(host: str, port: str) -> bool
    Determine if a microscope connection can be made.

enable_external_device(oem: tbt.ExternalDeviceOEM) -> bool
    Determine whether to enable external device control.

valid_enum_entry(obj: Any, check_type: Enum) -> bool
    Determine if an object is a member of an Enum class.

yml_format(version: float) -> tbt.YMLFormatVersion
    Return the YML file format for a given version.

yml_to_dict(*, yml_path_file: Path, version: float, required_keys: Tuple[str, ...]) -> Dict
    Convert a YAML file to a dictionary.

yml_version(file: Path, key_name="config_file_version") -> float
    Return the version of a YAML file if the proper key exists.

yes_no(question) -> bool
    Simple Yes/No function.

remove_directory(directory: Path)
    Recursively remove a directory.

split_list(data: List, chunk_size: int) -> List
    Split a list into equal-sized chunks.

tabular_list(data: List, num_columns: int = Constants.default_column_count, column_width: int = Constants.default_column_width) -> str
    Format a list into a tabular string.

Decorators
----------
hardware_movement(func)
    Decorator to run a function only when hardware testing is enabled.

run_on_standalone_machine(func)
    Decorator to run a function only on a standalone machine.

run_on_microscope_machine(func)
    Decorator to run a function only on a microscope machine.
"""

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
    """
    Return the beam property object as ion and electron beams have the same internal hierarchy.

    Parameters
    ----------
    beam : Any
        The beam object.

    Returns
    -------
    property
        The beam property object.

    Raises
    ------
    NotImplementedError
        If the beam type is not implemented.
    """
    _ = beam  # no operation
    raise NotImplementedError()


@beam_type.register
def _(beam: tbt.ElectronBeam, microscope: tbt.Microscope) -> property:
    """
    Return the electron beam property object.

    Parameters
    ----------
    beam : tbt.ElectronBeam
        The electron beam object.
    microscope : tbt.Microscope
        The microscope object.

    Returns
    -------
    property
        The electron beam property object.
    """
    return microscope.beams.electron_beam


@beam_type.register
def _(beam: tbt.IonBeam, microscope: tbt.Microscope) -> property:
    """
    Return the ion beam property object.

    Parameters
    ----------
    beam : tbt.IonBeam
        The ion beam object.
    microscope : tbt.Microscope
        The microscope object.

    Returns
    -------
    property
        The ion beam property object.
    """
    return microscope.beams.ion_beam


def connect_microscope(
    microscope: tbt.Microscope,
    quiet_output: bool = True,
    connection_host: str = None,
    connection_port: int = None,
):
    """
    Connect to the microscope with the option to suppress printout.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object to connect.
    quiet_output : bool, optional
        Whether to suppress printout (default is True).
    connection_host : str, optional
        The connection host (default is None).
    connection_port : int, optional
        The connection port (default is None).

    Returns
    -------
    bool
        True if the connection is successful.

    Raises
    ------
    ConnectionError
        If the connection fails.
    """

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
    Convert a dictionary to a YAML file.

    Parameters
    ----------
    db : dict
        The dictionary to convert.
    file_path : Path
        The path to save the YAML file.

    Returns
    -------
    Path
        The path to the saved YAML file.
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
    """
    Disconnect from the microscope with the option to suppress printout.

    Parameters
    ----------
    microscope : tbt.Microscope
        The microscope object to disconnect.
    quiet_output : bool, optional
        Whether to suppress printout (default is True).

    Returns
    -------
    bool
        True if the disconnection is successful.

    Raises
    ------
    ConnectionError
        If the disconnection fails.
    """
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
    """
    Grab general experiment settings from a .yml file and return them as a dictionary.

    Parameters
    ----------
    exp_settings : dict
        The experiment settings dictionary.
    yml_format : tbt.YMLFormat
        The YAML format version.

    Returns
    -------
    dict
        The general experiment settings as a dictionary.
    """
    general_key = yml_format.general_section_key
    return exp_settings[general_key]


def step_type(settings: dict, yml_format: tbt.YMLFormat) -> tbt.StepType:
    """
    Determine the step type for a specific step settings dictionary.

    Parameters
    ----------
    settings : dict
        The step settings dictionary.
    yml_format : tbt.YMLFormat
        The YAML format version.

    Returns
    -------
    tbt.StepType
        The step type.
    """
    step_type = tbt.StepType(
        settings[yml_format.step_general_key][yml_format.step_type_key]
    )

    return step_type


def in_interval(val: float, limit: tbt.Limit, type: tbt.IntervalType) -> bool:
    """
    Test whether a value is within an interval, with the interval type defined by an enumerated IntervalType.

    Parameters
    ----------
    val : float
        The input value to be compared against min and max.
    limit : tbt.Limit
        The bounds of the interval.
    type : tbt.IntervalType
        The type of interval.

    Returns
    -------
    bool
        True if within the interval, False otherwise.
    """
    if type == tbt.IntervalType.OPEN:
        return (val > limit.min) and (val < limit.max)
    if type == tbt.IntervalType.CLOSED:
        return (val >= limit.min) and (val <= limit.max)
    if type == tbt.IntervalType.LEFT_OPEN:
        return (val > limit.min) and (val <= limit.max)
    if type == tbt.IntervalType.RIGHT_OPEN:
        return (val >= limit.min) and (val < limit.max)


def gen_dict_extract(key, var):
    """
    Extract values from a nested dictionary by key.

    Parameters
    ----------
    key : str
        The key to search for.
    var : dict
        The nested dictionary to search.

    Yields
    ------
    Any
        The values associated with the specified key.
    """
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


def nested_dictionary_location(d: dict, key: str, value: Any) -> List[str]:
    """
    Find the nested location of a key-value pair in a dictionary.

    This function returns a list of key values from the highest to the lowest level of nested dictionaries.

    Parameters
    ----------
    d : dict
        The dictionary to search.
    key : str
        The key to search for.
    value : Any
        The value to search for.

    Returns
    -------
    List[str]
        The nested location of the key-value pair.

    Raises
    ------
    KeyError
        If the key-value pair is not found in the dictionary.
    """
    nesting = nested_find_key_value_pair(d=d, key=key, value=value)
    if nesting is None:
        raise KeyError(
            f'Key : value pair of "{key} : {value}" not found in the provided dictionary.'
        )
    return nesting


def nested_find_key_value_pair(d: dict, key: str, value: Any) -> List[str]:
    """
    Find a key-value pair in a nested dictionary.

    This function returns a list of key values from the highest to the lowest level of nested dictionaries.

    Parameters
    ----------
    d : dict
        The dictionary to search.
    key : str
        The key to search for.
    value : Any
        The value to search for.

    Returns
    -------
    List[str]
        The nested location of the key-value pair.
    """
    for k, v in d.items():
        if k == key:
            if v == value:
                return [k]
        if isinstance(v, dict):
            p = nested_find_key_value_pair(v, key, value)
            if p:
                return [k] + p


def _flatten(dictionary: dict) -> dict:
    """
    Flatten a dictionary using pandas.

    This function flattens a nested dictionary using pandas, which can be slow on large dictionaries.
    From https://stackoverflow.com/questions/6027558/flatten-nested-dictionaries-compressing-keys

    Parameters
    ----------
    dictionary : dict
        The dictionary to flatten.

    Returns
    -------
    dict
        The flattened dictionary.
    """
    data_frame = json_normalize(dictionary, sep="_")
    db_flat = data_frame.to_dict(orient="records")[0]
    return db_flat


def none_value_dictionary(dictionary: dict) -> bool:
    """
    Check if all values in a dictionary are None.

    This function returns True if all values in the dictionary are None, and False otherwise.

    Parameters
    ----------
    dictionary : dict
        The dictionary to check.

    Returns
    -------
    bool
        True if all values in the dictionary are None, False otherwise.
    """
    # flatten the dictionary first
    db_flat = _flatten(dictionary)
    return all([v is None for v in db_flat.values()])


@contextlib.contextmanager
def nostdout():
    """
    Create a dummy file to suppress output.

    This function creates a dummy file to suppress output.

    Yields
    ------
    None
    """
    save_stdout = sys.stdout
    sys.stdout = tbt.DummyFile()
    try:
        yield
    finally:
        # Always restore stdout, even if KeyboardInterrupt or other exceptions occur
        sys.stdout = save_stdout


def step_count(
    exp_settings: dict,
    yml_format: tbt.YMLFormatVersion,
):
    """
    Determine the maximum step number from a settings dictionary.

    This function determines the maximum step number from a settings dictionary, as specified by the step_number_key.

    Parameters
    ----------
    exp_settings : dict
        The experiment settings dictionary.
    yml_format : tbt.YMLFormatVersion
        The YAML format version.

    Returns
    -------
    int
        The maximum step number.

    Raises
    ------
    ValueError
        If the number of steps found does not match the expected step count.
    """

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
    """
    Grab specific step settings from an experimental dictionary and return them as a dictionary along with the user-defined step name.

    Parameters
    ----------
    exp_settings : dict
        The experiment settings dictionary.
    step_number_key : str
        The key for the step number.
    step_number_val : int
        The value for the step number.
    yml_format : tbt.YMLFormatVersion
        The YAML format version.

    Returns
    -------
    Tuple[str, dict]
        The step name and the step settings dictionary.
    """

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
    """
    Determine if a microscope connection can be made.

    This function checks if a microscope connection can be made and disconnects if a connection can be made.

    Parameters
    ----------
    host : str
        The connection host.
    port : str
        The connection port.

    Returns
    -------
    bool
        True if the connection can be made, False otherwise.
    """
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
    """
    Determine whether to enable external device control.

    This function checks if the external device control should be enabled based on the OEM.

    Parameters
    ----------
    oem : tbt.ExternalDeviceOEM
        The OEM of the external device.

    Returns
    -------
    bool
        True if the external device control should be enabled, False otherwise.

    Raises
    ------
    NotImplementedError
        If the OEM type is unsupported.
    """
    if not isinstance(oem, tbt.ExternalDeviceOEM):
        raise NotImplementedError(
            f"Unsupported type of {type(oem)}, only 'ExternalDeviceOEM' types are supported."
        )
    if oem != tbt.ExternalDeviceOEM.NONE:
        return True
    return False


def valid_enum_entry(obj: Any, check_type: Enum) -> bool:
    """
    Determine if an object is a member of an Enum class.

    This function checks if an object is a member of an Enum class.

    Parameters
    ----------
    obj : Any
        The object to check.
    check_type : Enum
        The Enum class to check against.

    Returns
    -------
    bool
        True if the object is a member of the Enum class, False otherwise.
    """
    return obj in check_type._value2member_map_


def yml_format(version: float) -> tbt.YMLFormatVersion:
    """
    Return the YML file format for a given version.

    This function returns the YML file format for a given version.

    Parameters
    ----------
    version : float
        The version of the YML file.

    Returns
    -------
    tbt.YMLFormatVersion
        The YML file format for the given version.

    Raises
    ------
    NotImplementedError
        If the YML file version is unsupported.
    """
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
    """
    Convert a YAML file to a dictionary.

    This function reads a YAML file and returns the result as a dictionary.

    Parameters
    ----------
    yml_path_file : Path
        The fully pathed location to the input file.
    version : float
        The version of the YAML file in x.y format.
    required_keys : Tuple[str, ...]
        The key(s) that must be in the YAML file for conversion to a dictionary to occur.

    Returns
    -------
    dict
        The YAML file represented as a dictionary.

    Raises
    ------
    TypeError
        If the file type is unsupported.
    OSError
        If the YAML file cannot be opened or decoded.
    KeyError
        If the required keys are not found in the YAML file.
    ValueError
        If the version specified in the file does not match the requested version.
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
    """
    Return the version of a YAML file if the proper key exists.

    Parameters
    ----------
    file : Path
        The path to the YAML file.
    key_name : str, optional
        The key name for the version in the YAML file (default is "config_file_version").

    Returns
    -------
    float
        The version of the YAML file.

    Raises
    ------
    KeyError
        If the version key is not found in the YAML file.
    ValueError
        If the version value is not a valid float.
    """
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
    """
    Simple Yes/No function.

    Parameters
    ----------
    question : str
        The question to ask the user.

    Returns
    -------
    bool
        True if the user answers "yes", False otherwise.
    """
    prompt = f"{question} (y/n): "
    ans = input(prompt).strip().lower()
    if ans not in ["y", "n"]:
        print(f"{ans} is invalid, please try again...")
        return yes_no(question)
    if ans == "y":
        return True
    return False


def remove_directory(directory: Path):
    """
    Recursively remove a directory.

    Parameters
    ----------
    directory : Path
        The path to the directory to remove.
    """
    shutil.rmtree(directory)


def split_list(data: List, chunk_size: int) -> List:
    """
    Split a list into equal-sized chunks.

    Parameters
    ----------
    data : List
        The list to split.
    chunk_size : int
        The size of each chunk.

    Returns
    -------
    List
        A list of chunks.
    """
    result = []
    for i in range(0, len(data), chunk_size):
        result.append(data[i : i + chunk_size])
    return result


def tabular_list(
    data: List,
    num_columns: int = Constants.default_column_count,
    column_width: int = Constants.default_column_width,
) -> str:
    """
    Format a list into a tabular string.

    Parameters
    ----------
    data : List
        The list to format.
    num_columns : int, optional
        The number of columns in the table (default is Constants.default_column_count).
    column_width : int, optional
        The width of each column in the table (default is Constants.default_column_width).

    Returns
    -------
    str
        The formatted tabular string.
    """
    rows = split_list(data, chunk_size=num_columns)
    result = ""
    for sublist in rows:
        result += "\n"
        for item in sublist:
            result += f"{item:^{column_width}}"
    return result


### Custom Decorators ###


def hardware_movement(func):
    """
    Decorator to run a function only when hardware testing is enabled.

    Parameters
    ----------
    func : function
        The function to decorate.

    Returns
    -------
    function
        The decorated function.
    """

    @run_on_microscope_machine
    def wrapper_func():
        if not Constants.test_hardware_movement:
            pytest.skip("Run only when hardware testing is enabled")
        func()

    return wrapper_func


def run_on_standalone_machine(func):
    """
    Decorator to run a function only on a standalone machine.

    Parameters
    ----------
    func : function
        The function to decorate.

    Returns
    -------
    function
        The decorated function.
    """

    def wrapper_func():
        current_machine = platform.uname().node.lower()
        test_machines = [machine.lower() for machine in Constants().offline_machines]
        if current_machine not in test_machines:
            pytest.skip("Run on Offline License Machine Only.")
        func()

    return wrapper_func


def run_on_microscope_machine(func):
    """
    Decorator to run a function only on a microscope machine.

    Parameters
    ----------
    func : function
        The function to decorate.

    Returns
    -------
    function
        The decorated function.
    """

    def wrapper_func():
        current_machine = platform.uname().node.lower()
        test_machines = [machine.lower() for machine in Constants().microscope_machines]
        if current_machine not in test_machines:
            pytest.skip("Run on Microscope Machine Only.")
        func()

    return wrapper_func
