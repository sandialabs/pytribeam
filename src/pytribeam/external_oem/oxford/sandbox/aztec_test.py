import os
import sys

from pythonnet import load

# Use .NET Framework runtime, not .NET Core.
load("netfx")

import clr

PLUGIN_DIR = r"C:\Program Files\Oxford Instruments NanoAnalysis\Plugin"
DLL_NAME = "OINA.Plugin.AcquisitionClient"

sys.path.append(PLUGIN_DIR)

if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(PLUGIN_DIR)

clr.AddReference(DLL_NAME)

from OINA.Plugin.AcquisitionClient import Session

session = None

try:
    session = Session.Connect("127.0.0.1:22201")
    print("Connected to AZtec Plugin.")

finally:
    if session is not None:
        Session.Disconnect(session)
        print("Disconnected.")
