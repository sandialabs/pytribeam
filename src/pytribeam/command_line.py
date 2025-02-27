"""
Command Line Entry Points Module
================================

This module provides command line entry points for various functions and utilities.
It serves as the interface between the command line and the underlying functionality
of the application.
"""

from typing import Final
import argparse
from pathlib import Path

# import pkg_resources  # part of setup tools
from importlib.metadata import version
import pytribeam.constants as cs
import pytribeam.GUI.runner as runner
import pytribeam.workflow as workflow

CLI_DOCS: Final[
    str
] = """
--------
pytribeam
--------

pytribeam
    (this command)

pytribeam_info
    Prints the module version and ThermoFisher Scientific Autoscript and Laser
    API version requirements.

pytribeam_gui
    Launches GUI for creating configuration .yml files and to control
    experimental collection.

pytribeam_exp <path_to_file>.yml
    Runs 3D data collection workflow based off of input .yml file.

    Example:
        path/to/experiment/directory> pytribeam_exp path/to/config/file.yml

"""


def pytribeam():
    """
    Prints the command line documentation to the command window.

    This function prints the contents of the global variable `CLI_DOCS` to the
    command window. It is assumed that `CLI_DOCS` contains the necessary
    documentation in string format.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    print(CLI_DOCS)


def module_info() -> None:
    """
    Prints the module version and the yml_schema_version.

    This function retrieves the version of the module and the YAML schema version
    from the `Constants` class in the `cs` module (constants.py). It prints these
    versions to the command window and returns the module version.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """

    # ver = pkg_resources.require("recon3d")[0].version
    module_name = cs.Constants().module_short_name
    ver = version(module_name)
    autoscript_version = cs.Constants().autoscript_version
    laser_api_version = cs.Constants().laser_api_version
    yml_schema_version = cs.Constants().yml_schema_version
    print(f"{module_name} module version: v{ver}")
    print(f"  Maximum supported .yml schema version: v{yml_schema_version}")
    print(
        f"  Maximum supported Thermo Fisher Autoscript version: v{autoscript_version}"
    )
    print(f"  Maximum supported Laser API version: v{laser_api_version}")
    return None


def launch_gui():
    # work_in_progress()
    app = runner.MainApplication()
    app.mainloop()


def run_experiment():
    """run experiment from command line"""

    def _positive_integer(prompt):
        """Helper function to get valid integer input"""
        while True:
            try:
                # Ask for input
                value = int(input(prompt))
                if value > 0:
                    return value  # Return the valid integer
                else:
                    print("Invalid input. Please enter an integer greater than 0.")
            except ValueError:
                print("Invalid input. Please enter a valid integer.")

    # Create the parser
    parser = argparse.ArgumentParser(description="Process a file.")

    # Add the file path argument
    parser.add_argument("file_path", type=str, help="Path to the file to process")

    # Parse the arguments
    args = parser.parse_args()

    start_slice = _positive_integer("Starting slice: ")
    start_step = _positive_integer("Starting step: ")

    # Call the main function with the provided file path
    workflow.run_experiment_cli(
        start_slice=start_slice, start_step=start_step, yml_path=Path(args.file_path)
    )


def work_in_progress():
    """
    Prints the 'Work in Progress (WIP)' warning message.

    This function prints a warning message indicating that the function is a
    work in progress and has not yet been implemented.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    print("Warning: Work in progress (WIP), function not yet implemented.")
