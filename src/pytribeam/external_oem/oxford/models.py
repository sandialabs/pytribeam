"""Plain-Python data models returned by and passed to the wrapper.

Nothing in here touches .NET; conversion happens in the controller modules.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .enums import (
    AcquisitionState,
    AcquisitionType,
    AutoLockMode,
    DataType,
    DeviceType,
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


def _check_unit(name, value):
    if not 0.0 <= value <= 1.0:
        raise ValueError(
            "%s must be a normalized coordinate in [0, 1], got %r" % (name, value)
        )


# --- Regions ---------------------------------------------------------------


@dataclass(frozen=True)
class RectangleRegion:
    """Rectangular acquisition region in normalized field-of-view coordinates (0-1).

    (x, y) is the top-left corner. Pass ``None`` as the region to acquire the full field.
    """

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self):
        for n in ("x", "y", "width", "height"):
            _check_unit(n, getattr(self, n))
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be > 0")
        if self.x + self.width > 1.0 + 1e-9 or self.y + self.height > 1.0 + 1e-9:
            raise ValueError("region extends outside the field of view")

    @classmethod
    def centered(cls, width: float, height: float, cx: float = 0.5, cy: float = 0.5):
        """Region of the given normalized size centred on (cx, cy)."""
        return cls(cx - width / 2.0, cy - height / 2.0, width, height)


@dataclass(frozen=True)
class LineRegion:
    """Line acquisition region (EDS linescans), normalized coordinates (0-1).

    ``point_separation_um`` is in micrometres. With ``definition=USE_AZTEC_SETTINGS``
    (the default) AZtec's current line settings decide the sampling.
    """

    x: float
    y: float
    x2: float
    y2: float
    max_points: Optional[int] = None
    point_separation_um: Optional[float] = None
    definition: LineDefinitionMode = LineDefinitionMode.USE_AZTEC_SETTINGS

    def __post_init__(self):
        for n in ("x", "y", "x2", "y2"):
            _check_unit(n, getattr(self, n))
        if self.definition == LineDefinitionMode.POINTS and not self.max_points:
            raise ValueError("definition=POINTS requires max_points")
        if (
            self.definition == LineDefinitionMode.SEPARATION
            and not self.point_separation_um
        ):
            raise ValueError("definition=SEPARATION requires point_separation_um")


# --- Acquisition --------------------------------------------------------------


@dataclass
class AcquisitionConfig:
    """Settings for a plugin-driven acquisition.

    Any field left as ``None`` is not sent, so the value already held by the
    acquisition client (or AZtec's default) applies.

    Note: technique settings such as step size, dwell time, frame count or map
    resolution are NOT part of the plugin API. AZtec uses its current settings for
    each technique; switch them with :meth:`AcquisitionController.load_profile`.
    """

    acquisition_type: AcquisitionType = AcquisitionType.EBSD_MAP
    region: Optional[Any] = None  # RectangleRegion | LineRegion | None (full field)
    site_name: Optional[str] = None  # None: keep client's current setting
    use_current_site: bool = False  # True: acquire into the site selected in AZtec
    project_id: Optional[uuid.UUID] = (
        None  # None: the project selected in the AZtec data tree
    )
    specimen_id: Optional[uuid.UUID] = (
        None  # None: the specimen selected in the AZtec data tree
    )
    auto_lock: Optional[AutoLockMode] = None
    status_images: Optional[StatusImageTypes] = None
    master_site_number: Optional[int] = None
    auto_increment_site_number: Optional[bool] = None
    reset_acquisition_number_for_each_site: Optional[bool] = None
    site_thickness_um: Optional[float] = None
    auto_contrast_brightness: Optional[bool] = None
    english_image_names: Optional[bool] = None

    def __post_init__(self):
        self.acquisition_type = AcquisitionType(self.acquisition_type)
        if self.acquisition_type == AcquisitionType.NONE:
            raise ValueError("acquisition_type must include at least one technique")
        if self.use_current_site and self.site_name:
            raise ValueError("use site_name or use_current_site, not both")
        if self.region is not None and not isinstance(
            self.region, (RectangleRegion, LineRegion)
        ):
            raise TypeError("region must be a RectangleRegion, LineRegion or None")


@dataclass(frozen=True)
class AcquisitionProgress:
    percent: int
    seconds_remaining: int


@dataclass
class AcquisitionResult:
    """Outcome of one plugin acquisition (from the .NET ``AcquisitionStatus``)."""

    state: AcquisitionState
    item_name: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    eds_map_id: Optional[uuid.UUID] = None
    ebsd_map_id: Optional[uuid.UUID] = None
    #: Encoded image bytes (format decided by AZtec), keyed "electron_image" | "eds_map" | "ebsd_map".
    images: Dict[str, bytes] = field(default_factory=dict, repr=False)
    acquisition_type: AcquisitionType = AcquisitionType.NONE
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    #: True if a map id was missing from AZtec's status and recovered from the data tree.
    ids_from_tree: bool = False

    @property
    def ok(self) -> bool:
        return self.state == AcquisitionState.COMPLETED

    @property
    def duration_s(self) -> Optional[float]:
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at


# --- Project data --------------------------------------------------------------


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    id: Optional[uuid.UUID]
    file_name: Optional[str] = None


@dataclass(frozen=True)
class SpecimenInfo:
    name: str
    id: Optional[uuid.UUID]
    project_id: Optional[uuid.UUID]


@dataclass(frozen=True)
class ProfileInfo:
    name: str
    id: Optional[uuid.UUID]
    description: Optional[str] = None


@dataclass
class DataItem:
    """A node in the AZtec data tree (project, specimen, site, map, spectrum...)."""

    id: Optional[uuid.UUID]
    data_type: DataType
    label: str
    #: The underlying .NET IDataItem, needed to pass the item back to AZtec.
    native: Any = field(default=None, repr=False, compare=False)


@dataclass
class ExportResult:
    state: ExportState
    path: Optional[str] = None
    message: Optional[str] = None
    items: List[DataItem] = field(default_factory=list)
    data_type: Optional[DataType] = None
    #: h5oina.H5oinaSummary when the file was visible locally and verified, else None.
    inspection: Any = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return self.state == ExportState.COMPLETED


@dataclass
class ScanFiles:
    """Files AZtec wrote for one map, in the project's ``data`` folder (paths as seen
    by the AZtec PC). EBSD maps have a pattern file (.ebsp); EDS maps don't."""

    map_id: uuid.UUID
    scan: str
    patterns: Optional[str] = None
    technique: str = "ebsd"  # "ebsd" | "eds"
    #: True/False if the .ebsp was checked from this machine; None if not visible / not EBSD.
    patterns_present: Optional[bool] = None
    patterns_size_bytes: Optional[int] = None
    export: Optional["ExportResult"] = field(default=None, repr=False)


@dataclass
class ScanResult:
    """Outcome of :meth:`AztecSession.scan`: the acquisition plus every exported map."""

    description: str
    acquisition: "AcquisitionResult"
    files: List[ScanFiles] = field(default_factory=list)

    @property
    def ebsd(self) -> Optional[ScanFiles]:
        return next((f for f in self.files if f.technique == "ebsd"), None)

    @property
    def eds(self) -> Optional[ScanFiles]:
        return next((f for f in self.files if f.technique == "eds"), None)

    @property
    def paths(self) -> List[str]:
        """Every file path (scan files and pattern files)."""
        out = []
        for f in self.files:
            out.append(f.scan)
            if f.patterns:
                out.append(f.patterns)
        return out


@dataclass
class EdsMapData:
    """EDS element maps. ``elements`` maps element/line name -> 2-D array (height, width)."""

    id: Optional[uuid.UUID]
    name: str
    width: int
    height: int
    result_type: EdResultType
    elements: Dict[str, Any] = field(repr=False)  # numpy arrays
    region: Optional[RectangleRegion] = None


@dataclass
class EdsLineData:
    """EDS linescan. ``elements`` maps element name -> 1-D array; ``points`` are the sample positions."""

    id: Optional[uuid.UUID]
    name: str
    result_type: EdResultType
    points: Any = field(repr=False)
    elements: Dict[str, Any] = field(repr=False)
    region: Optional[LineRegion] = None


# --- Detectors ------------------------------------------------------------------


@dataclass(frozen=True)
class DetectorInfo:
    id: str
    name: str
    device_type: DeviceType


@dataclass(frozen=True)
class EbsdInsertionState:
    position_mm: float
    activity: InsertionActivity
    state: InsertionPositionState
    is_touching: bool
    has_touch_sensor: bool
    can_drive_in: bool
    can_drive_out: bool
    can_stop: bool
    can_move_to: bool


@dataclass(frozen=True)
class EbsdTiltState:
    position_mm: float
    activity: TiltActivity
    state: TiltPositionState
    can_drive_up: bool
    can_drive_down: bool
    can_stop: bool
    can_move_to: bool


@dataclass(frozen=True)
class EdInsertionState:
    activity: InsertionActivity
    state: InsertionPositionState
    can_drive_in: bool
    can_drive_out: bool
    can_stop: bool


@dataclass(frozen=True)
class EdThermalState:
    operating_mode: OperatingMode
    operating_state: OperatingState
    vacuum_state: VacuumState
    has_vacuum_sensor: bool
    can_operate: bool
    can_standby: bool


@dataclass
class DetectorStatus:
    """Snapshot of one detector. Fields not supported by the hardware are None."""

    info: DetectorInfo
    insertion: Any = None  # EbsdInsertionState | EdInsertionState
    tilt: Optional[EbsdTiltState] = None
    proximity_sensor_enabled: Optional[bool] = None
    thermal: Optional[EdThermalState] = None
    error: Optional[str] = None


@dataclass
class TechniqueReadiness:
    """AZtec's own readiness report for a technique (``Session.GetDetectorStatus``)."""

    ready: Optional[bool]
    description: Optional[str]


@dataclass
class SystemStatus:
    """Aggregated connection + detector status. Collecting it never raises;
    problems encountered while polling are listed in ``errors``."""

    connected: bool
    address: str
    client_version: Optional[str] = None
    server_version: Optional[str] = None
    eds: Optional[TechniqueReadiness] = None
    ebsd: Optional[TechniqueReadiness] = None
    detectors: List[DetectorStatus] = field(default_factory=list)
    current_site: Optional[str] = None
    acquisition_running: bool = False
    errors: List[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return self.connected and not self.errors
