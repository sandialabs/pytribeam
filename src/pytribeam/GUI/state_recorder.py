import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import datetime

from pytribeam import utilities
from pytribeam import types as tbt
from pytribeam import factory
from pytribeam.GUI import CustomTkinterWidgets as ctk


def get_microscope_state(host: str, port: int) -> dict:
    microscope = tbt.Microscope()
    utilities.connect_microscope(
        microscope,
        quiet_output=True,
        connection_host="localhost",
        connection_port=None,
    )

    beam = factory.active_beam_with_settings(microscope)
    detector = factory.active_detector_settings(microscope)
    image_settings = factory.active_image_settings(microscope)
    image_device = factory.active_imaging_device(microscope)
    scan = factory.active_scan_settings(microscope)
    position = factory.active_stage_position_settings(microscope)

    beam = str(beam)
    detector = str(detector)
    image_settings = str(image_settings)
    image_device = str(image_device)
    scan = str(scan)
    position = str(position)

    return dict(beam=beam, detector=detector, image_settings=image_settings, image_device=image_device, scan=scan, position=position)


def ensure_file_exists():
    path = Path(file_path.get())
    if path == Path():
        raise RuntimeError("No file path provided.")
    if not path.suffix == ".yml" or not path.suffix == ".yaml":
        path = path.with_suffix(".yml")

    file_path.set(str(path))

    if not os.path.exists(path):
        db = dict(config_file_version=0.0, states={})
        utilities.dict_to_yml(db, path)


def save_state():
    """Record the state of the microscope, prompt the user for a description, and write out to yml"""

    # Ensure file exists
    ensure_file_exists()

    # Parse parameters
    path = Path(file_path.get())
    host = host_var.get()
    port = port_var.get().lower().replace("none", "")
    if port == "":
        port = None
    else:
        port = int(port)
    
    # Connect to the microscope and get the state
    try:
        microscope_state = get_microscope_state(host, port)
    except ConnectionError as e:
        messagebox.showerror("Error connecting to microscope", "Please check the host and port entries and retry.")
        return

    # Get the description and store in the state
    text = text_box.get("1.0", "end-1c")
    microscope_state["description"] = text

    # Read the current yml
    db = utilities.yml_to_dict(yml_path_file=path, version=0.0, required_keys=("config_file_version", "states"))

    # Use timestamp for key of current state in dictionary
    timestamp = datetime.datetime.now().strftime("%b %d, %Y %I:%M:%S %p")
    db["states"][timestamp] = microscope_state

    # Write out new yml
    utilities.dict_to_yml(db=db, file_path=path)


if __name__ == "__main__":
    # Prep
    theme = ctk.Theme("dark")
    entry_kw = dict(bg=theme.colors["bg_off"], fg=theme.colors["terminal_fg"], font=("Segoe UI", 11))
    label_kw = dict(bg=theme.bg, fg=theme.fg, font=("Segoe UI", 11))
    header_kw = dict(bg=theme.bg, fg=theme.fg, font=("Segoe UI", 15))
    button_kw = dict(bg=theme.colors["green"], fg=theme.colors["green_fg"], font=("Segoe UI", 15))

    # Build window
    master = tk.Tk()
    master.title("pyTriBeam state recorder")
    root = tk.Frame(master, bg=theme.bg)
    root.pack(fill="both")
    root.columnconfigure(0, weight=1)
    root.columnconfigure(1, weight=20)

    # Create var
    file_path = tk.StringVar()
    file_path.set(Path.home() / "pytribeam_state_record.yml")

    # Create widgets
    l1 = tk.Label(root, text="Microscope connection details (likely do not need to change)", **header_kw)
    l2 = tk.Label(root, text="Path to save the states to", **header_kw)
    l3 = tk.Label(root, text="Description of state and/or how you moved from the previous state to this state", **header_kw)
    host_l = tk.Label(root, text="Host:", **label_kw)
    port_l = tk.Label(root, text="Port:", **label_kw)
    host_var = tk.Entry(root, **entry_kw)
    port_var = tk.Entry(root, **entry_kw)
    pentry = ctk.PathEntry(root, var=file_path, directory=False, operation="save", **entry_kw)
    text_box = tk.Text(root, width=10, height=10, **entry_kw)
    f1 = tk.Frame(root, bg=theme.bg)
    f2 = tk.Frame(root, bg=theme.bg)
    save = tk.Button(root, text="Save current state", command=save_state, **button_kw)

    # Place everything
    l1.grid(row=0, column=0, columnspan=2, sticky="nsw", padx=6, pady=3)
    host_l.grid(row=1, column=0, sticky="nse", padx=6, pady=3)
    port_l.grid(row=2, column=0, sticky="nse", padx=6, pady=3)
    host_var.grid(row=1, column=1, sticky="nsw", padx=6, pady=3)
    port_var.grid(row=2, column=1, sticky="nsw", padx=6, pady=3)
    f1.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=20)
    l2.grid(row=4, column=0, columnspan=2, sticky="nsw")
    pentry.grid(row=5, column=0, columnspan=2, sticky="nsew", padx=6, pady=3)
    f2.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=20)
    l3.grid(row=7, column=0, columnspan=2, sticky="nsw", padx=6, pady=3)
    text_box.grid(row=8, column=0, columnspan=2, sticky="nsew", padx=6, pady=3)
    save.grid(row=9, column=0, columnspan=2, sticky="nsew", padx=6, pady=10)

    # Put text in text box
    host_var.insert(tk.END, "localhost")
    port_var.insert(tk.END, "None")
    text_box.insert(1.0, "Insert description...")

    # Run
    root.grab_set()
    root.update_idletasks()
    root.mainloop()
