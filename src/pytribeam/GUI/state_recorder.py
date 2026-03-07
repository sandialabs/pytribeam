import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import datetime
from typing import Any, Set, List

from pytribeam import utilities
from pytribeam import types as tbt
from pytribeam import factory
from pytribeam.GUI import CustomTkinterWidgets as ctk

import autoscript_sdb_microscope_client.structures as as_structs


def _is_public_name(name: str) -> bool:
    """Return ``True`` if *name* does not start with an underscore.

    Hidden attributes (``_private`` or ``__dunder__``) are filtered out.
    """
    return not name.startswith("_")


def _collect(
    obj: Any,
    prefix: str,
    visited: Set[int],
) -> List[str]:
    """Recursive helper for :func:`collect_attribute_paths`.

    Parameters
    ----------
    obj:
        The current object being inspected.
    prefix:
        Dot-separated prefix representing the path to *obj*.
    visited:
        Set of ``id`` values already seen to prevent infinite loops.
    """
    # Guard against circular references.
    obj_id = id(obj)
    if obj_id in visited:
        return []
    visited.add(obj_id)

    results: List[str] = []
    for name in dir(obj):
        if not _is_public_name(name):
            continue
        try:
            attr = getattr(obj, name)
        except Exception:
            # Some descriptors may raise; skip them.
            continue

        full_path = f"{prefix}.{name}" if prefix else name

        if callable(attr):
            continue
        elif isinstance(attr, str) or isinstance(attr, bool) or isinstance(attr, int) or isinstance(attr, float) or isinstance(attr, list) or isinstance(attr, tuple) or isinstance(attr, dict):
            results.append((full_path, attr))
        elif isinstance(attr, as_structs.StagePosition):
            results.extend([
                (full_path + ".coordinate_system", attr.coordinate_system),
                (full_path + ".x", attr.x),
                (full_path + ".y", attr.y),
                (full_path + ".z", attr.z),
                (full_path + ".t", attr.t),
                (full_path + ".r", attr.r),
            ])
        else:
            results.extend(_collect(attr, full_path, visited))

    return results


def collect_attribute_paths(obj: Any, name: str = None) -> List[str]:
    """Return a list of dot-separated attribute paths for *obj*.

    The function walks the public attribute tree of *obj* and records the path
    to every callable (function, method, built-in) it encounters. Sub-objects that
    are modules or classes are explored recursively. Private attributes (those
    beginning with an underscore) and non-callable values are omitted.

    Parameters
    ----------
    obj:
        The root Python object to introspect - typically a module.
    name:
        Optional explicit name for the root object. If omitted, ``obj``'s
        ``__name__`` attribute (when present) is used; otherwise an empty prefix
        is assumed.

    Returns
    -------
    List[str]
        A list of strings such as ``"pkg.f1"``, ``"pkg.submod.g2"``.
    """
    root_name = name or getattr(obj, "__name__", "")
    # If the root has no useful name, start with an empty prefix.
    prefix = root_name if root_name else ""
    return _collect(obj, prefix, set())


def get_microscope_state(host: str, port: int) -> dict:
    microscope = tbt.Microscope()
    utilities.connect_microscope(
        microscope,
        quiet_output=True,
        connection_host="localhost",
        connection_port=None,
    )

    state = {}

    for s in ["beams", "detector", "gas", "patterning", "specimen", "state", "vacuum", "imaging"]:
        state[s] = {k: i for (k, i) in collect_attribute_paths(getattr(microscope, s), "scope." + s)}
    
    for q in [1, 2, 3, 4]:
        microscope.imaging.set_active_view(q)
        device = str(tbt.Device(microscope.imaging.get_active_device()))
        state["imaging"][f"scope.imaging.quad{q}.active_device"] =  device

    return state


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
