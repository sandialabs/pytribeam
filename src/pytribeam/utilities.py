#!/usr/bin/python3
"""General-purpose utility functions for `pytribeam`.

This module contains shared helper functions used throughout the package. The
utilities here support microscope connection management, beam-object dispatch,
YAML configuration parsing, nested-dictionary inspection, interval checks,
console-output suppression, simple user prompts, list formatting, filesystem
cleanup, and test-environment detection.

Functions in this module are intentionally lightweight and generally avoid
owning workflow-specific logic. Higher-level modules use these helpers to keep
configuration parsing, validation, formatting, and microscope connection code
consistent across the package.

## Utility categories

| Category | Functions |
| --- | --- |
| Microscope connection | `connect_microscope`, `disconnect_microscope`, `valid_microscope_connection` |
| Beam dispatch | `beam_type` |
| YAML configuration | `yml_version`, `yml_format`, `yml_to_dict`, `dict_to_yml`, `general_settings`, `step_count`, `step_settings`, `step_type` |
| Dictionary helpers | `gen_dict_extract`, `nested_dictionary_location`, `nested_find_key_value_pair`, `none_value_dictionary` |
| Validation helpers | `in_interval`, `valid_enum_entry`, `enable_external_device` |
| Console helpers | `nostdout`, `yes_no`, `tabular_list`, `split_list` |
| Filesystem helpers | `remove_directory` |
| Test/environment helpers | `get_test_description`, `get_autoscript_version`, `is_laser_available` |

## Typical usage

Read and validate a YAML configuration file:

```python
from pathlib import Path

from pytribeam import utilities as ut

version = ut.yml_version(Path("experiment.yml"))
fmt = ut.yml_format(version)

settings = ut.yml_to_dict(
    yml_path_file=Path("experiment.yml"),
    version=version,
    required_keys=fmt.required_keys,
)
```

Check whether a value lies inside a closed interval:

```python
import pytribeam.types as tbt
from pytribeam import utilities as ut

is_valid = ut.in_interval(
    val=5.0,
    limit=tbt.Limit(min=0.0, max=10.0),
    type=tbt.IntervalType.CLOSED,
)
```

Connect to a microscope while suppressing connection output:

```python
import pytribeam.types as tbt
from pytribeam import utilities as ut

microscope = tbt.Microscope()

ut.connect_microscope(
    microscope=microscope,
    quiet_output=True,
)

# Use microscope...

ut.disconnect_microscope(microscope)
```

Format a long list for display:

```python
from pytribeam import utilities as ut

print(ut.tabular_list(["CBS", "ETD", "TLD", "ABS"]))
```

## YAML configuration helpers

The YAML helpers assume that experiment configuration files include a
`config_file_version` field and the package-specific top-level keys expected by
the selected `tbt.YMLFormatVersion`.

`step_count` validates that the number of discovered steps matches the declared
step count in the general configuration section. `step_settings` retrieves the
settings dictionary for a specific step number and returns both the user-defined
step name and the step settings.

## Beam dispatch

`beam_type` is implemented with `functools.singledispatch` and maps
`pytribeam` beam wrapper types to the corresponding microscope beam property:

| Input type | Returned microscope object |
| --- | --- |
| `tbt.ElectronBeam` | `microscope.beams.electron_beam` |
| `tbt.IonBeam` | `microscope.beams.ion_beam` |

Unsupported beam types raise `NotImplementedError`.

## Test and environment helpers

The test helper functions detect whether the current system appears to be an
offline/simulated machine, microscope hardware machine, or laser-capable
hardware machine. These utilities are primarily intended for test selection,
test naming, and CI/local test reporting.

## Notes

This module is broad by design, but utilities that become tightly coupled to a
specific subsystem may be better placed in that subsystem's module over time.

<hr style="height: 12px; background-color: #333; border: none;">
"""

__all__ = [
    "beam_type",
    "connect_microscope",
    "dict_to_yml",
    "disconnect_microscope",
    "general_settings",
    "step_type",
    "in_interval",
    "gen_dict_extract",
    "nested_dictionary_location",
    "nested_find_key_value_pair",
    "none_value_dictionary",
    "nostdout",
    "step_count",
    "step_settings",
    "valid_microscope_connection",
    "enable_external_device",
    "valid_enum_entry",
    "yml_format",
    "yml_to_dict",
    "yml_version",
    "yes_no",
    "remove_directory",
    "split_list",
    "tabular_list",
    "get_test_description",
    "get_autoscript_version",
    "is_laser_available",
]


# Default python modules
from pathlib import Path
from typing import Dict, Tuple, Any, List, Optional
from enum import Enum
import platform
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
def beam_type(beam: Any, microscope: tbt.Microscope) -> property:
    """
    Return the beam property object as ion and electron beams have the same internal hierarchy.

    ## Parameters

    - `beam` (`Any`): The beam object.

    ## Returns

    - `property`: The beam property object.

    ## Raises

    - `NotImplementedError`: If the beam type is not implemented.
    """
    _ = beam  # no operation
    raise NotImplementedError()


@beam_type.register
def _electron_beam_type(beam: tbt.ElectronBeam, microscope: tbt.Microscope) -> property:
    """
    Return the electron beam property object.

    ## Parameters

    - `beam` (`tbt.ElectronBeam`): The electron beam object.
    - `microscope` (`tbt.Microscope`): The microscope object.

    ## Returns

    - `property`: The electron beam property object.
    """
    return microscope.beams.electron_beam


@beam_type.register
def _ion_beam_type(beam: tbt.IonBeam, microscope: tbt.Microscope) -> property:
    """
    Return the ion beam property object.

    ## Parameters

    - `beam` (`tbt.IonBeam`): The ion beam object.
    - `microscope` (`tbt.Microscope`): The microscope object.

    ## Returns

    - `property`: The ion beam property object.
    """
    return microscope.beams.ion_beam


def connect_microscope(
    microscope: tbt.Microscope,
    quiet_output: bool = True,
    connection_host: str = None,
    connection_port: int = None,
) -> bool:
    """
    Connect to the microscope with the option to suppress printout.

    ## Parameters

    - `microscope` (`tbt.Microscope`): The microscope object to connect.
    - `quiet_output` (`bool, optional`): Whether to suppress printout (default is True).
    - `connection_host` (`str, optional`): The connection host (default is None).
    - `connection_port` (`int, optional`): The connection port (default is None).

    ## Returns

    - `bool`: True if the connection is successful.

    ## Raises

    - `ConnectionError`: If the connection fails.
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

    ## Parameters

    - `db` (`dict`): The dictionary to convert.
    - `file_path` (`Path`): The path to save the YAML file.

    ## Returns

    - `Path`: The path to the saved YAML file.
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
) -> bool:
    """
    Disconnect from the microscope with the option to suppress printout.

    ## Parameters

    - `microscope` (`tbt.Microscope`): The microscope object to disconnect.
    - `quiet_output` (`bool, optional`): Whether to suppress printout (default is True).

    ## Returns

    - `bool`: True if the disconnection is successful.

    ## Raises

    - `ConnectionError`: If the disconnection fails.
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

    ## Parameters

    - `exp_settings` (`dict`): The experiment settings dictionary.
    - `yml_format` (`tbt.YMLFormat`): The YAML format version.

    ## Returns

    - `dict`: The general experiment settings as a dictionary.
    """
    general_key = yml_format.general_section_key
    return exp_settings[general_key]


def step_type(settings: dict, yml_format: tbt.YMLFormat) -> tbt.StepType:
    """
    Determine the step type for a specific step settings dictionary.

    ## Parameters

    - `settings` (`dict`): The step settings dictionary.
    - `yml_format` (`tbt.YMLFormat`): The YAML format version.

    ## Returns

    - `tbt.StepType`: The step type.
    """
    step_type = tbt.StepType(
        settings[yml_format.step_general_key][yml_format.step_type_key]
    )

    return step_type


def in_interval(val: float, limit: tbt.Limit, type: tbt.IntervalType) -> bool:
    """
    Test whether a value is within an interval, with the interval type defined by an enumerated IntervalType.

    ## Parameters

    - `val` (`float`): The input value to be compared against min and max.
    - `limit` (`tbt.Limit`): The bounds of the interval.
    - `type` (`tbt.IntervalType`): The type of interval.

    ## Returns

    - `bool`: True if within the interval, False otherwise.
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

    ## Parameters

    - `key` (`str`): The key to search for.
    - `var` (`dict`): The nested dictionary to search.

    ## Yields

    - `Any`: The values associated with the specified key.
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

    ## Parameters

    - `d` (`dict`): The dictionary to search.
    - `key` (`str`): The key to search for.
    - `value` (`Any`): The value to search for.

    ## Returns

    - `List[str]`: The nested location of the key-value pair.

    ## Raises

    - `KeyError`: If the key-value pair is not found in the dictionary.
    """
    nesting = nested_find_key_value_pair(d=d, key=key, value=value)
    if nesting is None:
        raise KeyError(
            f'Key : value pair of "{key} : {value}" not found in the provided dictionary.'
        )
    return nesting


def nested_find_key_value_pair(d: dict, key: str, value: Any) -> Optional[List[str]]:
    """
    Find a key-value pair in a nested dictionary.

    This function returns a list of key values from the highest to the lowest level of nested dictionaries.

    ## Parameters

    - `d` (`dict`): The dictionary to search.
    - `key` (`str`): The key to search for.
    - `value` (`Any`): The value to search for.

    ## Returns

    - `List[str]`: The nested location of the key-value pair.
    - `None`: None if the key value pair does not exist
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

    ## Parameters

    - `dictionary` (`dict`): The dictionary to flatten.

    ## Returns

    - `dict`: The flattened dictionary.
    """
    data_frame = json_normalize(dictionary, sep="_")
    db_flat = data_frame.to_dict(orient="records")[0]
    return db_flat


def none_value_dictionary(dictionary: dict) -> bool:
    """
    Check if all values in a dictionary are None.

    This function returns True if all values in the dictionary are None, and False otherwise.

    ## Parameters

    - `dictionary` (`dict`): The dictionary to check.

    ## Returns

    - `bool`: True if all values in the dictionary are None, False otherwise.
    """
    # flatten the dictionary first
    db_flat = _flatten(dictionary)
    return all([v is None for v in db_flat.values()])


@contextlib.contextmanager
def nostdout():
    """
    Create a dummy file to suppress output.

    This function creates a dummy file to suppress output.

    ## Yields

    - `None`:
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

    ## Parameters

    - `exp_settings` (`dict`): The experiment settings dictionary.
    - `yml_format` (`tbt.YMLFormatVersion`): The YAML format version.

    ## Returns

    - `int`: The maximum step number.

    ## Raises

    - `ValueError`: If the number of steps found does not match the expected step count.
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

    ## Parameters

    - `exp_settings` (`dict`): The experiment settings dictionary.
    - `step_number_key` (`str`): The key for the step number.
    - `step_number_val` (`int`): The value for the step number.
    - `yml_format` (`tbt.YMLFormatVersion`): The YAML format version.

    ## Returns

    - `Tuple[str, dict]`: The step name and the step settings dictionary.
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


def valid_microscope_connection(host: str, port: int) -> bool:
    """
    Determine if a microscope connection can be made.

    This function checks if a microscope connection can be made and disconnects if a connection can be made.

    ## Parameters

    - `host` (`str`): The connection host.
    - `port` (`str`): The connection port.

    ## Returns

    - `bool`: True if the connection can be made, False otherwise.
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

    ## Parameters

    - `oem` (`tbt.ExternalDeviceOEM`): The OEM of the external device.

    ## Returns

    - `bool`: True if the external device control should be enabled, False otherwise.

    ## Raises

    - `NotImplementedError`: If the OEM type is unsupported.
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

    ## Parameters

    - `obj` (`Any`): The object to check.
    - `check_type` (`Enum`): The Enum class to check against.

    ## Returns

    - `bool`: True if the object is a member of the Enum class, False otherwise.
    """
    try:
        check_type(obj)
    except ValueError:
        return False
    return True


def yml_format(version: float) -> tbt.YMLFormatVersion:
    """
    Return the YML file format for a given version.

    This function returns the YML file format for a given version.

    ## Parameters

    - `version` (`float`): The version of the YML file.

    ## Returns

    - `tbt.YMLFormatVersion`: The YML file format for the given version.

    ## Raises

    - `NotImplementedError`: If the YML file version is unsupported.
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

    ## Parameters

    - `yml_path_file` (`Path`): The fully pathed location to the input file.
    - `version` (`float`): The version of the YAML file in x.y format.
    - `required_keys` (`Tuple[str, ...]`): The key(s) that must be in the YAML file for conversion to a dictionary to occur.

    ## Returns

    - `dict`: The YAML file represented as a dictionary.

    ## Raises

    - `TypeError`: If the file type is unsupported.
    - `OSError`: If the YAML file cannot be opened or decoded.
    - `KeyError`: If the required keys are not found in the YAML file.
    - `ValueError`: If the version specified in the file does not match the requested version or if the file is empty.
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

    if db is None:
        raise ValueError(f"YAML file is empty: {yml_path_file}")

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

    ## Parameters

    - `file` (`Path`): The path to the YAML file.
    - `key_name` (`str, optional`): The key name for the version in the YAML file (default is "config_file_version").

    ## Returns

    - `float`: The version of the YAML file.

    ## Raises

    - `KeyError`: If the version key is not found in the YAML file.
    - `ValueError`: If the version value is not a valid float.
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

    ## Parameters

    - `question` (`str`): The question to ask the user.

    ## Returns

    - `bool`: True if the user answers "yes", False otherwise.
    """
    prompt = f"{question} (y/n): "
    while True:
        ans = input(prompt).strip().lower()
        if ans == "y":
            return True
        if ans == "n":
            return False
        print(f"{ans} is invalid, please try again...")


def remove_directory(directory: Path) -> None:
    """
    Recursively remove a directory.

    ## Parameters

    - `directory` (`Path`): The path to the directory to remove.
    """
    shutil.rmtree(directory)


def split_list(data: List, chunk_size: int) -> List:
    """
    Split a list into equal-sized chunks.

    ## Parameters

    - `data` (`List`): The list to split.
    - `chunk_size` (`int`): The size of each chunk.

    ## Returns

    - `List`: A list of chunks.
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

    ## Parameters

    - `data` (`List`): The list to format.
    - `num_columns` (`int, optional`): The number of columns in the table (default is Constants.default_column_count).
    - `column_width` (`int, optional`): The width of each column in the table (default is Constants.default_column_width).

    ## Returns

    - `str`: The formatted tabular string.
    """
    rows = split_list(data, chunk_size=num_columns)
    result = ""
    for sublist in rows:
        result += "\n"
        for item in sublist:
            result += f"{item:^{column_width}}"
    return result


### Functions for tests and CI/CD###


def get_test_description() -> str:
    """
    Return a test-environment description string for the current machine.

    The description combines the detected machine type with the installed
    AutoScript version. It is intended for test naming, reporting, or selecting
    expected test behavior.

    ## Returns

    - `description` (`str`): A string containing a description of the platform and the autoscript version.
    """
    node = platform.uname().node.lower()
    offline_machine = any(
        node in machine.lower() or machine.lower() in node
        for machine in Constants.offline_machines
    )
    hardware_machine = any(
        node in machine.lower() or machine.lower() in node
        for machine in Constants.microscope_machines
    )

    laser_machine = is_laser_available()

    api_version = get_autoscript_version()

    if offline_machine:
        description = "simulated_"
    elif hardware_machine and laser_machine:
        description = "laser_hardware_"
    else:
        description = "hardware_"

    return description + api_version


def get_autoscript_version() -> str:
    """
    Get the version of autoscript for the present system

    ## Returns

    - `version : str`: The version of autoscript
    """
    try:
        import autoscript_sdb_microscope_client as asmc

        version = asmc.build_information.INFO_VERSIONSHORT
    except ImportError:
        version = "none"
    return version


def is_laser_available() -> bool:
    """
    Get the version of ThermoFisher Laser Control API for the present system

    ## Returns

    - `version : str`: The version of the Laser API
    """
    try:
        import Laser.PythonControl as tfs_laser

        return True
    except ImportError:
        return False
