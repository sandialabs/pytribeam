# Installation

This process uses **AutoScript 4.8.1** and **TriBeam_API_Python 2_2.1** provided by Thermo Fisher Scientific, which is a Windows-only configuration.

## Pre-installation

- Uninstall any prior installations of AutoScript

- Follow the Autoscript installation instructions provided by Thermo Fisher Scientific

- With `AutoScript_4.8.1.exe`, install **AutoScript** according to Thermo Fisher Scientific's instructions:
  - Section 5 - Procedure, select the appropriate scripting configuration. This codebase has been tested in both "Local" and "Offline" Scripting Configurations.
    - *Select Components* screen
      - AutoScript Client components
        - We recommend not installing the following: PyCharm Community IDE, .NET API, preferring to use VS Code as an IDE
  - Select the installer option to add `python` to the system `PATH`.
  - Register to activate the AutoScript license on this computer.
  - Restart the computer.

- Follow the Laser Control installation instructions provided by Thermo Fisher Scientific
  - Install iFast and Python APIs

The AutoScript installer installs several Python modules. Expand the section below to view the full `pip freeze` output.

<details>
<summary>Show full AutoScript Python module list</summary>

```text
<!-- cmdrun sh -lc "cat ./initial_autoscript_python_modules.txt" -->
```
</details>

Confirm the installation location of Autoscript's python environment, which should default to the following path: `C:/Program Files/Enthought/Python/envs/Autoscript/python.exe`. You can verify this by running the following in the Command Prompt (`cmd.exe`):

```sh
where python
```
which should output something similar to the following:

```bat
C:\Program Files\Enthought\Python\envs\AutoScript\python.exe
```

## Main Installation

The user should first download the source code from the `github` repository. For offline machines, you can create a `ZIP` archive of the desired branch and transfer it to the destination machine. Otherwise, standard `git clone` commands can be utilized. For normal client use, it is recommended to use the latest version of the `main` branch.

Installation can be performed by running the provided batch file [pytribeam_install.bat](https://github.com/sandialabs/pytribeam/blob/main/pytribeam_install.bat) from the local directory where you want to install the package. This can be accomplished by either simply by double clicking on the `pytribeam_install.bat` file from the Windows Explorer, or navigating to the source `pytribeam` directory and running from either `PowerShell` or `Command Prompt`:

```bat
./pytribeam_install.bat
```

This install script will uninstall any exisiting version of `pytribeam` before installing the current version. Wheels of various open-source dependencies with the package will be installed. Wheels are provided in order to eliminate the need for internet connectivity on the microscope, and a full list of the current provided wheels can be found here: [wheelhouse](https://github.com/sandialabs/pytribeam/tree/main/wheelhouse)

> [!NOTE]
> `pytribeam` currently defaults to install in developer (editable) mode, which provides the user with the ability to modify and expand the source code, such as adjusting default values in the `constants` module. Such editing would be needed to run unit tests included in the package, as running of tests are tied to specific machine names provided in the `constants` module. Compiled unit test coverage for the package can be found for the latest release without installing as a developer here: [test-coverage](https://sandialabs.github.io/pytribeam/coverage_reports/combined/htmlcov/index.html).

## Verification

After running the `install.bat` script, confirm the package installation by opening a new terminal and run the following to list the available package commands:

```sh
pytribeam
```

which should generate the following output:

```text
{{#include ../generated/cli/pytribeam.txt}}
```

> [!TIP]
> You can also find out what version of `pytribeam` is installed, as well as currently supported version of AutoScript and Laser APIs by running the following from a terminal:
> ```sh
> pytribeam_info
> ```
> API docs were last built in an environment with the following info:
> ```text
> {{#include ../generated/cli/pytribeam-info.txt}}
> ```

## Test Validation

If you are interested in running the test suite on your hardware, see additional instructions here: [Running Tests](./running_tests/README.md).

<!-- 
pytribeam-exp-help.txt:
```text
{{#include ../generated/cli/pytribeam-exp-help.txt}}
``` -->
