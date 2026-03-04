"""Reusable UI components for the runner application.

This module contains UI panels and widgets that can be composed
to build the main application window.
"""

import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from PIL import Image, ImageTk

import pytribeam.GUI.CustomTkinterWidgets as ctk
from pytribeam.GUI.common import AppResources
from pytribeam.GUI.runner_util.experiment_controller import ExperimentState


class ControlPanel(tk.Frame):
    """Control panel with experiment settings and action buttons.

    This panel contains:
    - Logo
    - Experiment info (slices, steps, thickness)
    - Config file management buttons
    - Starting slice/step selectors
    - Experiment control buttons (start, stop)

    Attributes:
        on_new_config: Callback for creating new config
        on_load_config: Callback for loading config
        on_edit_config: Callback for editing config
        on_validate_config: Callback for validating config
        on_start_experiment: Callback for starting experiment
        on_stop_step: Callback for stopping after step
        on_stop_slice: Callback for stopping after slice
        on_stop_now: Callback for immediate stop
    """

    def __init__(self, parent, theme, resources: AppResources, **kwargs):
        """Initialize control panel.

        Args:
            parent: Parent widget
            theme: Theme object
            resources: Application resources
            **kwargs: Additional frame arguments
        """
        super().__init__(parent, bg=theme.bg, relief="ridge", bd=2, **kwargs)
        self.theme = theme
        self.resources = resources

        # Callbacks (to be set by parent)
        self.on_new_config = None
        self.on_load_config = None
        self.on_edit_config = None
        self.on_validate_config = None
        self.on_start_experiment = None
        self.on_stop_step = None
        self.on_stop_slice = None
        self.on_stop_now = None

        # Grid configuration
        self.columnconfigure([0, 1, 2, 3], weight=1)

        # Variables for UI state
        self.starting_slice_var = tk.IntVar(value=1)
        self.starting_step_var = tk.StringVar(value="-")

        self._create_widgets()

    def _create_widgets(self):
        """Create all widgets in the control panel."""
        # Logo
        image = Image.open(self.resources.logo_dark_path)
        image_size = (image.size[0] // 3, image.size[1] // 3)
        image.thumbnail(image_size, Image.ANTIALIAS)
        self.logo = ImageTk.PhotoImage(image)

        logo_label = tk.Label(
            self,
            image=self.logo,
            bg=self.theme.bg,
            width=image_size[0],
            height=image_size[1],
        )
        logo_label.grid(row=0, column=0, columnspan=4)

        # Experiment info frame
        self._create_experiment_info_frame()

        # Starting position selectors
        self._create_starting_position_widgets()

        # Control buttons
        self._create_control_buttons()

    def _create_experiment_info_frame(self):
        """Create experiment information display."""
        info_frame = tk.LabelFrame(
            self,
            text="Experiment info",
            font=ctk.SUBHEADER_FONT,
            bg=self.theme.bg,
            fg=self.theme.fg,
        )
        info_frame.grid(row=1, column=0, columnspan=4, sticky="nsew", pady=5, padx=5)
        info_frame.columnconfigure(0, weight=5)
        info_frame.columnconfigure(1, weight=1)
        info_frame.rowconfigure([0, 1, 2, 3, 4, 5], weight=1)

        # Labels
        self.total_slices_label = tk.Label(
            info_frame,
            text="Total number of slices: -",
            font=ctk.FONT,
            bg=self.theme.bg,
            fg=self.theme.fg,
            anchor="w",
        )
        self.total_slices_label.grid(row=0, column=0, sticky="nsew", pady=2, padx=2)

        self.total_steps_label = tk.Label(
            info_frame,
            text="Number of steps per slice: -",
            font=ctk.FONT,
            bg=self.theme.bg,
            fg=self.theme.fg,
            anchor="w",
        )
        self.total_steps_label.grid(row=1, column=0, sticky="nsew", pady=2, padx=2)

        self.slice_thickness_label = tk.Label(
            info_frame,
            text="Slice thickness: -",
            font=ctk.FONT,
            bg=self.theme.bg,
            fg=self.theme.fg,
            anchor="w",
        )
        self.slice_thickness_label.grid(row=2, column=0, sticky="nsew", pady=2, padx=2)

        self.config_file_label = tk.Label(
            info_frame,
            text="No configuration file loaded",
            font=ctk.FONT_ITALIC,
            bg=self.theme.bg,
            fg=self.theme.fg,
            anchor="w",
        )
        self.config_file_label.grid(
            row=3, column=0, columnspan=2, sticky="nsew", pady=2, padx=2
        )

        self.exp_dir_label = tk.Label(
            info_frame,
            text="Exp dir: -",
            font=ctk.FONT_ITALIC,
            bg=self.theme.bg,
            fg=self.theme.fg,
            anchor="w",
        )
        self.exp_dir_label.grid(
            row=4, column=0, columnspan=2, sticky="nsew", pady=2, padx=2
        )

        self.valid_status_label = tk.Label(
            info_frame,
            text="...",
            font=ctk.FONT_ITALIC,
            bg=self.theme.bg,
            fg=self.theme.fg,
            anchor="w",
        )
        self.valid_status_label.grid(
            row=5, column=0, columnspan=2, sticky="nsew", pady=2, padx=2
        )

        # Buttons
        create_btn = tk.Button(
            info_frame,
            text="Create",
            font=ctk.FONT,
            command=lambda: self.on_new_config() if self.on_new_config else None,
            bg=self.theme.bg_off,
            fg=self.theme.fg,
        )
        create_btn.grid(row=0, column=1, sticky="nsew", pady=2, padx=2)
        ctk.tooltip(create_btn, "Create a new configuration file")

        load_btn = tk.Button(
            info_frame,
            text="Load",
            font=ctk.FONT,
            command=lambda: self.on_load_config() if self.on_load_config else None,
            bg=self.theme.bg_off,
            fg=self.theme.fg,
        )
        load_btn.grid(row=1, column=1, sticky="nsew", pady=2, padx=2)
        ctk.tooltip(load_btn, "Load an existing configuration file")

        edit_btn = tk.Button(
            info_frame,
            text="Edit",
            font=ctk.FONT,
            command=lambda: self.on_edit_config() if self.on_edit_config else None,
            bg=self.theme.bg_off,
            fg=self.theme.fg,
        )
        edit_btn.grid(row=2, column=1, sticky="nsew", pady=2, padx=2)
        ctk.tooltip(edit_btn, "Edit the current configuration file")

        validate_btn = tk.Button(
            info_frame,
            text="Validate",
            font=ctk.FONT,
            command=lambda: (
                self.on_validate_config() if self.on_validate_config else None
            ),
            bg=self.theme.bg_off,
            fg=self.theme.fg,
        )
        validate_btn.grid(row=5, column=1, sticky="nsew", pady=2, padx=2)
        ctk.tooltip(validate_btn, "Validate configuration file")

    def _create_starting_position_widgets(self):
        """Create slice and step starting position selectors."""
        # Starting slice
        slice_label = tk.Label(
            self,
            text="Starting slice",
            font=ctk.FONT,
            bg=self.theme.bg,
            fg=self.theme.fg,
            anchor="e",
        )
        slice_label.grid(row=2, column=0, sticky="nsew", pady=5, padx=5)

        self.starting_slice_spinbox = tk.Spinbox(
            self,
            font=ctk.FONT,
            width=4,
            from_=1,
            to=10,
            bg=self.theme.bg_off,
            buttonbackground=self.theme.bg_off,
            disabledbackground=self.theme.bg_off,
            fg=self.theme.fg,
            textvariable=self.starting_slice_var,
            state="disabled",
        )
        self.starting_slice_spinbox.grid(row=2, column=1, sticky="nsew", pady=5, padx=5)
        ctk.tooltip(
            self.starting_slice_spinbox, "Slice number to start the experiment at"
        )

        # Starting step
        step_label = tk.Label(
            self,
            text="Starting step",
            font=ctk.FONT,
            bg=self.theme.bg,
            fg=self.theme.fg,
            anchor="e",
        )
        step_label.grid(row=2, column=2, sticky="nsew", pady=5, padx=5)

        self.starting_step_menu = ctk.MenuButton(
            self,
            font=ctk.FONT,
            options=["-"],
            var=self.starting_step_var,
            width=12,
            state="disabled",
            bg=self.theme.bg_off,
            fg=self.theme.fg,
            h_bg=self.theme.accent1,
            h_fg=self.theme.accent1_fg,
        )
        self.starting_step_menu.grid(row=2, column=3, sticky="nsew", pady=5, padx=5)
        ctk.tooltip(self.starting_step_menu, "Step to start the experiment at")

    def _create_control_buttons(self):
        """Create experiment control buttons."""
        self.start_btn = tk.Button(
            self,
            text="Start experiment",
            font=ctk.FONT,
            command=lambda: (
                self.on_start_experiment() if self.on_start_experiment else None
            ),
            bg=self.theme.bg_off,
            fg=self.theme.fg,
        )
        self.start_btn.grid(
            row=3, column=0, columnspan=4, sticky="nsew", pady=3, padx=5
        )
        ctk.tooltip(
            self.start_btn,
            "Start the experiment with the current configuration",
        )

        self.stop_step_btn = tk.Button(
            self,
            text="Stop after current step",
            font=ctk.FONT,
            command=lambda: self.on_stop_step() if self.on_stop_step else None,
            bg=self.theme.bg_off,
            fg=self.theme.fg,
        )
        self.stop_step_btn.grid(
            row=4, column=0, columnspan=4, sticky="nsew", pady=3, padx=5
        )
        ctk.tooltip(self.stop_step_btn, "Stop after current step (Ctrl+Shift+X)")

        self.stop_slice_btn = tk.Button(
            self,
            text="Stop after current slice",
            font=ctk.FONT,
            command=lambda: self.on_stop_slice() if self.on_stop_slice else None,
            bg=self.theme.bg_off,
            fg=self.theme.fg,
        )
        self.stop_slice_btn.grid(
            row=5, column=0, columnspan=4, sticky="nsew", pady=3, padx=5
        )
        ctk.tooltip(self.stop_slice_btn, "Stop after current slice (Ctrl+X)")

        # Separator
        sep = tk.Frame(self, bg=self.theme.bg, height=5, relief="flat")
        sep.grid(row=6, column=0, columnspan=4, sticky="nsew", pady=10)

        self.stop_now_btn = tk.Button(
            self,
            text="Hard stop",
            font=ctk.FONT,
            command=lambda: self.on_stop_now() if self.on_stop_now else None,
            bg=self.theme.bg_off,
            fg=self.theme.fg,
        )
        self.stop_now_btn.grid(
            row=7, column=0, columnspan=4, sticky="nsew", pady=3, padx=5
        )
        ctk.tooltip(self.stop_now_btn, "Stop immediately (Ctrl+C)")

    def update_experiment_info(self, config_info: dict):
        """Update experiment information display.

        Args:
            config_info: Dictionary with keys: total_slices, total_steps,
                        slice_thickness, config_path, exp_dir, step_names
        """
        self.total_slices_label.config(
            text=f"Total number of slices: {config_info.get('total_slices', '-')}"
        )
        self.total_steps_label.config(
            text=f"Number of steps per slice: {config_info.get('total_steps', '-')}"
        )
        self.slice_thickness_label.config(
            text=f"Slice thickness: {config_info.get('slice_thickness', '-')}"
        )
        self.config_file_label.config(
            text=f"Config: {config_info.get('config_path', 'No file loaded')}"
        )
        self.exp_dir_label.config(text=f"Exp dir: {config_info.get('exp_dir', '-')}")

        # Update starting position controls
        if "total_slices" in config_info and config_info["total_slices"] != "-":
            self.starting_slice_spinbox.config(
                from_=1, to=config_info["total_slices"], state="normal"
            )

        if "step_names" in config_info and config_info["step_names"]:
            self.starting_step_menu.set_options(config_info["step_names"])
            self.starting_step_menu.config(state="normal")
            self.starting_step_var.set(config_info["step_names"][0])

    def set_validation_status(self, is_valid: bool, message: str = ""):
        """Update validation status display.

        Args:
            is_valid: Whether configuration is valid
            message: Status message to display
        """
        if is_valid:
            self.valid_status_label.config(
                text=message or "Configuration file is valid", fg=self.theme.green
            )
        else:
            self.valid_status_label.config(
                text=message or "Configuration file is invalid", fg=self.theme.red
            )

    def set_buttons_enabled(self, start: bool = True, stop_controls: bool = False):
        """Enable/disable control buttons.

        Args:
            start: Whether start button should be enabled
            stop_controls: Whether stop buttons should be enabled
        """
        self.start_btn.config(state="normal" if start else "disabled")
        stop_state = "normal" if stop_controls else "disabled"
        self.stop_step_btn.config(state=stop_state)
        self.stop_slice_btn.config(state=stop_state)
        self.stop_now_btn.config(state=stop_state)


class StatusPanel(tk.Frame):
    """Status panel showing current experiment progress.

    This panel displays:
    - Current step and slice
    - Average slice time
    - Remaining duration
    - Progress bar

    Attributes:
        None (updates via update_state method)
    """

    def __init__(self, parent, theme, **kwargs):
        """Initialize status panel.

        Args:
            parent: Parent widget
            theme: Theme object
            **kwargs: Additional frame arguments
        """
        super().__init__(parent, bg=theme.bg, relief="ridge", bd=2, **kwargs)
        self.theme = theme

        # Grid configuration
        self.columnconfigure([0, 1, 2, 3, 4, 5, 6, 7], weight=1)
        self.rowconfigure([0, 1], weight=1)

        # Variables
        self.current_step_var = tk.StringVar(value="-")
        self.current_slice_var = tk.StringVar(value="-")
        self.slice_time_var = tk.StringVar(value="-")
        self.time_left_var = tk.StringVar(value="-")

        self._create_widgets()

    def _create_widgets(self):
        """Create all widgets in status panel."""
        # Current step
        tk.Label(
            self,
            text="Current step",
            font=ctk.FONT_ITALIC,
            bg=self.theme.bg,
            fg=self.theme.fg,
            anchor="e",
        ).grid(row=0, column=0, sticky="nsew", pady=5, padx=5)

        tk.Label(
            self,
            textvariable=self.current_step_var,
            font=ctk.FONT_BOLD,
            bg=self.theme.bg,
            fg=self.theme.accent2,
            anchor="w",
        ).grid(row=0, column=1, sticky="nsew", pady=5, padx=5)

        # Current slice
        tk.Label(
            self,
            text="Current slice",
            font=ctk.FONT_ITALIC,
            bg=self.theme.bg,
            fg=self.theme.fg,
            anchor="e",
        ).grid(row=0, column=2, sticky="nsew", pady=5, padx=5)

        tk.Label(
            self,
            textvariable=self.current_slice_var,
            font=ctk.FONT_BOLD,
            bg=self.theme.bg,
            fg=self.theme.accent2,
            anchor="w",
        ).grid(row=0, column=3, sticky="nsew", pady=5, padx=5)

        # Average slice time
        tk.Label(
            self,
            text="Average slice time",
            font=ctk.FONT_ITALIC,
            bg=self.theme.bg,
            fg=self.theme.fg,
            anchor="e",
        ).grid(row=0, column=4, sticky="nsew", pady=5, padx=5)

        tk.Label(
            self,
            textvariable=self.slice_time_var,
            font=ctk.FONT_BOLD,
            bg=self.theme.bg,
            fg=self.theme.accent2,
            anchor="w",
        ).grid(row=0, column=5, sticky="nsew", pady=5, padx=5)

        # Time left
        tk.Label(
            self,
            text="Remaining duration",
            font=ctk.FONT_ITALIC,
            bg=self.theme.bg,
            fg=self.theme.fg,
            anchor="e",
        ).grid(row=0, column=6, sticky="nsew", pady=5, padx=5)

        tk.Label(
            self,
            textvariable=self.time_left_var,
            font=ctk.FONT_BOLD,
            bg=self.theme.bg,
            fg=self.theme.accent2,
            anchor="w",
        ).grid(row=0, column=7, sticky="nsew", pady=5, padx=5)

        # Progress bar
        self.progress = ctk.Progressbar(
            self,
            bg=self.theme.bg,
            fg=self.theme.green,
            text_fg=self.theme.fg,
            text_bg=self.theme.bg,
        )
        self.progress.grid(row=1, column=0, columnspan=8, sticky="nsew", pady=5, padx=5)

    def update_state(self, state: ExperimentState):
        """Update display from experiment state.

        Args:
            state: Current experiment state
        """
        self.current_step_var.set(state.current_step)
        self.current_slice_var.set(str(state.current_slice))
        self.slice_time_var.set(state.avg_slice_time_str)
        self.time_left_var.set(state.remaining_time_str)
        self.progress.set(state.progress_percent)
