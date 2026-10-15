import os
import sys

from pythonnet import load

load("netfx")

import System

PLUGIN_DIR = r"C:\Program Files\Oxford Instruments NanoAnalysis\Plugin"
DLL_PATH = os.path.join(PLUGIN_DIR, "OINA.Plugin.AcquisitionClient.dll")

sys.path.append(PLUGIN_DIR)

if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(PLUGIN_DIR)

assembly = System.Reflection.Assembly.LoadFrom(DLL_PATH)

for typ in sorted(assembly.GetExportedTypes(), key=lambda t: t.FullName):
    print(f"\n===== {typ.FullName} =====")

    print("Properties:")
    for prop in sorted(typ.GetProperties(), key=lambda p: p.Name):
        print(f"  {prop.PropertyType.FullName} {prop.Name}")

    print("Methods:")
    for method in sorted(typ.GetMethods(), key=lambda m: m.Name):
        if not method.IsPublic:
            continue
        if method.IsSpecialName:
            continue
        if method.DeclaringType.FullName != typ.FullName:
            continue

        params = []
        for p in method.GetParameters():
            params.append(f"{p.ParameterType.FullName} {p.Name}")

        params_text = ", ".join(params)
        print(f"  {method.ReturnType.FullName} {method.Name}({params_text})")

    print("Events:")
    for event in sorted(typ.GetEvents(), key=lambda e: e.Name):
        print(f"  {event.EventHandlerType.FullName} {event.Name}")
