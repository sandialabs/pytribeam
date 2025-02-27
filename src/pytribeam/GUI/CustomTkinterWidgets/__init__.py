#!/usr/bin/env python
"""
Code taken from https://github.com/Aboghazala/AwesomeTkinter/
"""

import tkinter as tk
from tkinter import ttk

from .button import Button, Button3d, Radiobutton, Checkbutton
from .frame import Frame3d, ScrollableFrame, ToggledFrame
from .menu import RightClickMenu
from .progressbar import RadialProgressbar, RadialProgressbar3d, Segmentbar, Progressbar
from .scrollbar import SimpleScrollbar
from .text import ScrolledText
from .utils import *
from .config import *
from .tooltip import tooltip
from .listbox import Listbox, DragDropListbox
from .menubutton import MenuButton, EntryMenuButton
from .entry import Entry, PathEntry
from .label import AutofitLabel, AutoWrappingLabel
from .dialog import filechooser, folderchooser
from .datepicker import DatePicker


def main():
    print("Hello from CustomTkinterWidgets!")
