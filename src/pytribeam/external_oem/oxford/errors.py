"""Exception hierarchy. Every error raised by this package derives from AztecError."""


class AztecError(Exception):
    """Base class for all errors raised by oxford_aztec."""


class DotNetUnavailableError(AztecError):
    """pythonnet or the AZtec Plugin assemblies could not be loaded."""


class AztecConnectionError(AztecError):
    """Could not connect to AZtec, or the connection was lost."""


class NotConnectedError(AztecConnectionError):
    """An operation needs a live session but the session is not connected."""


class AcquisitionError(AztecError):
    """An acquisition could not be started, or finished in an error state."""

    def __init__(self, message, result=None):
        super().__init__(message)
        #: The AcquisitionResult, when the failure came from a finished acquisition.
        self.result = result


class AcquisitionBusyError(AcquisitionError):
    """An acquisition is already running on this client."""


class AcquisitionTimeoutError(AcquisitionError):
    """An acquisition did not finish within the allowed time."""


class DetectorError(AztecError):
    """A detector command was refused or the detector reported a fault."""


class DetectorNotFoundError(DetectorError):
    """No detector of the requested type or name is available."""


class DetectorTimeoutError(DetectorError):
    """A detector did not reach its target state within the allowed time."""


class InterlockError(DetectorError):
    """A user-supplied interlock blocked a detector motion."""


class DataError(AztecError):
    """A project/data operation (export, lookup, ...) failed."""


class ExportTimeoutError(DataError):
    """An export did not report completion within the allowed time."""


class ScanExportError(DataError):
    """A scan was acquired but exporting one or more of its maps failed.
    ``scan_result`` lists the files that were exported."""

    def __init__(self, message, scan_result=None):
        super().__init__(message)
        self.scan_result = scan_result
