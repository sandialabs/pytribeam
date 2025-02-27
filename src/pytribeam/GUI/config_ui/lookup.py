from copy import deepcopy
from collections import namedtuple
import tkinter as tk
import pytribeam.GUI.CustomTkinterWidgets as ctk

from pytribeam import types as tbt


# TODO: Add in version control for the LUTs
#       Perhaps the LUTs could have a version number at the top
#       Maybe we create new lookup files? Or just new LUTs in the same file?


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
fib_applications = [i.value for i in tbt.FIBApplication]

### new method, which would need a microscope object
# from pytribeam.fib import application_files
# microscope = tbt.Microscope()
# microscope.connect("localhost") #this line is not applicable to every configuration of autoscript, so would need general settings, therefore a bit of a mess to implement in the GUI dynamically
# fib_applications = application_files(microscope=microscope)

fib_scan_dirs = [i.value for i in tbt.FIBPatternScanDirection]
fib_scan_types = [i.value for i in tbt.FIBPatternScanType]
bit_depths = [i.value for i in tbt.ColorDepth]
rotation_sides = [i.value for i in tbt.RotationSide]

# Options need empty values
beam_types.append("")
wavelengths.append("")
# polarizations.append("")
coordinate_refs.append("")
laser_scan_types_box.append("")
laser_scan_types_line.append("")
laser_pattern_modes.append("")
detector_types.append("")
detector_modes.append("")
resolutions.append("WIDTHxHEIGHT")
fib_applications.append("")
fib_scan_dirs.append("")
fib_scan_types.append("")
rotation_sides.append("")

# Create a named tuple for the entries
_e = namedtuple("LUTentry", ["label", "default", "widget", "kwargs", "help_text"])

# Create the general LUT
general_lookup = {
    "slice_thickness_um": _e(
        "Slice Thickness (um)",
        "",
        ctk.Entry,
        {"dtype": float},
        "Thickness of the laser cut slice in micrometers.",
    ),
    "max_slice_num": _e(
        "Max Slice Number",
        "",
        ctk.Entry,
        {"dtype": int},
        "The maximum slice number to cut. The experiment will stop after this slice number is complete.",
    ),
    "pre_tilt_deg": _e(
        "Pre-Tile Angle (deg)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The angle to pre-tilt sample holder used. This angle impacts how stage movements are determined.",
    ),
    "sectioning_axis": _e(
        "Sectioning Axis",
        "Z",
        ctk.MenuButton,
        {"options": ["X", "Y", "Z"], "dtype": str, "state": "disabled"},
        "The axis that the laser will cut along. Can be X, Y, or Z.",
    ),
    "stage_translational_tol_um": _e(
        "Stage Translational Tolerance (um)",
        0.5,
        ctk.Entry,
        {"dtype": float},
        "The tolerance for translational stage movements in micrometers.",
    ),
    "stage_angular_tol_deg": _e(
        "Stage Angular Tolerance (deg)",
        0.02,
        ctk.Entry,
        {"dtype": float},
        "The tolerance for angular stage movements in degrees.",
    ),
    "connection_host": _e(
        "Connection Host",
        "localhost",
        ctk.Entry,
        {"dtype": str},
        "The host of the connection to the SEM.",
    ),
    "connection_port": _e(
        "Connection Port",
        "",
        ctk.Entry,
        {"dtype": int},
        "The port of the connection to the SEM.",
    ),
    "EBSD_OEM": _e(
        "EBSD OEM",
        "",
        ctk.MenuButton,
        {"options": ["EDAX", "Oxford", "null"], "dtype": str},
        "The OEM of the EBSD system being used.",
    ),
    "EDS_OEM": _e(
        "EDS OEM",
        "",
        ctk.MenuButton,
        {"options": ["EDAX", "Oxford", "null"], "dtype": str},
        "The OEM of the EDS system being used.",
    ),
    "exp_dir": _e(
        "Experiment Directory",
        "./",
        ctk.PathEntry,
        {"directory": True},
        "The directory where the experiment data is saved.",
    ),
    "h5_log_name": _e(
        "H5 Log Name",
        "log",
        ctk.Entry,
        {"dtype": str},
        "The name of the HDF5 log file.",
    ),
    "step_count": _e(
        "Step Count",
        0,
        ctk.Entry,
        {"dtype": int},
        "The number of steps in the experiment.",
    ),
}

# Create the common LUTs that are shared between steps
_initial_pos_lookup = {
    "x_mm": _e(
        "Start X Position (mm)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The starting X position of the laser cut.",
    ),
    "y_mm": _e(
        "Start Y Position (mm)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The starting Y position of the laser cut.",
    ),
    "z_mm": _e(
        "Start Z Position (mm)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The starting Z position of the laser cut.",
    ),
    "t_deg": _e(
        "Start T Position (°)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The starting T position of the laser cut.",
    ),
    "r_deg": _e(
        "Start R Position (°)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The starting R position of the laser cut.",
    ),
}
_stage_lookup = {
    "rotation_side": _e(
        "Rotation Side",
        rotation_sides[-1],
        ctk.MenuButton,
        {"options": rotation_sides, "dtype": str},
        "Whether the sample pretilt is in the laser position or the FIB position.",
    ),
    "initial_position": deepcopy(_initial_pos_lookup),
}
_common_lookup = {
    "step_name": "",
    "step_number": _e(
        "Step Number",
        "",
        ctk.Entry,
        {"state": "disabled", "dtype": int},
        "The number of the step in the sequence of steps.",
    ),
    "step_type": _e(
        "Step Type", "", ctk.Entry, {"state": "disabled"}, "The step type."
    ),
    "frequency": _e(
        "Frequency",
        1,
        ctk.Entry,
        {"dtype": int},
        "The frequency that this step is activated (i.e. 1 means every slice, 2 means every other slice, etc.).",
    ),
    "stage": _stage_lookup,
}
_auto_cb_lookup = {
    "left": _e(
        "Left Fraction",
        "",
        ctk.Entry,
        {"dtype": float},
        "Fractional position (of the entire image) for the left edge of the reduced area for auto contrast and brightness adjustment. Empty/None/null for all fractions turns off ACB.",
    ),
    "width": _e(
        "Width Fraction",
        "",
        ctk.Entry,
        {"dtype": float},
        "The fractional width (of the entire image) to use for auto contrast and brightness. Empty/None for all fractions turns off ACB.",
    ),
    "top": _e(
        "Top Fraction",
        "",
        ctk.Entry,
        {"dtype": float},
        "Fractional position (of the entire image) for the top edge of the reduced area for auto contrast and brightness adjustment. Empty/None for all fractions turns off ACB.",
    ),
    "height": _e(
        "Height Fraction",
        "",
        ctk.Entry,
        {"dtype": float},
        "The fractional height (of the entire image) to use for auto contrast and brightness. Empty/None for all fractions turns off ACB.",
    ),
}
_beam_lookup = {
    "type": _e(
        "Beam Type",
        beam_types[-1],
        ctk.MenuButton,
        {"options": beam_types, "dtype": str},
        "The type of beam used to acquire the image.",
    ),
    "voltage_kv": _e(
        "Beam Voltage (kV)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The voltage of the beam in keV.",
    ),
    "voltage_tol_kv": _e(
        "Beam Voltage Tolerance (kV)",
        0.1,
        ctk.Entry,
        {"dtype": float},
        "The tolerance of the beam voltage in kV.",
    ),
    "current_na": _e(
        "Beam Current (nA)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The current of the beam in nA.",
    ),
    "current_tol_na": _e(
        "Beam Current Tolerance (nA)",
        0.5,
        ctk.Entry,
        {"dtype": float},
        "The tolerance of the beam current in nA.",
    ),
    "hfw_mm": _e(
        "Horizontal Field Width (mm)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The horizontal field width of the image in mm.",
    ),
    "working_dist_mm": _e(
        "Working Distance (mm)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The working distance of the image in mm.",
    ),
    "dynamic_focus": _e(
        "Use Dynamic Focus",
        "False",
        ctk.Checkbutton,
        {"offvalue": "False", "onvalue": "True", "bd": 0, "dtype": bool},
        "Whether to use dynamic focusing.",
    ),
    "tilt_correction": _e(
        "Use Tilt Correction",
        "False",
        ctk.Checkbutton,
        {"offvalue": "False", "onvalue": "True", "bd": 0, "dtype": bool},
        "Whether to use tilt correction.",
    ),
}
_deprecated_items_lookup = {
    "sectioning_direction": _e(
        "Sectioning Direction",
        "+",
        ctk.MenuButton,
        {"options": ["+", "-"], "dtype": str},
        "The direction that the laser will cut along the sectioning axis. Can be + or -.",
    ),
    "auto_cb": _e(
        "Auto Contrast/Brightness",
        "True",
        ctk.Checkbutton,
        {"offvalue": "False", "onvalue": "True", "bd": 0},
        "Whether to automatically adjust the contrast and brightness of the image.",
    ),
    "auto_focus": _e(
        "Auto Focus",
        "True",
        ctk.Checkbutton,
        {"offvalue": "False", "onvalue": "True", "bd": 0},
        "Whether to automatically focus the image. Overrides the provided working distance.",
    ),
    "auto_focus_hfw_mm": _e(
        "Auto Focus HFW (mm)",
        0.01,
        ctk.Entry,
        {"dtype": float},
        "The horizontal field width to use for auto focusing.",
    ),
}

# Create the rest of the LUTs
### Laser step ###
# Pulse
_laser_pulse_lookup = {
    "wavelength_nm": _e(
        "Wavelength (nm)",
        wavelengths[-1],
        ctk.MenuButton,
        {"options": wavelengths, "dtype": int},
        "The wavelength of the laser, cannot be switched yet.",
    ),
    "divider": _e(
        "Pulse divider",
        "",
        ctk.Entry,
        {"dtype": int},
        "Determines the repetition rate of the laser. 1 is 100kHz, 2 is 50kHz, etc.",
    ),
    "energy_uj": _e(
        "Energy (uJ)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The energy of the laser pulse in microjoules.",
    ),
    "polarization": _e(
        "Polarization",
        polarizations[0],
        ctk.MenuButton,
        {"options": polarizations, "dtype": str},
        "The polarization of the laser.",
    ),
}
# Pattern
_laser_pattern_box_lookup = {
    "passes": _e(
        "Passes",
        "",
        ctk.Entry,
        {"dtype": int},
        "The number of passes the laser will make.",
    ),
    "size_x_um": _e(
        "Size X (um)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The size of the box in the X direction in micrometers.",
    ),
    "size_y_um": _e(
        "Size Y (um)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The size of the box in the Y direction in micrometers.",
    ),
    "pitch_x_um": _e(
        "Pitch X (um)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The pitch of the box in the X direction in micrometers.",
    ),
    "pitch_y_um": _e(
        "Pitch Y (um)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The pitch of the box in the Y direction in micrometers.",
    ),
    "scan_type": _e(
        "Scan Type",
        laser_scan_types_box[-1],
        ctk.MenuButton,
        {"options": laser_scan_types_box},
        "The type of scan to perform.",
    ),
    "coordinate_ref": _e(
        "Coordinate Reference",
        coordinate_refs[-1],
        ctk.MenuButton,
        {"options": coordinate_refs},
        "The reference coordinate for the scan.",
    ),
}
_laser_pattern_line_lookup = {
    "passes": _e(
        "Passes",
        "",
        ctk.Entry,
        {"dtype": int},
        "The number of passes the laser will make.",
    ),
    "size_um": _e(
        "Size (um)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The size of the line in micrometers.",
    ),
    "pitch_um": _e(
        "Pitch (um)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The pitch of the line in micrometers.",
    ),
    "scan_type": _e(
        "Scan Type",
        laser_scan_types_line[-1],
        ctk.MenuButton,
        {"options": laser_scan_types_line},
        "The type of scan to perform.",
    ),
}
_laser_pattern_lookup = {
    "type": {
        "box": deepcopy(_laser_pattern_box_lookup),
        "line": deepcopy(_laser_pattern_line_lookup),
    },
    "rotation_deg": _e(
        "Scan Rotation (deg)",
        0.0,
        ctk.Entry,
        {"dtype": float},
        "The rotation of the scan in degrees.",
    ),
    "mode": _e(
        "Mode",
        laser_pattern_modes[-1],
        ctk.MenuButton,
        {"options": laser_pattern_modes, "dtype": str},
        "The mode of the laser.",
    ),
    "pulses_per_pixel": _e(
        "Pulses Per Pixel",
        1,
        ctk.Entry,
        {"dtype": int},
        "The number of pulses per pixel (only matters for fine).",
    ),
    "pixel_dwell_ms": _e(
        "Pixel Dwell Time (ms)",
        1,
        ctk.Entry,
        {"dtype": float},
        "The dwell time of the laser in milliseconds (only matters for coarse).",
    ),
}
# beam_shift_um
_beam_shift_lookup = {
    "x_um": _e(
        "Beam Shift X (um)",
        0.0,
        ctk.Entry,
        {"dtype": float},
        "The beam shift in the X direction in micrometers. Is applied on top of the hardware shift.",
    ),
    "y_um": _e(
        "Beam Shift Y (um)",
        0.0,
        ctk.Entry,
        {"dtype": float},
        "The beam shift in the Y direction in micrometers. Is applied on top of the hardware shift.",
    ),
}
laser_lookup = {
    "step_general": deepcopy(_common_lookup),
    "pulse": deepcopy(_laser_pulse_lookup),
    "objective_position_mm": _e(
        "Objective Position (mm)",
        0.0,
        ctk.Entry,
        {"dtype": float},
        "The position of the objective lens in millimeters.",
    ),
    "beam_shift": deepcopy(_beam_shift_lookup),
    "pattern": deepcopy(_laser_pattern_lookup),
}
laser_lookup["step_general"]["step_name"] = _e(
    "Step Name", "laser", ctk.Entry, {}, "The name of the step."
)

### Image, EDS, EBSD steps ###
# Detector
_image_detector_lookup = {
    "type": _e(
        "Detector Type",
        detector_types[-1],
        ctk.MenuButton,
        {"options": detector_types, "dtype": str},
        "The type of detector used to acquire the image.",
    ),
    "mode": _e(
        "Detector Mode",
        detector_modes[-1],
        ctk.MenuButton,
        {"options": detector_modes, "dtype": str},
        "The mode of the detector used to acquire the image.",
    ),
    "brightness": _e(
        "Brightness Fraction",
        "",
        ctk.Entry,
        {"dtype": float},
        "(If auto contrast/brightness is False) The fractional brightness value to use.",
    ),
    "contrast": _e(
        "Contrast Fraction",
        "",
        ctk.Entry,
        {"dtype": float},
        "(If auto contrast/brightness is False) The fractional contrast value to use.",
    ),
    "auto_cb": deepcopy(_auto_cb_lookup),
}
# Scan
_image_scan_lookup = {
    "rotation_deg": _e(
        "Scan Rotation (deg)",
        0.0,
        ctk.Entry,
        {"dtype": float},
        "The rotation of the scan in degrees.",
    ),
    "dwell_time_us": _e(
        "Dwell Time (us)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The dwell time of the image in microseconds.",
    ),
    "resolution": _e(
        "Resolution",
        resolutions[-1],
        ctk.EntryMenuButton,
        {"options": resolutions, "dtype": str},
        "The resolution of the image. Can be a present or a custom resolution (must be a rectangle of 3:2 aspect ratio).",
    ),
}
# Image
image_lookup = {
    "step_general": deepcopy(_common_lookup),
    "beam": deepcopy(_beam_lookup),
    "detector": deepcopy(_image_detector_lookup),
    "scan": deepcopy(_image_scan_lookup),
    "bit_depth": _e(
        "Bit Depth",
        bit_depths[0],
        ctk.MenuButton,
        {"options": bit_depths, "dtype": int},
        "The bit depth of the image.",
    ),
}
image_lookup["step_general"]["step_name"] = _e(
    "Step Name", "image", ctk.Entry, {}, "The name of the step."
)
# EDS
eds_lookup = {
    "step_general": deepcopy(_common_lookup),
    "beam": deepcopy(_beam_lookup),
    "detector": deepcopy(_image_detector_lookup),
    "scan": deepcopy(_image_scan_lookup),
    "bit_depth": _e(
        "Bit Depth", 8, ctk.Entry, {"dtype": int}, "The bit depth of the image."
    ),
}
eds_lookup["beam"]["type"] = _e(
    "Beam Type",
    beam_types[0],
    ctk.MenuButton,
    {"state": "disabled", "options": beam_types, "dtype": str},
    "The type of beam used to acquire the image.",
)
eds_lookup["step_general"]["step_name"] = _e(
    "Step Name", "eds", ctk.Entry, {}, "The name of the step."
)
# EBSD
ebsd_lookup = {
    "step_general": deepcopy(_common_lookup),
    "concurrent_EDS": _e(
        "Concurrent EDS",
        "True",
        ctk.Checkbutton,
        {"offvalue": "False", "onvalue": "True", "bd": 0, "dtype": bool},
        "Whether to acquire EDS data concurrently with the EBSD data.",
    ),
    "beam": deepcopy(_beam_lookup),
    "detector": deepcopy(_image_detector_lookup),
    "scan": deepcopy(_image_scan_lookup),
    "bit_depth": _e(
        "Bit Depth", 8, ctk.Entry, {"dtype": int}, "The bit depth of the image."
    ),
}
ebsd_lookup["beam"]["type"] = _e(
    "Beam Type",
    beam_types[0],
    ctk.MenuButton,
    {"state": "disabled", "options": beam_types, "dtype": str},
    "The type of beam used to acquire the image.",
)
ebsd_lookup["step_general"]["step_name"] = _e(
    "Step Name", "ebsd", ctk.Entry, {}, "The name of the step."
)

### PFIB step ###
_center_lookup = {
    "x_um": _e(
        "Center X (um)",
        0.0,
        ctk.Entry,
        {"dtype": float},
        "The X coordinate of the center of the milling pattern.",
    ),
    "y_um": _e(
        "Center Y (um)",
        0.0,
        ctk.Entry,
        {"dtype": float},
        "The Y coordinate of the center of the milling pattern.",
    ),
}
_fib_pattern_options_lookup = {
    "center": deepcopy(_center_lookup),
    "width_um": _e(
        "Width (um)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The width of the rectangle in micrometers. Patterning options should only be provided for one pattern type (all other should be empty/None/null).",
    ),
    "height_um": _e(
        "Height (um)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The height of the rectangle in micrometers. Patterning options should only be provided for one pattern type (all other should be empty/None/null).",
    ),
    "depth_um": _e(
        "Depth (um)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The depth of the rectangle in micrometers. Patterning options should only be provided for one pattern type (all other should be empty/None/null).",
    ),
    "scan_direction": _e(
        "Scan Direction",
        fib_scan_dirs[-1],
        ctk.MenuButton,
        {"options": fib_scan_dirs, "dtype": str},
        "The direction of the scan. Patterning options should only be provided for one pattern type (all other should be empty/None/null).",
    ),
    "scan_type": _e(
        "Scan Type",
        fib_scan_types[-1],
        ctk.MenuButton,
        {"options": fib_scan_types, "dtype": str},
        "The type of scan to perform. Patterning options should only be provided for one pattern type (all other should be empty/None/null).",
    ),
}
_fib_selected_pattern_lookup = {
    "dwell_us": _e(
        "Mill Dwell Time (us)",
        "",
        ctk.Entry,
        {"dtype": float},
        "The dwell time of the mill in microseconds. Patterning options should only be provided for one pattern type (all other should be empty/None/null).",
    ),
    "repeats": _e(
        "Pattern Repeats",
        "",
        ctk.Entry,
        {"dtype": int},
        "The number of times to repeat the pattern. Patterning options should only be provided for one pattern type (all other should be empty/None/null).",
    ),
    "recipe_file": _e(
        "Image Processing Recipe",
        "",
        ctk.PathEntry,
        {"directory": False, "defaultextension": ".py"},
        "The recipe to use for image processing. Must be a python (.py) file.",
    ),
    "mask_file": _e(
        "Mask File",
        "",
        ctk.PathEntry,
        {"directory": False, "defaultextension": ".tif"},
        "During this step, the mask file to use for milling will be saved (and overwritten) in this location. Should be a tiff (.tif) file. All masks will be saved automatically during the experiment.",
    ),
}
_fib_pattern_type_lookup = {
    "rectangle": deepcopy(_fib_pattern_options_lookup),
    "regular_cross_section": deepcopy(_fib_pattern_options_lookup),
    "cleaning_cross_section": deepcopy(_fib_pattern_options_lookup),
    "selected_area": deepcopy(_fib_selected_pattern_lookup),
}
_fib_pattern_lookup = {
    "application_file": _e(
        "Mill Pattern Preset",
        fib_applications[-1],
        ctk.MenuButton,
        {"options": fib_applications, "dtype": str},
        "The preset to use for milling.",
    ),
    "type": deepcopy(_fib_pattern_type_lookup),
}
_fib_mill_lookup = {
    "beam": deepcopy(_beam_lookup),
    "pattern": deepcopy(_fib_pattern_lookup),
}
fib_lookup = {
    "step_general": deepcopy(_common_lookup),
    "image": deepcopy(image_lookup),
    "mill": deepcopy(_fib_mill_lookup),
}
fib_lookup["image"].pop("step_general")
fib_lookup["mill"]["beam"]["type"] = _e(
    "Beam Type",
    beam_types[1],
    ctk.MenuButton,
    {"state": "disabled", "options": beam_types, "dtype": str},
    "The type of beam used to acquire the image.",
)
fib_lookup["image"]["beam"]["type"] = _e(
    "Beam Type",
    beam_types[1],
    ctk.MenuButton,
    {"state": "disabled", "options": beam_types, "dtype": str},
    "The type of beam used to acquire the image.",
)
fib_lookup["mill"]["beam"]["dynamic_focus"] = _e(
    "Use Dynamic Focus",
    "False",
    ctk.Checkbutton,
    {"state": "disabled", "offvalue": "False", "onvalue": "True", "bd": 0, "dtype": bool},
    "Whether to use dynamic focusing.",
)
fib_lookup["mill"]["beam"]["tilt_correction"] = _e(
    "Use Tilt Correction",
    "False",
    ctk.Checkbutton,
    {"state": "disabled", "offvalue": "False", "onvalue": "True", "bd": 0, "dtype": bool},
    "Whether to use tilt correction.",
)
fib_lookup["step_general"]["step_name"] = _e(
    "Step Name", "fib", ctk.Entry, {}, "The name of the step."
)

### Custom step ###
custom_lookup = {
    "step_general": deepcopy(_common_lookup),
    "executable_path": _e(
        "Executable Path",
        "",
        ctk.PathEntry,
        {"directory": False, "operation": "open"},
        "The path to the executable to run. For python, this would be the location of the python executable.",
    ),
    "script_path": _e(
        "Custom Script Path",
        "",
        ctk.PathEntry,
        {"directory": False, "operation": "open"},
        "The path to the custom script to run.",
    ),
}
custom_lookup["step_general"]["step_name"] = _e(
    "Step Name", "custom", ctk.Entry, {}, "The name of the step."
)

# Package everything
LUT = {
    "general": general_lookup,
    "laser": laser_lookup,
    "image": image_lookup,
    "fib": fib_lookup,
    "eds": eds_lookup,
    "ebsd": ebsd_lookup,
    "custom": custom_lookup,
}
