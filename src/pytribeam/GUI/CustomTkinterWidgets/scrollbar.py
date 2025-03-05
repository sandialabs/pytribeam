"""
Code taken from https://github.com/Aboghazala/AwesomeTkinter/
"""

import tkinter as tk
from tkinter import ttk
from .utils import *


class SimpleScrollbar(ttk.Scrollbar):
    """Scrollbar without arrows"""

    style = []

    def __init__(
        self,
        parent,
        orient="horizontal",
        bg=None,
        slider_color=None,
        width=None,
        **options,
    ):
        """initialize scrollbar

        Args:
            orient (str): 'horizontal' or 'vertical'
            bg (str): trough color
            slider_color (str): slider color
            width (int): slider width
        """
        # initialize super class
        ttk.Scrollbar.__init__(self, parent, **options)

        self.bg = bg or "blue"
        self.slider_color = slider_color or "white"
        self.width = width or 5

        # Create unique style name
        style = self.make_style(orient, self.bg, self.slider_color, self.bg)
        self.configure(orient=orient, style=style)

    def make_style(
        self,
        orient,
        troughcolor="black",
        background="grey",
        arrowcolor="white",
        relief="flat",
    ) -> str:
        """
        Style the scrollbars.  Usage:
            parent_frame = ... # tk.Frame(...) or tk.Tk() or whatever you're using for the parent
            hstyle, vstyle = make_scrollbar_styles()
            self._vbar = ttk.Scrollbar(parent_frame, orient='vertical', style=vstyle)
            self._hbar = ttk.Scrollbar(parent_frame, orient='horizontal', style=hstyle)
        """
        style = ttk.Style()

        # Parse the orientation
        if orient.lower() == "horizontal":
            v = "Horizontal"
            sticky = "we"
        else:
            v = "Vertical"
            sticky = "ns"
        style_name = f"CustomScrollbarStyle.{v}.TScrollbar"

        # If the style already exists, we just update the colors
        if f"CustomScrollbarStyle.{v}.Scrollbar.trough" not in style.element_names():
            style.element_create(
                f"CustomScrollbarStyle.{v}.Scrollbar.trough", "from", "default"
            )
        if f"CustomScrollbarStyle.{v}.Scrollbar.thumb" not in style.element_names():
            style.element_create(
                f"CustomScrollbarStyle.{v}.Scrollbar.thumb", "from", "default"
            )
        if f"CustomScrollbarStyle.{v}.Scrollbar.leftarrow" not in style.element_names():
            style.element_create(
                f"CustomScrollbarStyle.{v}.Scrollbar.leftarrow", "from", "default"
            )
        if (
            f"CustomScrollbarStyle.{v}.Scrollbar.rightarrow"
            not in style.element_names()
        ):
            style.element_create(
                f"CustomScrollbarStyle.{v}.Scrollbar.rightarrow", "from", "default"
            )
        if f"CustomScrollbarStyle.{v}.Scrollbar.downarrow" not in style.element_names():
            style.element_create(
                f"CustomScrollbarStyle.{v}.Scrollbar.downarrow", "from", "default"
            )
        if f"CustomScrollbarStyle.{v}.Scrollbar.uparrow" not in style.element_names():
            style.element_create(
                f"CustomScrollbarStyle.{v}.Scrollbar.uparrow", "from", "default"
            )
        if f"CustomScrollbarStyle.{v}.Scrollbar.grip" not in style.element_names():
            style.element_create(
                f"CustomScrollbarStyle.{v}.Scrollbar.grip", "from", "default"
            )
        style.layout(
            f"CustomScrollbarStyle.{v}.TScrollbar",
            [
                (
                    f"CustomScrollbarStyle.{v}.Scrollbar.trough",
                    {
                        "children": [
                            # Commenting in these 2 lines adds arrows (at least horizontally)
                            # (f'CustomScrollbarStyle.{v}.Scrollbar.leftarrow', {'side': 'left', 'sticky': ''}) if is_hori else (f'CustomScrollbarStyle.{v}.Scrollbar.uparrow', {'side': 'top', 'sticky': ''}),
                            # (f'CustomScrollbarStyle.{v}.Scrollbar.rightarrow', {'side': 'right', 'sticky': ''})  if is_hori else (f'CustomScrollbarStyle.{v}.Scrollbar.downarrow', {'side': 'bottom', 'sticky': ''}),
                            (
                                f"CustomScrollbarStyle.{v}.Scrollbar.thumb",
                                {
                                    "unit": "1",
                                    "children": [
                                        (
                                            f"CustomScrollbarStyle.{v}.Scrollbar.grip",
                                            {"sticky": ""},
                                        )
                                    ],
                                    "sticky": "nswe",
                                },
                            )
                        ],
                        "sticky": sticky,
                    },
                ),
            ],
        )
        style.configure(
            f"CustomScrollbarStyle.{v}.TScrollbar",
            activebackground=background,
            activerelief=relief,
            background=background,
            borderwidth=0,
            relief=relief,
            troughcolor=troughcolor,
            arrowcolor=arrowcolor,
        )
        # Comment in the following to customize disable/active colors, whatever that means
        # style.map(f'CustomScrollbarStyle.{v}.TScrollbar', background=[('pressed', '!disabled', disabledcolor), ('active', 'orange')])
        return style_name


class SimpleScrollbar_old(ttk.Scrollbar):
    """Scrollbar without arrows"""

    style = []

    def __init__(
        self,
        parent,
        orient="horizontal",
        bg=None,
        slider_color=None,
        width=None,
        **options,
    ):
        """intialize scrollbar

        Args:
            orient (srt): 'horizontal' or 'vertical'
            bg (str): trough color
            slider_color (str): slider color
            width (int): slider width
        """

        # initialize super class
        ttk.Scrollbar.__init__(self, parent, **options)

        s = ttk.Style()
        self.bg = bg or "blue"
        self.slider_color = slider_color or "white"
        self.width = width or 5

        if orient == "horizontal":
            # h_scrollbar
            custom_style = f"sb_{len(SimpleScrollbar.style)}.Horizontal.TScrollbar"
            s.layout(
                custom_style,
                [
                    (
                        "Horizontal.Scrollbar.trough",
                        {
                            "sticky": "we",
                            "children": [
                                (
                                    "Horizontal.Scrollbar.thumb",
                                    {"expand": "1", "sticky": "nswe"},
                                )
                            ],
                        },
                    )
                ],
            )
        else:
            # v_scrollbar
            custom_style = f"sb_{len(SimpleScrollbar.style)}.Vertical.TScrollbar"
            s.layout(
                custom_style,
                [
                    (
                        "Vertical.Scrollbar.trough",
                        {
                            "sticky": "ns",
                            "children": [
                                (
                                    "Vertical.Scrollbar.thumb",
                                    {"expand": "1", "sticky": "nswe"},
                                )
                            ],
                        },
                    )
                ],
            )

        SimpleScrollbar.style.append(custom_style)

        s.configure(
            custom_style,
            troughcolor=self.bg,
            borderwidth=1,
            relief="flat",
            width=self.width,
        )
        s.map(custom_style, background=[("", self.slider_color)])  # slider color

        self.config(orient=orient, style=custom_style)
