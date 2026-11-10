
from pytribeam import types as tbt
from pytribeam import utilities as ut
from autoscript_sdb_microscope_client import structures

# HOST = "134.252.9.187"
HOST = "192.168.0.1"
PORT = 7520

microscope = tbt.Microscope()

print("Connecting")
ut.connect_microscope(
    microscope,
    quiet_output=False,
    connection_host=HOST,
    connection_port=PORT
)

print("Connected")
print("Active device:", microscope.imaging.get_active_device())

print(microscope.detector.type.available_values)

ut.disconnect_microscope(microscope, quiet_output=False)

print("Complete")
