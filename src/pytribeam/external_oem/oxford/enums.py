"""Python mirrors of the AZtec Plugin .NET enums.

Values are copied verbatim from the metadata of ``OINA.Plugin.AcquisitionClient.dll``
(v6.1.0.0) so they can be converted to/from the .NET types by integer value.
Member names are the .NET names converted to UPPER_SNAKE_CASE.
"""

from enum import IntEnum, IntFlag
from typing import TypeVar

E = TypeVar("E", bound=IntEnum)


def coerce(enum_cls, value, default=0):
    """Convert an int-like (Python int or .NET enum) to ``enum_cls``.

    Unknown values map to ``enum_cls(default)`` rather than raising, so a newer
    AZtec server reporting a value we don't know about can't crash a status poll.
    """
    try:
        return enum_cls(int(value))
    except (ValueError, TypeError):
        return enum_cls(default)


# --- Acquisition ----------------------------------------------------------


class AcquisitionType(IntFlag):
    """Techniques to acquire. Flags may be combined to sequence acquisitions."""

    NONE = 0
    ELECTRON_IMAGE = 1
    EDS_MAP = 2
    EBSD_MAP = 4


class StatusImageTypes(IntFlag):
    """Image types returned in the acquisition result."""

    NONE = 0
    ELECTRON_IMAGE = 1
    EDS_MAP = 2
    EBSD_MAP = 4


class AutoLockMode(IntEnum):
    """Drift correction (AutoLock) mode."""

    OFF = 0
    AUTO = 1
    CUSTOM = 2
    USE_CURRENT_DRIFT_SETTINGS = 3


class AcquisitionState(IntEnum):
    UNKNOWN = 0
    COMPLETED = 1
    ERROR = 2
    STARTED = 3


class LineDefinitionMode(IntEnum):
    POINTS = 0
    SEPARATION = 1
    USE_AZTEC_SETTINGS = 2


class EdResultType(IntEnum):
    UNKNOWN = 0
    COUNTS_PER_SECOND = 1
    COUNTS = 2
    WEIGHT_PERCENT = 3
    ATOMIC_PERCENT = 4


class EdMappingMode(IntEnum):
    UNKNOWN = 0
    WINDOW_INTEGRAL = 1
    TRU_MAP = 2
    QUANT_MAP = 3


# --- Project data -----------------------------------------------------------


class DataType(IntEnum):
    UNKNOWN = 0
    PROJECT = 1
    SPECIMEN = 2
    SITE = 3
    ED_SPECTRUM = 4
    ED_MAP = 5
    ED_LINE = 6
    EBSD_MAP = 7
    EBSD_LINE = 8
    MAP_ACQUIRE = 9


class ExportState(IntEnum):
    UNKNOWN = 0
    COMPLETED = 1
    ERROR = 2
    TIMED_OUT = 3


class ProjectChangeState(IntEnum):
    OPENED = 0
    CLOSED = 1
    FAILED = 2
    ERROR = 3
    SPECIMEN_ADDED = 4


class ProfileChangeState(IntEnum):
    LOADED = 0
    DELETED = 1
    FAILED = 2
    ERROR = 3


# --- Detector control -------------------------------------------------------


class DeviceType(IntEnum):
    UNKNOWN = 0
    ED = 1
    EBSD = 2


class InsertionActivity(IntEnum):
    UNKNOWN = 0
    NOT_MOVING = 1
    MOVING_IN = 2
    MOVING_OUT = 3
    AUTO_RETRACTING = 4
    HOMING = 5


class InsertionPositionState(IntEnum):
    UNKNOWN = 0
    IN = 1
    OUT = 2
    INDETERMINATE = 3
    FAULT = 4
    AUTO_RETRACTED = 5
    REFERENCE_POSITION = 6
    INTERMEDIATE = 7


class TiltActivity(IntEnum):
    UNKNOWN = 0
    NOT_MOVING = 1
    TILTING_DOWN = 2
    TILTING_UP = 3
    HOMING = 4


class TiltPositionState(IntEnum):
    UNKNOWN = 0
    ABOVE_HOME_KNOWN = 1
    ABOVE_HOME_UNKNOWN = 2
    BELOW_HOME_KNOWN = 3
    BELOW_HOME_UNKNOWN = 4
    BOTTOM = 5
    DOWNWARDS_SOFT_LIMIT = 6
    FAULT = 7
    HOME = 8
    TOP = 9
    UPWARDS_SOFT_LIMIT = 10


class OperatingMode(IntEnum):
    UNKNOWN = 0
    MANUAL = 1
    AUTOMATIC = 2
    STANDBY = 3


class OperatingState(IntEnum):
    UNKNOWN = 0
    INITIALISING = 1
    MANUAL_CONTROL = 2
    STANDBY = 3
    WARMING = 4
    WARM = 5
    COOLING = 6
    COLD = 7
    FAULT = 8


class VacuumState(IntEnum):
    UNKNOWN = 0
    VENTED = 1
    UNDER_VACUUM = 2


#: Python enum class name -> .NET type name (namespace-relative to
#: ``OINA.Plugin.AcquisitionClient``). Used by the .NET adapter.
NET_ENUM_TYPES = {
    "AcquisitionType": "AcquisitionType",
    "StatusImageTypes": "StatusImageTypes",
    "AutoLockMode": "AutoLockMode",
    "AcquisitionState": "AcquisitionState",
    "LineDefinitionMode": "LineDefinitionMode",
    "EdResultType": "EdResultType",
    "EdMappingMode": "Ed.EdMappingMode",
    "DataType": "Data.DataType",
    "ExportState": "Data.ExportState",
    "ProjectChangeState": "ProjectChangeState",
    "ProfileChangeState": "ProfileChangeState",
    "DeviceType": "DetectorControl.DeviceType",
    "InsertionActivity": "DetectorControl.State.InsertionActivity",
    "InsertionPositionState": "DetectorControl.State.InsertionPositionState",
    "TiltActivity": "DetectorControl.State.TiltActivity",
    "TiltPositionState": "DetectorControl.State.TiltPositionState",
    "OperatingMode": "DetectorControl.State.OperatingMode",
    "OperatingState": "DetectorControl.State.OperatingState",
    "VacuumState": "DetectorControl.State.VacuumState",
}
