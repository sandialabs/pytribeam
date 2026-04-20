"""Automated tools for serial sectioning in the SEM.

"""
try:
    from ._version import version
except ImportError:
    version = "0.0.0+unknown"

__version__ = version


# Modules to generate docs for with pdocs
__all__ = [
    "image",
    "laser",
    "fib",
    "stage",
    "insertable_devices",
    "types",
    "utilities",
    "command_line",
    "constants",
    "factory",
    "log",
    "workflow",
]
