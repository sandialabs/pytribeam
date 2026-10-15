import ctypes
from pathlib import Path
from copy import deepcopy
import tkinter as tk
from tkinter import messagebox
import yaml

import pytribeam.utilities as ut
import pytribeam.types as tbt
import pytribeam.factory as factory
import pytribeam.laser as laser
import pytribeam.GUI.CustomTkinterWidgets as ctk
import pytribeam.GUI.config_ui.lookup as lut


class Configurator:
    def __init__(self, master, theme, yml_path=None, *args, **kwargs):
        self.master = master
        self.theme = theme
        self.toplevel = tk.Toplevel(
            self.master, background=self.theme.bg, *args, **kwargs
        )

        # Set app title, icon, size and grid structure
        self.YAML_PATH = yml_path
        self.update_title()
        ico_path = Path(__file__).parent.parent.parent.parent.parent.joinpath(
            "docs", "userguide", "src", "logos", "logo_color_alt.ico"
        )
        self.toplevel.iconbitmap(ico_path)
        self.toplevel.geometry("1000x700")
        self.toplevel.update_idletasks()
        self.toplevel.rowconfigure(0, weight=1)
        self.toplevel.columnconfigure(0, weight=1)

        # Set version and put a trace on it
        self.yml_version = tk.StringVar()
        self.yml_version.set(lut.VERSIONS[-1])
        self.yml_version.trace_id = self.yml_version.trace_add(
            "write", self._yaml_version_updated
        )

        # Fill the toplevel with the editor window
        self._fill_toplevel(redraw=False)

        # Initialize class variables
        self.STEP_INDEX = -1
        self.STEP = ""
        self.CONFIG = {}
        self.PYVARS = {}
        self.clean_exit = False
        self.frames_dict = {}
        self.pipeline_buttons = {}

        # Start the app
        if self.YAML_PATH is not None:
            self.load_config(self.YAML_PATH)
        else:
            self.new_config(ask_save=False)
            # self.create_pipeline_step("general")

        self.toplevel.protocol("WM_DELETE_WINDOW", self.quit)

        # Bind Ctrl+S to save the config
        self.toplevel.bind("<Control-s>", lambda e: self.save_config())

    def _fill_toplevel(self, redraw=True):
        """Create the editor window for the pipeline steps."""
        # First we clear everything in the toplevel (the menubar and the frames)
        for widget in self.toplevel.winfo_children():
            widget.destroy()
        self.toplevel.config(menu="")

        # Create menubar
        self.menu = tk.Menu(self.toplevel)
        # Create file menu
        file_menu = tk.Menu(
            self.menu,
            tearoff=False,
            font=ctk.MENU_FONT,
            # bg=self.theme.bg,
            activebackground=self.theme.accent1,
        )
        file_menu.add_command(label="New", command=self.new_config, font=ctk.MENU_FONT)
        file_menu.add_command(
            label="Load", command=self.load_config, font=ctk.MENU_FONT
        )
        file_menu.add_command(
            label="Save", command=self.save_config, font=ctk.MENU_FONT
        )
        file_menu.add_command(
            label="Save as",
            command=lambda: self.save_config(save_as=True),
            font=ctk.MENU_FONT,
        )
        file_menu.add_command(
            label="Save & Exit", command=self.save_exit, font=ctk.MENU_FONT
        )
        self.menu.add_cascade(label="Menu", menu=file_menu, font=ctk.MENU_FONT)
        # Create validation menu
        validate_menu = tk.Menu(
            self.menu,
            tearoff=False,
            font=ctk.MENU_FONT,
            # bg=self.theme.bg,
            activebackground=self.theme.accent1,
        )
        validate_menu.add_command(
            label="Full", command=self.validate_full, font=ctk.MENU_FONT
        )
        validate_menu.add_command(
            label="Step", command=self.validate_step, font=ctk.MENU_FONT
        )
        validate_menu.add_command(
            label="General", command=self.validate_general, font=ctk.MENU_FONT
        )
        self.menu.add_cascade(label="Validate", menu=validate_menu, font=ctk.MENU_FONT)
        # Create Microscope interaction menu
        microscope_menu = tk.Menu(
            self.menu,
            tearoff=False,
            font=ctk.MENU_FONT,
            # bg=self.theme.bg,
            activebackground=self.theme.accent1,
        )
        microscope_menu.add_command(
            label="Import stage position...",
            command=self.update_step_position_from_scope,
            font=ctk.MENU_FONT,
        )
        microscope_menu.add_command(
            label="Import imaging conditions...",
            command=self.update_step_imaging_from_scope,
            font=ctk.MENU_FONT,
        )
        microscope_menu.add_command(
            label="Import laser settings...",
            command=self.update_laser_from_scope,
            font=ctk.MENU_FONT,
        )
        self.menu.add_cascade(
            label="Microscope", menu=microscope_menu, font=ctk.MENU_FONT
        )
        # Create a version menu of checkbuttons, only one of which can be selected at a time, to choose the version of the config file
        version_menu = tk.Menu(
            self.menu,
            tearoff=False,
            font=ctk.MENU_FONT,
            # bg=self.theme.bg,
            activebackground=self.theme.accent1,
        )
        for version in lut.VERSIONS:
            version_menu.add_radiobutton(
                label=version,
                variable=self.yml_version,
                value=version,
                font=ctk.MENU_FONT,
            )
        self.menu.add_cascade(label="Version", menu=version_menu, font=ctk.MENU_FONT)

        # Put the menu on the app
        self.toplevel.config(menu=self.menu, bg=self.theme.bg)

        # Create and format workspace window, this contains the pipeline window and the step editor window
        self.frame = tk.Frame(self.toplevel, background=self.theme.bg)
        self.frame.grid(row=0, column=0, sticky="nsew", pady=0, padx=0)
        self.frame.columnconfigure(0, weight=1)
        self.frame.columnconfigure(1, weight=15)
        self.frame.columnconfigure(2, weight=15)
        self.frame.rowconfigure(0, weight=1)

        # Create pipeline window
        self.pipeline = ctk.ScrollableFrame(
            self.frame,
            vscroll=True,
            hscroll=False,
            bg=self.theme.bg,
            sbar_bg=self.theme.bg,
            sbar_fg=self.theme.bg,
        )
        self.pipeline.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.pipeline.columnconfigure(0, weight=1)
        self.pipeline.columnconfigure(1, weight=1)
        top_label = ctk.AutofitLabel(
            self.pipeline,
            text="Pipeline Editor",
            bg=self.theme.bg,
            fg=self.theme.fg,
            font=ctk.HEADER_FONT,
        )
        top_label.grid(row=0, column=0, sticky="nsew")
        self.status_label = ctk.AutofitLabel(
            self.pipeline,
            text="INVALID",
            bg=self.theme.red,
            fg=self.theme.red_fg,
            font=ctk.MENU_FONT,
            anchor="center",
            relief="raised",
            width=12,
        )
        self.status_label.grid(row=0, column=1, sticky="nse", padx=20, pady=5)
        step_types = [
            l.lower() for l in list(lut.LUTs.keys()) if l.lower() != "general"
        ]

        self.pick_step_b = ctk.MenuButton(
            self.pipeline,
            step_types,
            font=ctk.MENU_FONT,
            bg=self.theme.bg,
            fg=self.theme.fg,
            command=self.create_pipeline_step,
            relief="raised",
            padx=5,
            bd=3,
        )
        self.pick_step_b.grid(row=1, column=0, sticky="nsew", pady=1, padx=1)
        self.pick_step_b.var.set("Add Step")
        note_label = ctk.AutofitLabel(
            self.pipeline,
            text="Right click on a step to delete or rearrange",
            bg=self.theme.bg,
            fg=self.theme.fg,
            font=ctk.MENU_FONT,
            padx=5,
        )
        note_label.grid(row=1, column=1, sticky="nsew")

        self.editor = ctk.ScrollableFrame(
            self.frame,
            vscroll=True,
            hscroll=False,
            bg=self.theme.bg,
            sbar_bg=self.theme.bg,
            sbar_fg=self.theme.bg,
        )
        self.editor.grid(row=0, column=1, columnspan=2, sticky="nsew", padx=1, pady=0)
        self.editor.columnconfigure(0, weight=1)
        self.editor.columnconfigure(1, weight=1)
        self.editor.columnconfigure(2, weight=1)
        top_label = ctk.AutofitLabel(
            self.editor,
            text="Step Editor",
            bg=self.theme.bg,
            fg=self.theme.fg,
            font=ctk.HEADER_FONT,
        )
        top_label.grid(row=0, column=0, sticky="nsew")

        if redraw:
            self._update_pipeline()
            self._update_editor()

    def _yaml_version_updated(self, *args):
        """Function called when the yaml version is updated."""
        self._update_editor()

    def update_title(self):
        """Update the title of the app window based on the current yaml file."""
        if self.YAML_PATH is None:
            self.toplevel.title("TriBeam Configurator - Untitled")
        else:
            self.toplevel.title(f"TriBeam Configurator - {self.YAML_PATH}")

    def update_step_imaging_from_scope(self):
        """Update the imaging settings of the current step based on the current microscope settings."""
        if self.STEP not in ["image", "fib", "ebsd", "eds"]:
            messagebox.showinfo(
                parent=self.toplevel,
                title="Error",
                message=f"{self.STEP} step does not have imaging settings.",
            )
            return
        status, general_set = self.validate_general(return_config=True, suppress=True)
        if not status:
            return
        general_set = general_set["general"]
        Microscope = tbt.Microscope()
        ut.connect_microscope(
            Microscope,
            quiet_output=True,
            connection_host=general_set["connection_host"],
            connection_port=general_set["connection_port"],
        )
        # Get the settings
        imaging_settings = factory.active_image_settings(Microscope)
        # Disconnect the microscope
        ut.disconnect_microscope(Microscope)
        # First set the beam type (special case)
        # key = get_key(["beam", "type"], self.CONFIG[self.STEP_INDEX])
        value = imaging_settings.beam.__getattribute__("type").value
        # If this is a fib step, we check if the beam is ion, if not, we raise a warning and abort
        if self.STEP == "fib" and value != "ion":
            messagebox.showerror(
                parent=self.toplevel,
                title="Error",
                message="Importing imaging conditions for a FIB step requires the active beam to be an ion beam.",
            )
            return
        # If it is a fib step, copy imaging conditions to the mill setting
        if self.STEP == "fib":
            self.CONFIG[self.STEP_INDEX]["mill/beam/type"] = _check_value_type(
                value, str
            )
            self.CONFIG[self.STEP_INDEX]["mill/beam/voltage_kv"] = _check_value_type(
                imaging_settings.beam.settings.voltage_kv, float
            )
            self.CONFIG[self.STEP_INDEX]["mill/beam/current_na"] = _check_value_type(
                imaging_settings.beam.settings.current_na, float
            )
            self.CONFIG[self.STEP_INDEX]["mill/beam/voltage_tol_kv"] = (
                _check_value_type(imaging_settings.beam.settings.voltage_tol_kv, float)
            )
            self.CONFIG[self.STEP_INDEX]["mill/beam/current_tol_na"] = (
                _check_value_type(imaging_settings.beam.settings.current_tol_na, float)
            )
            self.CONFIG[self.STEP_INDEX]["mill/beam/hfw_mm"] = _check_value_type(
                imaging_settings.beam.settings.hfw_mm, float
            )
            self.CONFIG[self.STEP_INDEX]["mill/beam/working_dist_mm"] = (
                _check_value_type(imaging_settings.beam.settings.working_dist_mm, float)
            )
        # Do beam stuff
        self.CONFIG[self.STEP_INDEX]["beam/type"] = _check_value_type(value, str)
        self.CONFIG[self.STEP_INDEX]["beam/voltage_kv"] = _check_value_type(
            imaging_settings.beam.settings.voltage_kv, float
        )
        self.CONFIG[self.STEP_INDEX]["beam/current_na"] = _check_value_type(
            imaging_settings.beam.settings.current_na, float
        )
        self.CONFIG[self.STEP_INDEX]["beam/voltage_tol_kv"] = _check_value_type(
            imaging_settings.beam.settings.voltage_tol_kv, float
        )
        self.CONFIG[self.STEP_INDEX]["beam/current_tol_na"] = _check_value_type(
            imaging_settings.beam.settings.current_tol_na, float
        )
        self.CONFIG[self.STEP_INDEX]["beam/hfw_mm"] = _check_value_type(
            imaging_settings.beam.settings.hfw_mm, float
        )
        self.CONFIG[self.STEP_INDEX]["beam/working_dist_mm"] = _check_value_type(
            imaging_settings.beam.settings.working_dist_mm, float
        )
        # Now set the detector settings
        self.CONFIG[self.STEP_INDEX]["detector/type"] = _check_value_type(
            imaging_settings.detector.type, str
        )
        self.CONFIG[self.STEP_INDEX]["detector/mode"] = _check_value_type(
            imaging_settings.detector.mode, str
        )
        self.CONFIG[self.STEP_INDEX]["detector/brightness"] = _check_value_type(
            imaging_settings.detector.brightness, float
        )
        self.CONFIG[self.STEP_INDEX]["detector/contrast"] = _check_value_type(
            imaging_settings.detector.contrast, float
        )
        # Now the scan settings
        self.CONFIG[self.STEP_INDEX]["scan/rotation_deg"] = _check_value_type(
            imaging_settings.scan.rotation_deg, float
        )
        self.CONFIG[self.STEP_INDEX]["scan/dwell_time_us"] = _check_value_type(
            imaging_settings.scan.dwell_time_us, float
        )
        value = imaging_settings.scan.__getattribute__("resolution")
        value = _check_value_type(f"{value.width}x{value.height}", str)
        self.CONFIG[self.STEP_INDEX]["scan/resolution"] = value
        # Last is the bit depth
        self.CONFIG[self.STEP_INDEX]["bit_depth"] = _check_value_type(
            imaging_settings.bit_depth, int
        )
        # Update the editor
        self._update_editor()

    def update_step_position_from_scope(self):
        """Update the stage position of the current step based on the current microscope settings."""
        if self.STEP_INDEX == 0:
            messagebox.showinfo(
                parent=self.toplevel,
                title="Error",
                message="General step does not have a stage position.",
            )
            return
        status, general_set = self.validate_general(return_config=True, suppress=True)
        if not status:
            return
        general_set = general_set["general"]
        Microscope = tbt.Microscope()
        ut.connect_microscope(
            Microscope,
            quiet_output=True,
            connection_host=general_set["connection_host"],
            connection_port=general_set["connection_port"],
        )
        current_position = factory.active_stage_position_settings(Microscope)
        # Disconnect the microscope
        ut.disconnect_microscope(Microscope)
        # Put the current position in the step
        self.CONFIG[self.STEP_INDEX]["step_general/stage/initial_position/x_mm"] = (
            _check_value_type(current_position.x_mm, float)
        )
        self.CONFIG[self.STEP_INDEX]["step_general/stage/initial_position/y_mm"] = (
            _check_value_type(current_position.y_mm, float)
        )
        self.CONFIG[self.STEP_INDEX]["step_general/stage/initial_position/z_mm"] = (
            _check_value_type(current_position.z_mm, float)
        )
        self.CONFIG[self.STEP_INDEX]["step_general/stage/initial_position/t_deg"] = (
            _check_value_type(current_position.t_deg, float)
        )
        self.CONFIG[self.STEP_INDEX]["step_general/stage/initial_position/r_deg"] = (
            _check_value_type(current_position.r_deg, float)
        )
        # Update the editor
        self._update_editor()

    def update_laser_from_scope(self):
        """Update the laser settings of the current step based on the current microscope settings."""
        # Make sure the step is a laser step
        if self.STEP != "laser":
            messagebox.showinfo(
                parent=self.toplevel,
                title="Error",
                message="Active step does not have laser settings.",
            )
            return

        # Get the laser settings from the microscope, which first requires a microscope connection
        status, general_set = self.validate_general(return_config=True, suppress=True)
        if not status:
            return
        general_set = general_set["general"]
        Microscope = tbt.Microscope()
        ut.connect_microscope(
            Microscope,
            quiet_output=True,
            connection_host=general_set["connection_host"],
            connection_port=general_set["connection_port"],
        )
        try:
            laser_state = factory.active_laser_state()
        except Exception as e:
            messagebox.showerror(
                parent=self.toplevel,
                title="Error",
                message=f"Error getting laser state: {e}",
            )
            return
        ut.disconnect_microscope(Microscope)

        # Convert the laser state to a dictionary
        laser_state = laser.laser_state_to_db(laser_state)

        # Make any NoneType values into empty strings
        for key in laser_state.keys():
            if laser_state[key] is None:
                laser_state[key] = ""

        # Empty the current laser db
        for key in self.CONFIG[self.STEP_INDEX].keys():
            self.CONFIG[self.STEP_INDEX][key] = ""

        # Pass the laser state values to the config file
        self.CONFIG[self.STEP_INDEX]["pulse/wavelength_nm"] = laser_state[
            "wavelength_nm"
        ]
        self.CONFIG[self.STEP_INDEX]["pulse/divider"] = laser_state["pulse_divider"]
        self.CONFIG[self.STEP_INDEX]["pulse/energy_uj"] = laser_state["pulse_energy_uj"]
        self.CONFIG[self.STEP_INDEX]["objective_position_mm"] = laser_state[
            "objective_position_mm"
        ]
        self.CONFIG[self.STEP_INDEX]["beam_shift/x_um"] = laser_state["beam_shift_um_x"]
        self.CONFIG[self.STEP_INDEX]["beam_shift/y_um"] = laser_state["beam_shift_um_y"]
        self.CONFIG[self.STEP_INDEX]["pattern/mode"] = laser_state["laser_pattern_mode"]
        self.CONFIG[self.STEP_INDEX]["pattern/rotation_deg"] = laser_state[
            "laser_pattern_rotation_deg"
        ]
        self.CONFIG[self.STEP_INDEX]["pattern/pulses_per_pixel"] = laser_state[
            "laser_pattern_pulses_per_pixel"
        ]
        self.CONFIG[self.STEP_INDEX]["pattern/pixel_dwell_ms"] = laser_state[
            "laser_pattern_pixel_dwell_ms"
        ]
        if laser_state["geometry_type"] == "line":
            self.CONFIG[self.STEP_INDEX]["pattern/type/line/passes"] = laser_state[
                "passes"
            ]
            self.CONFIG[self.STEP_INDEX]["pattern/type/line/size_um"] = laser_state[
                "size_um"
            ]
            self.CONFIG[self.STEP_INDEX]["pattern/type/line/pitch_um"] = laser_state[
                "pitch_um"
            ]
            self.CONFIG[self.STEP_INDEX]["pattern/type/line/scan_type"] = laser_state[
                "laser_scan_type"
            ]
        elif laser_state["geometry_type"] == "box":
            self.CONFIG[self.STEP_INDEX]["pattern/type/box/passes"] = laser_state[
                "passes"
            ]
            self.CONFIG[self.STEP_INDEX]["pattern/type/box/size_x_um"] = laser_state[
                "size_x_um"
            ]
            self.CONFIG[self.STEP_INDEX]["pattern/type/box/size_y_um"] = laser_state[
                "size_y_um"
            ]
            self.CONFIG[self.STEP_INDEX]["pattern/type/box/pitch_x_um"] = laser_state[
                "pitch_x_um"
            ]
            self.CONFIG[self.STEP_INDEX]["pattern/type/box/pitch_y_um"] = laser_state[
                "pitch_y_um"
            ]
            self.CONFIG[self.STEP_INDEX]["pattern/type/box/scan_type"] = laser_state[
                "laser_scan_type"
            ]
            self.CONFIG[self.STEP_INDEX]["pattern/type/box/coordinate_ref"] = (
                laser_state["coordinate_ref"].value
            )

        # Update the editor
        self._update_editor()

    def new_config(self, ask_save=True):
        """Create a new configuration file by resetting the pipeline and editor.
        Prompts the user to save the current configuration."""
        if ask_save:
            save = messagebox.askyesno(
                parent=self.toplevel,
                title="Save current",
                message="Do you want to save the current configuration?",
            )
            if save:
                self.save_config()
        for key in self.PYVARS.keys():
            self.PYVARS[key].trace_vdelete("w", self.PYVARS[key].trace_id)
        self.STEP_INDEX = -1
        self.STEP = ""
        self.CONFIG = {}
        self.PYVARS = {}
        self.YAML_PATH = None
        self.create_pipeline_step("general")
        self.update_title()

    def load_config(self, path=None):
        """Load a configuration file by reading a yaml file and updating the pipeline and editor."""
        # If we have a path, then we are being transfered from the main GUI and therefore would not want to save the current config or open a file dialog
        if path is None:
            # Save the current config and reset the pipeline
            save = messagebox.askyesno(
                parent=self.toplevel,
                title="Save current",
                message="Do you want to save the current configuration?",
            )
            if save:
                self.save_config()
            # Get the path to the yaml file
            path = tk.filedialog.askopenfilename(
                parent=self.toplevel,
                filetypes=[
                    ("YAML files", "*.yml"),
                    ("YAML files", "*.yaml"),
                    ("All files", "*.*"),
                ],
            )
            if path == "" or path is None:
                return
        path = Path(path)
        # Clear the current configuration
        self.STEP_INDEX = -1
        self.STEP = ""
        self.CONFIG = {}
        # Remove all traces from the variables
        for key in self.PYVARS.keys():
            self.PYVARS[key].trace_vdelete("w", self.PYVARS[key].trace_id)
        self.PYVARS = {}
        # Read the yaml file
        try:
            yml_version = ut.yml_version(path)
            db = ut.yml_to_dict(
                yml_path_file=path,
                version=yml_version,
                required_keys=(
                    "general",
                    "config_file_version",
                ),
            )
        except Exception as e:
            messagebox.showerror(
                parent=self.toplevel, title="Error reading yaml file", message=f"{e}"
            )
            return
        # Extract relevant sections of the yaml file
        general = db["general"]
        steps = db["steps"]
        # Give general a stype type
        general["step_type"] = "general"
        general = flatten_dict(general, sep="/")
        # Flatten the nested dictionaries
        flat_steps = {}
        step_order = []
        for step_name in steps.keys():
            step = steps[step_name]
            step_type = step["step_general"]["step_type"]
            step_order.append(
                (step_name, step_type, step["step_general"]["step_number"])
            )
            flat_step = flatten_dict(step, sep="/")
            flat_step["step_general/step_name"] = step_name
            # flat_step["step_general"]["step_name"] = step_name
            flat_steps[step_name] = flat_step
        # Put the steps in the correct order
        step_order = sorted(step_order, key=lambda x: x[2])
        self.CONFIG = {0: general}
        for name, stype, number in step_order:
            self.CONFIG[number] = flat_steps[name]
        # Make all the values in the config file strings
        for step in self.CONFIG.keys():
            for key in self.CONFIG[step].keys():
                self.CONFIG[step][key] = str(self.CONFIG[step][key])
        # Set the step index to the general step and update the pipeline and editor windows
        self.STEP_INDEX = 0
        self.STEP = self.CONFIG[self.STEP_INDEX]["step_type"]
        self.yml_version.set(str(yml_version))
        self._update_pipeline()
        self._update_editor()
        self.YAML_PATH = str(path)
        self.update_title()

    def save_config(self, save_as=False):
        """Wrapper function to save the current configuration to a yaml file."""
        # Get the path to the pipeline yaml file
        if save_as or self.YAML_PATH is None:
            yml_path = tk.filedialog.asksaveasfilename(
                defaultextension=".yml",
                filetypes=[
                    ("YAML files", "*.yml"),
                    ("YAML files", "*.yaml"),
                    ("All files", "*.*"),
                ],
            )
            if yml_path == "" or yml_path is None:
                return
            self.YAML_PATH = yml_path
        config_db = self.format_config()
        ut.dict_to_yml(config_db, self.YAML_PATH)
        self.update_title()

    def save_exit(self):
        if self.YAML_PATH is None:
            yml_path = tk.filedialog.asksaveasfilename(
                parent=self.toplevel,
                defaultextension=".yml",
                filetypes=[
                    ("YAML files", "*.yml"),
                    ("YAML files", "*.yaml"),
                    ("All files", "*.*"),
                ],
            )
            if yml_path == "" or yml_path is None:
                return
        else:
            yml_path = self.YAML_PATH
        if self.export_pipeline(yml_path=yml_path):
            self.clean_exit = True
            self.YAML_PATH = yml_path
            self.toplevel.destroy()

    def quit(self):
        if self.clean_exit:
            self.toplevel.destroy()
        else:
            save = messagebox.askyesno(
                parent=self.toplevel,
                title="Save current",
                message="Do you want to save the current configuration?",
            )
            if save:
                self.save_exit()
            else:
                self.toplevel.destroy()

    def create_pipeline_step(self, step_type):
        """Function called when a new pipeline step is created.
        Will focus the new step in the editor and update the pipeline."""
        # print("Creating pipeline step...", step_type)
        self.STEP = step_type
        self.STEP_INDEX = len(self.CONFIG)
        # print("Step index:", self.STEP_INDEX)
        if self.STEP_INDEX == 0:
            self.CONFIG[self.STEP_INDEX] = {"step_type": self.STEP}
        else:
            self.CONFIG[self.STEP_INDEX] = {"step_general/step_type": self.STEP}
        # Update the step name to have the step type and the number of this type of step
        step_count = len(
            [
                v
                for v in list(self.CONFIG.values())[1:]
                if v["step_general/step_type"] == self.STEP
            ]
        )
        if self.STEP_INDEX != 0:
            self.CONFIG[self.STEP_INDEX][
                "step_general/step_name"
            ] = f"{self.STEP}_{step_count}"
        else:
            self._update_pipeline()
        self._update_editor()

        # Update the general to have an additional step
        self.CONFIG[0]["step_count"] = len(self.CONFIG) - 1

        # Set the pick step button back to "Add Step"
        self.pick_step_b.var.set("Add Step")

    def delete_pipeline_step(self, index):
        """Delete a pipeline step from the pipeline."""
        # print("Deleting pipeline step:", self.CONFIG[index])
        # Delete the config entry for the index to be deleted
        del self.CONFIG[index]
        # Update the step index if we deleted the active step
        if self.STEP_INDEX == index:
            self.STEP_INDEX = max(0, self.STEP_INDEX - 1)
        elif self.STEP_INDEX > index:
            self.STEP_INDEX -= 1
        # Re-key the config dictionary
        self.CONFIG = {i: v for i, v in enumerate(self.CONFIG.values())}
        if self.STEP_INDEX == 0:
            self.STEP = self.CONFIG[self.STEP_INDEX]["step_type"]
        else:
            self.STEP = self.CONFIG[self.STEP_INDEX]["step_general/step_type"]
        # Update the pipeline and editor
        self._update_pipeline()
        self._update_editor()
        # Update the general to have one less step
        self.CONFIG[0]["step_count"] = len(self.CONFIG) - 1

    def move_pipeline_step(self, index, direction):
        """Move a pipeline step up or down in the pipeline."""
        # print("Moving pipeline step...", self.CONFIG[index], direction)
        # Return if the first step is trying to be moved up or the last step down
        if index == 1 and direction == -1:
            return
        if index == len(self.CONFIG) - 1 and direction == 1:
            return
        # Edit the config directly
        self.CONFIG[index], self.CONFIG[index + direction] = (
            self.CONFIG[index + direction],
            self.CONFIG[index],
        )
        # If the moved steps don't touch the current step, just update the pipeline
        if abs(self.STEP_INDEX - index) > 1:
            pass
        # If we are moving a neighboring step, update the step index in the opposite direction
        elif index != self.STEP_INDEX:
            self.STEP_INDEX -= direction
        # If we are moving the current step, update the step index in the same direction
        else:
            self.STEP_INDEX += direction
        # Update the pipeline (editor doesnt change here)
        self._update_pipeline()
        self._update_editor()

    def duplicate_pipeline_step(self, index):
        """Duplicate a pipeline step."""
        # print("Duplicating pipeline step...", self.CONFIG[index])
        # Copy the step and add it to the end of the pipeline
        new_step = deepcopy(self.CONFIG[index])
        index = len(self.CONFIG)
        self.CONFIG[index] = new_step
        step_count = len(
            [
                v
                for v in list(self.CONFIG.values())[1:]
                if v["step_general/step_type"] == new_step["step_general/step_type"]
            ]
        )
        self.CONFIG[index]["step_general/step_name"] = f"{self.STEP}_{step_count}"
        # Update the pipeline and editor
        # self._update_pipeline()
        self._update_editor()
        # Update the general to have an additional step
        self.CONFIG[0]["step_count"] = len(self.CONFIG) - 1

    def select_pipeline_step(self, option):
        """Based on the selected step, update the editor with the new step."""
        # print("Selecting pipeline step...", option)
        index = int(option.split(".")[0])
        self.STEP_INDEX = index
        if index == 0:
            self.STEP = self.CONFIG[index]["step_type"]
        else:
            self.STEP = self.CONFIG[self.STEP_INDEX]["step_general/step_type"]
        self._update_pipeline()
        self._update_editor()

    def _update_pipeline(self):
        """Update the pipeline based on the current configuration.
        This does not remove the widgets, it just updates the text and command of the buttons.
        """
        #  Create all possible options for the pipeline based on the config file
        options = []
        for i, v in self.CONFIG.items():
            if i == 0:
                options.append(f"{i}. {v['step_type']}")
            else:
                options.append(
                    f"{i}. {v['step_general/step_name']} ({v['step_general/step_type']})"
                )
        # Get the maximum row of the current pipeline
        _, row = self.pipeline.grid_size()
        # Loop over the options and update the pipeline
        for i, option in enumerate(options):
            row_i = i + 2

            # Set the text to be displayed and the colors
            if i == self.STEP_INDEX:
                kw = {
                    "font": ctk.FONT,
                    "relief": "raised",
                    "bg": self.theme.accent1,
                    "fg": self.theme.accent1_fg,
                    # "h_bg": self.theme.accent1,
                    # "h_fg": self.theme.accent1_fg,
                    # "activebackground": self.theme.accent1,
                    # "activeforeground": self.theme.accent1_fg
                }
            else:
                kw = {
                    "font": ctk.FONT,
                    "relief": "groove",
                    "bg": self.theme.bg,
                    "fg": self.theme.fg,
                    # "highlightcolor": self.theme.accent1,
                    # "activebackground": self.theme.bg,
                    # "activeforeground": self.theme.fg,
                }

            # Create tooltip options and state
            right_click_map = {
                "Move up": lambda x=i: self.move_pipeline_step(x, -1),
                "Move down": lambda x=i: self.move_pipeline_step(x, 1),
                "Delete": lambda x=i: self.delete_pipeline_step(x),
                "Duplicate": lambda x=i: self.duplicate_pipeline_step(x),
            }
            right_click_states = ["normal", "normal", "normal", "normal"]
            if i == 1:
                right_click_states[0] = "disabled"
            if i == len(options) - 1:
                right_click_states[1] = "disabled"

            # If the row is the end of the pipeline, create a new button
            if row_i >= row or i == self.STEP_INDEX:
                button = ctk.Button(
                    self.pipeline,
                    text=option,
                    padx=5,
                    bd=3,
                    command=lambda a=option: self.select_pipeline_step(a),
                    **kw,
                )
                button.grid(
                    row=row_i, column=0, columnspan=2, sticky="nsew", pady=1, padx=1
                )
                # Add the right click menu to the button
                if i != 0:
                    button.right_click_menu = ctk.RightClickMenu(
                        button,
                        right_click_map.keys(),
                        bg=self.theme.bg,
                        fg=self.theme.fg,
                        abg=self.theme.accent1,
                        afg=self.theme.fg,
                    )

            # If the row is not the end of the pipeline, update the button with the new option (in case it has changed)
            else:
                button = self.pipeline.grid_slaves(row_i)[0]
                button.bg = self.theme.bg
                button.config(
                    text=option,
                    command=lambda a=option: self.select_pipeline_step(a),
                    **kw,
                )

            # Change the state of tthe commands in the right click menu based on position
            if i != 0:
                for j, state in enumerate(right_click_states):
                    key = list(right_click_map.keys())[j]
                    button.right_click_menu.entryconfig(
                        index=j,
                        label=f" {key}",
                        command=right_click_map[key],
                        state=state,
                    )

        # If the pipeline is longer than the options, delete the extra rows
        if row > len(options) + 2:
            for i in range(len(options) + 2, row):
                for widget in self.pipeline.grid_slaves(row=i):
                    widget.destroy()
        # Bind mouse scroll to the scrollable frame, but make sure the children also have the binding
        ctk.utils.scroll_with_mousewheel(
            self.pipeline, self.pipeline.canvas, apply_to_children=True
        )
        # Update the step numbers in the config file
        for step_number in self.CONFIG.keys():
            if step_number != 0:
                self.CONFIG[step_number]["step_general/step_number"] = str(step_number)

    def _update_editor(self):
        # print("Updating editor...", self.STEP)
        # Create an empty frame dictionary that we will populate
        frames_dict = {}
        # Get current row and the step type
        _, row = self.editor.grid_size()
        step_type = self.STEP.lower()
        # Clear the editor if there is anything in it
        self._clear_editor(row)
        # Get the entries for the step type from the editor lookup table, flatten the dictionary
        ##### Changes from new LUT
        ### entries = lut.LUT[step_type]
        ### entries_flat = flatten_dict(entries, sep="/")
        entries = lut.get_lut(step_type, float(self.yml_version.get()))
        entries_flat = deepcopy(entries)
        entries_flat.flatten()
        ##### End changes
        depth = max([len(k.split("/")) for k in entries_flat.keys()])
        # If depth is one, then we have no subframes and we just populate the editor
        if depth == 1:
            for key, value in entries.items():
                self._create_editor_entry(row, value, key, self.editor)
                row += 1
        else:
            # Break up the parameters based on the depth of the dictionary
            broken = [k.split("/") for k in entries_flat.keys()]
            # Create dictionaries to store the frames and rows
            frames = {"./": self.editor}
            rows = {"./": row}
            # Loop over the flattened dictionary and create the widgets
            # Here we create subframes if they are needed and not already created
            for i, (key, value) in enumerate(entries_flat.items()):
                if len(broken[i]) > 1:
                    for j in range(len(broken[i]) - 1):
                        parentframe_name = "./" + "/".join(broken[i][:j])
                        subframe_name = "./" + "/".join(broken[i][: j + 1])
                        if subframe_name not in frames.keys():
                            label_key = " ".join(
                                [
                                    l.lower().capitalize()
                                    for l in broken[i][j].split("_")
                                ]
                            )
                            f = ctk.ExpandableFrame(
                                frames[parentframe_name],
                                title=label_key,
                                level=j,
                                initial_state="collapsed",
                                bg=self.theme.bg,
                                fg=self.theme.fg,
                                font=ctk.FONT,
                            )
                            # f = ctk.ToggledFrame(
                            #     frames[parentframe_name],
                            #     bg=self.theme.bg,
                            #     text=label_key,
                            # )
                            f.grid(
                                row=rows[parentframe_name],
                                column=0,
                                columnspan=3,
                                sticky="nsew",
                                pady=5,
                                padx=5,
                            )
                            frame_dict_key = (
                                parentframe_name + "/" + label_key
                                if parentframe_name[-1] != "/"
                                else parentframe_name + label_key
                            )
                            frames_dict[frame_dict_key] = f
                            frames[subframe_name] = f.extension
                            frames[subframe_name].columnconfigure(0, weight=1)
                            frames[subframe_name].columnconfigure(1, weight=1)
                            rows[subframe_name] = 0
                            rows[parentframe_name] += 1
                else:
                    subframe_name = "./"
                self._create_editor_entry(
                    rows[subframe_name], value, key, frames[subframe_name]
                )
                rows[subframe_name] += 1
        # Check if collapsable frames were expanded previously and expand them now if they are
        for key in frames_dict.keys():
            if key in self.frames_dict.keys() and self.frames_dict[key].is_expanded:
                frames_dict[key].toggle()
        self.frames_dict = frames_dict

        # Bind mouse scroll to the scrollable frame, but make sure the children also have the binding
        ctk.utils.scroll_with_mousewheel(
            self.editor, self.editor.canvas, apply_to_children=True
        )

    def _create_editor_entry(self, row, value, path, frame):
        """Helper function to create a widget in the editor for a specific parameter."""
        # Create the tkinter variable and store it in the PYVARS dictionary
        var = tk.StringVar(self.editor, name=path)
        self.PYVARS[path] = var

        # Now trace the variable
        self.PYVARS[path].trace_id = self.PYVARS[path].trace_add(
            "write", self._var_update
        )

        # Set the value of the variable to the value in the config file
        if path in self.CONFIG[self.STEP_INDEX].keys():
            # print("Setting value:", self.CONFIG[self.STEP_INDEX][path])
            var.set(self.CONFIG[self.STEP_INDEX][path])
        else:
            self.CONFIG[self.STEP_INDEX][path] = ""
            var.set(value.default)

        # Create the widgets and place them on the grid
        # local_frame = tk.Frame(frame, bg=self.theme.bg)
        # local_frame.grid(row=row, column=0, columnspan=3, sticky="nsew", pady=5)
        kwargs = deepcopy(value.widget_kwargs)
        kwargs.update({"font": ctk.FONT, "bg": self.theme.bg_off})
        if value.widget == ctk.Entry:
            kwargs.update({"disabledbackground": self.theme.bg_off})
        elif value.widget == ctk.MenuButton:
            kwargs.update({"h_bg": self.theme.accent1, "h_fg": self.theme.accent1_fg})
        label = ctk.AutofitLabel(
            frame, text=value.label, font=ctk.FONT, bg=self.theme.bg, fg=self.theme.fg
        )
        widget = value.widget(
            frame,
            var=self.PYVARS[path],
            **kwargs,
        )
        # label.pack(side="left", padx=(0, 10))
        # widget.pack(side="left")
        label.grid(row=row, column=0, sticky="nsew", pady=2)
        widget.grid(row=row, column=1, columnspan=2, sticky="nsew", pady=2)

        # Add a tooltip to show information about the config entry/menu/etc.
        label.tp = ctk.tooltip(label, value.help_text, font=ctk.TIP_FONT)
        row += 1

    def _clear_editor(self, row):
        """Clear the editor by removing all widgets and traces.
        This is useful when switching between steps."""
        # Disconnect currently traced variables. They will be reconnected when the editor is updated
        relevant_keys = list(self.PYVARS.keys())
        for key in relevant_keys:
            self.PYVARS[key].trace_vdelete("w", self.PYVARS[key].trace_id)
        self.PYVARS = {}

        # Remove the old widgets
        for i in range(2, row + 1):
            for widget in self.editor.grid_slaves(row=i - 1):
                widget.destroy()

    def _var_update(self, *args):
        """Update the config dictionary with the new value of the variable.
        This is called whenever a variable is changed."""
        string = args[0]
        if self.PYVARS[string].get() != self.CONFIG[self.STEP_INDEX][string]:
            try:
                self.status_label.config(
                    text="UNVALIDATED", bg=self.theme.yellow, fg=self.theme.yellow_fg
                )
            except tk.TclError:
                pass
        # print("New value:", self.PYVARS[string].get())
        # print("Old value:", self.CONFIG[self.STEP_INDEX][string])
        self.CONFIG[self.STEP_INDEX][string] = self.PYVARS[string].get()
        # print("Updated config:", self.CONFIG[self.STEP_INDEX][string])
        if "step_name" in string:
            self._update_pipeline()

    def export_pipeline(self, yml_path, force_valid=True):
        """Export the pipeline to a yaml file.
        This will prompt the user for a file path and then write the yaml file.
        Checks are performed to ensure the yaml file is correct."""
        # Validate the pipeline before writing the yaml file
        status, config_db = self.validate_full(return_config=True)
        if not status and force_valid:
            return False
        # Write the yaml file
        ut.dict_to_yml(config_db, yml_path)
        return True

    def _entries_to_nested(self, out_dict):
        """Helper function for exporting the pipeline to a yaml file.
        This function takes the flat dictionary and converts it to a nested dictionary.
        """
        out_dict_nested = {}
        for step in out_dict.keys():
            if step == "general":
                step_type = "general"
            else:
                step_type = out_dict[step]["step_general/step_type"]
            out_dict_nested[step] = deepcopy(
                lut.get_lut(step_type.lower(), float(self.yml_version.get()))
            )
            for key in out_dict_nested[step].keys():
                if isinstance(out_dict_nested[step][key], dict):
                    for nkey in out_dict_nested[step][key].keys():
                        if isinstance(out_dict_nested[step][key][nkey], dict):
                            for nnkey in out_dict_nested[step][key][nkey].keys():
                                if isinstance(
                                    out_dict_nested[step][key][nkey][nnkey], dict
                                ):
                                    for nnnkey in out_dict_nested[step][key][nkey][
                                        nnkey
                                    ].keys():
                                        dtype = out_dict_nested[step][key][nkey][nnkey][
                                            nnnkey
                                        ].dtype
                                        path = f"{key}/{nkey}/{nnkey}/{nnnkey}"
                                        out_dict_nested[step][key][nkey][nnkey][
                                            nnnkey
                                        ] = self._check_value_type(
                                            out_dict[step][path], dtype
                                        )
                                else:
                                    dtype = out_dict_nested[step][key][nkey][
                                        nnkey
                                    ].dtype
                                    path = f"{key}/{nkey}/{nnkey}"
                                    out_dict_nested[step][key][nkey][nnkey] = (
                                        self._check_value_type(
                                            out_dict[step][path], dtype
                                        )
                                    )
                        else:
                            dtype = out_dict_nested[step][key][nkey].get("dtype", None)
                            path = f"{key}/{nkey}"
                            out_dict_nested[step][key][nkey] = self._check_value_type(
                                out_dict[step][path], dtype
                            )
                else:
                    dtype = out_dict_nested[step][key].dtype
                    path = key
                    out_dict_nested[step][key] = self._check_value_type(
                        out_dict[step][path], dtype
                    )

        # Remove the step names from the config file
        for step_number, step in enumerate(out_dict_nested.keys()):
            if step != "general":
                out_dict_nested[step]["step_general"].pop("step_name")
                # Put in step number and reorder
                _temp = {"step_number": step_number}
                _temp.update(out_dict_nested[step]["step_general"])
                out_dict_nested[step]["step_general"] = _temp
        return out_dict_nested

    def format_config(self, step=None):
        # Create a copy of the config file
        config_db = deepcopy(self.CONFIG)
        # Prepare the general step, including type checking
        general = config_db.pop(0)
        general.pop("step_type")
        # general.pop("step_general/step_name")
        general_db_flat = lut.get_lut("general", float(self.yml_version.get()))
        general_db_flat.flatten()
        params = list(general.keys())
        for param in params:
            if param not in list(general_db_flat.keys()):
                general.pop(param)
            else:
                general[param] = _check_value_type(
                    general[param], general_db_flat[param].dtype
                )
        general = unflatten_dict(general, sep="/")
        # If we are only formatting the general step, return the general step
        if step == 0:
            return {
                "config_file_version": float(self.yml_version.get()),
                "general": general,
            }
        # Re-key steps using step names
        for step_num in list(config_db.keys()):
            if step is not None and step_num != step:
                config_db.pop(step_num)
            else:
                step_name = config_db[step_num]["step_general/step_name"]
                config_db[step_name] = config_db.pop(step_num)
        # Unflatten the dictionary so that it can be written to a yaml file
        # Perform data type checking as well
        for step_name in config_db.keys():
            db_flat = deepcopy(
                lut.get_lut(
                    config_db[step_name]["step_general/step_type"].lower(),
                    float(self.yml_version.get()),
                )
                # lut.LUT[config_db[step_name]["step_general/step_type"].lower()]
            )
            db_flat.flatten()
            params = list(config_db[step_name].keys())
            for param in params:
                if param not in db_flat.keys():
                    config_db[step_name].pop(param)
                else:
                    config_db[step_name][param] = _check_value_type(
                        config_db[step_name][param], db_flat[param].dtype
                    )
            config_db[step_name].pop("step_general/step_name")
            config_db[step_name] = unflatten_dict(config_db[step_name], sep="/")
        # Format the dictionary as version, general, steps
        config_db = {
            "config_file_version": float(self.yml_version.get()),
            "general": general,
            "steps": config_db,
        }
        return config_db

    def validate_full(self, return_config=False):
        """Validate the full pipeline to make sure it is correct."""
        # Make sure there are no duplicate step names
        if self.CONFIG[0]["step_count"] == 0:
            return (
                messagebox.showerror(
                    parent=self.toplevel,
                    title="Error writing yaml file",
                    message="No steps found!\nPlease add at least one step.",
                ),
                False,
            )
        names = [
            v["step_general/step_name"]
            for v in self.CONFIG.values()
            if "step_general/step_name" in v.keys()
        ]
        if len(names) != len(set(names)):
            messagebox.showerror(
                parent=self.toplevel,
                title="Error writing yaml file",
                message="Duplicate step names found!\nAll steps must have unique names.",
            )
            return
        # Format the config into the Schema/yml format
        config_db = self.format_config()
        # Check the pipeline to make sure it is correct
        status = self.schema_check_pipeline(config_db)
        if status:
            self.status_label.config(
                text="VALID", bg=self.theme.green, fg=self.theme.green_fg
            )
        else:
            self.status_label.config(text="INVALID", bg=self.theme.red_fg)
        if return_config:
            return status, config_db
        else:
            return status

    def validate_step(self, return_config=False):
        """Validate the current step to make sure it is correct."""
        config_db = self.format_config(step=self.STEP_INDEX)
        if return_config:
            return self.schema_check_pipeline(config_db), config_db
        else:
            return self.schema_check_pipeline(config_db)

    def validate_general(self, return_config=False, suppress=False):
        config_db = self.format_config(step=0)
        if return_config:
            return self.schema_check_pipeline(config_db, suppress=suppress), config_db
        else:
            return self.schema_check_pipeline(config_db, suppress=suppress)

    def schema_check_pipeline(self, config_db, suppress=False):
        """Perform schema checking on the pipeline to make sure it is correct."""
        yml_format = ut.yml_format(version=1.0)
        success = True
        info = []
        # Do general first so that the microscope object is created
        try:
            general_set = factory.general(config_db["general"], yml_format=yml_format)
            info.append(("General", "passed"))
        except Exception as e:
            info.append(("General", f"failed: {type(e).__name__}, {e}"))
            general_set = None
            success = False
        # If we are checking steps, create the microscope object and check the steps
        if "steps" in config_db.keys() and general_set is not None:
            # Create the microscope object
            Microscope = tbt.Microscope()
            ut.connect_microscope(
                Microscope,
                quiet_output=True,
                connection_host=general_set.connection.host,
                connection_port=general_set.connection.port,
            )
            # Loop over the steps and perform schema checking
            for step_name in config_db["steps"].keys():
                try:
                    _ = factory.step(
                        Microscope,
                        step_name=step_name,
                        step_settings=config_db["steps"][step_name],
                        general_settings=general_set,
                        yml_format=yml_format,
                    )
                    info.append((step_name, "passed"))
                except Exception as e:
                    info.append((step_name, f"failed: {type(e).__name__}, {e}"))
                    success = False
        message = "\n".join([f"{step} - {status}" for step, status in info])
        if success and not suppress:
            messagebox.showinfo(
                parent=self.toplevel,
                title="Schema check completed successfully",
                message=message,
            )
            return True
        elif not success:
            messagebox.showerror(
                parent=self.toplevel,
                title="Schema check completed unsuccessfully",
                message=message,
            )
            return False
        else:
            return True


def _check_value_type(value, dtype):
    """Data type handler for exporting the pipeline to a yaml file.
    Requires a dtype to be passed in to convert the value to the correct type.
    Converts '', 'null', 'None' to None, 'True' or 'true' to True, 'False' or 'false' to False.
    """
    if type(value) == str:
        value = value.strip()
    if value in ["", "null", "None", None]:
        return None
    if dtype is None:
        return value
    if value in ["True", "true"]:
        return True
    elif value in ["False", "false"]:
        return False
    else:
        return dtype(value)


def flatten_dict(d, parent_key="", sep="/"):
    """Takes a nested dictionary and flattens it to a single level dictionary.
    Nested keys are combined using a separator.
    A parent key can be passed in to add to the beginning of all keys."""
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        try:
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        except:
            items.append((new_key, v))
    return dict(items)


def unflatten_dict(d, sep="/"):
    """Takes a flattened dictionary and unflattens it to a nested dictionary."""
    items = {}
    for k, v in d.items():
        keys = k.split(sep)
        sub_items = items
        for key in keys[:-1]:
            sub_items = sub_items.setdefault(key, {})
        sub_items[keys[-1]] = v
    return items


def get_key(keywords, dictionary):
    """Get the key from a dictionary based on a list of keywords.
    This is useful for finding a key in a flattened dictionary."""
    if not isinstance(keywords, list):
        check = lambda x, y: x in y
    else:
        check = lambda x, y: all([i in y for i in x])
    for key in dictionary.keys():
        if check(keywords, key):
            return key
    return None


if __name__ == "__main__":

    def open_configurator():
        root.withdraw()
        configurator = Configurator(root, theme=ctk.Theme("dark"))
        root.wait_window(configurator.toplevel)
        # print("Configurator closed.")
        root.deiconify()

    root = tk.Tk()
    root.title("Dummy window")
    l = tk.Button(
        root,
        text="This is a button to open the configurator.",
        command=open_configurator,
    )
    l.pack()
    root.mainloop()
