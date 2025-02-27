import sys
import shutil
import time
import os
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from pathlib import Path
from PIL import Image, ImageTk
import contextlib

# Threading for controlling experiment stops
import ctypes
import inspect
import threading

# from multiprocessing.pool import ThreadPool

# pytribeam imports
import pytribeam.GUI.CustomTkinterWidgets as ctk
from pytribeam.GUI.config_ui.App import Configurator
from pytribeam import workflow, stage, utilities, log, laser


class MainApplication(tk.Tk):
    def __init__(self, *args, **kwargs):
        # Create core
        tk.Tk.__init__(self, *args, **kwargs)
        self.title("TriBeam Runner")
        ico_path = Path(__file__).parent.parent.parent.parent.joinpath(
            "docs", "userguide", "src", "logos", "logo_color_alt.ico"
        )
        self.iconbitmap(ico_path)

        # Set the window size
        self.frame_w = int(1100)
        self.frame_h = int(620)
        self.geometry(f"{self.frame_w}x{self.frame_h}")
        self.resizable(False, False)

        # Set the grid structure
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=4)
        self.grid_rowconfigure(0, weight=4)
        self.grid_rowconfigure(1, weight=1)

        # Create the menubar
        self.menu = tk.Menu(self)
        self.menu.add_command(label="Help", command=self.open_help)
        self.menu.add_command(label="Clear terminal", command=self.clear_terminal)
        self.menu.add_command(label="Test connections", command=self.test_connections)
        self.menu.add_command(label="Export log", command=self.export_log)
        self.menu.add_command(label="Exit", command=self.quit)
        # Create file menu
        # file_menu = tk.Menu(self.menu, tearoff=False, font=ctk.MENU_FONT)
        # file_menu.add_command(
        #     label="Create new config", command=self.new_config, font=ctk.MENU_FONT
        # )
        # file_menu.add_command(
        #     label="Load config", command=self.load_config, font=ctk.MENU_FONT
        # )
        # file_menu.add_command(label="Exit", command=self.quit, font=ctk.MENU_FONT)
        # self.menu.add_cascade(label="Menu", menu=file_menu, font=ctk.MENU_FONT)
        self.config(menu=self.menu)

        # There are 3 main frames: controls (left vertical), display (right top), and status (right bottom)
        # Create the control frame
        self.control_frame = tk.Frame(self, bg=ctk.DEFAULT_COLOR, relief="ridge", bd=2)
        self.control_frame.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.control_frame.columnconfigure([0, 1, 2, 3], weight=1)
        img_path = Path(__file__).parent.parent.parent.parent.joinpath(
            "docs", "userguide", "src", "logos", "logo_color.png"
        )
        self.image = Image.open(img_path)

        # Print image size
        size = (self.image.size[0] // 3, self.image.size[1] // 3)
        self.image.thumbnail(size, Image.ANTIALIAS)
        self.image = ImageTk.PhotoImage(self.image)
        l = tk.Label(
            self.control_frame,
            font=ctk.HEADER_FONT,
            bg=ctk.DEFAULT_COLOR,
            image=self.image,
            width=size[0],
            height=size[1],
        )
        l.grid(row=0, column=0, columnspan=4)

        # Create experiment info labelframe
        sub_frame = tk.LabelFrame(
            self.control_frame,
            text="Experiment info",
            font=ctk.SUBHEADER_FONT,
            bg=ctk.DEFAULT_COLOR,
        )
        sub_frame.grid(row=1, column=0, columnspan=4, sticky="nsew", pady=5, padx=5)
        sub_frame.columnconfigure(0, weight=5)
        sub_frame.columnconfigure(1, weight=1)
        sub_frame.rowconfigure([0, 1, 2, 3, 4, 5], weight=1)
        self.total_slices_l = tk.Label(
            sub_frame,
            text="Total number of slices: -",
            font=ctk.FONT,
            bg=ctk.DEFAULT_COLOR,
            anchor="w",
        )
        self.total_slices_l.grid(row=0, column=0, sticky="nsew", pady=2, padx=2)
        self.total_steps_l = tk.Label(
            sub_frame,
            text="Number of steps per slice: -",
            font=ctk.FONT,
            bg=ctk.DEFAULT_COLOR,
            anchor="w",
        )
        self.total_steps_l.grid(row=1, column=0, sticky="nsew", pady=2, padx=2)
        self.slice_thickness_l = tk.Label(
            sub_frame,
            text="Slice thickness: -",
            font=ctk.FONT,
            bg=ctk.DEFAULT_COLOR,
            anchor="w",
        )
        self.slice_thickness_l.grid(row=2, column=0, sticky="nsew", pady=2, padx=2)
        self.config_file_path = tk.Label(
            sub_frame,
            text="No configuration file loaded",
            font=ctk.FONT_ITALIC,
            bg=ctk.DEFAULT_COLOR,
            anchor="w",
        )
        self.config_file_path.grid(
            row=3, column=0, columnspan=2, sticky="nsew", pady=2, padx=2
        )
        self.exp_dir_l = tk.Label(
            sub_frame,
            text="Exp dir: -",
            font=ctk.FONT_ITALIC,
            bg=ctk.DEFAULT_COLOR,
            anchor="w",
        )
        self.exp_dir_l.grid(
            row=4, column=0, columnspan=2, sticky="nsew", pady=2, padx=2
        )
        self.valid_status = tk.Label(
            sub_frame,
            text="...",
            font=ctk.FONT_ITALIC,
            bg=ctk.DEFAULT_COLOR,
            anchor="w",
        )
        self.valid_status.grid(
            row=5, column=0, columnspan=2, sticky="nsew", pady=2, padx=2
        )
        create_new = tk.Button(
            sub_frame, text="Create", font=ctk.FONT, command=self.new_config
        )
        create_new.grid(row=0, column=1, sticky="nsew", pady=2, padx=2)
        load_config = tk.Button(
            sub_frame, text="Load", font=ctk.FONT, command=self.load_config
        )
        load_config.grid(row=1, column=1, sticky="nsew", pady=2, padx=2)
        edit_config = tk.Button(
            sub_frame, text="Edit", font=ctk.FONT, command=self.edit_config
        )
        edit_config.grid(row=2, column=1, sticky="nsew", pady=2, padx=2)
        validate = tk.Button(
            sub_frame, text="Validate", font=ctk.FONT, command=self.validate_config
        )
        validate.grid(row=5, column=1, columnspan=2, sticky="nsew", pady=2, padx=2)

        # Put in the configuration buttons
        l = tk.Label(
            self.control_frame,
            text="Starting slice",
            font=ctk.FONT,
            bg=ctk.DEFAULT_COLOR,
            anchor="e",
        )
        l.grid(row=2, column=0, sticky="nsew", pady=5, padx=5)
        self.starting_slice_var = tk.IntVar()
        self.starting_slice = tk.Spinbox(
            self.control_frame,
            font=ctk.FONT,
            width=4,
            from_=0,
            to=10,
            textvariable=self.starting_slice_var,
            state="disabled",
        )
        self.starting_slice.grid(row=2, column=1, sticky="nsew", pady=5, padx=5)
        l = tk.Label(
            self.control_frame,
            text="Starting step",
            font=ctk.FONT,
            bg=ctk.DEFAULT_COLOR,
            anchor="e",
        )
        l.grid(row=2, column=2, sticky="nsew", pady=5, padx=5)
        self.starting_step_var = tk.StringVar()
        self.starting_step = ctk.MenuButton(
            self.control_frame,
            font=ctk.FONT,
            options=["-"],
            var=self.starting_step_var,
            width=12,
            state="disabled",
        )
        self.starting_step.grid(row=2, column=3, sticky="nsew", pady=5, padx=5)
        self.starting_step_var.set("-")

        # Put in the control buttons
        self.start_exp_b = tk.Button(
            self.control_frame,
            text="Start experiment",
            font=ctk.FONT,
            command=self.start_experiment,
        )
        self.start_exp_b.grid(
            row=3, column=0, columnspan=4, sticky="nsew", pady=3, padx=5
        )
        self.stop_step_b = tk.Button(
            self.control_frame,
            text="Stop after current step",
            font=ctk.FONT,
            command=self.stop_step,
        )
        self.stop_step_b.grid(
            row=4, column=0, columnspan=4, sticky="nsew", pady=3, padx=5
        )
        self.stop_slice_b = tk.Button(
            self.control_frame,
            text="Stop after current slice",
            font=ctk.FONT,
            command=self.stop_slice,
        )
        self.stop_slice_b.grid(
            row=5, column=0, columnspan=4, sticky="nsew", pady=3, padx=5
        )
        self.stop_now_b = tk.Button(
            self.control_frame, text="Hard stop", font=ctk.FONT, command=self.stop_hard
        )
        sep = tk.Frame(
            self.control_frame, bg=ctk.DEFAULT_COLOR, height=5, relief="flat"
        )
        sep.grid(row=6, column=0, columnspan=4, sticky="nsew", pady=10)
        self.stop_now_b.grid(
            row=7, column=0, columnspan=4, sticky="nsew", pady=3, padx=5
        )

        # Create the display frame
        # self.display_frame = ctk.ScrollableFrame(self, vscroll=True, hscroll=False, autoscroll=True, bg=ctk.DEFAULT_COLOR)
        self.display_frame = ctk.Frame3d(self, bg=ctk.DEFAULT_COLOR)
        self.display_frame.grid(row=0, column=1, sticky="nsew")
        self.display_frame.columnconfigure(0, weight=1)
        self.display_frame.rowconfigure(0, weight=1)
        # Put a listbox in the display frame that will act as a terminal for the program
        self.terminal = ctk.ScrolledText(
            self.display_frame,
            hscroll=False,
            bg=ctk.TERMINAL_COLOR,
            fg=ctk.ACCENT_COLOR1,
            autoscroll=True,
            font=ctk.FONT,
            wrap="word",
            state="disabled",
        )
        self.terminal.grid(row=0, column=0, sticky="nsew")

        # Create the status frame
        self.status_frame = tk.Frame(self, bg=ctk.DEFAULT_COLOR, relief="ridge", bd=2)
        self.status_frame.grid(row=1, column=1, sticky="nsew")
        self.status_frame.columnconfigure([0, 1, 2, 3, 4, 5], weight=1)
        self.status_frame.rowconfigure([0, 1], weight=1)
        # Current step
        current_step_label = tk.Label(
            self.status_frame,
            text="Current step",
            font=ctk.FONT_ITALIC,
            bg=ctk.DEFAULT_COLOR,
            anchor="e",
        )
        current_step_label.grid(row=0, column=0, sticky="nsew", pady=5, padx=5)
        self.current_step = tk.StringVar()
        self.current_step.set("-")
        current_step_label2 = tk.Label(
            self.status_frame,
            textvariable=self.current_step,
            font=ctk.FONT_BOLD,
            bg=ctk.DEFAULT_COLOR,
            fg=ctk.ACCENT_COLOR2,
            anchor="w",
        )
        current_step_label2.grid(row=0, column=1, sticky="nsew", pady=5, padx=5)
        # Current slice
        current_slice_label = tk.Label(
            self.status_frame,
            text="Current slice",
            font=ctk.FONT_ITALIC,
            bg=ctk.DEFAULT_COLOR,
            anchor="e",
        )
        current_slice_label.grid(row=0, column=2, sticky="nsew", pady=5, padx=5)
        self.current_slice = tk.StringVar()
        self.current_slice.set("-")
        current_slice_label2 = tk.Label(
            self.status_frame,
            textvariable=self.current_slice,
            font=ctk.FONT_BOLD,
            bg=ctk.DEFAULT_COLOR,
            fg=ctk.ACCENT_COLOR2,
            anchor="w",
        )
        current_slice_label2.grid(row=0, column=3, sticky="nsew", pady=5, padx=5)
        # Average slice time
        slice_time_label = tk.Label(
            self.status_frame,
            text="Average slice time",
            font=ctk.FONT_ITALIC,
            bg=ctk.DEFAULT_COLOR,
            anchor="e",
        )
        slice_time_label.grid(row=0, column=4, sticky="nsew", pady=5, padx=5)
        self.slice_time = tk.StringVar()
        self.slice_time.set("-")
        slice_time_label2 = tk.Label(
            self.status_frame,
            textvariable=self.slice_time,
            font=ctk.FONT_BOLD,
            bg=ctk.DEFAULT_COLOR,
            fg=ctk.ACCENT_COLOR2,
            anchor="w",
        )
        slice_time_label2.grid(row=0, column=5, sticky="nsew", pady=5, padx=5)
        # Progress bar
        self.progress = ctk.Progressbar(
            self.status_frame, bg=ctk.DEFAULT_COLOR, fg=ctk.ACCENT_COLOR1
        )
        self.progress.grid(row=1, column=0, columnspan=6, sticky="nsew", pady=5, padx=5)

        # Put on tooltips
        ctk.tooltip(create_new, "Create a new configuration file")
        ctk.tooltip(load_config, "Load an existing configuration file")
        ctk.tooltip(edit_config, "Edit the current configuration file")
        ctk.tooltip(self.starting_slice, "Slice number to start the experiment at.")
        ctk.tooltip(self.starting_step, "Step number to start the experiment at.")
        ctk.tooltip(
            self.start_exp_b,
            "Start the experiment with the current configuration at the selected slice and step.",
        )
        ctk.tooltip(
            self.stop_step_b,
            "Stop the experiment after the current step is complete. (Ctrl+Shift+X)",
        )
        ctk.tooltip(
            self.stop_slice_b,
            "Stop the experiment after the current slice is complete. (Ctrl+X)",
        )
        ctk.tooltip(self.stop_now_b, "Stop the experiment immediately. (Ctrl+C)")

        # Create variables
        self.config_path = None
        self.stop_after_slice = tk.BooleanVar(False)
        self.stop_after_step = tk.BooleanVar(False)
        self.stop_now = tk.BooleanVar(False)

        # Map stdout through decorator so that we get the stdout in the GUI and CLI
        self.original_out = sys.stdout
        self.original_err = sys.stderr
        self.terminal_log_path = os.path.join(os.getenv('LOCALAPPDATA'), 'pytribeam', time.strftime("%Y%m%d-%H%M%S") + '_log.txt')
        sys.stdout = TextRedirector(self.terminal, tag="stdout", log_path=self.terminal_log_path)
        sys.stderr = TextRedirector(self.terminal, tag="stderr", log_path=self.terminal_log_path)
        print("---")
        print("Welcome to TriBeam Layered Acquisition!")
        print("Please create a new configuration file or load an existing one.")
        print("---")

        # Bind the close button to the close function
        self.protocol("WM_DELETE_WINDOW", self.quit)
        self.thread_obj = None

        # Bind Ctrl+Shift+X to stop after step and Ctrl+X to stop after slice
        self.bind("<Control-X>", lambda e: self.stop_slice())
        self.bind("<Control-Shift-X>", lambda e: self.stop_step())

    def test_connections(self):
        """Test the connections to the EDS/EBSD and the laser."""
        with WaitCursor(self):
            out_dict = {"result": None}
            self.thread_obj = ThreadWithExc(
                target=wrapper_for_output, args=(laser._device_connections, out_dict)
            )
            self.thread_obj.start()
            while self.thread_obj.is_alive():
                try:
                    self.update()
                except tk.TclError:
                    return
        status = out_dict["result"]
        messagebox.showinfo("Connection status", str(status))

    def clear_terminal(self):
        self.terminal.config(state=tk.NORMAL)
        self.terminal.delete("1.0", tk.END)
        self.terminal.config(state=tk.DISABLED)
        print("---")
        print("Welcome to TriBeam Layered Acquisition!")
        print("Please create a new configuration file or load an existing one.")
        print("---")

    def export_log(self):
        """Export the log file to a user-selected location."""
        if not self.terminal_log_path:
            messagebox.showerror("Error", "No log file to export.")
            return
        save_path = Path(
            filedialog.asksaveasfilename(
                title="Save log file",
                filetypes=[("Text files", "*.txt")],
                initialdir=os.getcwd(),
            )
        )
        if not save_path:
            return
        shutil.copy(self.terminal_log_path, save_path)
        messagebox.showinfo("Success", f"Log file saved to {save_path}")

    def new_config(self):
        print("Creating new configuration file")
        self.edit_config(new=True)

    def load_config(self):
        self.config_path = Path(
            filedialog.askopenfilename(
                title="Select a configuration file",
                filetypes=[("YAML files", ("*.yaml", "*.yml"))],
                initialdir=os.getcwd(),
            )
        )
        if not self.config_path.is_file():
            print("No file selected.")
            return
        print(f"Imported configuration file from: {self.config_path}")
        self.valid_status.config(text="Configuration file is unvalidated", fg=ctk.RED)
        self._update_experiment_info()

    def edit_config(self, new=False):
        if new:
            app = Configurator(self)
        else:
            app = Configurator(self, self.config_path)
        self.wait_window(app.toplevel)
        if app.clean_exit:
            self.config_path = Path(app.YAML_PATH)
            print(f"Imported configuration file from: {self.config_path}")
            self.valid_status.config(text="Configuration file is valid", fg=ctk.GREEN)
            self._update_experiment_info()

    def validate_config(self, return_settings=False):
        if self.config_path is None:
            messagebox.showerror("Error", "No configuration file loaded.")
            return
        try:
            with WaitCursor(self):
                out_dict = {"result": None, "error": False}
                self.thread_obj = ThreadWithExc(
                    target=wrapper_for_output,
                    args=(workflow.pre_flight_check, out_dict, self.config_path),
                )
                self.thread_obj.start()
                while self.thread_obj.is_alive():
                    try:
                        self.update()
                    except tk.TclError:
                        return
                    except Exception as e:
                        break
                if out_dict["error"]:
                    raise Exception(out_dict["error"])
            experiment_settings = out_dict["result"]
            self.valid_status.config(text="Configuration file is valid", fg=ctk.GREEN)
            if return_settings:
                return experiment_settings
            else:
                return
        except Exception as e:
            messagebox.showerror(
                "Invalid config file", f"The provided config file is invalid:\n{e}"
            )
            self.valid_status.config(text="Configuration file is invalid", fg=ctk.RED)
            return

    def _update_experiment_info(self):
        """Update the experiment information in the GUI from the current yaml file."""
        try:
            db = utilities.yml_to_dict(
                yml_path_file=self.config_path,
                version=1.0,
                required_keys=("general", "steps"),
            )
            num_steps = db["general"]["step_count"]
            max_slice_num = db["general"]["max_slice_num"]
            slice_thickness = db["general"]["slice_thickness_um"]
            exp_dir = db["general"]["exp_dir"]
            step_names = list(db["steps"].keys())
        except Exception as e:
            messagebox.showerror("Error", f"Error loading configuration file:\n{e}")
            return
        # Split the config file path along a directory separator and only show the last 40 characters
        str_config_path = str(self.config_path).split(os.sep)
        while len(str_config_path) > 1 and len("".join(str_config_path)) > 30:
            str_config_path.pop(0)
        # Same for the experiment directory but 30 characters
        str_exp_dir = str(Path(exp_dir)).split(os.sep)
        while len(str_exp_dir) > 1 and len("".join(str_exp_dir)) > 30:
            str_exp_dir.pop(0)
        self.config_file_path.config(
            text=f"Config: ...{os.sep}{os.sep.join(str_config_path)}"
        )
        self.exp_dir_l.config(text=f"Exp dir: ...{os.sep}{os.sep.join(str_exp_dir)}")
        self.total_slices_l.config(text=f"Total number of slices: {max_slice_num}")
        self.total_steps_l.config(text=f"Number of steps per slice: {num_steps}")
        self.slice_thickness_l.config(text=f"Slice thickness: {slice_thickness}")
        self.starting_slice_var.set(1)
        self.starting_slice.config(from_=1, to=max_slice_num, state="normal")
        self.starting_step_var.set(step_names[0])
        self.starting_step.set_options(step_names)
        self.starting_step.config(state="normal")

    def _update_slice_info(self, slice_number):
        """Update the slice information in the GUI."""
        self.current_slice.set(slice_number)
        self.starting_slice_var.set(slice_number)

    def _update_step_info(self, step_name):
        """Update the step information in the GUI."""
        self.current_step.set(step_name)
        self.starting_step_var.set(step_name)

    def run_in_thread(self, func, *args, **kwargs):
        out_dict = {"error": False}
        self.thread_obj = ThreadWithExc(
            target=func, args=(out_dict,) + args, kwargs=kwargs
        )
        self.thread_obj.start()
        while self.thread_obj.is_alive():
            try:
                self.update()
            except tk.TclError:
                return
            if self.stop_now.get() and self.thread_obj.is_alive():
                self.thread_obj.raise_exc(KeyboardInterrupt)
                break
        return out_dict

    def start_experiment(self):
        """
        Start the experiment.

        This function is the main function that starts the experiment. It will loop over the
        slices and steps, calling the step function for each step. The starting slice and
        step are taken from the entries in the GUI.

        Stopping the experiment is control by keystrokes and the control buttons in the GUI.
        The experiment can be stopped after the current step, after the current slice, or
        immediately (hard stop). A modified Thread, ThreadWithExc, is used to run the steps
        in a separate thread so that the main thread can update the GUI and check for stop.
        The modified thread can raise a KeyboardInterrupt exception in the step function to
        stop the experiment.
        """
        # Set the start exp button to be disabled and green
        self._update_exp_control_buttons(start="disabled")

        # Grab experiment info
        starting_slice = self.starting_slice_var.get()
        starting_step_name = self.starting_step_var.get()

        # Run preflight check
        experiment_settings = self.validate_config(return_settings=True)
        if experiment_settings is None:
            self._update_exp_control_buttons(start="normal")
            return
        else:
            # Process the experiment settings
            num_steps = experiment_settings.general_settings.step_count
            step_names = [i.name for i in experiment_settings.step_sequence]
            starting_step_number = step_names.index(starting_step_name)
            ending_slice = experiment_settings.general_settings.max_slice_number
            # Log the experiment settings
            log.experiment_settings(
                slice_number=starting_slice,
                step_number=starting_step_number,
                log_filepath=experiment_settings.general_settings.log_filepath,
                yml_path=self.config_path,
            )
            print("Preflight check successful")

        # Check if EBSD and EDS are enabled
        if not experiment_settings.enable_EBSD or not experiment_settings.enable_EDS:
            pick = -1
            if not experiment_settings.enable_EBSD:
                pick += 1
            if not experiment_settings.enable_EDS:
                pick += 2
            message_part1 = [
                "EBSD is not enabled",
                "EDS is not enabled",
                "EBSD and EDS are not enabled",
            ][pick]
            message_part2 = ", you will not have access to safety checking and these modalities during data collection. Please ensure these detectors are retracted before proceeding."
            messagebox.showwarning("Warning", message_part1 + message_part2)

        # Setup the progress bar
        start_point = starting_slice * num_steps + starting_step_number
        self.progress.set(int((start_point - 1) / (ending_slice * num_steps) * 100))
        self.current_step.set(step_names[starting_step_number])
        self.current_slice.set(starting_slice)

        # Setup timer
        slice_times = []

        # Run the experiment (loop over the slices and steps)
        # Three levels here: try to catch KeyboardInterrupt, for i in slices, for j in steps
        print(
            f'Starting experiment at slice {starting_slice} and step "{starting_step_name}", number {starting_step_number+1} of {len(step_names)}'
        )
        try:
            if self.stop_now.get():
                raise KeyboardInterrupt
            for i in range(starting_slice, ending_slice + 1):
                # Get the slice start time and update the slice info
                t0 = time.time()
                self._update_slice_info(i)

                for j in range(num_steps):
                    # Skip steps if we are starting in the middle of a slice
                    if i == starting_slice and j < starting_step_number:
                        continue

                    # Update the current step
                    self._update_step_info(step_names[j])

                    # Create a thread object to run the step_call function
                    args = (i, j + 1, experiment_settings)
                    out_dict = self.run_in_thread(step_call_wrapper, *args)
                    stop_step = self.stop_after_step.get()
                    stop_slice = self.stop_after_slice.get()
                    stop_now = self.stop_now.get()
                    if out_dict["error"]:
                        stop_now = True

                    # exit_status = {"error": False}
                    # self.thread_obj = ThreadWithExc(target=self.step_call_wrapper, args=(i, j + 1, experiment_settings, exit_status))
                    # self.thread_obj.start()

                    # Wait for the step to complete, updating the GUI in the meantime so that the user can stop the experiment
                    # while self.thread_obj.is_alive():
                    #     try:
                    #         self.update()
                    #     except tk.TclError:
                    #         return
                    #     stop_step = self.stop_after_step.get()
                    #     stop_slice = self.stop_after_slice.get()
                    #     stop_now = self.stop_now.get()
                    #     if stop_now and self.thread_obj.is_alive():
                    #         self.thread_obj.raise_exc(KeyboardInterrupt)
                    #         break
                    # if exit_status["error"]:
                    #     stop_now = True

                    # Update progress bar if we didn't hard stop
                    if not stop_now:
                        perc_done = int(
                            ((i - 1) * num_steps + (j + 1))
                            / (ending_slice * num_steps)
                            * 100
                        )
                        self.progress.set(perc_done)
                        try:
                            self.update_idletasks()
                        except tk.TclError:
                            return

                    # Break out if we are stopping this step or right now
                    if stop_step or stop_now:
                        break

                # Break out if we are stopping at all
                if stop_step or stop_slice or stop_now:
                    break
                else:
                    try:
                        self.update_idletasks()
                    except tk.TclError:
                        return
                    t1 = time.time()
                    slice_times.append(t1 - t0)
                    avg_time = sum(slice_times) / len(slice_times)
                    avg_time_divmod = divmod(avg_time, 60)
                    if avg_time_divmod[0] < 1:
                        self.slice_time.set(f"{avg_time_divmod[1]:.2f} sec")
                    else:
                        self.slice_time.set(
                            f"{avg_time_divmod[0]:.0f} min {avg_time_divmod[1]:.2f} sec"
                        )

        except KeyboardInterrupt:
            print(
                "-----> Experiment was stopped immediately by user (keyboard interrupt)"
            )
            if self.thread_obj is not None and self.thread_obj.is_alive():
                self.thread_obj.raise_exc(KeyboardInterrupt)
                stop_now = True

        # Handle the end of the experiment
        if stop_now or stop_step or (stop_slice and i != ending_slice):
            # The experiment did not finish
            print("-----> Experiment stopped <-----")
            if not stop_now and j + 1 == num_steps:
                self.starting_slice_var.set(i + 1)
                self.starting_step_var.set(step_names[0])
            elif not stop_now:
                self.starting_slice_var.set(i)
                self.starting_step_var.set(step_names[j + 1])
            else:
                pass
        elif i == ending_slice and j == num_steps - 1:
            # The experiment finished
            print("-----> Experiment complete <-----")
            self.starting_slice_var.set(1)
            self.starting_step_var.set(step_names[0])
        else:
            # The experiment ended for an unknown reason
            print("-----> Experiment stopped (unknown) <-----")
        # Reset the stop flags
        self.stop_after_slice.set(False)
        self.stop_after_step.set(False)
        self.stop_now.set(False)
        # Update the GUI
        self._update_exp_control_buttons()

    def _update_exp_control_buttons(
        self, start="normal", step="normal", slice="normal", hard="normal"
    ):
        """Update the experiment control buttons."""
        start_kwards = {
            "normal": {"state": "normal", "bg": ctk.DEFAULT_COLOR},
            "disabled": {
                "state": "disabled",
                "bg": ctk.GREEN,
                "disabledforeground": ctk.DEFAULT_COLOR,
            },
        }
        step_kwargs = {
            "normal": {"state": "normal", "bg": ctk.DEFAULT_COLOR},
            "disabled": {
                "state": "disabled",
                "bg": ctk.ACCENT_COLOR3,
                "disabledforeground": ctk.DEFAULT_COLOR,
            },
        }
        slice_kwargs = {
            "normal": {"state": "normal", "bg": ctk.DEFAULT_COLOR},
            "disabled": {
                "state": "disabled",
                "bg": ctk.ACCENT_COLOR3,
                "disabledforeground": ctk.DEFAULT_COLOR,
            },
        }
        hard_kwargs = {
            "normal": {"state": "normal", "bg": ctk.DEFAULT_COLOR},
            "disabled": {
                "state": "disabled",
                "bg": ctk.ACCENT_COLOR3,
                "disabledforeground": ctk.DEFAULT_COLOR,
            },
        }
        self.start_exp_b.config(**start_kwards[start])
        self.stop_step_b.config(**step_kwargs[step])
        self.stop_slice_b.config(**slice_kwargs[slice])
        self.stop_now_b.config(**hard_kwargs[hard])
        self.update_idletasks()

    def stop_step(self):
        """
        Stop the experiment after the current step is complete.
        This is an experiment control function that sets a flag to stop the experiment after the current step is complete.
        """
        print("-----> Stopping after current step")
        if self.thread_obj is None:
            return
        self.stop_after_step.set(True)
        self._update_exp_control_buttons(
            start="disabled", step="disabled", slice="disabled", hard="normal"
        )

    def stop_slice(self):
        """
        Stop the experiment after the current slice is complete.
        This is an experiment control function that sets a flag to stop the experiment after the current slice is complete.
        """
        print("-----> Stopping after current slice")
        if self.thread_obj is None:
            return
        self.stop_after_slice.set(True)
        self._update_exp_control_buttons(
            start="disabled", step="normal", slice="disabled", hard="normal"
        )

    def stop_hard(self):
        """
        Stop the experiment immediately.
        This is an experiment control function that sets a flag to stop the experiment immediately.
        """
        print("-----> Experiment was stopped immediately by user (button press)")
        if self.thread_obj is None:
            return
        self.stop_now.set(True)
        self._update_exp_control_buttons(
            start="disabled", step="disabled", slice="disabled", hard="disabled"
        )

    def open_help(self):
        """Open the user guide in a web browser."""
        import webbrowser

        path = Path(__file__).parent.parent.parent.parent.joinpath(
            "docs", "userguide", "book", "index.html"
        )
        print(path)
        webbrowser.open(f"file://{path}")

    def quit(self):
        """
        Quit the program.
        This function is called when the user closes the window or selects the exit option from the menu.
        """
        sys.stdout = self.original_out
        sys.stderr = self.original_err
        if self.thread_obj is not None and self.thread_obj.is_alive():
            self.thread_obj.raise_exc(KeyboardInterrupt)
        self.update()
        self.destroy()



@contextlib.contextmanager
def WaitCursor(root):
    root.config(cursor="wait")
    root.update()
    try:
        yield root
    finally:
        root.config(cursor="")


def step_call_wrapper(out_dict, slice_number, step_index, experiment_settings):
    """
    A wrapper function to call the step function in a thread while also being able to catch a KeyboardInterrupt.
    If the exception is raised, the thread is stopped and the experiment is halted.
    """
    try:
        workflow.perform_step(slice_number, step_index, experiment_settings)
    except KeyboardInterrupt:
        try:
            escape_call()  ### TODO: Test if this helps with stopping the microscope during a hard stop
            stage.stop(experiment_settings.microscope)
            print("-----> Stage stop unsuccessful")
        except SystemError:
            print("-----> Stage stop successful")
        out_dict["error"] = True
        return False
    except Exception as e:
        print(
            f"Unexpected error in step {step_index} of slice {slice_number}: {e.__class__} {e}"
        )
        try:
            stage.stop(experiment_settings.microscope)
            print("-----> Stage stop unsuccessful")
        except SystemError:
            print("-----> Stage stop successful")
        out_dict["error"] = True
        return False
    out_dict["error"] = False
    return True


def wrapper_for_output(func, out_dict, *args, **kwargs):
    try:
        out_dict["result"] = func(*args, **kwargs)
    except Exception as e:
        out_dict["error"] = e
    return out_dict


def escape_call():
    """Function that generates an escape key press."""
    # Taken from https://stackoverflow.com/a/13615802/21828280
    import time
    import ctypes
    from ctypes import wintypes
    import time
    user32 = ctypes.WinDLL('user32', use_last_error=True)

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP       = 0x0002
    KEYEVENTF_UNICODE     = 0x0004
    MAPVK_VK_TO_VSC = 0

    # C struct definitions
    wintypes.ULONG_PTR = wintypes.WPARAM

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = (("dx",          wintypes.LONG),
                    ("dy",          wintypes.LONG),
                    ("mouseData",   wintypes.DWORD),
                    ("dwFlags",     wintypes.DWORD),
                    ("time",        wintypes.DWORD),
                    ("dwExtraInfo", wintypes.ULONG_PTR))

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = (("wVk",         wintypes.WORD),
                    ("wScan",       wintypes.WORD),
                    ("dwFlags",     wintypes.DWORD),
                    ("time",        wintypes.DWORD),
                    ("dwExtraInfo", wintypes.ULONG_PTR))

        def __init__(self, *args, **kwds):
            super(KEYBDINPUT, self).__init__(*args, **kwds)
            # some programs use the scan code even if KEYEVENTF_SCANCODE
            # isn't set in dwFflags, so attempt to map the correct code.
            if not self.dwFlags & KEYEVENTF_UNICODE:
                self.wScan = user32.MapVirtualKeyExW(self.wVk,
                                                    MAPVK_VK_TO_VSC, 0)

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = (("uMsg",    wintypes.DWORD),
                    ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD))

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = (("ki", KEYBDINPUT),
                        ("mi", MOUSEINPUT),
                        ("hi", HARDWAREINPUT))
        _anonymous_ = ("_input",)
        _fields_ = (("type",   wintypes.DWORD),
                    ("_input", _INPUT))

    LPINPUT = ctypes.POINTER(INPUT)

    def _check_count(result, func, args):
        if result == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        return args

    user32.SendInput.errcheck = _check_count
    user32.SendInput.argtypes = (wintypes.UINT, # nInputs
                                LPINPUT,       # pInputs
                                ctypes.c_int)  # cbSize

    # Functions

    def PressKey(hexKeyCode):
        x = INPUT(type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(wVk=hexKeyCode))
        user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))

    def ReleaseKey(hexKeyCode):
        x = INPUT(type=INPUT_KEYBOARD,
                ki=KEYBDINPUT(wVk=hexKeyCode,
                                dwFlags=KEYEVENTF_KEYUP))
        user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))
    
    # print("Pressing ESC in")
    # for i in range(3, 0, -1):
    #     print(i)
    #     time.sleep(1)
    VK_ESC = 0x1B
    PressKey(VK_ESC)
    time.sleep(0.05)
    ReleaseKey(VK_ESC)


def _async_raise(tid, exctype):
    """Raises an exception in the threads with id tid"""
    if not inspect.isclass(exctype):
        raise TypeError("Only types can be raised (not instances)")
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(tid), ctypes.py_object(exctype)
    )
    if res == 0:
        raise ValueError("invalid thread id")
    elif res != 1:
        # "if it returns a number greater than one, you're in trouble,
        # and you should call it again with exc=NULL to revert the effect"
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), None)
        raise SystemError("PyThreadState_SetAsyncExc failed")


class ThreadWithExc(threading.Thread):
    """
    A thread class that supports raising an exception in the thread from another thread.
    """

    def _get_my_tid(self):
        """
        Function to determine this (self's) thread id

        CAREFUL: this function is executed in the context of the caller
        thread, to get the identity of the thread represented by this
        instance.
        """
        if not self.is_alive():  # Note: self.isAlive() on older version of Python
            raise threading.ThreadError("the thread is not active")

        # do we have it cached?
        if hasattr(self, "_thread_id"):
            return self._thread_id

        # no, look for it in the _active dict
        for tid, tobj in threading._active.items():
            if tobj is self:
                self._thread_id = tid
                return tid

        raise AssertionError("could not determine the thread's id")

    def raise_exc(self, exctype):
        """
        Raises the given exception type in the context of this thread.

        If the thread is busy in a system call (time.sleep(),
        socket.accept(), ...), the exception is simply ignored.

        If you are sure that your exception should terminate the thread,
        one way to ensure that it works is:

            t = ThreadWithExc( ... )
            ...
            t.raise_exc( SomeException )
            while t.isAlive():
                time.sleep( 0.1 )
                t.raise_exc( SomeException )

        If the exception is to be caught by the thread, you need a way to
        check that your thread has caught it.

        CAREFUL: this function is executed in the context of the
        caller thread, to raise an exception in the context of the
        thread represented by this instance.
        """
        _async_raise(self._get_my_tid(), exctype)


class TextRedirector(object):
    def __init__(self, widget, tag="stdout", log_path=None):
        self.widget = widget
        self.tag = tag
        if log_path is None:
            log_path = os.path.join(os.getenv('LOCALAPPDATA'), 'pytribeam', time.strftime("%Y%m%d-%H%M%S") + '_log.txt')
        else:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
        self.file = open(log_path, "w")
        self.file.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")

    def write(self, s):
        # See if the widget was scrolled to the bottom, if it is, we will autoscroll down past the new text
        autoscroll = self.widget.autoscroll
        if autoscroll:
            bottom = self.widget.yview()[1]
        self.widget.config(state=tk.NORMAL)
        self.widget.insert(tk.END, s, (self.tag,))
        self.widget.config(state=tk.DISABLED)

        # Autoscroll if the scrollbar is at the bottom
        if autoscroll and bottom == 1:
            self.widget.see(tk.END)
        
        # Write to the log file
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.file.write(f"{timestamp} > {s}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.file.close()

    def flush(self):
        pass


if __name__ == "__main__":
    app = MainApplication()
    app.mainloop()
