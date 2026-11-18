"""Python wrapper for the Oxford Instruments AZtec Plugin API (EBSD / EDS).

Quick start::

    from oxford_aztec import AztecSession, AcquisitionConfig, AcquisitionType

    with AztecSession("127.0.0.1") as az:          # AZtec PC address, port 22201
        print(az.status())
        az.ebsd.insert()
        result = az.acquisition.run(AcquisitionConfig(AcquisitionType.EBSD_MAP), name="Map 1")
        az.data.export_acquisition_h5oina(result, r"D:\\Exports")
        az.ebsd.retract()

Use ``AztecSession.simulated()`` to develop without AZtec or .NET.
"""

from .acquisition import AcquisitionController, AcquisitionJob
from .data import DataManager
from .detectors import DetectorManager, EbsdDetector, EdsDetector
from .enums import (
    AcquisitionState,
    AcquisitionType,
    AutoLockMode,
    DataType,
    DeviceType,
    EdMappingMode,
    EdResultType,
    ExportState,
    InsertionActivity,
    InsertionPositionState,
    LineDefinitionMode,
    OperatingMode,
    OperatingState,
    StatusImageTypes,
    TiltActivity,
    TiltPositionState,
    VacuumState,
)
from .errors import (
    AcquisitionBusyError,
    AcquisitionError,
    AcquisitionTimeoutError,
    AztecConnectionError,
    AztecError,
    DataError,
    DetectorError,
    DetectorNotFoundError,
    DetectorTimeoutError,
    DotNetUnavailableError,
    ExportTimeoutError,
    InterlockError,
    NotConnectedError,
    ScanExportError,
)
from .models import (
    AcquisitionConfig,
    AcquisitionProgress,
    AcquisitionResult,
    DataItem,
    DetectorInfo,
    DetectorStatus,
    EbsdInsertionState,
    EbsdTiltState,
    EdInsertionState,
    EdsLineData,
    EdsMapData,
    EdThermalState,
    ExportResult,
    LineRegion,
    ProfileInfo,
    ProjectInfo,
    RectangleRegion,
    ScanFiles,
    ScanResult,
    SpecimenInfo,
    SystemStatus,
    TechniqueReadiness,
)
from .session import DEFAULT_PORT, AztecSession, check_port

__version__ = "0.1.0"

__all__ = [n for n in dir() if not n.startswith("_")]
