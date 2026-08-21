"""
Command Line Entry Points Module
================================

This module provides command line entry points for various functions and utilities.
It serves as the interface between the command line and the underlying functionality
of the application.

Important:
    This module should remain lightweight at import time. Do not import AutoScript,
    Laser API, pytribeam.constants, pytribeam.workflow, or GUI modules at the top
    level. Import those only inside functions that actually need them.
"""

import argparse
from pathlib import Path
from typing import Final

CLI_DOCS: Final[str] = """
--------
pytribeam
--------

pytribeam
    Prints this command line documentation.

pytribeam_info
    Prints the module version, supported AutoScript and Laser API versions,
    and detected installed environment.

pytribeam_gui
    Launches the GUI for creating configuration .yml files and controlling
    experimental collection.

pytribeam_exp <path_to_file>.yml
    Runs the 3D data collection workflow based on an input .yml file.

pytribeam_exp --help
    Prints help for the experiment command.

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
    print(CLI_DOCS.strip())


def module_info() -> None:
    """
    Prints lightweight package and environment information.

    This command is intended to verify installation and should not require a
    microscope connection, AutoScript runtime initialization, Laser API runtime
    initialization, or a license check.
    """
    import pytribeam._package_metadata as pm

    pytribeam_version = pm.get_pytribeam_version()
    pytribeam_commit = pm.get_pytribeam_commit_id()
    autoscript_version = pm.get_autoscript_version()
    laser_version = pm.get_laser_api_version()

    print(f"{pm.MODULE_SHORT_NAME} module version: v{pytribeam_version or 'unknown'}")

    if pytribeam_commit:
        print(f"  Git commit: {pytribeam_commit}")

    print(f"  Maximum supported .yml schema version: v{pm.YML_SCHEMA_VERSION}")

    print(
        "  Supported Thermo Fisher AutoScript versions: "
        + ", ".join(f"v{x}" for x in pm.SUPPORTED_AUTOSCRIPT_VERSIONS)
    )

    print(
        "  Supported Laser API versions: "
        + ", ".join(f"v{x}" for x in pm.SUPPORTED_LASER_API_VERSIONS)
    )

    print()
    print("Installed environment:")

    print("  AutoScript:")
    print(
        "    Distribution metadata: "
        f"{'detected' if autoscript_version else 'not detected'}, "
        f"version: {autoscript_version or 'not detected'}"
    )
    print(
        "    Import package autoscript_sdb_microscope_client: "
        f"{'available' if pm.autoscript_available() else 'not importable'}"
    )

    print()
    print("  Laser API:")
    print(
        "    Distribution metadata: "
        f"{'detected' if laser_version else 'not detected'}, "
        f"version: {laser_version or 'not detected'}"
    )
    print(
        "    Import package Laser: "
        f"{'available' if pm.laser_api_available() else 'not importable'}"
    )
    print(
        "    Import package Laser.PythonControl: "
        f"{'available' if pm.laser_pythoncontrol_available() else 'not importable'}"
    )


def launch_gui() -> None:
    """
    Launches the pytribeam GUI.

    GUI imports are intentionally delayed until this function is called.
    """
    import pytribeam.GUI.runner as runner

    app = runner.MainApplication()
    app.mainloop()


def build_experiment_parser() -> argparse.ArgumentParser:
    """
    Builds the argument parser for the pytribeam_exp command.
    """
    parser = argparse.ArgumentParser(
        description="Run a pytribeam experiment from a configuration .yml file."
    )

    parser.add_argument(
        "file_path",
        type=str,
        help="Path to the experiment configuration .yml file.",
    )

    return parser


def run_experiment() -> None:
    """
    Runs an experiment from the command line.

    The workflow import is intentionally delayed until after argument parsing.
    This allows `pytribeam_exp --help` to run without importing workflow,
    AutoScript, or Laser runtime modules.
    """

    def _positive_integer(prompt: str) -> int:
        """Helper function to get valid integer input."""
        while True:
            try:
                value = int(input(prompt))
                if value > 0:
                    return value
                print("Invalid input. Please enter an integer greater than 0.")
            except ValueError:
                print("Invalid input. Please enter a valid integer.")

    parser = build_experiment_parser()
    args = parser.parse_args()

    start_slice = _positive_integer("Starting slice: ")
    start_step = _positive_integer("Starting step: ")

    import pytribeam.workflow as workflow

    workflow.run_experiment_cli(
        start_slice=start_slice,
        start_step=start_step,
        yml_path=Path(args.file_path),
    )


def work_in_progress():
    """
    Prints the 'Work in Progress (WIP)' warning message to the console.

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
