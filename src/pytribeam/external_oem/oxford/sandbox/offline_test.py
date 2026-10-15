import os
import sys

from pythonnet import load

load("netfx")

import clr
import System

PLUGIN_DIR = r"C:\Program Files\Oxford Instruments NanoAnalysis\Plugin"

sys.path.append(PLUGIN_DIR)

if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(PLUGIN_DIR)

clr.AddReference("OINA.Plugin.AcquisitionClient")

from OINA.Plugin.AcquisitionClient import Session
from OINA.Plugin.AcquisitionClient.DetectorControl import DeviceType

session = None

try:
    session = Session.Connect("127.0.0.1:22201")

    print("Connected")
    print("Client version:", session.ClientVersion)
    print("Server version:", session.ServerVersion)

    detector_client = session.GetDetectorControlClient()

    print("Detector control connected:", detector_client.IsConnected())

    print("\nDeviceType enum values:")
    for name in System.Enum.GetNames(DeviceType):
        value = System.Enum.Parse(DeviceType, name)
        print(f"  {name} = {int(value)}")

    print("\nAll devices:")
    devices = list(detector_client.GetDevices())
    print(f"Found {len(devices)} devices")
    for d in devices:
        print("----")
        print("ID:", d.ID)
        print("DisplayName:", d.DisplayName)
        print("DeviceType:", d.DeviceType)

    print("\nDevices by type:")
    for name in System.Enum.GetNames(DeviceType):
        value = System.Enum.Parse(DeviceType, name)
        try:
            typed_devices = list(detector_client.GetDevices(value))
            print(f"{name}: {len(typed_devices)} devices")
            for d in typed_devices:
                print("----")
                print("ID:", d.ID)
                print("DisplayName:", d.DisplayName)
                print("DeviceType:", d.DeviceType)
        except Exception as exc:
            print(f"{name}: query failed: {exc}")

finally:
    if session is not None:
        Session.Disconnect(session)
