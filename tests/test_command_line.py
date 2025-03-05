""""This module tests the command_line services.
"""

# from pytribeam import command_line as cl
from pytribeam import command_line as cl
from pytribeam import constants as cs
from importlib.metadata import version


def test_version():
    """Tests that the module version is returned."""
    pass  # TODO
    # known_version = version(cs.Constants().module_short_name)

    # found_version = cl.module_info()
    # assert found_version == known_version
