import traceback
from pathlib import Path
from copy import deepcopy
import tkinter as tk
from tkinter import messagebox

from skimage import io


import pytribeam.utilities as ut
import pytribeam.types as tbt
import pytribeam.factory as factory
import pytribeam.laser as laser
from pytribeam.constants import Conversions
import pytribeam.GUI.CustomTkinterWidgets as ctk
import pytribeam.GUI.config_ui.lookup as lut
from pytribeam.GUI.common import AppResources
from pytribeam.GUI.config_ui.pipeline_model import flatten_dict, unflatten_dict
from pytribeam.GUI.config_ui.microscope_interface import (
    MicroscopeInterface,
    format_stage_info,
)
from pytribeam.GUI.config_ui.validator import ConfigValidator
from pytribeam.GUI.config_ui.editor_controller import EditorController
from pytribeam.GUI.config_ui.parameter_tracker import ParameterTracker


import tkinter as tk
import numpy as np
from PIL import Image, ImageTk


class RoiSelector:
    def __init__(self, image: np.ndarray, master=None, title="ROI Selector"):
        if master is None:
            master = tk._get_default_root()

        bg = master.cget("bg")
        fg = ctk.calc_font_color(bg)

        self.root = tk.Toplevel(master)
        self.root.protocol("WM_DELETE_WINDOW", self.destroy)
        self.root.title(title)
        self.root.update_idletasks()
        self.root.config(bg=bg)

        self.roi = None

        self._start_x = None
        self._start_y = None
        self._rect_id = None

        self._image_array = np.asarray(image)
        self._orig_h, self._orig_w = self._image_array.shape[:2]

        pil_image = self._numpy_to_pil(self._image_array)

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        max_w = int(screen_w * 0.85)
        max_h = int(screen_h * 0.75)

        self._scale = min(
            1.0,
            max_w / self._orig_w,
            max_h / self._orig_h,
        )

        self._disp_w = int(self._orig_w * self._scale)
        self._disp_h = int(self._orig_h * self._scale)

        if self._scale != 1.0:
            display_image = pil_image.resize(
                (self._disp_w, self._disp_h),
                Image.Resampling.LANCZOS,
            )
        else:
            display_image = pil_image

        self._photo = ImageTk.PhotoImage(display_image)

        instructions = tk.Label(
            self.root,
            text="Click and drag on the image to select a region of interest.",
            bg=bg,
            fg=fg,
        )
        instructions.pack(padx=8, pady=(8, 4))

        self.canvas = tk.Canvas(
            self.root,
            width=self._disp_w,
            height=self._disp_h,
            bg="black",
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.pack(padx=8, pady=4)

        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)

        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        button_frame = tk.Frame(self.root, bg=bg)
        button_frame.pack(fill="x", padx=8, pady=(4, 8))

        self.status_label = tk.Label(
            button_frame,
            text="ROI: None",
            bg=bg,
            fg=fg,
            anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        reset_button = tk.Button(
            button_frame,
            text="Reset",
            command=self._reset_roi,
        )
        reset_button.pack(side="right", padx=(4, 0))

        cancel_button = tk.Button(
            button_frame,
            text="Cancel",
            command=self.destroy,
        )
        cancel_button.pack(side="right", padx=(4, 0))

        finish_button = tk.Button(
            button_frame,
            text="Finish",
            command=self._finish,
        )
        finish_button.pack(side="right", padx=(4, 0))

        self.root.bind("<Escape>", lambda event: self.destroy())
        self.root.bind("<Return>", lambda event: self._finish())

        self.root.grab_set()
        self.root.wait_window()

    def _numpy_to_pil(self, image: np.ndarray) -> Image.Image:
        """
        Convert a NumPy image array to a PIL image suitable for display.

        Supports:
            - 2D grayscale
            - 3D RGB/RGBA
            - uint8, uint16, int, float
        """
        arr = np.asarray(image)

        if arr.ndim not in (2, 3):
            raise ValueError(
                "Image array must be either 2D grayscale or 3D RGB/RGBA."
            )

        if arr.ndim == 3 and arr.shape[2] not in (3, 4):
            raise ValueError(
                "3D image array must have 3 channels RGB or 4 channels RGBA."
            )

        if arr.dtype == np.uint8:
            display_arr = arr

        elif np.issubdtype(arr.dtype, np.floating):
            display_arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=0.0)

            min_val = display_arr.min()
            max_val = display_arr.max()

            if min_val >= 0.0 and max_val <= 1.0:
                display_arr = display_arr * 255.0
            elif max_val > min_val:
                display_arr = 255.0 * (display_arr - min_val) / (max_val - min_val)
            else:
                display_arr = np.zeros_like(display_arr)

            display_arr = np.clip(display_arr, 0, 255).astype(np.uint8)

        else:
            display_arr = arr.astype(np.float32)

            min_val = display_arr.min()
            max_val = display_arr.max()

            if max_val > min_val:
                display_arr = 255.0 * (display_arr - min_val) / (max_val - min_val)
            else:
                display_arr = np.zeros_like(display_arr)

            display_arr = np.clip(display_arr, 0, 255).astype(np.uint8)

        return Image.fromarray(display_arr)

    def _on_mouse_down(self, event):
        self._start_x, self._start_y = self._clamp_canvas_xy(event.x, event.y)

        if self._rect_id is not None:
            self.canvas.delete(self._rect_id)

        self._rect_id = self.canvas.create_rectangle(
            self._start_x,
            self._start_y,
            self._start_x,
            self._start_y,
            outline="red",
            width=2,
        )

    def _on_mouse_drag(self, event):
        if self._rect_id is None:
            return

        x, y = self._clamp_canvas_xy(event.x, event.y)

        self.canvas.coords(
            self._rect_id,
            self._start_x,
            self._start_y,
            x,
            y,
        )

        self._update_roi_from_canvas_coords(self._start_x, self._start_y, x, y)

    def _on_mouse_up(self, event):
        if self._rect_id is None:
            return

        x, y = self._clamp_canvas_xy(event.x, event.y)

        self.canvas.coords(
            self._rect_id,
            self._start_x,
            self._start_y,
            x,
            y,
        )

        self._update_roi_from_canvas_coords(self._start_x, self._start_y, x, y)

    def _clamp_canvas_xy(self, x, y):
        x = max(0, min(x, self._disp_w))
        y = max(0, min(y, self._disp_h))
        return x, y

    def _update_roi_from_canvas_coords(self, x0, y0, x1, y1):
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))

        img_x0 = int(round(x0 / self._scale))
        img_x1 = int(round(x1 / self._scale))
        img_y0 = int(round(y0 / self._scale))
        img_y1 = int(round(y1 / self._scale))

        img_x0 = max(0, min(img_x0, self._orig_w))
        img_x1 = max(0, min(img_x1, self._orig_w))
        img_y0 = max(0, min(img_y0, self._orig_h))
        img_y1 = max(0, min(img_y1, self._orig_h))

        if img_x1 <= img_x0 or img_y1 <= img_y0:
            self.roi = None
            self.status_label.config(text="ROI: None")
            return

        self.roi = [[img_x0, img_x1], [img_y0, img_y1]]
        self.status_label.config(text=f"ROI: {self.roi}")

    def _reset_roi(self):
        self.roi = None
        self.status_label.config(text="ROI: None")

        if self._rect_id is not None:
            self.canvas.delete(self._rect_id)
            self._rect_id = None

    def _finish(self):
        self.root.quit()
        self.root.destroy()

    def destroy(self):
        self.roi = None
        self.root.quit()
        self.root.destroy()


class Popup:
    def __init__(self, master=None, title="Popup", message=""):
        if master is None:
            master = tk._get_default_root()
        bg = master.cget("bg")
        fg = ctk.calc_font_color(bg)

        self.root = tk.Toplevel(master)
        self.root.minsize(200, 70)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.destroy)
        self.root.title(title)
        self.root.update_idletasks()
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        self.root.config(bg=bg)

        width = int(max(map(len, message.split("\n"))) * 1.1)
        height = message.count("\n") + 1
        self.text = tk.Text(
            self.root,
            bg=bg,
            fg=fg,
            height=height,
            width=width,
            highlightthickness=0,
            bd=0,
            selectbackground="orange",
            font=ctk.FONT,
            padx=10,
            pady=10,
        )
        self.text.insert("end", message)
        self.text.config(state="disabled")
        self.text.tag_config("tag", justify="left")
        self.text.tag_add("tag", "1.0", tk.END)
        self.text.pack()

        self.b = ctk.Button(
            self.root, text="OK", command=self.destroy, bg=bg, fg=fg, width=width // 2
        )
        self.b.pack(side="right")

        self.root.grab_set()
        self.root.mainloop()

    def destroy(self):
        self.root.quit()
        self.root.destroy()


class Configurator:
    def __init__(self, master, theme, yml_path=None, *args, **kwargs):
        self.master = master
        self.theme = theme
        self.toplevel = tk.Toplevel(
            self.master, background=self.theme.bg, *args, **kwargs
        )

        # Initialize resources
        self.resources = AppResources.from_module_file(__file__)

        # Set app title, icon, size and grid structure
        self.YAML_PATH = yml_path
        self.update_title()
        self.toplevel.iconbitmap(self.resources.icon_path)
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

        # Initialize EditorController
        self.controller = EditorController(version=float(self.yml_version.get()))

        # Initialize ParameterTracker for managing UI variable bindings
        self.param_tracker = ParameterTracker(self.controller)

        # Register callbacks for controller events
        self.controller.register_callback("pipeline_created", self._on_pipeline_created)
        self.controller.register_callback("pipeline_loaded", self._on_pipeline_loaded)
        self.controller.register_callback("pipeline_changed", self._on_pipeline_changed)
        self.controller.register_callback("step_selected", self._on_step_selected)
        self.controller.register_callback("step_added", self._on_step_added)
        self.controller.register_callback("step_removed", self._on_step_removed)
        self.controller.register_callback(
            "parameter_changed", self._on_parameter_changed
        )
        self.controller.register_callback(
            "step_validation_complete", self._on_step_validation_complete
        )
        self.controller.register_callback(
            "pipeline_validation_complete", self._on_pipeline_validation_complete
        )

        # Fill the toplevel with the editor window
        self._fill_toplevel(redraw=False)

        # Initialize class variables (kept for backward compatibility during migration)
        self.STEP_INDEX = -1
        self.STEP = ""
        self.clean_exit = False
        self.frames_dict = {}
        self.pipeline_buttons = {}

        # Start the app
        if self.YAML_PATH is not None:
            self.load_config(self.YAML_PATH)
        else:
            self.new_config(ask_save=False)

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
            label="View position & WD's",
            command=self.show_stage_position,
            font=ctk.MENU_FONT,
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
        microscope_menu.add_separator()
        microscope_menu.add_command(
            label="Take FIB alignment images",
            command=self.take_fib_alignment_images,
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
        self.controller.set_version(float(self.yml_version.get()))
        self._update_editor()

    def update_title(self):
        """Update the title of the app window based on the current yaml file."""
        if self.YAML_PATH is None:
            self.toplevel.title("TriBeam Configurator - Untitled")
        else:
            self.toplevel.title(f"TriBeam Configurator - {self.YAML_PATH}")

    def save_exit(self):
        """Validate and save the current configuration and exit the application."""
        # Save first
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
            self.YAML_PATH = yml_path
        else:
            yml_path = self.YAML_PATH

        # Save the configuration
        success, error = self.controller.save_pipeline(Path(yml_path))
        if success:
            self.YAML_PATH = yml_path
        else:
            messagebox.showerror(
                parent=self.toplevel,
                title="Error saving configuration",
                message=f"{error}",
            )
            return False

        # Validate first, exiting if invalid
        valid = self.validate_full()
        if not valid:
            return False
        # Exit
        self.clean_exit = True
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

    # -------- Controller Callbacks -------- #

    def _on_pipeline_created(self, pipeline):
        """Handle pipeline creation."""
        self._on_step_selected(0, pipeline.general)

    def _on_pipeline_loaded(self, pipeline):
        """Handle pipeline load."""
        self.yml_version.trace_remove("write", self.yml_version.trace_id)
        self.yml_version.set(str(pipeline.version))
        self.yml_version.trace_id = self.yml_version.trace_add(
            "write", self._yaml_version_updated
        )
        self._update_pipeline()
        self._update_editor()

    def _on_pipeline_changed(self, pipeline):
        """Handle pipeline changes."""
        self._update_pipeline()

    def _on_step_selected(self, index, step):
        """Handle step selection."""
        self.STEP_INDEX = index
        self.STEP = step.step_type if hasattr(step, "step_type") else "general"
        self._update_pipeline()
        self._update_editor()

    def _on_step_added(self, step):
        """Handle step addition."""
        pass
        # self._update_pipeline()

    def _on_step_removed(self, index):
        """Handle step removal."""
        # Select general or previous step
        if index == self.STEP_INDEX:
            self.controller.select_step(0)
        elif index < self.STEP_INDEX:
            self.controller.select_step(self.STEP_INDEX - 1)
        else:
            self.controller.select_step(self.STEP_INDEX)

    def _on_parameter_changed(self, path, value):
        """Handle parameter change from controller."""
        # Mark configuration as unvalidated
        try:
            self.status_label.config(
                text="UNVALIDATED", bg=self.theme.yellow, fg=self.theme.yellow_fg
            )
        except tk.TclError:
            pass  # Widget may not exist yet

        # If step name changed, update pipeline display
        if "step_name" in path:
            self._update_pipeline_names()

    def _on_step_validation_complete(self, index, success, message):
        """Handle step validation completion."""
        if index == self.STEP_INDEX:
            if success:
                self.status_label.config(
                    text="VALID", bg=self.theme.green, fg=self.theme.green_fg
                )
            else:
                self.status_label.config(
                    text="INVALID", bg=self.theme.red, fg=self.theme.red_fg
                )

    def _on_pipeline_validation_complete(self, success, message):
        """Handle pipeline validation completion."""
        if success:
            self.status_label.config(
                text="VALID", bg=self.theme.green, fg=self.theme.green_fg
            )
        else:
            self.status_label.config(
                text="INVALID", bg=self.theme.red, fg=self.theme.red_fg
            )

    # -------- Microscope Connection -------- #

    def _create_microscope_connection(self):
        """Create microscope interface with connection settings from config."""
        # Get general settings for connection
        general_db = self.controller.pipeline.general.parameters
        host = general_db.get("connection_host", "localhost")
        port = general_db.get("connection_port", "")
        port = int(port) if port != "" else None
        interface = MicroscopeInterface(host=host, port=port)

        # Try to connect using both the default and custom host/port
        hosts_to_try = [host, "localhost"] if host != "localhost" else [host]
        ports_to_try = [port, None] if port is not None else [port]
        tries = []
        for h in hosts_to_try:
            for p in ports_to_try:
                interface.host = h
                interface.port = p
                tries.append(f"{h}:{p}")

                try:
                    interface.connect()
                    return interface
                except ConnectionError:
                    continue

        # If we reach here, all connection attempts failed
        messagebox.showerror(
            parent=self.toplevel,
            title="ConnectionError",
            message=f"Failed to connect to microscope. Tried {','.join(tries)}.",
        )
        return None

    def show_stage_position(self):
        """Display current stage position and working distances."""
        interface = self._create_microscope_connection()
        if interface is None:
            return

        try:
            stage_info = interface.get_stage_info()
            message = format_stage_info(stage_info)
        except Exception as e:
            messagebox.showerror(
                parent=self.toplevel,
                title="Error",
                message=f"Failed to get stage position: {e}",
            )
            return
        finally:
            interface.disconnect()

        # Present it as a popup
        Popup(
            master=self.toplevel,
            title="Current stage position",
            message=message,
        )

    def update_step_imaging_from_scope(self):
        """Update the imaging settings of the current step based on the current microscope settings."""
        if self.STEP not in ["image", "fib", "ebsd", "eds"]:
            messagebox.showinfo(
                parent=self.toplevel,
                title="Error",
                message=f"{self.STEP} step does not have imaging settings.",
            )
            return

        interface = self._create_microscope_connection()
        if interface is None:
            return

        try:
            # Get the settings
            imaging_settings = interface.get_imaging_settings()
        except Exception as e:
            messagebox.showerror(
                parent=self.toplevel,
                title="Error",
                message=f"Failed to get imaging settings: {e}",
            )
            return
        finally:
            interface.disconnect()
        # First set the beam type (special case)
        beam_type = imaging_settings.beam.__getattribute__("type").value
        # For FIB / EBSD / EDS steps, the beam must be ion / electron / electron, otherwise raise an error
        if self.STEP == "fib" and beam_type != "ion":
            messagebox.showerror(
                parent=self.toplevel,
                title="Error",
                message="Importing imaging conditions for a FIB step requires the active beam to be an ion beam.",
            )
            return
        elif self.STEP == "ebsd" and beam_type != "electron":
            messagebox.showerror(
                parent=self.toplevel,
                title="Error",
                message="Importing imaging conditions for an EBSD step requires the active beam to be an electron beam.",
            )
            return
        elif self.STEP == "eds" and beam_type != "electron":
            messagebox.showerror(
                parent=self.toplevel,
                title="Error",
                message="Importing imaging conditions for an EDS step requires the active beam to be an electron beam.",
            )
            return
        # Image steps do not have a parent key (the step is the parent key), but FIB steps have imaging parameters within an Image and Mill parent
        # For image steps, we just use the keys to the specific parameter (i.e. beam/type), but with the FIB we have to pass the parent (i.e. image/beam/type)
        # Since FIB also shares parameters between milling and imaging, we iterate twice to fill both parents
        # Note that milling does not have detector or scan parameters, so those are only updated for the image.
        if self.STEP == "fib":
            parent_keys = ["mill/", "image/"]
        else:
            parent_keys = [""]
        for pkey in parent_keys:
            self.controller.update_parameter(
                f"{pkey}beam/type",
                beam_type,
            )
            self.controller.update_parameter(
                f"{pkey}beam/voltage_kv",
                imaging_settings.beam.settings.voltage_kv,
            )
            self.controller.update_parameter(
                f"{pkey}beam/current_na",
                imaging_settings.beam.settings.current_na,
            )
            self.controller.update_parameter(
                f"{pkey}beam/voltage_tol_kv",
                imaging_settings.beam.settings.voltage_tol_kv,
            )
            self.controller.update_parameter(
                f"{pkey}beam/current_tol_na",
                imaging_settings.beam.settings.current_tol_na,
            )
            self.controller.update_parameter(
                f"{pkey}beam/hfw_mm",
                imaging_settings.beam.settings.hfw_mm,
            )
            self.controller.update_parameter(
                f"{pkey}beam/working_dist_mm",
                imaging_settings.beam.settings.working_dist_mm,
            )
            # if self.STEP != "fib":
            self.controller.update_parameter(
                f"{pkey}beam/dynamic_focus",
                imaging_settings.beam.settings.dynamic_focus,
            )
            self.controller.update_parameter(
                f"{pkey}beam/tilt_correction",
                imaging_settings.beam.settings.tilt_correction,
            )
            if "mill" not in pkey:
                self.controller.update_parameter(
                    f"{pkey}detector/type",
                    imaging_settings.detector.type.value,
                )
                self.controller.update_parameter(
                    f"{pkey}detector/mode",
                    imaging_settings.detector.mode.value,
                )
                self.controller.update_parameter(
                    f"{pkey}detector/brightness",
                    imaging_settings.detector.brightness,
                )
                self.controller.update_parameter(
                    f"{pkey}detector/contrast",
                    imaging_settings.detector.contrast,
                )
                self.controller.update_parameter(
                    f"{pkey}scan/rotation_deg",
                    imaging_settings.scan.rotation_deg,
                )
                self.controller.update_parameter(
                    f"{pkey}scan/dwell_time_us",
                    imaging_settings.scan.dwell_time_us,
                )
                resolution = imaging_settings.scan.__getattribute__("resolution")
                resolution_str = f"{resolution.width}x{resolution.height}"
                self.controller.update_parameter(
                    f"{pkey}scan/resolution",
                    resolution_str,
                )
                self.controller.update_parameter(
                    f"{pkey}bit_depth",
                    imaging_settings.bit_depth.value,
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

        interface = self._create_microscope_connection()
        if interface is None:
            return

        try:
            current_position = interface.get_stage_position()
        except Exception as e:
            messagebox.showerror(
                parent=self.toplevel,
                title="Error",
                message=f"Failed to get stage position: {e}",
            )
            return
        finally:
            interface.disconnect()
        # Put the current position in the step
        self.controller.update_parameter(
            "step_general/stage/initial_position/x_mm",
            current_position.x_mm,
        )
        self.controller.update_parameter(
            "step_general/stage/initial_position/y_mm",
            current_position.y_mm,
        )
        self.controller.update_parameter(
            "step_general/stage/initial_position/z_mm",
            current_position.z_mm,
        )
        self.controller.update_parameter(
            "step_general/stage/initial_position/t_deg",
            current_position.t_deg,
        )
        self.controller.update_parameter(
            "step_general/stage/initial_position/r_deg",
            current_position.r_deg,
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

        # Try and grab the laser settings, stopping if errors show up.
        interface = self._create_microscope_connection()
        try:
            laser_state = interface.get_laser_state()
        except Exception as e:
            messagebox.showerror(
                parent=self.toplevel,
                title="Error",
                message=f"Error getting laser state: {e}",
            )
            return
        finally:
            if interface:
                interface.disconnect()

        # Make any NoneType values into empty strings
        for key in laser_state.keys():
            if laser_state[key] is None:
                laser_state[key] = ""

        # Update pulse parameters
        self.controller.update_parameter(
            "pulse/wavelength_nm", laser_state["wavelength_nm"]
        )
        self.controller.update_parameter("pulse/divider", laser_state["pulse_divider"])
        self.controller.update_parameter(
            "pulse/energy_uj", laser_state["pulse_energy_uj"]
        )

        # Update pattern geometry based on type
        if laser_state["geometry_type"] == "line":
            keys = ["passes", "size_um", "pitch_um"]
            for key in keys:
                self.controller.update_parameter(
                    f"pattern/type/line/{key}", laser_state[key]
                )
            self.controller.update_parameter(
                "pattern/type/line/scan_type", laser_state["laser_scan_type"]
            )
        elif laser_state["geometry_type"] == "box":
            keys = [
                "passes",
                "size_x_um",
                "size_y_um",
                "pitch_x_um",
                "pitch_y_um",
            ]
            for key in keys:
                self.controller.update_parameter(
                    f"pattern/type/box/{key}", laser_state[key]
                )
            self.controller.update_parameter(
                "pattern/type/box/scan_type", laser_state["laser_scan_type"]
            )
            self.controller.update_parameter(
                "pattern/type/box/coordinate_ref",
                laser_state["coordinate_ref"].value,
            )

        # Update beam shift
        self.controller.update_parameter(
            "beam_shift/x_um", laser_state["beam_shift_um_x"]
        )
        self.controller.update_parameter(
            "beam_shift/y_um", laser_state["beam_shift_um_y"]
        )

        # Update special cases (such as naming is different between the two dictionaries)
        self.controller.update_parameter(
            "objective_position_mm", laser_state["objective_position_mm"]
        )
        self.controller.update_parameter(
            "pattern/mode", laser_state["laser_pattern_mode"]
        )
        self.controller.update_parameter(
            "pattern/rotation_deg", laser_state["laser_pattern_rotation_deg"]
        )
        self.controller.update_parameter(
            "pattern/pulses_per_pixel", laser_state["laser_pattern_pulses_per_pixel"]
        )
        self.controller.update_parameter(
            "pattern/pixel_dwell_ms", laser_state["laser_pattern_pixel_dwell_ms"]
        )

        # Update the editor
        self._update_editor()

    def take_fib_alignment_images(self):
        # Take image at current position with the current image settings
        # Make sure the step is an imaging step
        step_name = self.controller.get_current_step().name

        # Create the location for the template
        exp_dir = self.controller.pipeline.general.get_param("exp_dir")
        if exp_dir is None:
            messagebox.showerror(
                parent=self.toplevel,
                title="Error",
                message=f"Please set the experiment directory before collecting alignment images.",
            )
        exp_dir = Path(exp_dir)

        # Create the save paths
        template_dir = exp_dir.joinpath("templates")
        template_dir.mkdir(parents=True, exist_ok=True)
        full_save_path = template_dir.joinpath(f"{step_name}_template_full.tiff")
        patch_save_path = template_dir.joinpath(f"{step_name}_template_patch.tiff")

        # Try and grab the an image
        interface = self._create_microscope_connection()
        try:
            interface.collect_image(full_save_path)
        except Exception as e:
            messagebox.showerror(
                parent=self.toplevel,
                title="Error",
                message=f"Error getting laser state: {e}",
            )
            return
        finally:
            if interface:
                interface.disconnect()

        # Read the image that was created
        template_full = io.imread(full_save_path)

        # Open up a popup to have the user select the ROI for the patch
        selector = RoiSelector(template_full, master=self.toplevel)
        if selector.roi is None:
            messagebox.showerror(
                parent=self.toplevel,
                title="Error",
                message=f"An ROI was not selected.",
            )
        else:
            x0, x1 = selector.roi[0]
            y0, y1 = selector.roi[1]

        # Crop the full image and save it as the patch
        template_patch = template_full[y0:y1, x0:x1]
        io.imsave(patch_save_path, template_patch)


    # -------- Configuration File Operations -------- #

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

        # Clean up old UI bindings
        self.param_tracker.clear()

        # Create new pipeline via controller
        self.controller.create_new_pipeline(version=float(self.yml_version.get()))

        # Reset state
        self.YAML_PATH = None
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

        # Clean up old UI bindings
        self.param_tracker.clear()

        # Load pipeline via controller
        success, error = self.controller.load_pipeline(path)
        if not success:
            messagebox.showerror(
                parent=self.toplevel,
                title="Error reading yaml file",
                message=f"{error}",
            )
            return

        # Update state
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

        # Save via controller
        success, error = self.controller.save_pipeline(Path(self.YAML_PATH))
        if not success:
            messagebox.showerror(
                parent=self.toplevel,
                title="Error saving configuration",
                message=f"{error}",
            )
            return

        self.update_title()

    # -------- Pipeline Operations -------- #

    def create_pipeline_step(self, step_type):
        """Function called when a new pipeline step is created.
        Will focus the new step in the editor and update the pipeline."""
        if step_type == "general":
            # Special case for general - just select it
            self.controller.select_step(0)
        else:
            # Add step via controller
            step = self.controller.add_step(step_type)
            # Select the newly added step
            new_index = self.controller.get_step_count()
            self.controller.select_step(new_index)

        # Set the pick step button back to "Add Step"
        self.pick_step_b.var.set("Add Step")

    def delete_pipeline_step(self, index):
        """Delete a pipeline step from the pipeline."""
        # Can't delete general (index 0)
        if index == 0:
            return

        # Delete step via controller
        self.controller.remove_step(index)

    def move_pipeline_step(self, index, direction):
        """Move a pipeline step up or down in the pipeline."""
        # Can't move general (index 0)
        if index == 0:
            return

        # Move step via controller
        self.controller.move_step(index, direction)

    def duplicate_pipeline_step(self, index):
        """Duplicate a pipeline step."""
        # Can't duplicate general (index 0)
        if index == 0:
            return

        # Duplicate step via controller
        new_step = self.controller.duplicate_step(index)
        if new_step:
            # Select the newly duplicated step
            new_index = self.controller.get_step_count()
            self.controller.select_step(new_index)

    def select_pipeline_step(self, option):
        """Based on the selected step, update the editor with the new step."""
        index = int(option.split(".")[0])
        self.controller.select_step(index)

    def _update_pipeline_names(self):
        """Updates the text on the buttons in the pipeline window"""
        labels = ["0. general"]
        labels.extend(
            [
                f"{i + 1}. {s.name} ({s.step_type})"
                for i, s in enumerate(self.controller.pipeline.steps)
            ]
        )

        for i, label in enumerate(labels):
            row_i = i + 2
            try:
                button = self.pipeline.grid_slaves(row=row_i)[0]
                button.config(text=label)
            except IndexError:
                continue

    def _update_pipeline(self):
        """Update the pipeline based on the current configuration.
        This does not remove the widgets, it just updates the text and command of the buttons.
        """
        #  Create all possible options for the pipeline based on the config file
        options = ["0. general"]
        options.extend(
            [
                f"{i + 1}. {s.name} ({s.step_type})"
                for i, s in enumerate(self.controller.pipeline.steps)
            ]
        )
        # Get the maximum row of the current pipeline
        try:
            _, row = self.pipeline.grid_size()
        except tk.TclError:
            return

        # Create kwargs
        kw_current = {
            "font": ctk.FONT,
            "relief": "raised",
            "bg": self.theme.accent1,
            "fg": self.theme.accent1_fg,
            "activebackground": self.theme.accent1,
            "activeforeground": self.theme.accent1_fg,
        }
        kw_other = {
            "font": ctk.FONT,
            "relief": "groove",
            "bg": self.theme.bg,
            "fg": self.theme.fg,
            "activebackground": self.theme.accent1,
            "activeforeground": self.theme.accent1_fg,
        }

        # Loop over the options and update the pipeline
        for i, option in enumerate(options):
            row_i = i + 2

            # Create tooltip options and state
            right_click_map = {
                "Move up": lambda x=i: self.move_pipeline_step(x, -1),
                "Move down": lambda x=i: self.move_pipeline_step(x, 1),
                "Delete": lambda x=i: self.delete_pipeline_step(x),
                "Duplicate": lambda x=i: self.duplicate_pipeline_step(x),
            }
            if i == 1:
                right_click_map.pop("Move up")
            if i != 0 and i == len(options) - 1:
                right_click_map.pop("Move down")

            # If the row is the end of the pipeline, create a new button
            if row_i >= row:
                button = ctk.Button(
                    self.pipeline,
                    text=option,
                    padx=5,
                    bd=3,
                    command=lambda a=option: self.select_pipeline_step(a),
                    **kw_other,
                )
                button.grid(
                    row=row_i, column=0, columnspan=2, sticky="nsew", pady=1, padx=1
                )

            # If the row is not the end of the pipeline, update the button with the new option (in case it has changed)
            else:
                button = self.pipeline.grid_slaves(row_i)[0]
                button.config(
                    text=option,
                    command=lambda a=option: self.select_pipeline_step(a),
                    **kw_other,
                )

            # Change the state of the commands in the right click menu based on position
            if i != 0:
                if hasattr(button, "right_click_menu"):
                    button.right_click_menu.remove()
                button.right_click_menu = ctk.RightClickMenu(
                    button,
                    right_click_map.keys(),
                    bg=self.theme.bg,
                    fg=self.theme.fg,
                    abg=self.theme.accent1,
                    afg=self.theme.fg,
                )
                for j, key in enumerate(right_click_map.keys()):
                    button.right_click_menu.entryconfig(
                        index=j,
                        label=f" {key}",
                        command=right_click_map[key],
                        state="normal",
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

        # Highlight the current step
        self.pipeline.grid_slaves(self.STEP_INDEX + 2)[0].config(**kw_current)

    # -------- Editor Operations -------- #

    def _update_editor(self):
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
        # Create the tracked variable using ParameterTracker
        # The tracker automatically handles validation and updates to the controller
        var = self.param_tracker.create_variable(
            param_path=path,
            dtype=value.dtype,
            default=value.default,
        )

        # Create the widgets and place them on the grid
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
            var=var,
            **kwargs,
        )
        # Ensure checkbuttons are selected if the current value is True
        if type(value.default) == bool and var.get():
            widget.select()
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
        # Clear all tracked variables and their traces
        self.param_tracker.clear()

        # Remove the old widgets
        for i in range(2, row + 1):
            for widget in self.editor.grid_slaves(row=i - 1):
                widget.destroy()

    # -------- Validation Operations -------- #

    def validate_full(self):
        """Validate the full pipeline to make sure it is correct."""
        # Validate structure first
        success, message = self.controller.validate_structure()
        if not success:
            messagebox.showerror(
                parent=self.toplevel,
                title="Error validating pipeline structure",
                message=message,
            )
            return success

        # Validate full pipeline
        success, message = self.controller.validate_full()

        pre = "" if success else "un"
        messagebox.showinfo(
            parent=self.toplevel,
            title=f"Schema check completed {pre}successfully",
            message=message,
        )
        return success

    def validate_step(self):
        """Validate the current step to make sure it is correct."""
        # Get step index
        step_index = self.STEP_INDEX
        if step_index == 0:
            self.validate_general()
            return

        # Get microscope connection
        microscope = self._create_microscope_connection()
        if microscope is None:
            return False

        try:
            # Validate step
            success, message = self.controller.validate_step(
                step_index, microscope._microscope
            )

            pre = "" if success else "un"
            messagebox.showinfo(
                parent=self.toplevel,
                title=f"Schema check completed {pre}successfully",
                message=message,
            )
            return success
        finally:
            microscope.disconnect()

    def validate_general(self):
        """Validate the general step to make sure it is correct."""
        # Validate general step
        success, message = self.controller.validate_general()

        pre = "" if success else "un"
        messagebox.showinfo(
            parent=self.toplevel,
            title=f"Schema check completed {pre}successfully",
            message=message,
        )
        return success


if __name__ == "__main__":

    def open_configurator():
        root.withdraw()
        configurator = Configurator(root, theme=ctk.Theme("dark"))
        root.wait_window(configurator.toplevel)
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
