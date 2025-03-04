# Default python modules
from typing import NamedTuple, List, Union
from enum import Enum, IntEnum
from pathlib import Path

# Autoscript modules
from autoscript_sdb_microscope_client import SdbMicroscopeClient
import autoscript_sdb_microscope_client.enumerations as as_enums
import autoscript_sdb_microscope_client.structures as as_structs
import autoscript_sdb_microscope_client._dynamic_object_proxies as as_dynamics


### BASE CLASSES


class AdornedImage(as_structs.AdornedImage):
    pass


class AngularCorrectionMode(as_enums.AngularCorrectionMode):
    pass


class Limit(NamedTuple):
    """Limit range for a value"""

    min: float  # | int
    max: float  # | int


class BeamType(Enum):
    """Specific enumerated beam types"""

    ELECTRON: str = "electron"
    ION: str = "ion"


class BeamSettings(NamedTuple):
    """Settings for generic Beam types

    Attributes:
        voltage_kv: float
        current_na: float
        hfw_mm: float
        working_dist_mm: float
        voltage_tol_kv: float
        current_tol_na: float

    """

    # read from microscope:
    voltage_kv: float = None
    current_na: float = None
    hfw_mm: float = None
    working_dist_mm: float = None
    # use relative values for default tolerances
    voltage_tol_kv: float = None
    current_tol_na: float = None
    # ebeam only:
    dynamic_focus: bool = None
    tilt_correction: bool = None


class StreamDepth(IntEnum):
    """but depth of stream patterns"""

    # BITS_12 = 12 #no longer supported by TFS
    BITS_16 = 16


class ColorDepth(IntEnum):
    """bit depth of images"""

    BITS_8 = 8
    BITS_16 = 16


class CoordinateReference(Enum):
    """enum of coordinate reference frames used for laser milling operations.

    Tiling support planned for future release"""

    CENTER: str = "center"
    UPPER_CENTER: str = "uppercenter"
    UPPER_LEFT: str = "upperleft"


class DetectorMode(Enum):
    """enum adapter for autoscript DetectorMode enum"""

    ALL: str = as_enums.DetectorMode.ALL
    A_MINUS_B: str = as_enums.DetectorMode.A_MINUS_B
    ANGULAR: str = as_enums.DetectorMode.ANGULAR
    ANGULAR_PARTIAL: str = as_enums.DetectorMode.ANGULAR_PARTIAL
    ANGULAR_PARTIAL_COMPLEMENT: str = as_enums.DetectorMode.ANGULAR_PARTIAL_COMPLEMENT
    ANULAR_A: str = as_enums.DetectorMode.ANULAR_A
    ANULAR_B: str = as_enums.DetectorMode.ANULAR_B
    ANULAR_C: str = as_enums.DetectorMode.ANULAR_C
    ANULAR_D: str = as_enums.DetectorMode.ANULAR_D
    A_PLUS_B: str = as_enums.DetectorMode.A_PLUS_B
    BACKSCATTER_ELECTRONS: str = as_enums.DetectorMode.BACKSCATTER_ELECTRONS
    BEAM_DECELERATION: str = as_enums.DetectorMode.BEAM_DECELERATION
    BRIGHT_FIELD: str = as_enums.DetectorMode.BRIGHT_FIELD
    CATHODO_LUMINESCENCE: str = as_enums.DetectorMode.CATHODO_LUMINESCENCE
    CHARGE_NEUTRALIZATION: str = as_enums.DetectorMode.CHARGE_NEUTRALIZATION
    CUSTOM: str = as_enums.DetectorMode.CUSTOM
    CUSTOM2: str = as_enums.DetectorMode.CUSTOM2
    CUSTOM3: str = as_enums.DetectorMode.CUSTOM3
    CUSTOM4: str = as_enums.DetectorMode.CUSTOM4
    CUSTOM5: str = as_enums.DetectorMode.CUSTOM5
    DARK_FIELD: str = as_enums.DetectorMode.DARK_FIELD
    DARK_FIELD1: str = as_enums.DetectorMode.DARK_FIELD1
    DARK_FIELD2: str = as_enums.DetectorMode.DARK_FIELD2
    DARK_FIELD3: str = as_enums.DetectorMode.DARK_FIELD3
    DARK_FIELD4: str = as_enums.DetectorMode.DARK_FIELD4
    DOWN_HOLE_VISIBILITY: str = as_enums.DetectorMode.DOWN_HOLE_VISIBILITY
    HIGH_ANGLE: str = as_enums.DetectorMode.HIGH_ANGLE
    INNER_MINUS_OUTER: str = as_enums.DetectorMode.INNER_MINUS_OUTER
    LOW_ANGLE: str = as_enums.DetectorMode.LOW_ANGLE
    MIX: str = as_enums.DetectorMode.MIX
    NONE: str = as_enums.DetectorMode.NONE
    SCINTILLATION: str = as_enums.DetectorMode.SCINTILLATION
    SECONDARY_ELECTRONS: str = as_enums.DetectorMode.SECONDARY_ELECTRONS
    SECONDARY_IONS: str = as_enums.DetectorMode.SECONDARY_IONS
    SEGMENT_A: str = as_enums.DetectorMode.SEGMENT_A
    SEGMENT_B: str = as_enums.DetectorMode.SEGMENT_B
    TOPOGRAPHY: str = as_enums.DetectorMode.TOPOGRAPHY
    Z_CONTRAST: str = as_enums.DetectorMode.Z_CONTRAST


class DetectorType(Enum):
    """enum adapter for autoscript DetectorType enum"""

    ABS: str = as_enums.DetectorType.ABS
    BSD: str = "BSD"
    CBS: str = as_enums.DetectorType.CBS
    CDEM: str = as_enums.DetectorType.CDEM
    CRD: str = "CRD"
    DUAL_BSD: str = "DualBSD"
    EBSD: str = "EBSD"
    EDS: str = "EDS"
    ECD: str = as_enums.DetectorType.ECD
    ETD: str = as_enums.DetectorType.ETD
    EXTERNAL: str = as_enums.DetectorType.EXTERNAL
    GAS: str = "GAD"
    GBSD: str = as_enums.DetectorType.GBSD
    GSED: str = as_enums.DetectorType.GSED
    HIRES_OPTICAL: str = "HiResOptical"
    HIRES_OPTICAL_LO_MAG: str = "HiResOpticalLowMag"
    ICE: str = as_enums.DetectorType.ICE
    IN_COLUMN_BSD: str = "InColumnBSD"
    IR: str = "IR"
    IR2: str = "IR2"
    IR_CAMERA: str = "IRCameraDetector"
    LFD: str = as_enums.DetectorType.LFD
    LVD: str = as_enums.DetectorType.LVD
    LVSED: str = as_enums.DetectorType.LVSED
    MD: str = as_enums.DetectorType.MD
    MIX: str = as_enums.DetectorType.MIX
    NONE: str = as_enums.DetectorType.NONE
    PMT: str = "PMT"
    QUAD_BSD: str = "QuadBSD"
    SED: str = "SED"
    SINGLE_BSD: str = "SingleBSD"
    STEM3: str = as_enums.DetectorType.STEM3
    STEM3_PLUS: str = as_enums.DetectorType.STEM3_PLUS
    STEM4: str = as_enums.DetectorType.STEM4
    T1: str = as_enums.DetectorType.T1
    T2: str = as_enums.DetectorType.T2
    T3: str = as_enums.DetectorType.T3
    TLD: str = as_enums.DetectorType.TLD
    TLD2: str = "TLD2"


class Device(IntEnum):
    """enum adapter for autoscript ImagingDevice enum"""

    ELECTRON_BEAM = as_enums.ImagingDevice.ELECTRON_BEAM
    ION_BEAM = as_enums.ImagingDevice.ION_BEAM
    CCD_CAMERA = as_enums.ImagingDevice.CCD_CAMERA
    IR_CAMERA = as_enums.ImagingDevice.IR_CAMERA
    NAV_CAM = as_enums.ImagingDevice.NAV_CAM
    OPTICAL_MICROSCOPE = as_enums.ImagingDevice.OPTICAL_MICROSCOPE
    VOLUMESCOPE_APPROACH_CAMERA = as_enums.ImagingDevice.VOLUMESCOPE_APPROACH_CAMERA


class DummyFile(object):
    """To suppress excessive printing"""

    def write(selfself, x):
        pass


class ExternalDeviceOEM(Enum):
    """Specific EBSD and EDS OEMS supported for collection"""

    OXFORD: str = "Oxford"
    EDAX: str = "EDAX"
    NONE: str = None


# TODO remove this class and fix references
# class FIBApplication(Enum):
#     AL: str = "Al"
#     AL_DEP: str = "Al dep"
#     AU_E_DEP: str = "Au e-dep"
#     AU: str = "Au"
#     C_DEP_HIGH: str = "C dep high"
#     C_DEP: str = "C dep"
#     C_E_DEP_SURFACE: str = "C e-dep surface"
#     DEL_ETCH: str = "Del etch"
#     ENH_ETCH: str = "Enh etch"
#     FE2O3: str = "Fe2O3"
#     GAAS: str = "GaAs"
#     I_DEP2: str = "Idep2"
#     IEE: str = "IEE"
#     INP: str = "InP"
#     PMM: str = "PMMA"
#     PT_DEP: str = "Pt dep"
#     PT_DEP_STRUCTURES: str = "Pt dep structures"
#     PT_DEP_SURFACE: str = "Pt dep surface"
#     SCE: str = "SCE"
#     SI3: str = "Si3"
#     SI: str = "Si"
#     SI_SMALL: str = "Si_small"
#     SI_CCS: str = "Si-ccs"
#     SI_MULTIPASS: str = "Si-multipass"
#     W_DEP_HIGH: str = "W dep high"
#     W_DEP: str = "W dep"
#     W_E_DEP_SURFACE: str = "W e-dep surface"


class FIBPatternType(Enum):
    RECTANGLE: str = "rectangle"
    REGULAR_CROSS_SECTION: str = "regular_cross_section"
    CLEANING_CROSS_SECTION: str = "cleaning_cross_section"
    SELECTED_AREA: str = "selected_area"


class FIBPatternScanDirection(Enum):
    """Replaces Thermo Fisher PatternScanDirection enumeration, which does not work as a pythonic enum class"""

    BOTTOM_TO_TOP: str = "BottomToTop"
    DYNAMIC_ALL_DIRECTIONS: str = "DynamicAllDirections"
    DYNAMIC_INNER_TO_OUTER: str = "DynamicInnerToOuter"
    DYNAMIC_LEFT_TO_RIGHT: str = "DynamicLeftToRight"
    DYNAMIC_TOP_TO_BOTTOM: str = "DynamicTopToBottom"
    INNER_TO_OUTER: str = "InnerToOuter"
    LEFT_TO_RIGHT: str = "LeftToRight"
    OUTER_TO_INNER: str = "OuterToInner"
    RIGHT_TO_LEFT: str = "RightToLeft"
    TOP_TO_BOTTOM: str = "TopToBottom"


class FIBPatternScanType(Enum):
    """Replaces Thermo Fisher PatternScanType enumeration, which does not work as a pythonic enum class"""

    RASTER: str = "Raster"
    SERPENTINE: str = "Serpentine"
    CIRCULAR: str = "Circular"  # TODO not yet supported by pyTriBeam


class FocusPlaneGrid(NamedTuple):
    """Settings for performing a focus grid to fit plane for image tiling.
    Uses same coordinate reference as requested for tiling operation"""

    num_grid_points_x: int
    num_grid_points_y: int
    grid_dx_um: float
    grid_dy_um: float


class GrabFrameSettings(as_structs.GrabFrameSettings):
    """Class adapter for autoscript GrabFrameSettings"""

    pass


class ImageFileFormat(Enum):
    """Enum adapter for autoscript ImageFileFormat"""

    RAW: str = as_enums.ImageFileFormat.RAW
    TIFF: str = as_enums.ImageFileFormat.TIFF


class ImageTileSettings(NamedTuple):
    """Settings for image tiling operations"""

    tile_origin: CoordinateReference
    length_x_mm: float
    length_y_mm: float
    overlap_frac_x: float
    overlap_frac_y: float
    focus_plane_grid: FocusPlaneGrid


class IntervalType(Enum):
    """Enumerated interval types for limit checking"""

    OPEN: str = "open"
    """
    Fully-open interval (a,b), does not include endpoints
    """
    CLOSED: str = "closed"
    """
    Fully-closed interval [a,b], includes both endpoints
    """
    LEFT_OPEN: str = "left_open"
    """
    Half-open interval on left side (a,b], does not include 'a'
    """
    RIGHT_OPEN: str = "right_open"
    """
    Half-open interval on right side [a,b), does not include 'b'
    """


class LaserPatternMode(Enum):
    COARSE: str = "coarse"
    FINE: str = "fine"


class LaserWavelength(IntEnum):
    NM_515 = 515
    NM_1030 = 1030


class Point(as_structs.Point):
    """Adapter class"""

    pass


class ProtectiveShutterMode(as_enums.ProtectiveShutterMode):
    """Adapter class"""

    pass


class MapStatus(Enum):
    """Map status for EBSD or EDS"""

    ACTIVE = "Active"
    IDLE = "Idle"
    ERROR = "Error"


class Microscope(SdbMicroscopeClient):
    """Class adapter for autoscript SdbMicroscopeClient.
    Can add functionality with inheritance and super() in init, commented out below"""

    # def __init__(self):
    #     super().__init__()

    pass


class MicroscopeConnection(NamedTuple):
    """connection to initialize microscope object"""

    host: str
    port: int = None


class PretiltAngleDegrees(NamedTuple):
    """Specimen pretilt as measured with regard to the electron beam normal direction.
    For example, when facing the front of the microscope (chamber door),
    the laser is installed at 60 degrees clockwise from the electron beam.
    A specimen at pretilt = 36 degrees would tilt the T-axis to -6 degrees for laser parallel
    machining (glancing-angle), and either -96 degrees or -84 degrees after a
    180 degree rotation about the R-axis for laser normal machining (drilling).
    As -96 and -84 degrees are beyond the scope of the stage limits,
    laser drilling operations are not achievable with a pretilt of -36 degrees.

    Importantly, this convention differs from that of ThermoFisher, which instead considers this
    configuration to be a 54 degree pre-tilt (the complement of the angle used here)

    Value must be in degrees."""

    value: float


class Resolution(NamedTuple):
    """Abritrary scan resolution, with limits of (12 <= input <= 65536)"""

    width: int
    height: int

    @property
    def value(self) -> str:
        return f"{self.width}x{self.height}"


class RetractableDeviceState(Enum):
    """enum adapter for autoscript RetractableDeviceState enum"""

    BUSY: str = as_enums.RetractableDeviceState.BUSY
    ERROR: str = as_enums.RetractableDeviceState.ERROR
    INSERTED: str = as_enums.RetractableDeviceState.INSERTED
    OTHER: str = as_enums.RetractableDeviceState.OTHER
    RETRACTED: str = as_enums.RetractableDeviceState.RETRACTED
    INDERTERMINATE: str = "Indeterminate"  # For Oxford EBSD and EDS detectors
    CONNECTED: str = "Connected"  # For laser status


class DeviceStatus(NamedTuple):
    laser: RetractableDeviceState
    ebsd: RetractableDeviceState
    eds: RetractableDeviceState

    def __str__(self):
        return f'Laser: "{self.laser.value}"\nEBSD Detector: "{self.ebsd.value}"\nEDS Detector: "{self.eds.value}"'


class RotationSide(Enum):
    """enum for specific rotation sides.
    Requried to accurately move stage during sectioning.

    While sectioning along the Z axis with a pretilted specimen,
    stage will move along the raw negative Y axis on FSL_MILL side (toward the laser),
    but along the raw positive Y axis on FIB_MILL side (toward the FIB).

    EBEAM_NORMAL can be used when Y axis corrections are not required during Z-axis
    sectioning, as for pretilted specimens during operations that require a constant
    X or Y position independent of slice number, as for reference fiducials for
    rotation corrections."""

    FSL_MILL: str = "fsl_mill"
    FIB_MILL: str = "fib_mill"
    EBEAM_NORMAL: str = "ebeam_normal"


class ScanArea(NamedTuple):
    """Reduced scan area box, coordinate range in [0,1] from top left corner"""

    # TODO check what (left + width > 1) or (top + height > 1) will do
    left: float
    top: float
    width: float
    height: float


class ScanMode(IntEnum):
    """enum adapter for autoscript ScanningMode enum"""

    FULL_FRAME = as_enums.ScanningMode.FULL_FRAME
    LINE = as_enums.ScanningMode.LINE
    SPOT = as_enums.ScanningMode.SPOT
    REDUCED_AREA = as_enums.ScanningMode.REDUCED_AREA
    EXTERNAL = as_enums.ScanningMode.EXTERNAL
    CROSSOVER = as_enums.ScanningMode.CROSSOVER
    OTHER = as_enums.ScanningMode.OTHER


class SectioningAxis(Enum):
    """Specific sectioning directions supported for 3D collection"""

    X_POS: str = "X+"
    X_NEG: str = "X-"
    Y_POS: str = "Y+"
    Y_NEG: str = "Y-"
    Z: str = "Z"


class StageAxis(as_enums.StageAxis):
    """Class adapter for autoscript StageAxis enum"""

    pass


class StageCoordinateSystem(Enum):
    """Adapter enum class for autoscript CoordinateSystem.
    Stage movement operations are all done in RAW coordinates for
    increased accuracy, reliability, and constancy of positions"""

    RAW: str = as_enums.CoordinateSystem.RAW
    SPECIMEN: str = as_enums.CoordinateSystem.SPECIMEN


class StageMovementMode(Enum):
    """Movement mode of the stage.
    IN_PLANE mode is used for in-plane tiling operations
    OUT_OF_PLANE mode is used for out-of-plane slice increments"""

    IN_PLANE: str = "in_plane"
    OUT_OF_PLANE: str = "out_of_plane"


class StagePositionEncoder(as_structs.StagePosition):
    """Class adapter for autoscript StagePosition
    length units in meters, angular units in radians
    contains the following properties:
    x: float, in meters
    y: float, in meters
    z: float, in meters
    r: float, in radians
    t: float, in radians
    coordinate_system: str, tbt.StageCoordinateSystem.value
    """

    pass


class StagePositionUser(NamedTuple):
    """Stage object with axis positions in units of mm and degrees"""

    x_mm: float
    y_mm: float
    z_mm: float
    r_deg: float
    t_deg: float
    coordinate_system: StageCoordinateSystem = StageCoordinateSystem.RAW


class StageLimits(NamedTuple):
    """Limits for stage positions as determined by autoscript"""

    x_mm: Limit
    y_mm: Limit
    z_mm: Limit
    r_deg: Limit
    t_deg: Limit


class StageTolerance(NamedTuple):
    translational_um: float
    angular_deg: float


class StepType(Enum):
    """Specific step types supported for data collection"""

    LASER: str = "laser"
    IMAGE: str = "image"
    FIB: str = "fib"
    EDS: str = "eds"
    EBSD: str = "ebsd"
    # EBSD_EDS: str = "ebsd_eds"
    CUSTOM: str = "custom"


class StreamPatternDefinition(as_structs.StreamPatternDefinition):
    """Adapter class"""

    pass


class TimeStamp(NamedTuple):
    human_readable: str
    unix: int


class ViewQuad(IntEnum):
    """Quadrant in xTUI to select for viewing/imaging"""

    UPPER_LEFT = 1
    UPPER_RIGHT = 2
    LOWER_LEFT = 3
    LOWER_RIGHT = 4


class VacuumState(Enum):
    """enum adpater for autoscript VacuumState enum"""

    ERROR: str = as_enums.VacuumState.ERROR
    PUMPED: str = as_enums.VacuumState.PUMPED
    PUMPED_FOR_WAFER_EXCHANGE: str = as_enums.VacuumState.PUMPED_FOR_WAFER_EXCHANGE
    PUMPING: str = as_enums.VacuumState.PUMPING
    UNKNOWN: str = as_enums.VacuumState.UNKNOWN
    VENTED: str = as_enums.VacuumState.VENTED
    VENTING: str = as_enums.VacuumState.VENTING


### DERIVED CLASSES ###


class Beam(NamedTuple):
    """A generic Beam type, used as a template for concrete beam types."""

    settings: BeamSettings
    type: BeamType = None
    default_view: ViewQuad = None
    device: Device = None


class BeamLimits(NamedTuple):
    """Limits for beam setting as determined by autoscript"""

    voltage_kv: Limit
    current_na: Limit
    hfw_mm: Limit
    working_distance_mm: Limit


class ElectronBeam(Beam):
    """The specific beam type 'electron'."""

    settings: BeamSettings
    type: BeamType = BeamType.ELECTRON
    default_view: ViewQuad = ViewQuad.UPPER_LEFT
    device: Device = Device.ELECTRON_BEAM


class GeneralSettings(NamedTuple):
    """General settings object"""

    yml_version: float
    slice_thickness_um: float
    max_slice_number: int
    pre_tilt_deg: float
    sectioning_axis: SectioningAxis
    stage_tolerance: StageTolerance
    connection: MicroscopeConnection
    EBSD_OEM: ExternalDeviceOEM
    EDS_OEM: ExternalDeviceOEM
    exp_dir: Path
    h5_log_name: str
    step_count: int

    @property
    def log_filepath(self) -> Path:
        return Path(self.exp_dir).joinpath(self.h5_log_name + ".h5")


class IonBeam(Beam):
    """The specific beam type 'ion'."""

    settings: BeamSettings
    type: BeamType = BeamType.ION
    default_view: ViewQuad = ViewQuad.UPPER_RIGHT
    device: Device = Device.ION_BEAM


class Detector(NamedTuple):
    """Generic detector settings"""

    type: DetectorType = None  # error check with "available_values" call
    mode: DetectorMode = None  # error check with "available_values" call
    brightness: float = None
    contrast: float = None
    auto_cb_settings: ScanArea = ScanArea(
        left=None, top=None, width=None, height=None
    )  # only reduced area supported currently
    custom_settings: dict = None


class PresetResolution(Resolution, Enum):
    """Enum adapter for autoscript ScanningResolution enum"""

    # python 3.11 will support StrEnum like so: StandardResolution(StrEnum)
    PRESET_512X442 = Resolution(width=512, height=442)
    PRESET_768X512 = Resolution(width=768, height=512)
    PRESET_1024X884 = Resolution(width=1024, height=884)
    PRESET_1536X1024 = Resolution(width=1536, height=1024)
    PRESET_2048X1768 = Resolution(width=2048, height=1768)
    PRESET_3072X2048 = Resolution(width=3072, height=2048)
    PRESET_4096X3536 = Resolution(width=4096, height=3536)
    PRESET_6144X4096 = Resolution(width=6144, height=4096)


class Scan(NamedTuple):
    """Generic scan settings"""

    rotation_deg: float = None  # enforce resolution limit (tolerance)
    dwell_time_us: float = (
        None  # error check with "limits" call, may want tolerance too
    )
    resolution: Resolution = None
    # mode: ScanMode = None


class ImageSettings(NamedTuple):
    microscope: Microscope
    beam: Beam
    detector: Detector
    scan: Scan
    bit_depth: ColorDepth
    # TODO incorporate tiling settings
    # tiling_settings: ImageTileSettings = None


class StageSettings(NamedTuple):
    """Settings for high-level stage movement operation."""

    microscope: Microscope
    initial_position: StagePositionUser
    pretilt_angle_deg: PretiltAngleDegrees
    sectioning_axis: SectioningAxis
    rotation_side: RotationSide  # = RotationSide.EBEAM_NORMAL
    movement_mode: StageMovementMode = StageMovementMode.OUT_OF_PLANE


class ScanLimits(NamedTuple):
    """Limits for beam scan settings as determined by autoscript"""

    rotation_deg: Limit
    dwell_us: Limit


class CustomSettings(NamedTuple):
    script_path: Path
    executable_path: Path


class RectanglePattern(as_dynamics.RectanglePattern):
    pass


class CleaningCrossSectionPattern(as_dynamics.CleaningCrossSectionPattern):
    pass


class RegularCrossSectionPattern(as_dynamics.RegularCrossSectionPattern):
    pass


class StreamPattern(as_dynamics.StreamPattern):
    pass


class FIBBoxPattern(NamedTuple):
    center_um: Point
    width_um: float
    height_um: float
    depth_um: float
    scan_direction: FIBPatternScanDirection
    scan_type: FIBPatternScanType


class FIBRectanglePattern(FIBBoxPattern):
    pass


class FIBRegularCrossSection(FIBBoxPattern):
    pass


class FIBCleaningCrossSection(FIBBoxPattern):
    pass


class FIBStreamPattern(NamedTuple):
    dwell_us: float  # must be multiple of 25 ns
    repeats: int
    recipe_file: Path
    mask_file: Path


class FIBPattern(NamedTuple):
    application: str
    type: FIBPatternType
    geometry: Union[
        FIBRectanglePattern,
        FIBRegularCrossSection,
        FIBCleaningCrossSection,
        FIBStreamPattern,
    ]


class FIBSettings(NamedTuple):
    microscope: Microscope
    image: ImageSettings
    mill_beam: Beam
    pattern: FIBPattern


class EBSDSettings(NamedTuple):
    image: ImageSettings
    enable_eds: bool
    enable_ebsd: bool = True


class EDSSettings(NamedTuple):
    image: ImageSettings
    enable_eds: bool = True


class LaserPolarization(Enum):
    VERTICAL: str = "vertical"
    HORIZONTAL: str = "horizontal"


class LaserPulse(NamedTuple):
    wavelength_nm: LaserWavelength
    divider: int
    energy_uj: float
    polarization: LaserPolarization


class LaserScanType(Enum):
    SERPENTINE: str = "serpentine"
    RASTER: str = "raster"
    SINGLE: str = "single"
    LAP: str = "lap"


class LaserPatternType(Enum):
    BOX: str = "box"
    LINE: str = "line"


class LaserBoxPattern(NamedTuple):
    passes: int
    size_x_um: float
    size_y_um: float
    pitch_x_um: float
    pitch_y_um: float
    scan_type: LaserScanType  # Serpentine or Raster
    coordinate_ref: CoordinateReference  # Center, UpperCenter, or UpperLeft
    type = LaserPatternType.BOX


class LaserLinePattern(NamedTuple):
    passes: int
    size_um: float
    pitch_um: float
    scan_type: LaserScanType  # Single or Lap
    type = LaserPatternType.LINE


class LaserPattern(NamedTuple):
    mode: LaserPatternMode
    rotation_deg: float
    geometry: Union[LaserBoxPattern, LaserLinePattern]
    pulses_per_pixel: int = None
    pixel_dwell_ms: float = None


class LaserState(NamedTuple):
    """Settings for all readable values from TFS Laser Control"""

    wavelength_nm: LaserWavelength  # LaserPulse.wavelength_nm setting
    frequency_khz: float
    pulse_divider: int  # LaserPulse.divider setting
    pulse_energy_uj: float  # LaserPulse.energy_uj setting
    objective_position_mm: float  # LaserSettings.objective_position_mm
    beam_shift_um: Point  # LaserSettings.beam_shift_um
    pattern: LaserPattern
    expected_pattern_duration_s: float = None
    # burst_count: int #shouldnt need this but we can read it
    # shutter_state: RetractableDeviceState #shouldnt need this but we can read it


class LaserSettings(NamedTuple):
    microscope: Microscope
    pulse: LaserPulse
    objective_position_mm: float
    beam_shift_um: Point
    pattern: LaserPattern


class Step(NamedTuple):
    type: StepType
    name: str
    number: int
    frequency: int
    stage: StageSettings
    operation_settings: Union[
        CustomSettings,
        EBSDSettings,
        EDSSettings,
        ImageSettings,
        FIBSettings,
        LaserSettings,
    ]


class ExperimentSettings(NamedTuple):
    microscope: Microscope
    general_settings: GeneralSettings
    step_sequence: List[Step]
    enable_EBSD: bool
    enable_EDS: bool


class YMLFormat(NamedTuple):
    version: float
    general_section_key: str
    non_step_section_count: int
    general_exp_settings: dict
    step_count_key: str

    step_section_key: str
    step_general_settings: dict
    step_general_key: str
    step_number_key: str
    step_frequency_key: str
    step_type_key: str
    step_stage_settings_key: str

    image_step_settings: dict

    # step_settings: List[
    #     custom,
    #     ebsd,
    #     ebsd_eds,
    #     eds,
    #     fib,
    #     image,
    #     laser,
    # ]

    # image: ImageSettings
    # ebsd: dict
    #     image
    # eds: dict
    #     image
    # ebsd_eds: dict
    #     image

    # fib: dict
    #     image
    #     milling_Settings

    # laser: dict
    #     special things

    # custom_step_settings: dict


class YMLFormatVersion(YMLFormat, Enum):
    V_1_0 = YMLFormat(
        version=1.0,
        # general settings
        general_section_key="general",
        non_step_section_count=2,
        step_number_key="step_number",
        general_exp_settings={
            "slice_thickness_um": float,
            "max_slice_num": int,
            "pre_tilt_deg": float,
            "sectioning_axis": SectioningAxis,
            "stage_translational_tol_um": float,
            "stage_angular_tol_deg": float,
            "connection_host": str,
            "connection_port": int,
            "EBSD_OEM": ExternalDeviceOEM,
            "EDS_OEM" "exp_dir": Path,
            "h5_log_name": str,
            "step_count": int,
        },
        step_count_key="step_count",
        # step settings
        step_section_key="steps",
        step_general_key="step_general",
        step_type_key="step_type",
        step_frequency_key="frequency",
        step_stage_settings_key="stage",
        step_general_settings={
            "step_number": int,
            "step_type": StepType,
            "frequency": int,
            "stage": StagePositionUser,
        },
        image_step_settings={
            "beam_type": BeamType,
            "beam_settings": BeamSettings,
            "detector": Detector,
            "scan": Scan,
            "bit_depth": ColorDepth,
            "tiling_settings": ImageTileSettings,
        },
        # custom_step_settings={
        #     "script_path": Path,
        #     "script_type": ScriptType,
        # }
    )
