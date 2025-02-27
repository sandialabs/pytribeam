import tkinter as tk
import pytribeam.GUI.CustomTkinterWidgets as ctk

import pytribeam.GUI.config_ui.lookup as lut


kwargs = {"offvalue": "False", "onvalue": "True", "bd": 0, "dtype": bool}


root = tk.Tk()
# root.config(background="white")
root.config(background=ctk.DEFAULT_COLOR)
root.title("Sandbox")
root.geometry("800x600")

VAR = tk.StringVar()
c = ctk.Checkbutton(root, text="Checkbutton", var=VAR, **kwargs)
c.grid(row=0, column=0)

trace_id = VAR.trace_add("write", lambda *args: print(VAR.get()))


root.mainloop()
