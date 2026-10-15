import os
import sys

from pythonnet import load

load("netfx")

import clr

PLUGIN_DIR = r"C:\Program Files\Oxford Instruments NanoAnalysis\Plugin"

sys.path.append(PLUGIN_DIR)

if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(PLUGIN_DIR)

clr.AddReference("System.ServiceModel")
clr.AddReference("OINA.Plugin.AcquisitionClient")

from OINA.Plugin.AcquisitionClient.DetectorControl.WCF import (
    IDetectorControlControl,
)
from System import TimeSpan
from System.ServiceModel import (
    ChannelFactory,
    EndpointAddress,
    NetTcpBinding,
)

endpoint = "net.tcp://localhost:21201/ed/ed_simulator1"

binding = NetTcpBinding()
binding.OpenTimeout = TimeSpan.FromSeconds(5)
binding.CloseTimeout = TimeSpan.FromSeconds(5)
binding.SendTimeout = TimeSpan.FromSeconds(10)
binding.ReceiveTimeout = TimeSpan.FromSeconds(10)

factory = None

try:
    factory = ChannelFactory[IDetectorControlControl](
        binding,
        EndpointAddress(endpoint),
    )

    channel = factory.CreateChannel()

    print("Calling Connect()")
    print("Connect returned:", channel.Connect())

    print("IsConnected:", channel.IsConnected())

    print("Calling GetDevices()")
    devices = list(channel.GetDevices())

    print(f"Found {len(devices)} devices from direct endpoint")

    for d in devices:
        print("----")
        print("ID:", d.ID)
        print("DisplayName:", d.DisplayName)
        print("DeviceType:", d.DeviceType)

except Exception as exc:
    print("Direct WCF endpoint probe failed:")
    print(type(exc))
    print(exc)

finally:
    if factory is not None:
        try:
            factory.Close()
        except Exception:
            factory.Abort()
