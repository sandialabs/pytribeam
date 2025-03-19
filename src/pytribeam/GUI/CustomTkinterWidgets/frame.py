"""
Code taken from https://github.com/Aboghazala/AwesomeTkinter/
"""

import tkinter as tk
from tkinter import ttk
from .utils import *
from .config import *
from .images import *
from .scrollbar import SimpleScrollbar


class ScrollableFrame(tk.Frame):
    """A frame with scrollbars
    inspired by : https://stackoverflow.com/a/3092341
    basically it is a frame inside a canvas inside another frame

    usage:
        frame = ScrollableFrame(root)
        frame.pack(fill='both', expand=True)

        # add your widgets normally
        tk.Label(frame, text=hello).pack()
    """

    def __init__(
        self,
        parent,
        vscroll=True,
        hscroll=True,
        autoscroll=False,
        bg=None,
        sbar_fg=None,
        sbar_bg=None,
        vbar_width=10,
        hbar_width=10,
    ):
        """initialize

        Args:
            parent (tk.Widget): tkinter master widget
            vscroll (bool): use vertical scrollbar
            hscroll (bool): use horizontal scrollbar
            autoscroll (bool): auto scroll to bottom if new items added to frame
            bg (str): background
            sbar_fg (str): color of scrollbars' slider
            sbar_bg (str): color of scrollbars' trough, default to frame's background
            vbar_width (int): vertical scrollbar width
            hbar_width (int): horizontal scrollbar width
        """
        self.autoscroll = autoscroll
        self.current_height = None

        self.sbar_bg = sbar_bg or "blue"
        self.sbar_fg = sbar_fg or "white"

        # create outside frame
        self.outer_frame = tk.Frame(parent, bg=bg)

        # create canvas
        self.canvas = tk.Canvas(
            self.outer_frame, borderwidth=0, highlightthickness=0, background=bg
        )

        # initialize super class
        tk.Frame.__init__(self, self.canvas, bg=bg)

        # scrollbars
        if vscroll:
            self.vsb = SimpleScrollbar(
                self.outer_frame,
                orient="vertical",
                command=self.canvas.yview,
                bg=self.sbar_bg,
                slider_color=self.sbar_fg,
                width=vbar_width,
            )
            self.canvas.configure(yscrollcommand=self.vsb.set)

            self.vsb.pack(side="right", fill="y")
        if hscroll:
            self.hsb = SimpleScrollbar(
                self.outer_frame,
                orient="horizontal",
                command=self.canvas.xview,
                bg=self.sbar_bg,
                slider_color=self.sbar_fg,
                width=hbar_width,
            )
            self.canvas.configure(xscrollcommand=self.hsb.set)

            self.hsb.pack(side="bottom", fill="x")

        self.canvas.pack(side="left", fill="both", expand=True)

        self._id = self.canvas.create_window(
            (0, 0), window=self, anchor="nw", tags="self"
        )

        self.bind("<Configure>", self._on_self_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # scroll with mousewheel
        scroll_with_mousewheel(self, target=self.canvas, apply_to_children=True)

        # use outer frame geometry managers
        self.pack = self.outer_frame.pack
        self.pack_forget = self.outer_frame.pack_forget

        self.grid = self.outer_frame.grid
        self.grid_forget = self.outer_frame.grid_forget
        self.grid_remove = self.outer_frame.grid_remove

        self.place = self.outer_frame.place
        self.place_forget = self.outer_frame.place_forget

        # get scroll methods from canvas
        self.yview_moveto = self.canvas.yview_moveto
        self.xview_moveto = self.canvas.xview_moveto

    def yview_scroll(self, *args):
        if self.winfo_height() > self.outer_frame.winfo_height():
            self.canvas.yview_scroll(*args)

    def xview_scroll(self, *args):
        if self.winfo_width() > self.outer_frame.winfo_width():
            self.canvas.xview_scroll(*args)

    def _on_self_configure(self, event):
        """Reset the scroll region to match contents"""
        if self.winfo_height() != self.current_height:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

            # scroll to bottom, if new widgets added to frame
            if self.autoscroll:
                self.scrolltobottom()

            self.current_height = self.winfo_height()

    def _on_canvas_configure(self, event):
        """expand self to fill canvas"""
        self.canvas.itemconfigure(self._id, width=self.canvas.winfo_width())

    def vscroll(self, fraction):
        """scroll canvas vertically

        Args:
            fraction (float): from 0 "top" to 1.0 "bottom"
        """

        self.canvas.yview_moveto(fraction)

    def scrolltobottom(self):
        self.vscroll(1.0)

    def scrolltotop(self):
        self.vscroll(0)

    def hscroll(self, fraction):
        """scroll canvas horizontally

        Args:
            fraction (float): from 0 "left" to 1.0 "right"
        """

        self.canvas.xview_moveto(fraction)


class Frame3d(ttk.Frame):
    """create a frame with 3d background color and shadow"""

    styles = []

    def __init__(self, parent, bg=None, **options):
        """initialize

        Args:
            parent: tkinter container widget, i.e. root or another frame
            bg (str): color of frame
        """
        self.bg = bg or DEFAULT_COLOR
        parent_color = get_widget_attribute(parent, "background") or DEFAULT_COLOR

        # initialize super class
        ttk.Frame.__init__(self, parent, **options)

        # create unique style name based on frame color
        frame_style = f"Frame3d_{generate_unique_name(color_to_rgba(self.bg))}"

        # create style
        if frame_style not in Frame3d.styles:

            self.img = self.create_image()

            # create elements
            s = ttk.Style()
            element_style = f"{frame_style}_element"
            s.element_create(element_style, "image", self.img, border=15, sticky="nsew")
            s.layout(frame_style, [(element_style, {"sticky": "nsew"})])
            s.map(frame_style, background=[("", parent_color)])

            # add to styles
            Frame3d.styles.append(frame_style)

        self["style"] = frame_style

    def create_image(self):

        shadow_img = create_pil_image(b64=btn_base)
        img = create_pil_image(b64=btn_face, color=self.bg)

        # merge face with base image
        img = mix_images(shadow_img, img)

        return ImageTk.PhotoImage(img)


class ExpandableFrame(ttk.Frame):
    """
    A custom frame that can be expanded or collapsed to show/hide its contents.
    Supports nested hierarchical structure with proper visual indentation and consistent coloring.
    """

    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        level: int = 0,
        initial_state: str = "collapsed",
        bg: str = "#ffffff",  # Default white background
        fg: str = "#000000",  # Default black text
        font: tuple = ("TkDefaultFont", 10, "bold"),
        *args,
        **kwargs,
    ):
        super().__init__(parent, *args, **kwargs)

        # Store colors
        self.bg_color = bg
        self.fg_color = fg
        self.font = font

        # Configuration
        self.title = title
        self.level = level
        self.is_expanded = initial_state == "expanded"

        # Style setup - create unique style names for this instance
        self.frame_style = f"Expandable_{id(self)}.TFrame"
        self.label_style = f"Expandable_{id(self)}.TLabel"
        self.entry_style = f"Expandable_{id(self)}.TEntry"
        self.checkbutton_style = f"Expandable_{id(self)}.TCheckbutton"

        # Configure styles
        self.style = ttk.Style()
        self.style.configure(self.frame_style, background=self.bg_color)
        self.style.configure(
            self.label_style, background=self.bg_color, foreground=self.fg_color
        )
        self.style.configure(
            self.entry_style, fieldbackground=self.bg_color, foreground=self.fg_color
        )
        self.style.configure(
            self.checkbutton_style, background=self.bg_color, foreground=self.fg_color
        )

        # Apply frame style
        self.configure(style=self.frame_style, padding=(level * 20, 5, 5, 5))

        # Create header with consistent styling
        self.header_frame = ttk.Frame(self, style=self.frame_style)
        self.header_frame.pack(fill="x", expand=False)

        # Toggle button with arrow
        self.toggle_button = tk.Label(
            self.header_frame,
            text="▼" if self.is_expanded else "▶",
            width=2,
            bg=self.bg_color,
            fg=self.fg_color,
            font=self.font,
        )
        self.toggle_button.pack(side="left")
        self.toggle_button.bind("<Button-1>", self.toggle)

        # Title label with consistent styling
        self.title_label = tk.Label(
            self.header_frame,
            text=title,
            bg=self.bg_color,
            fg=self.fg_color,
            font=self.font,
        )
        self.title_label.pack(side="left", padx=5)
        self.title_label.bind("<Button-1>", self.toggle)

        # Content frame with consistent styling
        self.extension = ttk.Frame(self, style=self.frame_style)
        if self.is_expanded:
            self.extension.pack(fill="both", expand=True, padx=5)

    def toggle(self, event=None):
        """Toggle the expanded/collapsed state of the frame."""
        self.is_expanded = not self.is_expanded
        self.toggle_button.configure(text="▼" if self.is_expanded else "▶")

        if self.is_expanded:
            self.extension.pack(fill="both", expand=True, padx=5)
        else:
            self.extension.pack_forget()


class ToggledFrame(tk.Frame):

    def __init__(self, parent, text="", **kwargs):
        # Handle style
        bg = kwargs.pop("bg", get_widget_attribute(parent, "background"))
        fg = kwargs.pop("fg", calc_font_color(bg))
        ft = kwargs.pop("font", "10")
        super().__init__(parent, bg=bg, **kwargs)

        # Set toggled status variable
        self.showing = False

        # Create title frame
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.title_frame = tk.Frame(self, bg=bg, relief="groove", borderwidth=2)
        self.title_frame.pack(side="top", fill="both", expand=True)

        # Create title label
        self.title_label = tk.Label(
            self.title_frame, text=text, bg=bg, fg=fg, font=ft, anchor="w"
        )
        self.title_label.pack(side="left", fill="both", expand=True)

        # Create toggle button
        self.toggle_button = tk.Button(
            self.title_frame,
            text="▼",
            command=self.toggle,
            bg=bg,
            fg=fg,
            font=ft,
            relief="flat",
            anchor="e",
        )
        self.toggle_button.pack(side="right", fill="both", expand=True)

        # Create content frame
        self.extension = tk.Frame(self, bg=bg, relief="sunken", borderwidth=2)

        # frame = tk.Frame(self,relief=tk.SOLID, bd=1)
        # self.label = tk.Label(
        #     frame, bg=bg, fg=fg, text=tx)
        # self.button = tk.Button(
        #     frame, bg=bg, fg=fg, text='↲', relief=tk.FLAT,
        #     font=ft, command=self.toggle)
        # frame.grid(row=0, column=0, sticky='nsew')
        # self.label.grid(row=0, column=0, sticky='nsew')
        # self.button.grid(row=0, column=1, sticky='nsew')
        # frame.pack(side=tk.TOP,expand=True,fill=tk.BOTH)
        # self.label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # self.button.pack(side=tk.RIGHT,fill=tk.Y)
        # self.extension = tk.Frame(self, bg=bg, **kwargs)
        return

    def toggle(self):
        if not self.showing:
            # self.extension.grid(row=1, column=0, sticky='ewns')
            self.extension.pack(side="bottom", fill="both", expand=True)
            self.toggle_button.config(text="▲")
            self.showing = True
        else:
            # self.extension.grid_forget()
            self.extension.pack_forget()
            self.toggle_button.config(text="▼")
            self.showing = False
        # if self.extension not in self.grid_slaves():
        #     self.extension.grid(row=1, column=0, sticky='ewns')
        # else:
        #     self.extension.grid_forget()
