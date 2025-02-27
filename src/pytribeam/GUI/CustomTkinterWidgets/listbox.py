import tkinter as tk
from .utils import *
from .config import *
from .images import *


class Listbox(tk.Listbox):
    """A tk listbox."""

    def __init__(
        self,
        parent,
        options,
        h_bg=None,
        h_fg=None,
        bg=None,
        fg=None,
        activestyle=None,
        command=None,
        **kw,
    ):
        """Initialize the listbox.

        Keyword arguments:
        master -- parent widget
        bg     -- background color
        kw     -- keyword arguments passed to listbox"""
        self.bg = bg or DEFAULT_COLOR
        bg = bg or get_widget_attribute(parent, "background")
        fg = fg or calc_font_color(bg)
        h_bg = h_bg or bg
        h_fg = h_fg or bg
        activestyle = activestyle or "dotbox"
        kw.update(
            dict(
                bg=bg,
                fg=fg,
                highlightbackground=bg,
                highlightcolor=h_fg,
                selectmode=tk.SINGLE,
                listvariable=options,
                activestyle=activestyle,
                command=command,
            )
        )

        tk.Listbox.__init__(self, parent, **kw)


class DragDropListbox(tk.Listbox):
    """A tk listbox with drag'n'drop reordering of entries."""

    def __init__(
        self,
        parent,
        options,
        h_bg=None,
        h_fg=None,
        bg=None,
        fg=None,
        activestyle=None,
        **kw,
    ):
        """Initialize the listbox.

        Keyword arguments:
        master -- parent widget
        bg     -- background color
        kw     -- keyword arguments passed to listbox"""
        self.bg = bg or DEFAULT_COLOR
        bg = bg or get_widget_attribute(parent, "background")
        fg = fg or calc_font_color(bg)
        h_bg = h_bg or bg
        h_fg = h_fg or fg
        activestyle = activestyle or "dotbox"
        kw.update(
            dict(
                bg=bg,
                fg=fg,
                highlightbackground=bg,
                highlightcolor=h_fg,
                selectmode=tk.SINGLE,
                listvariable=options,
                activestyle=activestyle,
            )
        )
        tk.Listbox.__init__(self, parent, **kw)
        self.bind("<Button-1>", self.setCurrent)
        self.bind("<B1-Motion>", self.shiftSelection)
        self.curIndex = None

    def setCurrent(self, event):
        self.curIndex = self.nearest(event.y)

    def shiftSelection(self, event):
        i = self.nearest(event.y)
        if i < self.curIndex:
            x = self.get(i)
            self.delete(i)
            self.insert(i + 1, x)
            self.curIndex = i
        elif i > self.curIndex:
            x = self.get(i)
            self.delete(i)
            self.insert(i - 1, x)
            self.curIndex = i


__all__ = ["Listbox", "DragDropListbox"]
