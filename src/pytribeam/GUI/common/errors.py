"""Custom exception classes for GUI application.

This module defines a hierarchy of exceptions specific to the pytribeam GUI,
making it easier to catch and handle specific error conditions.
"""


class TriBeamGUIError(Exception):
    """Base exception for all GUI-related errors.

    All custom GUI exceptions should inherit from this class, allowing
    for broad exception catching when needed.
    """

    pass


class ConfigurationError(TriBeamGUIError):
    """Raised when configuration file operations fail.

    This includes errors in:
    - Loading configuration files
    - Parsing YAML
    - Invalid configuration structure
    - Missing required configuration fields
    """

    pass


class MicroscopeConnectionError(TriBeamGUIError):
    """Raised when microscope connection operations fail.

    This includes errors in:
    - Establishing connection to microscope
    - Communication with microscope
    - Microscope API errors
    """

    pass


class ValidationError(TriBeamGUIError):
    """Raised when configuration validation fails.

    This includes errors in:
    - Schema validation
    - Parameter range validation
    - Step configuration validation
    """

    pass


class ResourceError(TriBeamGUIError):
    """Raised when required resources are missing or inaccessible.

    This includes errors in:
    - Missing image/icon files
    - Inaccessible documentation
    - File permission issues
    """

    pass


class ExperimentError(TriBeamGUIError):
    """Raised when experiment execution encounters errors.

    This includes errors in:
    - Step execution failures
    - Stage movement errors
    - Imaging errors
    """

    pass


class ThreadError(TriBeamGUIError):
    """Raised when thread management operations fail.

    This includes errors in:
    - Thread creation
    - Thread stopping
    - Thread exception injection
    """

    pass
