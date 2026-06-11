import pytribeam.types as tbt
import pytribeam.utilities as ut
import pytribeam.factory as factory

# define parameters for your specific microscope connection
connection_host = "localhost" # a string or NoneType
connection_port = None # a string or NoneType

# create the microscope object and connect to it
microscope = tbt.Microscope()
ut.connect_microscope(
    microscope=microscope,
    connection_host=connection_host,
    connection_port=connection_port,
)

# determine what application files are available on this connection
found_application_files = factory.active_fib_applications(
    microscope=microscope
) # returns a list
print("Found the following application files:")
for item in found_application_files:
    print(f"\t{item}")
    