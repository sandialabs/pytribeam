import tkinter as tk
import tkinter.ttk as ttk
from .utils import *
from .config import *
from .images import *


class MenuButton(tk.Menubutton):
    """A tk MenuButton showing its value on the left and a dropdown arrow on the right."""

    ARROW = "▼"
    ARROW_GAP = "  "  # minimum space between the value and the arrow

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

        # Display the value with an arrow so the button reads as a dropdown,
        # while self.var keeps holding just the value
        self._display_var = tk.StringVar(parent)
        self._trace_id = self.var.trace_add("write", self._update_display)
        # The arrow is pushed to the right edge by padding the text to the widget's
        # width, so a text-sized request would grow with every resize. Without an
        # explicit width, size the widget to its values instead.
        self._auto_width = not kw.get("width")

        relief = kw.get("relief", "raised")
        kw.setdefault("anchor", "w")
        kw.update(
            dict(
                textvariable=self._display_var,
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
        self.bind("<Configure>", self._update_display, add="+")

    def _update_display(self, *args):
        """Show the current value with the dropdown arrow at the right edge."""
        # Read the raw Tcl value so a non-numeric value in an IntVar/DoubleVar can't raise
        value = str(self.getvar(str(self.var)))
        if self._auto_width:
            longest = max([len(str(opt)) for opt in self.options] + [len(value)])
            width = longest + len(self.ARROW_GAP) + 2
            if int(self.cget("width")) != width:
                self.configure(width=width)
        self._display_var.set(self._fit_to_width(value))

    def _fit_to_width(self, value):
        """Pad (or shorten) the value so the arrow ends at the right edge of the text area."""
        font = self.cget("font")

        def measure(text):
            return int(self.tk.call("font", "measure", font, text))

        arrow = self.ARROW_GAP + self.ARROW
        inset = sum(
            self.winfo_fpixels(self.cget(opt))
            for opt in ("borderwidth", "highlightthickness", "padx")
        )
        available = self.winfo_width() - 2 * inset
        if available <= 0:
            return value + arrow  # not laid out yet, <Configure> will refit it

        # Shorten values that don't fit so the arrow stays visible
        if measure(value + arrow) > available:
            while value and measure(value + "…" + arrow) > available:
                value = value[:-1]
            value += "…"
        spaces = int((available - measure(value + arrow)) // max(measure(" "), 1))
        return value + " " * max(spaces, 0) + arrow

    def destroy(self):
        """Stop mirroring the variable, which may outlive this widget."""
        self.var.trace_remove("write", self._trace_id)
        tk.Menubutton.destroy(self)

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
        self._update_display()


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

        # Set the style to use the correct background and foreground colors,
        # matching the other entry widgets (e.g. white text on a dark field in dark mode)
        self.bg = bg or DEFAULT_COLOR
        self.fg = fg or calc_font_color(self.bg)

        custom_style = f"EMB_{len(EntryMenuButton.style)}.TCombobox"
        EntryMenuButton.style.append(custom_style)
        style.configure(
            custom_style,
            padding=(1, 1, 1, 1),
            fieldbackground=self.bg,
            background=self.bg,
            foreground=self.fg,
            insertcolor=self.fg,
            selectbackground="#0078D7",  # Standard blue selection
            selectforeground="white",
            arrowcolor=self.fg,
        )
        style.map(
            custom_style,
            fieldbackground=[
                ("readonly", self.bg),
                ("disabled", self.bg),
                ("", self.bg),
            ],
            background=[("readonly", self.bg), ("disabled", self.bg), ("", self.bg)],
            foreground=[
                ("readonly", self.fg),
                ("disabled", "#808080"),
                ("", self.fg),
            ],
            selectbackground=[("", "#0078D7")],
            selectforeground=[("", "white")],
        )
        self.configure(style=custom_style)


__all__ = ["MenuButton", "EntryMenuButton"]
