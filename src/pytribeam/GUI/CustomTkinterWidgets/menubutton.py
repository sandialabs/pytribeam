import tkinter as tk
import tkinter.ttk as ttk
from .utils import *
from .config import *
from .images import *


class MenuButton(tk.Menubutton):
    """A tk  MenuButton."""

    def __init__(
        self,
        parent,
        options,
        var=None,
        h_bg=None,
        h_fg=None,
        bg=None,
        fg=None,
        command=None,
        dtype=None,
        **kw,
    ):
        """Initialize the menubutton."""

        self.bg = bg or DEFAULT_COLOR
        bg = bg or get_widget_attribute(parent, "background")
        fg = fg or calc_font_color(bg)
        h_bg = h_bg or ACCENT_COLOR1
        h_fg = h_fg or fg
        if var is None:
            if dtype is None or dtype == "str":
                self.var = tk.StringVar(parent)
            elif dtype == "int":
                self.var = tk.IntVar(parent)
            elif dtype == "float":
                self.var = tk.DoubleVar(parent)
            else:
                self.var = tk.StringVar(parent)
        else:
            self.var = var

        relief = kw.get("relief", "raised")
        kw.update(
            dict(
                textvariable=self.var,
                bg=bg,
                fg=fg,
                highlightbackground=bg,
                highlightcolor=h_fg,
                activebackground=h_bg,
                activeforeground=h_fg,
                relief=relief,
            )
        )
        tk.Menubutton.__init__(self, parent, **kw)
        kw = dict(
            tearoff=0,
            bg=bg,
            fg=fg,
            activebackground=h_bg,
            activeforeground=h_fg,
            selectcolor=fg,
        )
        self.menu = tk.Menu(self, **kw)
        self["menu"] = self.menu
        self.options = options
        self.set_options(options, command)

    def set_options(self, options, command=None):
        """Set the options for the menubutton."""
        self.options = options
        # Clear the menu
        self.menu.delete(0, tk.END)
        for opt in options:
            if command is None:
                self.menu.add_radiobutton(label=opt, variable=self.var, value=opt)
            else:
                self.menu.add_radiobutton(
                    label=opt,
                    variable=self.var,
                    value=opt,
                    command=lambda: command(self.var.get()),
                )


class EntryMenuButton(ttk.Combobox):
    """Remove the dropdown from a combobox and use it for displaying a limited
    set of historical entries for the entry widget.
    <Key-Down> to show the list.
    It is up to the programmer when to add new entries into the history via `add()`"""

    style = []

    def __init__(
        self,
        master,
        bg=None,
        fg=None,
        command=None,
        var=None,
        options=None,
        dtype=None,
        **kwargs,
    ):
        """Initialize the custom combobox and intercept the length option."""
        self.length = 10
        # if "length" in kwargs:
        #     self.length = kwargs["length"]
        #     del kwargs["length"]
        var = var or tk.StringVar(master, value="")
        values = options or []
        kwargs.update(
            dict(
                textvariable=var,
                values=values,
            )
        )
        super(EntryMenuButton, self).__init__(master, **kwargs)

        if command is not None:
            self.var = var
            self.var.trace_add("write", command)

        style = ttk.Style()
        # self.configure(width=self.width)
        custom_style = f"EMB_{len(EntryMenuButton.style)}.TCombobox"
        style.layout(
            custom_style,
            [
                (
                    "Combobox.border",
                    {
                        "sticky": "nswe",
                        "children": [
                            (
                                "Combobox.padding",
                                {
                                    "expand": "1",
                                    "sticky": "nswe",
                                    "children": [
                                        (
                                            "Combobox.background",
                                            {
                                                "sticky": "nswe",
                                                "children": [
                                                    (
                                                        "Combobox.focus",
                                                        {
                                                            "expand": "1",
                                                            "sticky": "nswe",
                                                            "children": [
                                                                (
                                                                    "Combobox.textarea",
                                                                    {"sticky": "nswe"},
                                                                )
                                                            ],
                                                        },
                                                    )
                                                ],
                                            },
                                        )
                                    ],
                                },
                            )
                        ],
                    },
                ),
                ("Combobox.downarrow", {"side": "right", "sticky": "nse"}),
            ],
        )

        # Set the style to use the correct background and foreground colors
        # Note: On Windows, ttk.Combobox fieldbackground cannot be reliably styled
        # The entry field will remain white, so we use dark text for visibility
        self.bg = bg or DEFAULT_COLOR
        self.fg = fg or calc_font_color(self.bg)
        # Force dark text on white background for readability in the entry field
        entry_fg = calc_font_color("#FFFFFF")  # Calculate text color for white background

        custom_style = f"EMB_{len(EntryMenuButton.style)}.TCombobox"
        EntryMenuButton.style.append(custom_style)
        style.configure(
            custom_style,
            padding=(1, 1, 1, 1),
            fieldbackground="white",  # Explicitly set to white since we can't override it
            background=self.bg,
            foreground=entry_fg,  # Dark text for white background
            selectbackground="#0078D7",  # Standard blue selection
            selectforeground="white",
            arrowcolor=entry_fg,
        )
        style.map(
            custom_style,
            fieldbackground=[("readonly", "white"), ("disabled", "#F0F0F0"), ("", "white")],
            background=[("readonly", self.bg), ("disabled", self.bg), ("", self.bg)],
            foreground=[("readonly", entry_fg), ("disabled", "#808080"), ("", entry_fg)],
            selectbackground=[("", "#0078D7")],
            selectforeground=[("", "white")],
        )
        self.configure(style=custom_style)


__all__ = ["MenuButton", "EntryMenuButton"]
