import re
import tkinter as tk
from tkinter import ttk
import tkinter.filedialog as filedialog
from .utils import *
from .config import *
from .images import *


class Entry(tk.Entry):
    """A tk Entry."""

    def __init__(
        self,
        parent,
        var=None,
        h_bg=None,
        h_fg=None,
        bg=None,
        fg=None,
        command=None,
        dtype=str,
        borders="bottom",
        **kw,
    ):
        """Initialize the menubutton."""

        self.bg = bg or DEFAULT_COLOR
        bg = bg or get_widget_attribute(parent, "background")
        fg = fg or calc_font_color(bg)
        h_bg = h_bg or ACCENT_COLOR1
        h_fg = h_fg or fg
        var = var or tk.StringVar(parent, value="")
        kw.update(
            dict(
                textvariable=var,
                bg=bg,
                fg=fg,
                selectbackground=h_bg,
                selectforeground=h_fg,
            )
        )
        if borders.lower() != "all":
            kw.update(dict(borderwidth=0))
        tk.Entry.__init__(self, parent, **kw)
        self.dtype = dtype
        self.bypass_validation = False
        self.var = var
        vcmd = (
            self.register(self.validate),
            "%d",
            "%i",
            "%P",
            "%s",
            "%S",
            "%v",
            "%V",
            "%W",
        )
        self.config(validate="key", validatecommand=vcmd)

        if command is not None:
            self.config(textvariable=self.var)
            self.var.trace_add("write", command)

        # Handle borders
        if "bottom" in borders.lower():
            separator = ttk.Separator(self, orient="horizontal")
            separator.place(in_=self, x=0, rely=1.0, height=2, relwidth=1.0)
        if "top" in borders.lower():
            separator = ttk.Separator(self, orient="horizontal")
            separator.place(in_=self, x=0, rely=0.0, height=2, relwidth=1.0)
        if "left" in borders.lower():
            separator = ttk.Separator(self, orient="vertical")
            separator.place(in_=self, y=0, relx=0.0, width=2, relheight=1.0)
        if "right" in borders.lower():
            separator = ttk.Separator(self, orient="vertical")
            separator.place(in_=self, y=0, relx=1.0, width=2, relheight=1.0)
        

    def validate(
        self,
        action,
        index,
        value_if_allowed,
        prior_value,
        text,
        validation_type,
        trigger_type,
        widget_name,
    ):
        """Validate the input."""
        # Bypass validation if we are reverting to prior value
        if self.bypass_validation:
            return True
        # Allow empty string
        if value_if_allowed == "":
            return True
        # Validate input based on dtype
        if self.dtype == int:
            if re.match(r"^[+1]?\d*$", value_if_allowed):
                return True
        elif self.dtype == float:
            if re.match(r"^[+-]?\d*\.?\d+$", value_if_allowed) or re.match(r"^[+-]?\d+\.\d*$", value_if_allowed) or value_if_allowed == "-":
                return True
        elif self.dtype == str:
            return True
        # Revert to prior value if input is invalid
        self.bypass_validation = True
        self.var.set(prior_value)
        self.bypass_validation = False
        return False


class PathEntry(tk.Frame):
    """A tk Entry with a button to open a file dialog."""

    def __init__(
        self,
        parent,
        var=None,
        h_bg=None,
        h_fg=None,
        bg=None,
        fg=None,
        command=None,
        defaultextension=None,
        directory=False,
        operation="save",
        **kw,
    ):
        """Initialize the menubutton."""

        self.defaultextension = defaultextension
        self.directory = directory
        self.operation = operation
        self.bg = bg or DEFAULT_COLOR
        bg = bg or get_widget_attribute(parent, "background")
        fg = fg or calc_font_color(bg)
        h_bg = h_bg or ACCENT_COLOR1
        h_fg = h_fg or fg
        self.var = var or tk.StringVar(parent, value="")
        tk.Frame.__init__(self, parent, bg=bg, padx=0, pady=0, bd=0)
        self.columnconfigure(0, weight=10)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.entry = Entry(self, var=self.var, bg=bg, fg=fg, command=command)
        self.entry.grid(row=0, column=0, sticky="ewns", padx=0, pady=0)
        self.button = tk.Button(
            self, text="...", command=self.open_file_dialog, bg=bg, fg=fg
        )
        self.button.grid(row=0, column=1, sticky="ewns")

    def open_file_dialog(self):
        """Open a file dialog."""
        if self.directory:
            file = filedialog.askdirectory()
        else:
            f_types = [
                ("All files", "*.*"),
                ("YAML files", "*.yml"),
                ("Python files", "*.py"),
                ("HDF5 files", "*.h5"),
            ]
            if self.operation == "open":
                file = filedialog.askopenfilename(
                    title="Select a file",
                    filetypes=f_types,
                    defaultextension=self.defaultextension,
                )
            else:
                file = filedialog.asksaveasfilename(
                    title="Select a file",
                    filetypes=f_types,
                    defaultextension=self.defaultextension,
                )
        if file:
            self.var.set(file)
        return file
