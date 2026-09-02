import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Optional, Tuple

from pytribeam import types as tbt
from pytribeam import utilities
from pytribeam.GUI import CustomTkinterWidgets as ctk
from pytribeam.mcp.state.capture import build_provenance, capture_to_directory


# -----------------------------------------------------------------------------
# Microscope connection
# -----------------------------------------------------------------------------
# The recorder holds one connection for the lifetime of the session rather than
# reconnecting on every read. Only one capture runs at a time (guarded by
# save_in_progress), so a single shared client is not contended. If a capture
# fails, the client is dropped so the next attempt reconnects from scratch.

_microscope = None
_microscope_key: Optional[Tuple[str, Optional[int]]] = None
_microscope_lock = threading.Lock()


def get_connected_microscope(host: str, port: Optional[int]) -> tbt.Microscope:
    """Return a connected microscope, reusing the existing connection.

    Parameters
    ----------
    host : str
        Microscope connection host.
    port : int, optional
        Microscope connection port, or None for the default.

    Returns
    -------
    tbt.Microscope
        A connected microscope client.
    """
    global _microscope
    global _microscope_key

    key = (host, port)

    with _microscope_lock:
        if _microscope is not None and _microscope_key == key:
            return _microscope

    scope = tbt.Microscope()
    utilities.connect_microscope(
        scope,
        quiet_output=True,
        connection_host=host,
        connection_port=port,
    )

    with _microscope_lock:
        _microscope = scope
        _microscope_key = key

    return scope


def invalidate_microscope():
    """Drop the cached connection, disconnecting it if possible."""
    global _microscope
    global _microscope_key

    with _microscope_lock:
        scope = _microscope
        _microscope = None
        _microscope_key = None

    if scope is not None:
        try:
            utilities.disconnect_microscope(scope, quiet_output=True)
        except Exception:
            pass


def set_status(message: str):
    """Update the GUI status line.

    This should only be called from the Tkinter main thread.
    """
    try:
        status_var.set(message)
    except NameError:
        pass


def ensure_directory_exists() -> Path:
    """Make sure the output state directory exists and return it.

    States are written one file per record into a directory alongside an
    index, rather than appended to a single growing YAML file. This keeps each
    write constant-time, survives an interrupted write, and makes individual
    states convenient to hand around as test fixtures.

    Returns
    -------
    Path
        The state directory.

    Raises
    ------
    RuntimeError
        If no path has been provided, or the path exists as a file.
    """
    raw = output_dir.get().strip()

    if raw == "":
        raise RuntimeError("No output directory provided.")

    path = Path(raw)

    # Tolerate an old-style path ending in .yml by using its stem as a folder.
    if path.suffix.lower() in (".yml", ".yaml"):
        path = path.with_suffix("")
        output_dir.set(str(path))

    if path.exists() and not path.is_dir():
        raise RuntimeError(f"{path} exists and is not a directory.")

    path.mkdir(parents=True, exist_ok=True)

    return path


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
    directory: Path,
    host: str,
    port: Optional[int],
    description: str,
    intended_action: Optional[str],
    include_quads: bool,
):
    """Background-thread worker for recording microscope state.

    Important:
    This function must not directly touch Tkinter widgets, Tkinter variables,
    or messageboxes. It communicates results back to the GUI thread through
    ``result_queue``.
    """
    try:
        microscope = get_connected_microscope(host, port)

        record = capture_to_directory(
            microscope,
            directory,
            description=description,
            intended_action=intended_action,
            include_quads=include_quads,
            provenance=build_provenance(host=host, port=port),
        )

        result_queue.put(
            {
                "success": True,
                "record_id": record.id,
                "recorded_at": record.recorded_at,
                "n_values": len(record.values),
                "n_read_errors": len(record.read_errors),
                "error": None,
            }
        )

    except Exception as e:
        # The connection may be the thing that broke. Force a reconnect on the
        # next attempt rather than reusing a client in an unknown state.
        invalidate_microscope()

        result_queue.put(
            {
                "success": False,
                "record_id": None,
                "recorded_at": None,
                "n_values": 0,
                "n_read_errors": 0,
                "error": e,
            }
        )


def record_state_once_threaded() -> bool:
    """Start one microscope-state recording in a background thread.

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
        directory = ensure_directory_exists()

        host = host_var.get().strip()
        port = parse_port()
        include_quads = bool(include_quads_var.get())

        # Consume only previously queued annotations.
        # Do not touch the draft note box here, because the user may be typing.
        description, intended_action = pop_pending_annotations()

    except Exception as e:
        messagebox.showerror("Error preparing microscope state recording", str(e))
        set_status("Error preparing state recording.")
        return False

    save_in_progress = True
    set_status("Recording microscope state...")
    show_recording_indicator()

    worker = threading.Thread(
        target=record_state_worker,
        args=(directory, host, port, description, intended_action, include_quads),
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
            hide_recording_indicator()

            if result["success"]:
                message = (
                    f"Saved {result['record_id']} "
                    f"({result['n_values']} values"
                )

                # Surface read errors in the status line. Attributes that fail
                # on a healthy microscope are exactly the ones worth knowing
                # about, and they are invisible if only the count of values is
                # reported.
                if result["n_read_errors"]:
                    message += f", {result['n_read_errors']} read errors"

                set_status(message + ")")

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
    """Queue the current draft note and action for the next saved state."""
    queue_current_draft_note(silent=False)


def pop_pending_annotations() -> Tuple[str, Optional[str]]:
    """Return and clear the queued note and intended action.

    This intentionally does not touch the draft text box or action entry.

    Returns
    -------
    tuple of (str, str or None)
        The queued description and intended action.
    """
    global pending_note
    global pending_action

    note = pending_note
    action = pending_action or None

    pending_note = ""
    pending_action = ""

    update_queue_note_button()

    return note, action


def queue_current_draft_note(silent: bool = False) -> bool:
    """Move current draft note and action into the pending slots.

    The intended action names the capability the operator believes they just
    used, e.g. ``move_stage``. It is optional, but supplying it turns a
    recorded pair into labelled ground truth: a diff tool can then be checked
    on whether it groups several changed paths into the one operation that
    actually caused them.

    Returns
    -------
    bool
        True if anything was queued, False otherwise.
    """
    global pending_note
    global pending_action
    global note_placeholder_active

    note = "" if note_placeholder_active else text_box.get("1.0", "end-1c").strip()
    action = action_var.get().strip()

    if not note and not action:
        if not silent:
            set_status("No draft note or action to queue.")
        return False

    if note:
        if pending_note:
            pending_note = pending_note + "\n\n" + note
        else:
            pending_note = note

    if action:
        pending_action = action

    text_box.delete("1.0", tk.END)
    text_box.config(fg=theme.colors["terminal_fg"])
    note_placeholder_active = False

    action_entry.delete(0, tk.END)

    if text_box.focus_get() != text_box:
        show_note_placeholder()

    update_queue_note_button()

    if not silent:
        set_status("Queued for next saved state.")

    return True


def update_queue_note_button():
    """Update the queue button text/color based on pending annotations."""
    try:
        if pending_note or pending_action:
            queue_note_button.config(
                text="Queued annotations pending — add another",
                **note_button_pending_kw,
            )
        else:
            queue_note_button.config(
                text="Queue note and action for next saved state",
                **note_button_kw,
            )
    except NameError:
        # Button/style variables may not exist yet during startup.
        pass


def show_recording_indicator():
    """Show a small non-modal indicator while state recording is active."""
    global recording_indicator_window

    try:
        if not show_recording_indicator_var.get():
            return

        if (
            recording_indicator_window is not None
            and recording_indicator_window.winfo_exists()
        ):
            return

        recording_indicator_window = tk.Toplevel(master)
        recording_indicator_window.title("Recording state")
        recording_indicator_window.transient(master)
        recording_indicator_window.resizable(False, False)

        try:
            recording_indicator_window.attributes("-topmost", True)
        except tk.TclError:
            pass

        label = tk.Label(
            recording_indicator_window,
            text="Recording microscope state...",
            padx=20,
            pady=12,
            bg=theme.bg,
            fg=theme.fg,
            font=("Segoe UI", 12),
        )
        label.pack(fill="both", expand=True)

        # Put it near the main window.
        master.update_idletasks()
        x = master.winfo_rootx() + 40
        y = master.winfo_rooty() + 40
        recording_indicator_window.geometry(f"+{x}+{y}")

        # Closing the popup hides it for the current recording only.
        recording_indicator_window.protocol(
            "WM_DELETE_WINDOW",
            hide_recording_indicator,
        )

    except NameError:
        pass


def hide_recording_indicator():
    """Hide the recording indicator popup."""
    global recording_indicator_window

    try:
        if (
            recording_indicator_window is not None
            and recording_indicator_window.winfo_exists()
        ):
            recording_indicator_window.destroy()
    except tk.TclError:
        pass

    recording_indicator_window = None


def on_show_recording_indicator_changed():
    """Handle toggling the recording-indicator checkbox."""
    try:
        if show_recording_indicator_var.get() and save_in_progress:
            show_recording_indicator()
        else:
            hide_recording_indicator()
    except NameError:
        pass


def save_state():
    """Manual one-shot save.

    If the draft note box or action entry contains text, queue it first so it
    is attached to this manual save. This mirrors the stop button behavior,
    but only for a single save.
    """
    queue_current_draft_note(silent=True)
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

    # if the user types a draft note before starting, attach it to the first save.
    queue_current_draft_note(silent=True)

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
        if save_final and (pending_note or pending_action):
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

    invalidate_microscope()

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
    pending_action = ""
    final_save_after_current = False

    recording_indicator_window = None

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
    output_dir = tk.StringVar()
    output_dir.set(str(Path.home() / "pytribeam_state_record"))

    interval_var = tk.StringVar()
    interval_var.set("10")

    action_var = tk.StringVar()

    status_var = tk.StringVar()
    status_var.set("Idle.")

    show_recording_indicator_var = tk.BooleanVar()
    show_recording_indicator_var.set(False)

    include_quads_var = tk.BooleanVar()
    include_quads_var.set(True)

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

    include_quads_checkbox = tk.Checkbutton(
        root,
        text="Sweep imaging quadrants (records per-quad device, briefly changes view)",
        variable=include_quads_var,
        bg=theme.bg,
        fg=theme.fg,
        activebackground=theme.bg,
        activeforeground=theme.fg,
        selectcolor=theme.colors["bg_off"],
        font=("Segoe UI", 11),
    )

    operator_note_label = tk.Label(
        root,
        text=(
            "Operator note: State recording may briefly interact with the microscope UI. "
            "Open drop-down menus may close during a recording. "
            "The active view is restored afterward."
        ),
        wraplength=600,
        justify="left",
        **label_kw,
    )

    l2 = tk.Label(
        root,
        text="Directory to save the states to",
        **header_kw,
    )

    pentry = ctk.PathEntry(
        root,
        var=output_dir,
        directory=True,
        operation="save",
        **entry_kw,
    )

    l3 = tk.Label(
        root,
        text=(
            "Draft note. Click 'Queue note and action' when ready. "
            "Queued annotations are attached to the next manual or automatic save."
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

    action_l = tk.Label(root, text="Intended action:", **label_kw)

    action_entry = tk.Entry(
        root,
        textvariable=action_var,
        **entry_kw,
    )

    action_hint = tk.Label(
        root,
        text=(
            "Optional. Name the operation you just performed, e.g. move_stage, "
            "set_hfw. Leave blank if the change was incidental or unknown."
        ),
        wraplength=600,
        justify="left",
        **label_kw,
    )

    queue_note_button = tk.Button(
        root,
        text="Queue note and action for next saved state",
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

    show_indicator_checkbox = tk.Checkbutton(
        root,
        text="Show recording indicator popup",
        variable=show_recording_indicator_var,
        command=on_show_recording_indicator_changed,
        bg=theme.bg,
        fg=theme.fg,
        activebackground=theme.bg,
        activeforeground=theme.fg,
        selectcolor=theme.colors["bg_off"],
        font=("Segoe UI", 11),
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

    include_quads_checkbox.grid(
        row=6,
        column=0,
        columnspan=2,
        sticky="w",
        padx=6,
        pady=3,
    )

    operator_note_label.grid(
        row=7,
        column=0,
        columnspan=2,
        sticky="w",
        padx=6,
        pady=3,
    )

    f2.grid(row=8, column=0, columnspan=2, sticky="nsew", pady=20)

    l2.grid(row=9, column=0, columnspan=2, sticky="nsw", padx=6, pady=3)
    pentry.grid(row=10, column=0, columnspan=2, sticky="nsew", padx=6, pady=3)

    f3.grid(row=11, column=0, columnspan=2, sticky="nsew", pady=20)

    l3.grid(row=12, column=0, columnspan=2, sticky="nsw", padx=6, pady=3)
    text_box.grid(row=13, column=0, columnspan=2, sticky="nsew", padx=6, pady=3)

    action_l.grid(row=14, column=0, sticky="nse", padx=6, pady=3)
    action_entry.grid(row=14, column=1, sticky="nsew", padx=6, pady=3)

    action_hint.grid(row=15, column=0, columnspan=2, sticky="w", padx=6, pady=3)

    queue_note_button.grid(
        row=16,
        column=0,
        columnspan=2,
        sticky="nsew",
        padx=6,
        pady=5,
    )

    save_once_button.grid(
        row=17,
        column=0,
        columnspan=2,
        sticky="nsew",
        padx=6,
        pady=5,
    )

    start_button.grid(
        row=18,
        column=0,
        columnspan=2,
        sticky="nsew",
        padx=6,
        pady=5,
    )

    stop_button.grid(
        row=19,
        column=0,
        columnspan=2,
        sticky="nsew",
        padx=6,
        pady=5,
    )

    show_indicator_checkbox.grid(
        row=20,
        column=0,
        columnspan=2,
        sticky="w",
        padx=6,
        pady=5,
    )

    status_label.grid(
        row=21,
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
    show_note_placeholder()
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
    