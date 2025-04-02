from typing import Any, Dict, NamedTuple, Optional, Type, Union
from copy import deepcopy
import tkinter as tk
import pytribeam.GUI.CustomTkinterWidgets as ctk

from pytribeam import types as tbt
from pytribeam import utilities as ut
from pytribeam import constants as cs

MAX_VERSION = float(cs.Constants.yml_schema_version)
MIN_VERSION = 1.0
increment = 0.1

numbers = [
    round(MIN_VERSION + i * increment, 1)
    for i in range(int((MAX_VERSION - MIN_VERSION) / increment) + 1)
]
VERSIONS = [str(i) for i in numbers]

# Import options from types
beam_types = [i.value for i in tbt.BeamType]
wavelengths = [i.value for i in tbt.LaserWavelength]
polarizations = [i.value for i in tbt.LaserPolarization]
coordinate_refs = [i.value for i in tbt.CoordinateReference]
laser_scan_types_box = [i.value for i in tbt.LaserScanType]
laser_scan_types_line = [i.value for i in tbt.LaserScanType]
laser_pattern_modes = [i.value for i in tbt.LaserPatternMode]
detector_types = [i.value for i in tbt.DetectorType]
detector_modes = [i.value for i in tbt.DetectorMode]
resolutions = [i.value for i in tbt.PresetResolution]
fib_scan_dirs = [i.value for i in tbt.FIBPatternScanDirection]
fib_scan_types = [i.value for i in tbt.FIBPatternScanType]
bit_depths = [i.value for i in tbt.ColorDepth]
rotation_sides = [i.value for i in tbt.RotationSide]
ebsd_grid_types = [i.value for i in tbt.EBSDGridType]

# Options need empty values
beam_types.append("")
wavelengths.append("")
coordinate_refs.append("")
laser_scan_types_box.append("")
laser_scan_types_line.append("")
laser_pattern_modes.append("")
detector_types.append("")
detector_modes.append("")
resolutions.append("WIDTHxHEIGHT")
fib_scan_dirs.append("")
fib_scan_types.append("")
rotation_sides.append("")


class LUTField(NamedTuple):
    """Represents a single field in the LUT with both GUI and type information"""

    label: str
    default: Any
    widget: Type[tk.Widget]
    widget_kwargs: Dict[str, Any]
    help_text: str
    dtype: Type
    version_limit: tbt.Limit


class LUT:
    """Base class for type-aware lookup tables"""

    def __init__(self, name: Optional[str] = None):
        self._entries = {}
        self.name = name

    def __repr__(self):
        return f"LUT({self.name})"

    def __str__(self):
        """Should behave like a dictionary."""
        return str(self._entries)

    def __getitem__(self, key: str) -> LUTField:
        return self.get_entry(key)

    def __setitem__(self, key: str, value: Union[LUTField, "LUT"]):
        self.add_entry(key, value)

    def __eq__(self, other: "LUT") -> bool:
        """Compare two TypedLUTs for equality"""
        if not isinstance(other, LUT):
            return False

        # Compare flattened versions to check structure and content
        this = self._flatten()
        that = other._flatten()
        return this == that

    def keys(self):
        return self._entries.keys()

    def values(self):
        return self._entries.values()

    def items(self):
        return self._entries.items()

    def add_entry(self, name: str, field: Union[LUTField, "LUT"]):
        self._entries[name] = field

    def get_entry(self, name: str) -> LUTField:
        return self._entries[name]

    def remove_entry(self, name: str):
        return self._entries.pop(name)

    def flatten(self, separator: str = "/") -> Dict[str, LUTField]:
        """Flatten the LUT into a dictionary of fields with paths as keys."""
        self._entries = self._flatten(separator=separator)

    def _flatten(self, separator: str = "/", prefix: str = ""):
        """Flattens the fields using a separator. This is done in place."""
        flattened = {}

        for name, entry in self._entries.items():
            current_path = f"{prefix}{name}" if prefix else name

            if isinstance(entry, LUTField):
                flattened[current_path] = entry
            elif isinstance(entry, LUT):
                # Recursively flatten nested LUT
                nested_flat = entry._flatten(
                    separator=separator, prefix=f"{current_path}{separator}"
                )
                flattened.update(nested_flat)

        return flattened

    def unflatten(self, separator: str = "/") -> "LUT":
        """Reconstruct a TypedLUT from a flattened dictionary."""
        self._entries = self._unflatten(self._entries, separator=separator)._entries

    @classmethod
    def _unflatten(cls, flat_dict: Dict[str, LUTField], separator: str = "/") -> "LUT":
        """
        Reconstruct a TypedLUT from a flattened dictionary.
        Args:
            flat_dict: Dictionary with path-based keys and LUTField values
            separator: String used as path separator in the keys

        Returns:
            TypedLUT: Reconstructed hierarchical structure
        """
        root = cls()

        for path, field in flat_dict.items():
            # Split path into components
            parts = path.split(separator)

            # Start at root
            current = root

            # Create/traverse path
            for i, part in enumerate(parts[:-1]):  # All but last component
                if part not in current._entries:
                    current._entries[part] = cls(name=part)
                current = current._entries[part]

            # Add the field at the final location
            current._entries[parts[-1]] = field

        return root

    @property
    def entries(self) -> Dict[str, LUTField]:
        return self._entries


### EDAX LUT ###
edax_host = LUTField(
    "EDAX Host Address",
    "",
    ctk.Entry,
    {"dtype": str},
    "The host IP address of the computer that runs the EDAX machines.",
    str,
    tbt.Limit(min=1.1, max=MAX_VERSION),
)
edax_port = LUTField(
    "EDAX Port",
    "",
    ctk.Entry,
    {"dtype": int},
    "The port used to access the computer that runs the EDAX machines.",
    int,
    tbt.Limit(min=1.1, max=MAX_VERSION),
)
edax_save_directory = LUTField(
    "Save Folder",
    "",
    ctk.Entry,
    {"dtype": str},
    "The folder on the EDAX PC where the collected EBSD images should be saved.",
    str,
    tbt.Limit(min=1.1, max=MAX_VERSION),
)
edax_project_name = LUTField(
    "Project Name",
    "",
    ctk.Entry,
    {"dtype": str},
    "The name under which to save the EBSD images on the EDAX PC.",
    str,
    tbt.Limit(min=1.1, max=MAX_VERSION),
)
edax_connection_lut = LUT("connection")
edax_connection_lut.add_entry("host", edax_host)
edax_connection_lut.add_entry("port", edax_port)
edax_settings_lut = LUT("EDAX_settings")
edax_settings_lut.add_entry("connection", edax_connection_lut)
edax_settings_lut.add_entry("save_directory", edax_save_directory)
edax_settings_lut.add_entry("project_name", edax_project_name)

### Email LUT ###
email_ssh_host = LUTField(
    "SSH Tunnel Host",
    "",
    ctk.Entry,
    {"dtype": str},
    "The IP address of the host to tunnel through for the email server.",
    str,
    tbt.Limit(min=1.2, max=MAX_VERSION),
)
email_ssh_port = LUTField(
    "SSH Tunnel Port",
    1025,
    ctk.Entry,
    {"dtype": int},
    "The port to tunnel through for the email server.",
    int,
    tbt.Limit(min=1.2, max=MAX_VERSION),
)
email_ssh_user = LUTField(
    "SSH Tunnel User",
    "",
    ctk.Entry,
    {"dtype": str},
    "The username of the PC hosting the SSH tunnel.",
    str,
    tbt.Limit(min=1.2, max=MAX_VERSION),
)
email_ssh_key_path = LUTField(
    "SSH Key Path",
    "",
    ctk.PathEntry,
    {"dtype": str, "directory": False, "operation": "open"},
    "The path to the SSH private key used for passwordless authentication through tunnel.",
    str,
    tbt.Limit(min=1.2, max=MAX_VERSION),
)
email_smtp_server = LUTField(
    "SMTP Server",
    "smtp.gmail.com",
    ctk.Entry,
    {"dtype": str},
    "The SMTP server to use for sending the email.",
    str,
    tbt.Limit(min=1.2, max=MAX_VERSION),
)
email_smtp_port = LUTField(
    "SMTP Port",
    587,
    ctk.Entry,
    {"dtype": int},
    "The port of the SMTP server to use for sending the email.",
    int,
    tbt.Limit(min=1.2, max=MAX_VERSION),
)
email_sender = LUTField(
    "Email User",
    "",
    ctk.Entry,
    {"dtype": str},
    "The email address used to send the email.",
    str,
    tbt.Limit(min=1.2, max=MAX_VERSION),
)
email_password = LUTField(
    "Email Password",
    "",
    ctk.Entry,
    {"dtype": str},
    "The password for the email address used to send the email. For Gmail, this should be a 'App Password' generated from the Google account settings.",
    str,
    tbt.Limit(min=1.2, max=MAX_VERSION),
)
email_recipients = LUTField(
    "Recipients",
    "",
    ctk.Entry,
    {"dtype": str},
    "The email addresses to send the email to. Separate multiple addresses with commas.",
    str,
    tbt.Limit(min=1.2, max=MAX_VERSION),
)
email_lut = LUT("email")
email_lut.add_entry("ssh_host", email_ssh_host)
email_lut.add_entry("ssh_port", email_ssh_port)
email_lut.add_entry("ssh_user", email_ssh_user)
email_lut.add_entry("ssh_key_path", email_ssh_key_path)
email_lut.add_entry("smtp_server", email_smtp_server)
email_lut.add_entry("smtp_port", email_smtp_port)
email_lut.add_entry("sender", email_sender)
email_lut.add_entry("sender_password", email_password)
email_lut.add_entry("recipients", email_recipients)

### General LUT ###
slice_thickness_um = LUTField(
    "Slice Thickness (um)",
    "1.0",
    ctk.Entry,
    {"dtype": float},
    "Thickness of the laser cut slice in micrometers.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
max_slice_num = LUTField(
    "Max Slice Number",
    "1",
    ctk.Entry,
    {"dtype": int},
    "The maximum slice number to cut. The experiment will stop after this slice number is complete.",
    int,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
pre_tilt_deg = LUTField(
    "Pre-Tilt Angle (deg)",
    "0.0",
    ctk.Entry,
    {"dtype": float},
    "The angle to pre-tilt sample holder used. This angle impacts how stage movements are determined.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
sectioning_axis = LUTField(
    "Sectioning Axis",
    "Z",
    ctk.MenuButton,
    {"options": ["X+", "X-", "Y+", "Y-", "Z"], "dtype": str},
    "The axis that the laser will cut along. Can be X, Y, or Z.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
stage_translational_tol_um = LUTField(
    "Stage Translational Tolerance (um)",
    0.5,
    ctk.Entry,
    {"dtype": float},
    "The tolerance for translational stage movements in micrometers.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
stage_angular_tol_deg = LUTField(
    "Stage Angular Tolerance (deg)",
    0.02,
    ctk.Entry,
    {"dtype": float},
    "The tolerance for angular stage movements in degrees.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
connection_host = LUTField(
    "Connection Host",
    "localhost",
    ctk.Entry,
    {"dtype": str},
    "The host of the connection to the SEM.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
connection_port = LUTField(
    "Connection Port",
    "",
    ctk.Entry,
    {"dtype": int},
    "The port of the connection to the SEM.",
    int,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
ebsd_oem = LUTField(
    "EBSD OEM",
    "",
    ctk.MenuButton,
    {"options": ["EDAX", "Oxford", "null"], "dtype": str},
    "The OEM of the EBSD system being used.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
eds_oem = LUTField(
    "EDS OEM",
    "",
    ctk.MenuButton,
    {"options": ["EDAX", "Oxford", "null"], "dtype": str},
    "The OEM of the EDS system being used.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
exp_dir = LUTField(
    "Experiment Directory",
    "./",
    ctk.PathEntry,
    {"directory": True},
    "The directory where the experiment data is saved.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
h5_log_name = LUTField(
    "H5 Log Name",
    "log",
    ctk.Entry,
    {"dtype": str},
    "The name of the HDF5 log file.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
step_count = LUTField(
    "Step Count",
    0,
    ctk.Entry,
    {"dtype": int},
    "The number of steps in the experiment.",
    int,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
general_lut = LUT("general")
general_lut.add_entry("slice_thickness_um", deepcopy(slice_thickness_um))
general_lut.add_entry("max_slice_num", deepcopy(max_slice_num))
general_lut.add_entry("pre_tilt_deg", deepcopy(pre_tilt_deg))
general_lut.add_entry("sectioning_axis", deepcopy(sectioning_axis))
general_lut.add_entry(
    "stage_translational_tol_um", deepcopy(stage_translational_tol_um)
)
general_lut.add_entry("stage_angular_tol_deg", deepcopy(stage_angular_tol_deg))
general_lut.add_entry("connection_host", deepcopy(connection_host))
general_lut.add_entry("connection_port", deepcopy(connection_port))
general_lut.add_entry("EBSD_OEM", deepcopy(ebsd_oem))
general_lut.add_entry("EDS_OEM", deepcopy(eds_oem))
general_lut.add_entry("exp_dir", deepcopy(exp_dir))
general_lut.add_entry("h5_log_name", deepcopy(h5_log_name))
general_lut.add_entry("email_update_settings", deepcopy(email_lut))
general_lut.add_entry("EDAX_settings", deepcopy(edax_settings_lut))
general_lut.add_entry("step_count", deepcopy(step_count))

### STAGE ###
x_mm = LUTField(
    "Start X Position (mm)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The starting X position of the step on slice 1.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
y_mm = LUTField(
    "Start Y Position (mm)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The starting Y position of the step on slice 1.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
z_mm = LUTField(
    "Start Z Position (mm)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The starting Z position of the step on slice 1.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
t_deg = LUTField(
    "Start T Position (°)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The starting T position of the step on slice 1.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
r_deg = LUTField(
    "Start R Position (°)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The starting R position of the step on slice 1.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
rotation_side = LUTField(
    "Rotation Side",
    rotation_sides[-1],
    ctk.MenuButton,
    {"options": rotation_sides, "dtype": str},
    "Whether the sample pretilt is in the laser position or the FIB position.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
initial_pos_lut = LUT("initial_position")
initial_pos_lut.add_entry("x_mm", x_mm)
initial_pos_lut.add_entry("y_mm", y_mm)
initial_pos_lut.add_entry("z_mm", z_mm)
initial_pos_lut.add_entry("t_deg", t_deg)
initial_pos_lut.add_entry("r_deg", r_deg)
stage_lut = LUT("stage")
stage_lut.add_entry("rotation_side", rotation_side)
stage_lut.add_entry("initial_position", initial_pos_lut)

### COMMON ###
step_name = LUTField(
    "Step Name",
    "",
    ctk.Entry,
    {"dtype": str},
    "The name of the step.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
step_number = LUTField(
    "Step Number",
    "",
    ctk.Entry,
    {"state": "disabled", "dtype": int},
    "The number of the step in the sequence of steps.",
    int,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
step_type = LUTField(
    "Step Type",
    "",
    ctk.Entry,
    {"state": "disabled", "dtype": str},
    "The step type.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
frequency = LUTField(
    "Frequency",
    1,
    ctk.Entry,
    {"dtype": int},
    "The frequency that this step is activated (i.e. 1 means every slice, 2 means every other slice, etc.).",
    int,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
common_lut = LUT("stage")
common_lut.add_entry("step_name", step_name)
common_lut.add_entry("step_number", step_number)
common_lut.add_entry("step_type", step_type)
common_lut.add_entry("frequency", frequency)
common_lut.add_entry("stage", stage_lut)

### AUTO_CB ###
left = LUTField(
    "Left Fraction",
    "",
    ctk.Entry,
    {"dtype": float},
    "Fractional position (of the entire image) for the left edge of the reduced area for auto contrast and brightness adjustment. Empty/None/null for all fractions turns off ACB.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
width = LUTField(
    "Width Fraction",
    "",
    ctk.Entry,
    {"dtype": float},
    "The fractional width (of the entire image) to use for auto contrast and brightness. Empty/None for all fractions turns off ACB.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
top = LUTField(
    "Top Fraction",
    "",
    ctk.Entry,
    {"dtype": float},
    "Fractional position (of the entire image) for the top edge of the reduced area for auto contrast and brightness adjustment. Empty/None for all fractions turns off ACB.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
height = LUTField(
    "Height Fraction",
    "",
    ctk.Entry,
    {"dtype": float},
    "The fractional height (of the entire image) to use for auto contrast and brightness. Empty/None for all fractions turns off ACB.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
auto_cb_lut = LUT("auto_cb")
auto_cb_lut.add_entry("left", left)
auto_cb_lut.add_entry("width", width)
auto_cb_lut.add_entry("top", top)
auto_cb_lut.add_entry("height", height)

### BEAM ###
beam_type = LUTField(
    "Beam Type",
    beam_types[-1],
    ctk.MenuButton,
    {"options": beam_types, "dtype": str},
    "The type of beam used to acquire the image.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
voltage_kv = LUTField(
    "Beam Voltage (kV)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The voltage of the beam in keV.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
voltage_tol_kv = LUTField(
    "Beam Voltage Tolerance (kV)",
    0.1,
    ctk.Entry,
    {"dtype": float},
    "The tolerance of the beam voltage in kV.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
current_na = LUTField(
    "Beam Current (nA)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The current of the beam in nA.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
current_tol_na = LUTField(
    "Beam Current Tolerance (nA)",
    0.5,
    ctk.Entry,
    {"dtype": float},
    "The tolerance of the beam current in nA.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
hfw_mm = LUTField(
    "Horizontal Field Width (mm)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The horizontal field width of the image in mm.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
working_dist_mm = LUTField(
    "Working Distance (mm)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The working distance of the image in mm.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
dynamic_focus = LUTField(
    "Use Dynamic Focus",
    "False",
    ctk.Checkbutton,
    {"offvalue": "False", "onvalue": "True", "bd": 0, "dtype": bool},
    "Whether to use dynamic focusing.",
    bool,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
tilt_correction = LUTField(
    "Use Tilt Correction",
    "False",
    ctk.Checkbutton,
    {"offvalue": "False", "onvalue": "True", "bd": 0, "dtype": bool},
    "Whether to use tilt correction.",
    bool,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
beam_lut = LUT("beam")
beam_lut.add_entry("type", beam_type)
beam_lut.add_entry("voltage_kv", voltage_kv)
beam_lut.add_entry("voltage_tol_kv", voltage_tol_kv)
beam_lut.add_entry("current_na", current_na)
beam_lut.add_entry("current_tol_na", current_tol_na)
beam_lut.add_entry("hfw_mm", hfw_mm)
beam_lut.add_entry("working_dist_mm", working_dist_mm)
beam_lut.add_entry("dynamic_focus", dynamic_focus)
beam_lut.add_entry("tilt_correction", tilt_correction)

### LASER ###
laser_pulse_wavelength_nm = LUTField(
    "Wavelength (nm)",
    wavelengths[-1],
    ctk.MenuButton,
    {"options": wavelengths, "dtype": int},
    "The wavelength of the laser.",
    int,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pulse_divider = LUTField(
    "Pulse Divider",
    "",
    ctk.Entry,
    {"dtype": int},
    "Determines the repetition rate of the laser.",
    int,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pulse_energy_uj = LUTField(
    "Energy (uJ)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The energy of the laser pulse in microjoules.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pulse_polarization = LUTField(
    "Polarization",
    polarizations[0],
    ctk.MenuButton,
    {"options": polarizations, "dtype": str},
    "The polarization of the laser.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_objective_position_mm = LUTField(
    "Objective Position (mm)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The position of the objective lens in millimeters.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pattern_passes = LUTField(
    "Passes",
    "",
    ctk.Entry,
    {"dtype": int},
    "The number of passes the laser will make.",
    int,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pattern_size_x_um = LUTField(
    "Size X (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The size of the box in the X direction in micrometers.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pattern_size_y_um = LUTField(
    "Size Y (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The size of the box in the Y direction in micrometers.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pattern_pitch_x_um = LUTField(
    "Pitch X (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The pitch of the box in the X direction in micrometers.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pattern_pitch_y_um = LUTField(
    "Pitch Y (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The pitch of the box in the Y direction in micrometers.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pattern_scan_type = LUTField(
    "Scan Type",
    laser_scan_types_box[-1],
    ctk.MenuButton,
    {"options": laser_scan_types_box, "dtype": str},
    "The type of scan to perform.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pattern_coordinate_ref = LUTField(
    "Coordinate Reference",
    coordinate_refs[-1],
    ctk.MenuButton,
    {"options": coordinate_refs, "dtype": str},
    "The reference coordinate for the scan.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pattern_size_um = LUTField(
    "Size (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The size of the line in micrometers.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pattern_pitch_um = LUTField(
    "Pitch (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The pitch of the line in micrometers.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pattern_rotation_deg = LUTField(
    "Scan Rotation (deg)",
    0.0,
    ctk.Entry,
    {"dtype": float},
    "The rotation of the scan in degrees.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pattern_mode = LUTField(
    "Mode",
    laser_pattern_modes[-1],
    ctk.MenuButton,
    {"options": laser_pattern_modes, "dtype": str},
    "The mode of the laser.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pattern_pulses_per_pixel = LUTField(
    "Pulses Per Pixel",
    "",
    ctk.Entry,
    {"dtype": int},
    "The number of pulses per pixel (only matters for fine).",
    int,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pattern_pixel_dwell_ms = LUTField(
    "Pixel Dwell Time (ms)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The dwell time of the laser in milliseconds (only matters for coarse).",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_beam_shift_x_um = LUTField(
    "Beam Shift X (um)",
    0.0,
    ctk.Entry,
    {"dtype": float},
    "The beam shift in the X direction in micrometers. Is applied on top of the hardware shift.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_beam_shift_y_um = LUTField(
    "Beam Shift Y (um)",
    0.0,
    ctk.Entry,
    {"dtype": float},
    "The beam shift in the Y direction in micrometers. Is applied on top of the hardware shift.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_pulse_lut = LUT("pulse")
laser_pulse_lut.add_entry("wavelength_nm", laser_pulse_wavelength_nm)
laser_pulse_lut.add_entry("divider", laser_pulse_divider)
laser_pulse_lut.add_entry("energy_uj", laser_pulse_energy_uj)
laser_pulse_lut.add_entry("polarization", laser_pulse_polarization)
laser_line_pattern_lut = LUT("line")
laser_line_pattern_lut.add_entry("passes", laser_pattern_passes)
laser_line_pattern_lut.add_entry("size_um", laser_pattern_size_um)
laser_line_pattern_lut.add_entry("pitch_um", laser_pattern_pitch_um)
laser_line_pattern_lut.add_entry("scan_type", laser_pattern_scan_type)
laser_box_pattern_lut = LUT("box")
laser_box_pattern_lut.add_entry("passes", laser_pattern_passes)
laser_box_pattern_lut.add_entry("size_x_um", laser_pattern_size_x_um)
laser_box_pattern_lut.add_entry("size_y_um", laser_pattern_size_y_um)
laser_box_pattern_lut.add_entry("pitch_x_um", laser_pattern_pitch_x_um)
laser_box_pattern_lut.add_entry("pitch_y_um", laser_pattern_pitch_y_um)
laser_box_pattern_lut.add_entry("scan_type", laser_pattern_scan_type)
laser_box_pattern_lut.add_entry("coordinate_ref", laser_pattern_coordinate_ref)
laser_pattern_type_lut = LUT("type")
laser_pattern_type_lut.add_entry("box", laser_box_pattern_lut)
laser_pattern_type_lut.add_entry("line", laser_line_pattern_lut)
laser_pattern_lut = LUT("pattern")
laser_pattern_lut.add_entry("type", laser_pattern_type_lut)
laser_pattern_lut.add_entry("rotation_deg", laser_pattern_rotation_deg)
laser_pattern_lut.add_entry("mode", laser_pattern_mode)
laser_pattern_lut.add_entry("pulses_per_pixel", laser_pattern_pulses_per_pixel)
laser_pattern_lut.add_entry("pixel_dwell_ms", laser_pattern_pixel_dwell_ms)
laser_beam_shift_lut = LUT("beam_shift")
laser_beam_shift_lut.add_entry("x_um", laser_beam_shift_x_um)
laser_beam_shift_lut.add_entry("y_um", laser_beam_shift_y_um)
laser_lut = LUT("laser")
laser_lut.add_entry("step_general", deepcopy(common_lut))
laser_lut.add_entry("pulse", deepcopy(laser_pulse_lut))
laser_lut.add_entry("objective_position_mm", deepcopy(laser_objective_position_mm))
laser_lut.add_entry("beam_shift", deepcopy(laser_beam_shift_lut))
laser_lut.add_entry("pattern", deepcopy(laser_pattern_lut))
# Laser should have a step type and name of laser

### IMAGE ###
detector_type = LUTField(
    "Detector Type",
    detector_types[-1],
    ctk.MenuButton,
    {"options": detector_types, "dtype": str},
    "The type of detector used to acquire the image.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
detector_mode = LUTField(
    "Detector Mode",
    detector_modes[-1],
    ctk.MenuButton,
    {"options": detector_modes, "dtype": str},
    "The mode of the detector used to acquire the image.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
brightness_fraction = LUTField(
    "Brightness Fraction",
    "",
    ctk.Entry,
    {"dtype": float},
    "(If auto contrast/brightness is False) The fractional brightness value to use.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
contrast_fraction = LUTField(
    "Contrast Fraction",
    "",
    ctk.Entry,
    {"dtype": float},
    "(If auto contrast/brightness is False) The fractional contrast value to use.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
image_rotation_deg = LUTField(
    "Scan Rotation (deg)",
    0.0,
    ctk.Entry,
    {"dtype": float},
    "The rotation of the scan in degrees.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
image_dwell_time_us = LUTField(
    "Dwell Time (us)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The dwell time of the image in microseconds.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
image_resolution = LUTField(
    "Resolution",
    resolutions[-1],
    ctk.EntryMenuButton,
    {"options": resolutions, "dtype": str},
    "The resolution of the image. Can be a present or custom resolution.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
image_bit_depth = LUTField(
    "Bit Depth",
    bit_depths[0],
    ctk.MenuButton,
    {"options": bit_depths, "dtype": int},
    "The bit depth of the image.",
    int,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
detector_lut = LUT("detector")
detector_lut.add_entry("type", detector_type)
detector_lut.add_entry("mode", detector_mode)
detector_lut.add_entry("brightness", brightness_fraction)
detector_lut.add_entry("contrast", contrast_fraction)
detector_lut.add_entry("auto_cb", auto_cb_lut)
scan_lut = LUT("scan")
scan_lut.add_entry("rotation_deg", image_rotation_deg)
scan_lut.add_entry("dwell_time_us", image_dwell_time_us)
scan_lut.add_entry("resolution", image_resolution)
image_lut = LUT("image")
image_lut.add_entry("step_general", deepcopy(common_lut))
image_lut.add_entry("beam", deepcopy(beam_lut))
image_lut.add_entry("detector", deepcopy(detector_lut))
image_lut.add_entry("scan", deepcopy(scan_lut))
image_lut.add_entry("bit_depth", deepcopy(image_bit_depth))
# Image should have a step type and name of image

### EDS ###
eds_lut = LUT("eds")
eds_lut.add_entry("step_general", deepcopy(common_lut))
eds_lut.add_entry("beam", deepcopy(beam_lut))
eds_lut.add_entry("detector", deepcopy(detector_lut))
eds_lut.add_entry("scan", deepcopy(scan_lut))
eds_lut.add_entry("bit_depth", deepcopy(image_bit_depth))
# EDS should be electron beam types only, and should have a step type and name of eds

### EBSD ###
ebsd_concurrent_eds = LUTField(
    "Concurrent EDS",
    "False",
    ctk.Checkbutton,
    {"offvalue": "False", "onvalue": "True", "bd": 0, "dtype": bool},
    "Whether to acquire EDS data concurrently with the EBSD data.",
    bool,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
edax_x_start_um = LUTField(
    "X Start (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The starting X position of the EBSD scan in micrometers.",
    float,
    tbt.Limit(min=1.1, max=MAX_VERSION),
)
edax_y_start_um = LUTField(
    "Y Start (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The starting Y position of the EBSD scan in micrometers.",
    float,
    tbt.Limit(min=1.1, max=MAX_VERSION),
)
edax_x_size_um = LUTField(
    "X Size (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The horizontal span of the EBSD scan in micrometers.",
    float,
    tbt.Limit(min=1.1, max=MAX_VERSION),
)
edax_y_size_um = LUTField(
    "Y Size (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The vertical span of the EBSD scan in micrometers.",
    float,
    tbt.Limit(min=1.1, max=MAX_VERSION),
)
edax_step_size_um = LUTField(
    "Step Size (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The step size of the EBSD scan in micrometers.",
    float,
    tbt.Limit(min=1.1, max=MAX_VERSION),
)
edax_grid_type = LUTField(
    "Grid Type",
    ebsd_grid_types[-1],
    ctk.MenuButton,
    {"dtype": str, "options": ebsd_grid_types},
    "The type of grid to use for the EBSD scan. 0 is hexagonal, 1 is square.",
    str,
    tbt.Limit(min=1.1, max=MAX_VERSION),
)
edax_save_patterns = LUTField(
    "Save Patterns",
    "False",
    ctk.Checkbutton,
    {"offvalue": "False", "onvalue": "True", "bd": 0, "dtype": bool},
    "Whether to save the patterns.",
    bool,
    tbt.Limit(min=1.1, max=MAX_VERSION),
)
edax_scan_box_lut = LUT("scan_box")
edax_scan_box_lut.add_entry("x_start_um", edax_x_start_um)
edax_scan_box_lut.add_entry("y_start_um", edax_y_start_um)
edax_scan_box_lut.add_entry("x_size_um", edax_x_size_um)
edax_scan_box_lut.add_entry("y_size_um", edax_y_size_um)
edax_scan_box_lut.add_entry("step_size_um", edax_step_size_um)
edax_params_lut = LUT("edax_settings")
edax_params_lut.add_entry("scan_box", edax_scan_box_lut)
edax_params_lut.add_entry("scan_box", edax_scan_box_lut)
edax_params_lut.add_entry("grid_type", edax_grid_type)
edax_params_lut.add_entry("save_patterns", edax_save_patterns)
ebsd_lut = LUT("ebsd")
ebsd_lut.add_entry("step_general", deepcopy(common_lut))
ebsd_lut.add_entry("beam", deepcopy(beam_lut))
ebsd_lut.add_entry("detector", deepcopy(detector_lut))
ebsd_lut.add_entry("scan", deepcopy(scan_lut))
ebsd_lut.add_entry("bit_depth", deepcopy(image_bit_depth))
ebsd_lut.add_entry("concurrent_EDS", deepcopy(ebsd_concurrent_eds))
ebsd_lut.add_entry("edax_settings", deepcopy(edax_params_lut))
# EBSD should be electron beam types only, and should have a step type and name of ebsd

### PFIB ###
center_x_um = LUTField(
    "Center X (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The X coordinate of the center of the milling pattern.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
center_y_um = LUTField(
    "Center Y (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The Y coordinate of the center of the milling pattern.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
width_um = LUTField(
    "Width (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The width of the rectangle in micrometers.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
height_um = LUTField(
    "Height (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The height of the rectangle in micrometers.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
depth_um = LUTField(
    "Depth (um)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The depth of the rectangle in micrometers.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
scan_direction = LUTField(
    "Scan Direction",
    fib_scan_dirs[-1],
    ctk.MenuButton,
    {"options": fib_scan_dirs, "dtype": str},
    "The direction of the scan.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
scan_type = LUTField(
    "Scan Type",
    fib_scan_types[-1],
    ctk.MenuButton,
    {"options": fib_scan_types, "dtype": str},
    "The type of scan to perform.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
dwell_us = LUTField(
    "Mill Dwell Time (us)",
    "",
    ctk.Entry,
    {"dtype": float},
    "The dwell time of the mill in microseconds.",
    float,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
repeats = LUTField(
    "Pattern Repeats",
    "",
    ctk.Entry,
    {"dtype": int},
    "The number of times to repeat the pattern.",
    int,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
recipe_file = LUTField(
    "Image Processing Recipe",
    "",
    ctk.PathEntry,
    {"directory": False, "defaultextension": ".py"},
    "The recipe to use for image processing. Must be a python (.py) file.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
mask_file = LUTField(
    "Mask File",
    "",
    ctk.PathEntry,
    {"directory": False, "defaultextension": ".tif"},
    "During this step, the mask file to use for milling will be saved (and overwritten) in this location. Should be a tiff (.tif) file. All masks will be saved automatically during the experiment.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
application_file = LUTField(
    "Application File",
    "",
    ctk.Entry,
    {"dtype": str},
    "The application file preset to use for milling.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
fib_center_lut = LUT("center")
fib_center_lut.add_entry("x_um", center_x_um)
fib_center_lut.add_entry("y_um", center_y_um)
fib_rectangle_pattern_lut = LUT("rectangle")
fib_rectangle_pattern_lut.add_entry("center", fib_center_lut)
fib_rectangle_pattern_lut.add_entry("width_um", width_um)
fib_rectangle_pattern_lut.add_entry("height_um", height_um)
fib_rectangle_pattern_lut.add_entry("depth_um", depth_um)
fib_rectangle_pattern_lut.add_entry("scan_direction", scan_direction)
fib_rectangle_pattern_lut.add_entry("scan_type", scan_type)
fib_selected_pattern_lut = LUT("selected_area")
fib_selected_pattern_lut.add_entry("dwell_us", dwell_us)
fib_selected_pattern_lut.add_entry("repeats", repeats)
fib_selected_pattern_lut.add_entry("recipe_file", recipe_file)
fib_selected_pattern_lut.add_entry("mask_file", mask_file)
fib_pattern_type_lut = LUT("type")
fib_pattern_type_lut.add_entry("rectangle", fib_rectangle_pattern_lut)
fib_pattern_type_lut.add_entry("regular_cross_section", fib_rectangle_pattern_lut)
fib_pattern_type_lut.add_entry("cleaning_cross_section", fib_rectangle_pattern_lut)
fib_pattern_type_lut.add_entry("selected_area", fib_selected_pattern_lut)
fib_pattern_lut = LUT("pattern")
fib_pattern_lut.add_entry("application_file", application_file)
fib_pattern_lut.add_entry("type", fib_pattern_type_lut)
fib_mill_lut = LUT("mill")
fib_mill_lut.add_entry("beam", beam_lut)
fib_mill_lut.add_entry("pattern", fib_pattern_lut)
fib_image_lut = LUT("image")
fib_image_lut.add_entry("beam", beam_lut)
fib_image_lut.add_entry("detector", detector_lut)
fib_image_lut.add_entry("scan", scan_lut)
fib_image_lut.add_entry("bit_depth", image_bit_depth)
fib_lut = LUT("fib")
fib_lut.add_entry("step_general", deepcopy(common_lut))
fib_lut.add_entry("image", deepcopy(fib_image_lut))
fib_lut.add_entry("mill", deepcopy(fib_mill_lut))
# FIB should be ion beam types only, dynamic focus should be off, and tilt correction should be off, and step type and name should be fib

### Custom step ###
custom_executable_path = LUTField(
    "Executable Path",
    "",
    ctk.PathEntry,
    {"directory": False, "operation": "open"},
    "The path to the executable to run. For python, this would be the location of the python executable.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
custom_script_path = LUTField(
    "Custom Script Path",
    "",
    ctk.PathEntry,
    {"directory": False, "operation": "open"},
    "The path to the custom script to run.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
custom_lut = LUT("custom")
custom_lut.add_entry("step_general", deepcopy(common_lut))
custom_lut.add_entry("executable_path", deepcopy(custom_executable_path))
custom_lut.add_entry("script_path", deepcopy(custom_script_path))
# Custom should have a step type and name of custom

# Apply edits to luts based on step type (enforce names/types, disable/enable fields, etc.)
laser_lut["step_general"]["step_type"] = LUTField(
    "Step Type",
    "laser",
    ctk.Entry,
    {"state": "disabled", "dtype": str},
    "The step type.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
laser_lut["step_general"]["step_name"] = LUTField(
    "Step Name",
    "laser",
    ctk.Entry,
    {"dtype": str},
    "The name of the step.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
image_lut["step_general"]["step_type"] = LUTField(
    "Step Type",
    "image",
    ctk.Entry,
    {"state": "disabled", "dtype": str},
    "The step type.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
image_lut["step_general"]["step_name"] = LUTField(
    "Step Name",
    "image",
    ctk.Entry,
    {"dtype": str},
    "The name of the step.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
eds_lut["step_general"]["step_type"] = LUTField(
    "Step Type",
    "eds",
    ctk.Entry,
    {"state": "disabled", "dtype": str},
    "The step type.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
eds_lut["step_general"]["step_name"] = LUTField(
    "Step Name",
    "eds",
    ctk.Entry,
    {"dtype": str},
    "The name of the step.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
eds_lut["beam"]["type"] = LUTField(
    "Beam Type",
    beam_types[0],
    ctk.MenuButton,
    {"options": beam_types, "dtype": str, "state": "disabled"},
    "The type of beam used to acquire the image.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
ebsd_lut["step_general"]["step_type"] = LUTField(
    "Step Type",
    "ebsd",
    ctk.Entry,
    {"state": "disabled", "dtype": str},
    "The step type.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
ebsd_lut["step_general"]["step_name"] = LUTField(
    "Step Name",
    "ebsd",
    ctk.Entry,
    {"dtype": str},
    "The name of the step.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
ebsd_lut["beam"]["type"] = LUTField(
    "Beam Type",
    beam_types[0],
    ctk.MenuButton,
    {"options": beam_types, "dtype": str, "state": "disabled"},
    "The type of beam used to acquire the image.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
fib_lut["step_general"]["step_type"] = LUTField(
    "Step Type",
    "fib",
    ctk.Entry,
    {"state": "disabled", "dtype": str},
    "The step type.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
fib_lut["step_general"]["step_name"] = LUTField(
    "Step Name",
    "fib",
    ctk.Entry,
    {"dtype": str},
    "The name of the step.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
fib_lut["image"]["beam"]["type"] = LUTField(
    "Beam Type",
    beam_types[1],
    ctk.MenuButton,
    {"options": beam_types, "dtype": str, "state": "disabled"},
    "The type of beam used to acquire the image.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
fib_lut["image"]["beam"]["dynamic_focus"] = LUTField(
    "Use Dynamic Focus",
    "False",
    ctk.Checkbutton,
    {
        "offvalue": "False",
        "onvalue": "True",
        "bd": 0,
        "dtype": bool,
        "state": "disabled",
    },
    "Whether to use dynamic focusing.",
    bool,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
fib_lut["image"]["beam"]["tilt_correction"] = LUTField(
    "Use Tilt Correction",
    "False",
    ctk.Checkbutton,
    {
        "offvalue": "False",
        "onvalue": "True",
        "bd": 0,
        "dtype": bool,
        "state": "disabled",
    },
    "Whether to use tilt correction.",
    bool,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
fib_lut["mill"]["beam"]["type"] = LUTField(
    "Beam Type",
    beam_types[1],
    ctk.MenuButton,
    {"options": beam_types, "dtype": str, "state": "disabled"},
    "The type of beam used to acquire the image.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
fib_lut["mill"]["beam"]["dynamic_focus"] = LUTField(
    "Use Dynamic Focus",
    "False",
    ctk.Checkbutton,
    {
        "offvalue": "False",
        "onvalue": "True",
        "bd": 0,
        "dtype": bool,
        "state": "disabled",
    },
    "Whether to use dynamic focusing.",
    bool,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
fib_lut["mill"]["beam"]["tilt_correction"] = LUTField(
    "Use Tilt Correction",
    "False",
    ctk.Checkbutton,
    {
        "offvalue": "False",
        "onvalue": "True",
        "bd": 0,
        "dtype": bool,
        "state": "disabled",
    },
    "Whether to use tilt correction.",
    bool,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
custom_lut["step_general"]["step_type"] = LUTField(
    "Step Type",
    "custom",
    ctk.Entry,
    {"state": "disabled", "dtype": str},
    "The step type.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)
custom_lut["step_general"]["step_name"] = LUTField(
    "Step Name",
    "custom",
    ctk.Entry,
    {"dtype": str},
    "The name of the step.",
    str,
    tbt.Limit(min=1.0, max=MAX_VERSION),
)


LUTs = {
    "general": general_lut,
    "laser": laser_lut,
    "image": image_lut,
    "fib": fib_lut,
    "eds": eds_lut,
    "ebsd": ebsd_lut,
    "custom": custom_lut,
}


class VersionedLUT:
    def __init__(self):
        self._default_version = MAX_VERSION
        self.LUTs = deepcopy(LUTs)

    def get_lut(self, step_type: str, version: Optional[str] = None) -> LUT:
        """Retrieve the LUT for the given version and step type.
        This is done by walking through the LUTs and removing the ones that don't match the version and the step type.
        If the version is not provided, the highest version is used.
        """
        if version is None:
            version = self._default_version
        if float(version) > MAX_VERSION:
            raise ValueError(
                f'YML version "{version}" is not supported. Max supported version is "{MAX_VERSION}"'
            )
        if step_type.lower() not in self.LUTs:
            raise ValueError(
                f"Step type {step_type} is not in the list of step types: {list(self.LUTs.keys())}"
            )

        lut = deepcopy(self.LUTs[step_type.lower()])
        lut.flatten()
        items = list(lut.entries.items())
        for name, entry in items:
            if not ut.in_interval(
                version, entry.version_limit, tbt.IntervalType.CLOSED
            ):
                lut.remove_entry(name)
        lut.unflatten()
        return lut


def get_lut(step_type: str, version: Optional[str] = None) -> LUT:
    """Retrieve the LUT for the given version and step type.
    This is done by walking through the LUTs and removing the ones that don't match the version and the step type.
    If the version is not provided, the highest version is used.
    """
    VLUT = VersionedLUT()
    return VLUT.get_lut(step_type, version)


if __name__ == "__main__":
    out_1_1 = get_lut("general", 1.1)
    print(out_1_1.keys())
    out_1_1.flatten()
    print(out_1_1.keys())
