"""Automated tools for serial sectioning in the SEM."""

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0+unknown"


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
    "doc_examples",
]
