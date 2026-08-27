#!/usr/bin/python3
"""
Command-line entry points for `pytribeam`.

This module defines the functions used by the package's console-script entry
points. These commands provide lightweight access to package documentation,
installation/environment diagnostics, GUI startup, and experiment execution from
a configuration file.

The command functions are intentionally small wrappers around package
functionality. Runtime-heavy imports, such as workflow, GUI, AutoScript, and
Laser API modules, are delayed until they are needed so that simple commands
such as help text and module information can run in environments without
microscope or laser runtime support.

## Console commands

| Function | Purpose |
| --- | --- |
| `pytribeam` | Print command-line documentation. |
| `module_info` | Print package, dependency, and runtime availability information. |
| `launch_gui` | Start the `pytribeam` graphical user interface. |
| `run_experiment` | Run an experiment from a configuration `.yml` file. |
| `work_in_progress` | Print a placeholder warning for unfinished commands. |

## Examples

```console
$ pytribeam
$ pytribeam_info
$ pytribeam_gui
$ pytribeam_exp path/to/experiment.yml
```

## Import behavior

Runtime-heavy imports are delayed until the corresponding command is executed.
This keeps help text, package metadata inspection, and documentation commands
usable even when optional hardware-control dependencies are unavailable.

<hr style="height: 12px; background-color: #333; border: none;">
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path
from typing import Final, Optional

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


# ----------------------------
# -------  pytribeam  --------
# ----------------------------


def work_in_progress():
    """
    Prints the 'Work in Progress (WIP)' warning message to the console.

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


# ----------------------------
# -----  pytribeam_info  -----
# ----------------------------


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


# ----------------------------
# -----  pytribeam_gui  ------
# ----------------------------


def launch_gui() -> None:
    """
    Launches the pytribeam GUI.

    GUI imports are intentionally delayed until this function is called.
    """
    import pytribeam.GUI.runner as runner

    app = runner.MainApplication()
    app.mainloop()


# ----------------------------
# -----  pytribeam_exp  ------
# ----------------------------


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


# ----------------------------
# ----  pytribeam_setup  -----
# ----------------------------

NEEDED_AUTOSCRIPT_PACKAGES = [
    "autoscript_core",
    "autoscript_sdb_microscope_client",
    "autoscript_toolkit",
    "thermoscientific_logging",
]


def _build_setup_parser() -> argparse.ArgumentParser:
    """
    Builds the argument parser for the pytribeam_exp command.
    """
    parser = argparse.ArgumentParser(
        description="Install AutoScript packages in the local environment."
    )

    parser.add_argument(
        "-f",
        "--folder",
        default=None,
        help="Path to the folder containing the autoscript wheels.",
    )

    parser.add_argument(
        "--installer",
        choices=["auto", "pip", "uv"],
        default="auto",
        help=(
            "Installer to use. "
            "'pip' uses the current Python interpreter via `python -m pip`; "
            "'uv' uses `uv pip install --python`; "
            "'auto' attempts to choose a reasonable default."
        ),
    )

    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Pass --upgrade to the installer.",
    )

    return parser


def _normalize_package_name(name: str) -> str:
    """
    Normalize package names enough for matching wheel filenames.

    Wheel filenames generally begin with:

        distribution-version-...

    For these AutoScript wheels, this should be sufficient.
    """
    return name.lower().replace("-", "_")


def _wheel_distribution_name(wheel: Path) -> str:
    """
    Extract the distribution portion from a wheel filename.

    Example:
        autoscript_core-1.2.3-py3-none-any.whl -> autoscript_core
    """
    return _normalize_package_name(wheel.name.split("-", 1)[0])


def _find_autoscript_folder(folder: Optional[str]) -> Path:
    """
    Find the folder containing the AutoScript wheels.
    """
    if folder is not None:
        wheel_folder = Path(folder).expanduser().resolve()
    else:
        if os.name != "nt":
            raise RuntimeError(
                "Automatic identification of the Thermo Scientific AutoScript "
                "folder is not possible on non-Windows machines. Please provide "
                "the folder explicitly with --folder."
            )

        program_files = os.environ.get("ProgramFiles")
        if program_files is None:
            raise RuntimeError("Unable to determine the Program Files directory.")

        autoscript_folder = Path(program_files) / "Thermo Scientific AutoScript"
        if not autoscript_folder.is_dir():
            raise RuntimeError(
                "Unable to find the Thermo Scientific AutoScript folder in "
                "Program Files."
            )

        wheel_folder = autoscript_folder / "PythonPackages"
        if not wheel_folder.is_dir():
            raise RuntimeError(
                "Unable to find the 'PythonPackages' folder in the Thermo "
                "Scientific AutoScript folder in Program Files."
            )

    if not wheel_folder.is_dir():
        raise RuntimeError(f"The wheel folder does not exist: {wheel_folder}")

    return wheel_folder


def _find_required_wheels(folder: Path) -> list[Path]:
    """
    Find the required AutoScript wheels in the given folder.
    """
    wheels = sorted(folder.glob("*.whl"))

    if not wheels:
        raise RuntimeError(f"No wheel files were found in {folder}.")

    wheels_by_distribution: dict[str, list[Path]] = {}

    for wheel in wheels:
        distribution_name = _wheel_distribution_name(wheel)
        wheels_by_distribution.setdefault(distribution_name, []).append(wheel)

    selected_wheels: list[Path] = []
    missing_packages: list[str] = []

    for package in NEEDED_AUTOSCRIPT_PACKAGES:
        normalized_package = _normalize_package_name(package)
        matches = wheels_by_distribution.get(normalized_package, [])

        if not matches:
            missing_packages.append(package)
            continue

        if len(matches) > 1:
            raise RuntimeError(
                f"Found multiple wheels for package {package!r}: "
                f"{[str(w) for w in matches]}. Please remove duplicates or "
                "provide a folder with only one version of each required wheel."
            )

        selected_wheels.append(matches[0])

    if missing_packages:
        raise RuntimeError(
            f"Unable to find all necessary wheels in {folder}. "
            f"Missing wheels for packages: {missing_packages}."
        )

    return selected_wheels


def _pip_available(python_executable: str) -> bool:
    """
    Return True if `python -m pip` is available for the given interpreter.
    """
    result = subprocess.run(
        [python_executable, "-m", "pip", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _choose_installer(requested: str, python_executable: str) -> str:
    """
    Choose pip or uv.

    This is intentionally conservative. There is no perfect way to know whether
    the user considers the environment to be managed by uv, pip, venv, conda,
    etc.
    """
    if requested != "auto":
        return requested

    uv_available = shutil.which("uv") is not None
    pip_available = _pip_available(python_executable)

    # If pip is not installed but uv is available, uv is the better option.
    if uv_available and not pip_available:
        return "uv"

    # If this looks like a uv-managed project, prefer uv.
    if uv_available and Path("uv.lock").is_file():
        return "uv"

    # Otherwise, use pip through the current interpreter.
    if pip_available:
        return "pip"

    if uv_available:
        return "uv"

    raise RuntimeError(
        "Neither pip nor uv appears to be available. Cannot install wheels."
    )


def _install_wheels(
    wheels: list[Path],
    installer: str,
    upgrade: bool = False,
    python_executable: str = sys.executable,
) -> None:
    """
    Install wheels into the environment associated with python_executable.
    """
    wheel_args = [str(wheel) for wheel in wheels]

    if installer == "pip":
        cmd = [python_executable, "-m", "pip", "install"]

        if upgrade:
            cmd.append("--upgrade")

        cmd.extend(wheel_args)

    elif installer == "uv":
        if shutil.which("uv") is None:
            raise RuntimeError(
                "The requested installer was 'uv', but uv was not found on PATH."
            )

        cmd = [
            "uv",
            "pip",
            "install",
            "--python",
            python_executable,
        ]

        if upgrade:
            cmd.append("--upgrade")

        cmd.extend(wheel_args)

    else:
        raise ValueError(f"Unknown installer: {installer}")

    print("Installing AutoScript wheels with command:")
    print(" ".join(cmd))

    subprocess.run(cmd, check=True)


def setup_env() -> None:
    """
    Setup current python environment for AutoScript.

    This only works if the AutoScript wheels are present on the system somewhere.
    The function will search in default locations if a folder is not provided.
    """
    parser = _build_setup_parser()
    args = parser.parse_args()

    folder = _find_autoscript_folder(args.folder)
    wheels = _find_required_wheels(folder)

    installer = _choose_installer(args.installer, sys.executable)

    print(f"Using Python interpreter: {sys.executable}")
    print(f"Using installer: {installer}")
    print("Wheels to install:")
    for wheel in wheels:
        print(f"  {wheel}")

    _install_wheels(
        wheels=wheels,
        installer=installer,
        upgrade=args.upgrade,
        python_executable=sys.executable,
    )
