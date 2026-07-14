import datetime
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Any, List, Optional, Set, Tuple

import autoscript_sdb_microscope_client.structures as as_structs

from pytribeam import types as tbt
from pytribeam import utilities
from pytribeam.GUI import CustomTkinterWidgets as ctk


def _is_public_name(name: str) -> bool:
    """Return ``True`` if *name* does not start with an underscore.

    Hidden attributes, such as ``_private`` or ``__dunder__``, are filtered out.
    """
    return not name.startswith("_")


def _collect(
    obj: Any,
    prefix: str,
    visited: Set[int],
) -> List[Tuple[str, Any]]:
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

    results: List[Tuple[str, Any]] = []

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

        elif (
            isinstance(attr, str)
            or isinstance(attr, bool)
            or isinstance(attr, int)
            or isinstance(attr, float)
            or isinstance(attr, list)
            or isinstance(attr, tuple)
            or isinstance(attr, dict)
        ):
            results.append((full_path, attr))

        elif isinstance(attr, as_structs.StagePosition):
            results.extend(
                [
                    (full_path + ".coordinate_system", attr.coordinate_system),
                    (full_path + ".x", attr.x),
                    (full_path + ".y", attr.y),
                    (full_path + ".z", attr.z),
                    (full_path + ".t", attr.t),
                    (full_path + ".r", attr.r),
                ]
            )

        else:
            results.extend(_collect(attr, full_path, visited))

    return results


def collect_attribute_paths(obj: Any, name: str = None) -> List[Tuple[str, Any]]:
    """Return a list of dot-separated attribute paths and values for *obj*.

    The function walks the public attribute tree of *obj* and records paths
    to public non-callable values.

    Parameters
    ----------
    obj:
        The root Python object to introspect.
    name:
        Optional explicit name for the root object.

    Returns
    -------
    List[Tuple[str, Any]]
        A list of ``(path, value)`` tuples.
    """
    root_name = name or getattr(obj, "__name__", "")
    prefix = root_name if root_name else ""
    return _collect(obj, prefix, set())


def get_microscope_state(host: str, port: Optional[int]) -> dict:
    """Connect to the microscope and collect its current state."""
    microscope = tbt.Microscope()

    utilities.connect_microscope(
        microscope,
        quiet_output=True,
        connection_host=host,
        connection_port=port,
    )

    state = {}

    for s in [
        "beams",
        "detector",
        "gas",
        "patterning",
        "specimen",
        "state",
        "vacuum",
        "imaging",
    ]:
        state[s] = {
            k: i
            for (k, i) in collect_attribute_paths(getattr(microscope, s), "scope." + s)
        }

    for q in [1, 2, 3, 4]:
        microscope.imaging.set_active_view(q)
        device = str(tbt.Device(microscope.imaging.get_active_device()))
        state["imaging"][f"scope.imaging.quad{q}.active_device"] = device

    return state


def set_status(message: str):
    """Update the GUI status line.

    This should only be called from the Tkinter main thread.
    """
    try:
        status_var.set(message)
    except NameError:
        pass


def ensure_file_exists():
    """Make sure the YAML state file exists."""
    path = Path(file_path.get())

    if path == Path() or str(path).strip() == "":
        raise RuntimeError("No file path provided.")

    # Keep .yml or .yaml. Otherwise add .yml.
    if path.suffix.lower() not in [".yml", ".yaml"]:
        path = path.with_suffix(".yml")

    file_path.set(str(path))

    if not os.path.exists(path):
        db = dict(config_file_version=0.0, states={})
        utilities.dict_to_yml(db, path)


def parse_port() -> Optional[int]:
    """Parse the microscope port from the GUI."""
    port = port_var.get().lower().replace("none", "").strip()

    if port == "":
        return None

    return int(port)


def parse_interval_seconds() -> float:
    """Parse the recording interval from the GUI."""
    value = interval_var.get().strip()

    try:
        interval_seconds = float(value)
    except ValueError:
        raise ValueError("Recording interval must be a number of seconds.")

    if interval_seconds <= 0:
        raise ValueError("Recording interval must be greater than zero seconds.")

    return interval_seconds


def record_state_worker(
    path: Path,
    host: str,
    port: Optional[int],
    description: str,
):
    """Background-thread worker for recording microscope state.

    Important:
    This function must not directly touch Tkinter widgets, Tkinter variables,
    or messageboxes. It communicates results back to the GUI thread through
    ``result_queue``.
    """
    try:
        microscope_state = get_microscope_state(host, port)
        microscope_state["description"] = description

        db = utilities.yml_to_dict(
            yml_path_file=path,
            version=0.0,
            required_keys=("config_file_version", "states"),
        )

        # Include milliseconds to avoid overwriting if states are saved quickly.
        now = datetime.datetime.now()
        timestamp = now.strftime("%b %d, %Y %I:%M:%S.%f")[:-3] + now.strftime(" %p")

        db["states"][timestamp] = microscope_state

        utilities.dict_to_yml(db=db, file_path=path)

        result_queue.put(
            {
                "success": True,
                "timestamp": timestamp,
                "error": None,
            }
        )

    except Exception as e:
        result_queue.put(
            {
                "success": False,
                "timestamp": None,
                "error": e,
            }
        )


def record_state_once_threaded() -> bool:
    """Start one microscope-state recording in a background thread.

    This duplicates the functionality of the original "Save current state"
    button, but does the slow microscope read/YAML write in the background.

    Returns
    -------
    bool
        True if a background worker was started.
        False if validation failed or another save is already running.
    """
    global save_in_progress

    if save_in_progress:
        set_status(
            "Previous state recording is still in progress; skipping this interval."
        )
        return False

    try:
        # These GUI reads must happen on the Tkinter main thread.
        ensure_file_exists()

        path = Path(file_path.get())
        host = host_var.get().strip()
        port = parse_port()

        # Consume only a previously queued note.
        # Do not touch the draft note box here, because the user may be typing.
        description = pop_pending_note()

    except Exception as e:
        messagebox.showerror("Error preparing microscope state recording", str(e))
        set_status("Error preparing state recording.")
        return False

    save_in_progress = True
    set_status("Recording microscope state...")

    worker = threading.Thread(
        target=record_state_worker,
        args=(path, host, port, description),
        daemon=True,
    )
    worker.start()

    return True


def check_recording_result_queue():
    """Check for completed background recordings.

    This function runs on the Tkinter main thread, so it is allowed to update
    widgets, variables, and messageboxes.
    """
    global save_in_progress
    global final_save_after_current

    try:
        while True:
            result = result_queue.get_nowait()

            save_in_progress = False

            if result["success"]:
                timestamp = result["timestamp"]
                set_status(f"Last saved: {timestamp}")

                if final_save_after_current:
                    final_save_after_current = False
                    set_status("Saving final state with queued note...")
                    record_state_once_threaded()

            else:
                error = result["error"]
                set_status("Error recording microscope state.")

                messagebox.showerror(
                    "Error recording microscope state",
                    str(error),
                )

                # If periodic recording is active, stop after an error.
                if recording:
                    stop_recording()

    except queue.Empty:
        pass

    # Keep polling for future worker results.
    root.after(100, check_recording_result_queue)


NOTE_PLACEHOLDER = "Optional note for the next saved state..."


def show_note_placeholder():
    """Show ghost text in the note box if it is empty."""
    global note_placeholder_active

    current_text = text_box.get("1.0", "end-1c")

    if current_text.strip() == "":
        note_placeholder_active = True
        text_box.config(fg=theme.colors.get("gray", "#888888"))
        text_box.delete("1.0", tk.END)
        text_box.insert("1.0", NOTE_PLACEHOLDER)


def hide_note_placeholder(event=None):
    """Remove ghost text when the user enters the note box."""
    global note_placeholder_active

    if note_placeholder_active:
        text_box.delete("1.0", tk.END)
        text_box.config(fg=theme.colors["terminal_fg"])
        note_placeholder_active = False


def restore_note_placeholder_if_empty(event=None):
    """Restore ghost text if the user leaves the note box empty."""
    show_note_placeholder()


def clear_note_placeholder_for_typing(event=None):
    """Clear ghost text when the user starts typing.

    This handles the case where an automatic save restores the placeholder
    while the note box already has keyboard focus.
    """
    global note_placeholder_active

    if note_placeholder_active:
        text_box.delete("1.0", tk.END)
        text_box.config(fg=theme.colors["terminal_fg"])
        note_placeholder_active = False


def queue_note_for_next_save():
    """Queue the current draft note for the next saved state."""
    queue_current_draft_note(silent=False)


def pop_pending_note() -> str:
    """Return and clear the queued note.

    This intentionally does not touch the draft text box.
    """
    global pending_note

    note = pending_note
    pending_note = ""

    update_queue_note_button()

    return note


def queue_current_draft_note(silent: bool = False) -> bool:
    """Move current draft text into the pending-note slot.

    Returns True if a note was queued, False otherwise.
    """
    global pending_note
    global note_placeholder_active

    if note_placeholder_active:
        if not silent:
            set_status("No draft note to queue.")
        return False

    note = text_box.get("1.0", "end-1c").strip()

    if not note:
        if not silent:
            set_status("No draft note to queue.")
        return False

    if pending_note:
        pending_note = pending_note + "\n\n" + note
    else:
        pending_note = note

    text_box.delete("1.0", tk.END)
    text_box.config(fg=theme.colors["terminal_fg"])
    note_placeholder_active = False

    if text_box.focus_get() != text_box:
        show_note_placeholder()

    update_queue_note_button()

    if not silent:
        set_status("Note queued for next saved state.")

    return True


def update_queue_note_button():
    """Update the queue-note button text/color based on pending-note state."""
    try:
        if pending_note:
            queue_note_button.config(
                text="Queued notes pending — add another",
                **note_button_pending_kw,
            )
        else:
            queue_note_button.config(
                text="Queue note for next saved state",
                **note_button_kw,
            )
    except NameError:
        # Button/style variables may not exist yet during startup.
        pass


def save_state():
    """Manual one-shot save."""
    record_state_once_threaded()


def schedule_next_recording():
    """Schedule the next periodic recording using the current interval setting."""
    global recording_after_id

    try:
        interval_seconds = parse_interval_seconds()
    except Exception as e:
        messagebox.showerror("Invalid recording interval", str(e))
        stop_recording()
        return

    interval_ms = int(interval_seconds * 1000)
    recording_after_id = root.after(interval_ms, recording_tick)


def recording_tick():
    """Called periodically by Tkinter after recording has started."""
    if not recording:
        return

    # Start a background recording if one is not already running.
    # If one is still running, this will skip the current interval.
    record_state_once_threaded()

    # Schedule the next tick. This keeps the interval regular even if one
    # recording occasionally takes too long and gets skipped.
    if recording:
        schedule_next_recording()


def start_recording():
    """Start recording the microscope state every N seconds."""
    global recording

    if recording:
        return

    try:
        parse_interval_seconds()
    except Exception as e:
        messagebox.showerror("Invalid recording interval", str(e))
        return

    recording = True
    start_button.config(state=tk.DISABLED)
    stop_button.config(state=tk.NORMAL)

    set_status("Recording started.")

    # Record immediately, then schedule the next recording.
    record_state_once_threaded()
    schedule_next_recording()


def stop_recording(save_final: bool = False, queue_draft: bool = False):
    """Stop periodic recording.

    If queue_draft is True, any current draft text is queued first.

    If save_final is True and no save is currently in progress, record one
    final microscope state after cancelling future automatic polls.

    If a save is already in progress and a note was queued by this stop action,
    request one final save after the current save finishes so the queued note
    is captured.
    """
    global recording
    global recording_after_id
    global final_save_after_current

    recording = False

    if recording_after_id is not None:
        try:
            root.after_cancel(recording_after_id)
        except tk.TclError:
            pass

        recording_after_id = None

    note_queued_by_stop = False

    if queue_draft:
        note_queued_by_stop = queue_current_draft_note(silent=True)

    start_button.config(state=tk.NORMAL)
    stop_button.config(state=tk.DISABLED)

    if save_in_progress:
        if save_final and pending_note:
            final_save_after_current = True
            set_status(
                "Recording stopped. Current save will finish, then final state "
                "will be saved with queued note."
            )
        elif save_final:
            set_status(
                "Recording stopped. Current in-progress save will serve as final state."
            )
        else:
            set_status("Recording stopped. Current in-progress save will finish.")

    else:
        if save_final:
            if note_queued_by_stop:
                set_status("Recording stopped. Saving final state with note...")
            else:
                set_status("Recording stopped. Saving final state...")

            record_state_once_threaded()
        else:
            set_status("Recording stopped.")


def on_close():
    """Handle the user closing the GUI window."""
    global recording

    recording = False

    if recording_after_id is not None:
        try:
            root.after_cancel(recording_after_id)
        except tk.TclError:
            pass

    master.destroy()


if __name__ == "__main__":
    # -------------------------------------------------------------------------
    # GUI setup
    # -------------------------------------------------------------------------
    theme = ctk.Theme("dark")

    entry_kw = dict(
        bg=theme.colors["bg_off"],
        fg=theme.colors["terminal_fg"],
        font=("Segoe UI", 11),
    )

    label_kw = dict(
        bg=theme.bg,
        fg=theme.fg,
        font=("Segoe UI", 11),
    )

    header_kw = dict(
        bg=theme.bg,
        fg=theme.fg,
        font=("Segoe UI", 15),
    )

    button_kw = dict(
        bg=theme.colors["green"],
        fg=theme.colors["green_fg"],
        font=("Segoe UI", 15),
    )
    note_button_kw = dict(
        bg="#6f8f72",  # muted gray-green
        fg=theme.colors["green_fg"],
        activebackground="#8daa8f",
        activeforeground=theme.colors["green_fg"],
        font=("Segoe UI", 15),
    )

    note_button_pending_kw = dict(
        bg="#9fbc9f",  # lighter gray-green when a note is pending
        fg=theme.colors["green_fg"],
        activebackground="#b3cdb3",
        activeforeground=theme.colors["green_fg"],
        font=("Segoe UI", 15),
    )

    stop_button_kw = dict(
        bg=theme.colors["red"] if "red" in theme.colors else theme.colors["bg_off"],
        fg=theme.colors["red_fg"] if "red_fg" in theme.colors else theme.fg,
        font=("Segoe UI", 15),
    )

    # -------------------------------------------------------------------------
    # Recording state globals
    # -------------------------------------------------------------------------
    recording = False
    recording_after_id = None
    save_in_progress = False
    result_queue = queue.Queue()

    note_placeholder_active = False
    pending_note = ""
    final_save_after_current = False

    # -------------------------------------------------------------------------
    # Build window
    # -------------------------------------------------------------------------
    master = tk.Tk()
    master.title("pyTriBeam state recorder")
    master.protocol("WM_DELETE_WINDOW", on_close)

    root = tk.Frame(master, bg=theme.bg)
    root.pack(fill="both")

    root.columnconfigure(0, weight=1)
    root.columnconfigure(1, weight=20)

    # -------------------------------------------------------------------------
    # Create vars
    # -------------------------------------------------------------------------
    file_path = tk.StringVar()
    file_path.set(str(Path.home() / "pytribeam_state_record.yml"))

    interval_var = tk.StringVar()
    interval_var.set("10")

    status_var = tk.StringVar()
    status_var.set("Idle.")

    # -------------------------------------------------------------------------
    # Create widgets
    # -------------------------------------------------------------------------
    l1 = tk.Label(
        root,
        text="Microscope connection details, likely do not need to change",
        **header_kw,
    )

    host_l = tk.Label(root, text="Host:", **label_kw)
    port_l = tk.Label(root, text="Port:", **label_kw)

    host_var = tk.Entry(root, **entry_kw)
    port_var = tk.Entry(root, **entry_kw)

    l_interval = tk.Label(
        root,
        text="Recording interval",
        **header_kw,
    )

    interval_l = tk.Label(root, text="Interval, seconds:", **label_kw)

    interval_entry = tk.Entry(
        root,
        textvariable=interval_var,
        **entry_kw,
    )

    l2 = tk.Label(
        root,
        text="Path to save the states to",
        **header_kw,
    )

    pentry = ctk.PathEntry(
        root,
        var=file_path,
        directory=False,
        operation="save",
        **entry_kw,
    )

    l3 = tk.Label(
        root,
        text=(
            "Draft note. Click 'Queue note for next saved state' when ready. "
            "Queued notes are attached to the next manual or automatic save."
        ),
        **header_kw,
    )

    text_box = tk.Text(
        root,
        width=10,
        height=10,
        **entry_kw,
    )
    text_box.bind("<FocusIn>", hide_note_placeholder)
    text_box.bind("<FocusOut>", restore_note_placeholder_if_empty)
    text_box.bind("<KeyPress>", clear_note_placeholder_for_typing)

    queue_note_button = tk.Button(
        root,
        text="Queue note for next saved state",
        command=queue_note_for_next_save,
        **note_button_kw,
    )

    f1 = tk.Frame(root, bg=theme.bg)
    f2 = tk.Frame(root, bg=theme.bg)
    f3 = tk.Frame(root, bg=theme.bg)

    save_once_button = tk.Button(
        root,
        text="Save current state once",
        command=save_state,
        **button_kw,
    )

    start_button = tk.Button(
        root,
        text="Start recording state",
        command=start_recording,
        **button_kw,
    )

    stop_button = tk.Button(
        root,
        text="Stop recording state",
        command=lambda: stop_recording(save_final=True, queue_draft=True),
        state=tk.DISABLED,
        **stop_button_kw,
    )

    status_label = tk.Label(
        root,
        textvariable=status_var,
        anchor="w",
        **label_kw,
    )

    # -------------------------------------------------------------------------
    # Place widgets
    # -------------------------------------------------------------------------
    l1.grid(row=0, column=0, columnspan=2, sticky="nsw", padx=6, pady=3)

    host_l.grid(row=1, column=0, sticky="nse", padx=6, pady=3)
    port_l.grid(row=2, column=0, sticky="nse", padx=6, pady=3)

    host_var.grid(row=1, column=1, sticky="nsw", padx=6, pady=3)
    port_var.grid(row=2, column=1, sticky="nsw", padx=6, pady=3)

    f1.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=20)

    l_interval.grid(row=4, column=0, columnspan=2, sticky="nsw", padx=6, pady=3)
    interval_l.grid(row=5, column=0, sticky="nse", padx=6, pady=3)
    interval_entry.grid(row=5, column=1, sticky="nsw", padx=6, pady=3)

    f2.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=20)

    l2.grid(row=7, column=0, columnspan=2, sticky="nsw", padx=6, pady=3)
    pentry.grid(row=8, column=0, columnspan=2, sticky="nsew", padx=6, pady=3)

    f3.grid(row=9, column=0, columnspan=2, sticky="nsew", pady=20)

    l3.grid(row=10, column=0, columnspan=2, sticky="nsw", padx=6, pady=3)
    text_box.grid(row=11, column=0, columnspan=2, sticky="nsew", padx=6, pady=3)

    queue_note_button.grid(
        row=12,
        column=0,
        columnspan=2,
        sticky="nsew",
        padx=6,
        pady=5,
    )

    save_once_button.grid(
        row=13,
        column=0,
        columnspan=2,
        sticky="nsew",
        padx=6,
        pady=5,
    )

    start_button.grid(
        row=14,
        column=0,
        columnspan=2,
        sticky="nsew",
        padx=6,
        pady=5,
    )

    stop_button.grid(
        row=15,
        column=0,
        columnspan=2,
        sticky="nsew",
        padx=6,
        pady=5,
    )

    status_label.grid(
        row=16,
        column=0,
        columnspan=2,
        sticky="nsew",
        padx=6,
        pady=5,
    )
    # -------------------------------------------------------------------------
    # Default values
    # -------------------------------------------------------------------------
    host_var.insert(tk.END, "localhost")
    port_var.insert(tk.END, "None")
    # text_box.insert(1.0, "Insert description...")
    show_note_placeholder()  # replace the above line with this to show placeholder text
    update_queue_note_button()

    # -------------------------------------------------------------------------
    # Start polling the background-thread result queue
    # -------------------------------------------------------------------------
    check_recording_result_queue()

    # -------------------------------------------------------------------------
    # Run
    # -------------------------------------------------------------------------
    root.grab_set()
    root.update_idletasks()
    root.mainloop()
