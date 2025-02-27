# Installation

This process uses **AutoScript 4.8.1** and **TriBeam_API_Python 2_2.1** provided by Thermo Fisher Scientific, which is a Windows-only configuration.

## Pre-installation

- Uninstall any prior installations of AutoScript

- Follow the Autoscript installation instructions provided by Thermo Fisher Scientific

- With `AutoScript_4.8.1.exe`, install **Autoscript**
  - Section 5 - Procedure, select the appropriate scripting configuration
  - AutoScript Server
  - AutoScript Client
    - Python 3.8 Distribution
    - AutoScript Python Packages
    - We recommend not installing the following: PyCharm Community IDE, .NET API, preferring to use VS Code as an IDE
  - Select the installer option to add Python to the system Path.
  - Register to activate AutoScript license on this computer.
  - Restart the computer.

- Follow the Laser Control installation instructions provided by Thermo Fisher Scientific
  - Install iFast and Python APIs

The AutoScript installer installs the following modules (generated with `pip freeze`):

```sh
<!-- cmdrun type initial_autoscript_python_modules.txt -->
```

Confirm the installation location of Autoscript's python environment, which should default to the following path: `C:/Program Files/Enthought/Python/envs/Autoscript/python.exe`. You can verify this by running the following in the Command Prompt (`cmd.exe`):

```sh
where python
```
which should output something similar to the following:

```sh
<!-- cmdrun echo C:\Program Files\Enthought\Python\envs\AutoScript\python.exe -->
```

<!-- ```sh
<!-- cmdrun where python -->
``` -->

## Main Installation

Installation can be performed by running the provided batch file [install.bat](https://gitlab-ex.sandia.gov/tribeam/pytribeam/-/blob/develop/install.bat) from the local directory where you want to install the package. This can be accomplished simply by double clicking on the `install.bat` file from the Windows Explorer. Options are provided for both client and developer (editable) use. This will install the wheels of various open-source python packages included with the package that are provided here: [wheels](https://gitlab-ex.sandia.gov/tribeam/pytribeam/-/tree/main/pytribeam/wheelhouse). Wheels are provided in order to eliminate the need for internet connectivity on the microscope.

**NOTE**: Developer (editable) use provides the user with the ability to modify and expand the source code, such as adjusting default values in the `constants` module, which would be needed to run unit tests included in the package, as running of tests are tied to specific machine names provided in the `constants` module. Compiled unit test coverage for the package can be found for the latest release without installing as a developer here: [test-coverage](https://gitlab-ex.sandia.gov/tribeam/pytribeam/-/archive/develop/pytribeam-develop.zip?path=coverage_reports/combined/htmlcov).

After running the `install.bat` script, confirm the package installation by opening a new terminal and run the following to list the available package commands:

```sh
pytribeam
```

which should generate the following output along with any relevant warning messages:

```plaintext
<!-- cmdrun pytribeam -->
```
