#!/usr/bin/python3
"""
Types Module
============

This module contains classes for internal data types used in the microscope operations, including settings, patterns, and enums.

Classes
-------
AdornedImage(as_structs.AdornedImage)
    Adapter class for autoscript AdornedImage.

AngularCorrectionMode(as_enums.AngularCorrectionMode)
    Adapter class for autoscript AngularCorrectionMode.

Limit(NamedTuple)
    Limit range for a value.

BeamType(Enum)
    Specific enumerated beam types.

BeamSettings(NamedTuple)
    Settings for generic Beam types.

StreamDepth(IntEnum)
    Bit depth of stream patterns.

ColorDepth(IntEnum)
    Bit depth of images.

CoordinateReference(Enum)
    Enum of coordinate reference frames used for laser milling operations.

DetectorMode(Enum)
    Enum adapter for autoscript DetectorMode enum.

DetectorType(Enum)
    Enum adapter for autoscript DetectorType enum.

Device(IntEnum)
    Enum adapter for autoscript ImagingDevice enum.

DummyFile(object)
    Dummy file to suppress excessive printing.

ExternalDeviceOEM(Enum)
    Specific EBSD and EDS OEMs supported for collection.

FIBPatternType(Enum)
    Enum for FIB pattern types.

FIBPatternScanDirection(Enum)
    Enum for FIB pattern scan directions.

FIBPatternScanType(Enum)
    Enum for FIB pattern scan types.

FocusPlaneGrid(NamedTuple)
    Settings for performing a focus grid to fit plane for image tiling.

GrabFrameSettings(as_structs.GrabFrameSettings)
    Class adapter for autoscript GrabFrameSettings.

ImageFileFormat(Enum)
    Enum adapter for autoscript ImageFileFormat.

ImageTileSettings(NamedTuple)
    Settings for image tiling operations.

IntervalType(Enum)
    Enumerated interval types for limit checking.

LaserPatternMode(Enum)
    Enum for laser pattern modes.

LaserWavelength(IntEnum)
    Enum for laser wavelengths.

Point(as_structs.Point)
    Adapter class for autoscript Point.

ProtectiveShutterMode(as_enums.ProtectiveShutterMode)
    Adapter class for autoscript ProtectiveShutterMode.

MapStatus(Enum)
    Map status for EBSD or EDS.

Microscope(SdbMicroscopeClient)
    Class adapter for autoscript SdbMicroscopeClient.

MicroscopeConnection(NamedTuple)
    Connection to initialize microscope object.

PretiltAngleDegrees(NamedTuple)
    Specimen pretilt as measured with regard to the electron beam normal direction.

Resolution(NamedTuple)
    Arbitrary scan resolution, with limits of (12 <= input <= 65536).

RetractableDeviceState(Enum)
    Enum adapter for autoscript RetractableDeviceState enum.

DeviceStatus(NamedTuple)
    Status of connected devices.

RotationSide(Enum)
    Enum for specific rotation sides.

ScanArea(NamedTuple)
    Reduced scan area box, coordinate range in [0,1] from top left corner.

ScanMode(IntEnum)
    Enum adapter for autoscript ScanningMode enum.

SectioningAxis(Enum)
    Specific sectioning directions supported for 3D collection.

StageAxis(as_enums.StageAxis)
    Class adapter for autoscript StageAxis enum.

StageCoordinateSystem(Enum)
    Adapter enum class for autoscript CoordinateSystem.

StageMovementMode(Enum)
    Movement mode of the stage.

StagePositionEncoder(as_structs.StagePosition)
    Class adapter for autoscript StagePosition.

StagePositionUser(NamedTuple)
    Stage object with axis positions in units of mm and degrees.

StageLimits(NamedTuple)
    Limits for stage positions as determined by autoscript.

StageTolerance(NamedTuple)
    Tolerance for stage positions.

StepType(Enum)
    Specific step types supported for data collection.

StreamPatternDefinition(as_structs.StreamPatternDefinition)
    Adapter class for autoscript StreamPatternDefinition.

TimeStamp(NamedTuple)
    Timestamp with human-readable and UNIX time formats.

ViewQuad(IntEnum)
    Quadrant in xTUI to select for viewing/imaging.

VacuumState(Enum)
    Enum adapter for autoscript VacuumState enum.

EdaxMappingStatus(Enum)
    Enum adapter for EDAX EDS mapping status.

EdaxEbsdCameraStatus(Enum)
    Enum adapter for EDAX EBSD camera status.

EdaxEdsDetectorStatus(Enum)
    Enum adapter for EDAX EDS detector status.

EdaxEdsDetectorSlideStatus(Enum)
    Enum adapter for EDAX EDS detector slide status.

Beam(NamedTuple)
    A generic Beam type, used as a template for concrete beam types.

BeamLimits(NamedTuple)
    Limits for beam settings as determined by autoscript.

ElectronBeam(Beam)
    The specific beam type 'electron'.

EDAXConfig(NamedTuple)
    EDAX configuration settings.

GeneralSettings(NamedTuple)
    General settings object.

IonBeam(Beam)
    The specific beam type 'ion'.

Detector(NamedTuple)
    Generic detector settings.

PresetResolution(Resolution, Enum)
    Enum adapter for autoscript ScanningResolution enum.

Scan(NamedTuple)
    Generic scan settings.

ImageSettings(NamedTuple)
    Image settings for the microscope.

StageSettings(NamedTuple)
    Settings for high-level stage movement operation.

ScanLimits(NamedTuple)
    Limits for beam scan settings as determined by autoscript.

CustomSettings(NamedTuple)
    Custom settings for running scripts.

RectanglePattern(as_dynamics.RectanglePattern)
    Adapter class for autoscript RectanglePattern.

CleaningCrossSectionPattern(as_dynamics.CleaningCrossSectionPattern)
    Adapter class for autoscript CleaningCrossSectionPattern.

RegularCrossSectionPattern(as_dynamics.RegularCrossSectionPattern)
    Adapter class for autoscript RegularCrossSectionPattern.

StreamPattern(as_dynamics.StreamPattern)
    Adapter class for autoscript StreamPattern.

FIBBoxPattern(NamedTuple)
    FIB box pattern settings.

FIBRectanglePattern(FIBBoxPattern)
    FIB rectangle pattern settings.

FIBRegularCrossSection(FIBBoxPattern)
    FIB regular cross-section pattern settings.

FIBCleaningCrossSection(FIBBoxPattern)
    FIB cleaning cross-section pattern settings.

FIBStreamPattern(NamedTuple)
    FIB stream pattern settings.

FIBPattern(NamedTuple)
    FIB pattern settings.

FIBSettings(NamedTuple)
    FIB settings for the microscope.

EBSDGridType(IntEnum)
    Enum for EBSD grid types.

EBSDScanBox(NamedTuple)
    EBSD scan box settings.

EBSDSettings(NamedTuple)
    EBSD settings for the microscope.

EDSSettings(NamedTuple)
    EDS settings for the microscope.

LaserPolarization(Enum)
    Enum for laser polarization.

LaserPulse(NamedTuple)
    Laser pulse settings.

LaserScanType(Enum)
    Enum for laser scan types.

LaserPatternType(Enum)
    Enum for laser pattern types.

LaserBoxPattern(NamedTuple)
    Laser box pattern settings.

LaserLinePattern(NamedTuple)
    Laser line pattern settings.

LaserPattern(NamedTuple)
    Laser pattern settings.

LaserState(NamedTuple)
    Settings for all readable values from TFS Laser Control.

LaserSettings(NamedTuple)
    Laser settings for the microscope.

Step(NamedTuple)
    Step settings for the experiment.

ExperimentSettings(NamedTuple)
    Experiment settings for the experiment.

YMLFormat(NamedTuple)
    YAML format settings.

YMLFormatVersion(YMLFormat, Enum)
    Enum for YAML format versions.
"""

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
    """
    Adapter class for autoscript AdornedImage.
    """

    pass


class AngularCorrectionMode(as_enums.AngularCorrectionMode):
    """
    Adapter class for autoscript AngularCorrectionMode.
    """

    pass


class Limit(NamedTuple):
    """
    Limit range for a value.

    Attributes
    ----------
    min : float
        The minimum value of the limit.
    max : float
        The maximum value of the limit.
    """

    min: float  # | int
    max: float  # | int


class BeamType(Enum):
    """
    Specific enumerated beam types.

    Attributes
    ----------
    ELECTRON : str
        Electron beam type.
    ION : str
        Ion beam type.
    """

    ELECTRON: str = "electron"
    ION: str = "ion"


class BeamSettings(NamedTuple):
    """
    Settings for generic Beam types.

    Attributes
    ----------
    voltage_kv : float
        The voltage in kV.
    current_na : float
        The current in nA.
    hfw_mm : float
        The horizontal field width in mm.
    working_dist_mm : float
        The working distance in mm.
    voltage_tol_kv : float
        The voltage tolerance in kV.
    current_tol_na : float
        The current tolerance in nA.
    dynamic_focus : bool
        Whether dynamic focus is enabled (ebeam only).
    tilt_correction : bool
        Whether tilt correction is enabled (ebeam only).
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
    """
    Bit depth of stream patterns.

    Attributes
    ----------
    BITS_16 : int
        16-bit depth.
    """

    # BITS_12 = 12 #no longer supported by TFS
    BITS_16 = 16


class ColorDepth(IntEnum):
    """
    Bit depth of images.

    Attributes
    ----------
    BITS_8 : int
        8-bit depth.
    BITS_16 : int
        16-bit depth.
    """

    BITS_8 = 8
    BITS_16 = 16


class CoordinateReference(Enum):
    """
    Enum of coordinate reference frames used for laser milling operations.

    Attributes
    ----------
    CENTER : str
        Center coordinate reference.
    UPPER_CENTER : str
        Upper center coordinate reference.
    UPPER_LEFT : str
        Upper left coordinate reference.
    """

    CENTER: str = "center"
    UPPER_CENTER: str = "uppercenter"
    UPPER_LEFT: str = "upperleft"


class DetectorMode(Enum):
    """
    Enum adapter for autoscript DetectorMode enum.

    Attributes
    ----------
    ALL : str
        All detector mode.
    A_MINUS_B : str
        A minus B detector mode.
    ANGULAR : str
        Angular detector mode.
    ANGULAR_PARTIAL : str
        Angular partial detector mode.
    ANGULAR_PARTIAL_COMPLEMENT : str
        Angular partial complement detector mode.
    ANULAR_A : str
        Anular A detector mode.
    ANULAR_B : str
        Anular B detector mode.
    ANULAR_C : str
        Anular C detector mode.
    ANULAR_D : str
        Anular D detector mode.
    A_PLUS_B : str
        A plus B detector mode.
    BACKSCATTER_ELECTRONS : str
        Backscatter electrons detector mode.
    BEAM_DECELERATION : str
        Beam deceleration detector mode.
    BRIGHT_FIELD : str
        Bright field detector mode.
    CATHODO_LUMINESCENCE : str
        Cathodo luminescence detector mode.
    CHARGE_NEUTRALIZATION : str
        Charge neutralization detector mode.
    CUSTOM : str
        Custom detector mode.
    CUSTOM2 : str
        Custom2 detector mode.
    CUSTOM3 : str
        Custom3 detector mode.
    CUSTOM4 : str
        Custom4 detector mode.
    CUSTOM5 : str
        Custom5 detector mode.
    DARK_FIELD : str
        Dark field detector mode.
    DARK_FIELD1 : str
        Dark field1 detector mode.
    DARK_FIELD2 : str
        Dark field2 detector mode.
    DARK_FIELD3 : str
        Dark field3 detector mode.
    DARK_FIELD4 : str
        Dark field4 detector mode.
    DOWN_HOLE_VISIBILITY : str
        Down hole visibility detector mode.
    HIGH_ANGLE : str
        High angle detector mode.
    INNER_MINUS_OUTER : str
        Inner minus outer detector mode.
    LOW_ANGLE : str
        Low angle detector mode.
    MIX : str
        Mix detector mode.
    NONE : str
        None detector mode.
    SCINTILLATION : str
        Scintillation detector mode.
    SECONDARY_ELECTRONS : str
        Secondary electrons detector mode.
    SECONDARY_IONS : str
        Secondary ions detector mode.
    SEGMENT_A : str
        Segment A detector mode.
    SEGMENT_B : str
        Segment B detector mode.
    TOPOGRAPHY : str
        Topography detector mode.
    Z_CONTRAST : str
        Z contrast detector mode.
    """

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
    """
    Enum adapter for autoscript DetectorType enum.

    Attributes
    ----------
    ABS : str
        ABS detector type.
    BSD : str
        BSD detector type.
    CBS : str
        CBS detector type.
    CDEM : str
        CDEM detector type.
    CRD : str
        CRD detector type.
    DUAL_BSD : str
        Dual BSD detector type.
    EBSD : str
        EBSD detector type.
    EDS : str
        EDS detector type.
    ECD : str
        ECD detector type.
    ETD : str
        ETD detector type.
    EXTERNAL : str
        External detector type.
    GAS : str
        GAD detector type.
    GBSD : str
        GBSD detector type.
    GSED : str
        GSED detector type.
    HIRES_OPTICAL : str
        HiRes Optical detector type.
    HIRES_OPTICAL_LO_MAG : str
        HiRes Optical Low Mag detector type.
    ICE : str
        ICE detector type.
    IN_COLUMN_BSD : str
        In Column BSD detector type.
    IR : str
        IR detector type.
    IR2 : str
        IR2 detector type.
    IR_CAMERA : str
        IR Camera detector type.
    LFD : str
        LFD detector type.
    LVD : str
        LVD detector type.
    LVSED : str
        LVSED detector type.
    MD : str
        MD detector type.
    MIX : str
        Mix detector type.
    NONE : str
        None detector type.
    PMT : str
        PMT detector type.
    QUAD_BSD : str
        Quad BSD detector type.
    SED : str
        SED detector type.
    SINGLE_BSD : str
        Single BSD detector type.
    STEM3 : str
        STEM3 detector type.
    STEM3_PLUS : str
        STEM3 Plus detector type.
    STEM4 : str
        STEM4 detector type.
    T1 : str
        T1 detector type.
    T2 : str
        T2 detector type.
    T3 : str
        T3 detector type.
    TLD : str
        TLD detector type.
    TLD2 : str
        TLD2 detector type.
    """

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
    """
    Enum adapter for autoscript ImagingDevice enum.

    Attributes
    ----------
    ELECTRON_BEAM : int
        Electron beam device.
    ION_BEAM : int
        Ion beam device.
    CCD_CAMERA : int
        CCD camera device.
    IR_CAMERA : int
        IR camera device.
    NAV_CAM : int
        Navigation camera device.
    OPTICAL_MICROSCOPE : int
        Optical microscope device.
    VOLUMESCOPE_APPROACH_CAMERA : int
        Volumescope approach camera device.
    """

    ELECTRON_BEAM = as_enums.ImagingDevice.ELECTRON_BEAM
    ION_BEAM = as_enums.ImagingDevice.ION_BEAM
    CCD_CAMERA = as_enums.ImagingDevice.CCD_CAMERA
    IR_CAMERA = as_enums.ImagingDevice.IR_CAMERA
    NAV_CAM = as_enums.ImagingDevice.NAV_CAM
    OPTICAL_MICROSCOPE = as_enums.ImagingDevice.OPTICAL_MICROSCOPE
    VOLUMESCOPE_APPROACH_CAMERA = as_enums.ImagingDevice.VOLUMESCOPE_APPROACH_CAMERA


class DummyFile(object):
    """
    Dummy file to suppress excessive printing.
    """

    def write(selfself, x):
        pass


class ExternalDeviceOEM(Enum):
    """
    Specific EBSD and EDS OEMs supported for collection.

    Attributes
    ----------
    OXFORD : str
        Oxford OEM.
    EDAX : str
        EDAX OEM.
    NONE : str
        No OEM.
    """

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
    """
    Enum for FIB pattern types.

    Attributes
    ----------
    RECTANGLE : str
        Rectangle pattern type.
    REGULAR_CROSS_SECTION : str
        Regular cross-section pattern type.
    CLEANING_CROSS_SECTION : str
        Cleaning cross-section pattern type.
    SELECTED_AREA : str
        Selected area pattern type.
    """

    RECTANGLE: str = "rectangle"
    REGULAR_CROSS_SECTION: str = "regular_cross_section"
    CLEANING_CROSS_SECTION: str = "cleaning_cross_section"
    SELECTED_AREA: str = "selected_area"


class FIBPatternScanDirection(Enum):
    """
    Enum for FIB pattern scan directions.

    Attributes
    ----------
    BOTTOM_TO_TOP : str
        Bottom to top scan direction.
    DYNAMIC_ALL_DIRECTIONS : str
        Dynamic all directions scan direction.
    DYNAMIC_INNER_TO_OUTER : str
        Dynamic inner to outer scan direction.
    DYNAMIC_LEFT_TO_RIGHT : str
        Dynamic left to right scan direction.
    DYNAMIC_TOP_TO_BOTTOM : str
        Dynamic top to bottom scan direction.
    INNER_TO_OUTER : str
        Inner to outer scan direction.
    LEFT_TO_RIGHT : str
        Left to right scan direction.
    OUTER_TO_INNER : str
        Outer to inner scan direction.
    RIGHT_TO_LEFT : str
        Right to left scan direction.
    TOP_TO_BOTTOM : str
        Top to bottom scan direction.
    """

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
    """
    Enum for FIB pattern scan types.

    Attributes
    ----------
    RASTER : str
        Raster scan type.
    SERPENTINE : str
        Serpentine scan type.
    CIRCULAR : str
        Circular scan type (not yet supported by pyTriBeam).
    """

    RASTER: str = "Raster"
    SERPENTINE: str = "Serpentine"
    CIRCULAR: str = "Circular"  # TODO not yet supported by pyTriBeam


class FocusPlaneGrid(NamedTuple):
    """
    Settings for performing a focus grid to fit plane for image tiling.

    Attributes
    ----------
    num_grid_points_x : int
        Number of grid points in the x direction.
    num_grid_points_y : int
        Number of grid points in the y direction.
    grid_dx_um : float
        Grid spacing in the x direction in micrometers.
    grid_dy_um : float
        Grid spacing in the y direction in micrometers.
    """

    num_grid_points_x: int
    num_grid_points_y: int
    grid_dx_um: float
    grid_dy_um: float


class GrabFrameSettings(as_structs.GrabFrameSettings):
    """
    Adapter Class for autoscript GrabFrameSettings.
    """

    pass


class ImageFileFormat(Enum):
    """
    Enum adapter for autoscript ImageFileFormat.

    Attributes
    ----------
    RAW : str
        RAW image file format.
    TIFF : str
        TIFF image file format.
    """

    RAW: str = as_enums.ImageFileFormat.RAW
    TIFF: str = as_enums.ImageFileFormat.TIFF


class ImageTileSettings(NamedTuple):
    """
    Settings for image tiling operations.

    Attributes
    ----------
    tile_origin : CoordinateReference
        The origin of the tile.
    length_x_mm : float
        The length of the tile in the x direction in millimeters.
    length_y_mm : float
        The length of the tile in the y direction in millimeters.
    overlap_frac_x : float
        The overlap fraction in the x direction.
    overlap_frac_y : float
        The overlap fraction in the y direction.
    focus_plane_grid : FocusPlaneGrid
        The focus plane grid settings.
    """

    tile_origin: CoordinateReference
    length_x_mm: float
    length_y_mm: float
    overlap_frac_x: float
    overlap_frac_y: float
    focus_plane_grid: FocusPlaneGrid


class IntervalType(Enum):
    """
    Enumerated interval types for limit checking.

    Attributes
    ----------
    OPEN : str
        Fully-open interval (a,b), does not include endpoints.
    CLOSED : str
        Fully-closed interval [a,b], includes both endpoints.
    LEFT_OPEN : str
        Half-open interval on left side (a,b], does not include 'a'.
    RIGHT_OPEN : str
        Half-open interval on right side [a,b), does not include 'b'.
    """

    OPEN: str = "open"
    CLOSED: str = "closed"
    LEFT_OPEN: str = "left_open"
    RIGHT_OPEN: str = "right_open"


class LaserPatternMode(Enum):
    """
    Enum for laser pattern modes.

    Attributes
    ----------
    COARSE : str
        Coarse pattern mode.
    FINE : str
        Fine pattern mode.
    """

    COARSE: str = "coarse"
    FINE: str = "fine"


class LaserWavelength(IntEnum):
    """
    Enum for laser wavelengths.

    Attributes
    ----------
    NM_515 : int
        515 nm wavelength.
    NM_1030 : int
        1030 nm wavelength.
    """

    NM_515 = 515
    NM_1030 = 1030


class Point(as_structs.Point):
    """
    Adapter class for autoscript Point.
    """

    pass


class ProtectiveShutterMode(as_enums.ProtectiveShutterMode):
    """
    Adapter class for autoscript ProtectiveShutterMode.
    """

    pass


class MapStatus(Enum):
    """
    Map status for EBSD or EDS.

    Attributes
    ----------
    ACTIVE : str
        Active map status.
    IDLE : str
        Idle map status.
    ERROR : str
        Error map status.
    """

    ACTIVE = "Active"
    IDLE = "Idle"
    ERROR = "Error"


class Microscope(SdbMicroscopeClient):
    """
    Class adapter for autoscript SdbMicroscopeClient.

    Can add functionality with inheritance and super() in init, commented out below.
    """

    # def __init__(self):
    #     super().__init__()

    pass


class MicroscopeConnection(NamedTuple):
    """
    Connection to initialize microscope object.

    Attributes
    ----------
    host : str
        The host for the microscope connection.
    port : int, optional
        The port for the microscope connection (default is None).
    """

    host: str
    port: int = None


class PretiltAngleDegrees(NamedTuple):
    """
    Specimen pretilt as measured with regard to the electron beam normal direction.

    Attributes
    ----------
    value : float
        The pretilt angle in degrees.
    """

    value: float


class Resolution(NamedTuple):
    """
    Arbitrary scan resolution, with limits of (12 <= input <= 65536).

    Attributes
    ----------
    width : int
        The width of the resolution.
    height : int
        The height of the resolution.

    Properties
    ----------
    value : str
        The resolution as a string in the format "widthxheight".
    """

    width: int
    height: int

    @property
    def value(self) -> str:
        return f"{self.width}x{self.height}"


class RetractableDeviceState(Enum):
    """
    Enum adapter for autoscript RetractableDeviceState enum.

    Attributes
    ----------
    BUSY : str
        Busy state.
    ERROR : str
        Error state.
    INSERTED : str
        Inserted state.
    OTHER : str
        Other state.
    RETRACTED : str
        Retracted state.
    INDERTERMINATE : str
        Indeterminate state (for Oxford EBSD and EDS detectors).
    CONNECTED : str
        Connected state (for laser status).
    """

    BUSY: str = as_enums.RetractableDeviceState.BUSY
    ERROR: str = as_enums.RetractableDeviceState.ERROR
    INSERTED: str = as_enums.RetractableDeviceState.INSERTED
    OTHER: str = as_enums.RetractableDeviceState.OTHER
    RETRACTED: str = as_enums.RetractableDeviceState.RETRACTED
    INDERTERMINATE: str = "Indeterminate"  # For Oxford EBSD and EDS detectors
    CONNECTED: str = "Connected"  # For laser status


class DeviceStatus(NamedTuple):
    """
    Status of connected devices.

    Attributes
    ----------
    laser : RetractableDeviceState
        The status of the laser.
    ebsd : RetractableDeviceState
        The status of the EBSD detector.
    eds : RetractableDeviceState
        The status of the EDS detector.

    Methods
    -------
    __str__():
        Return a string representation of the device status.
    """

    laser: RetractableDeviceState
    ebsd: RetractableDeviceState
    eds: RetractableDeviceState

    def __str__(self):
        return f'Laser: "{self.laser.value}"\nEBSD Detector: "{self.ebsd.value}"\nEDS Detector: "{self.eds.value}"'


class RotationSide(Enum):
    """
    Enum for specific rotation sides.

    Attributes
    ----------
    FSL_MILL : str
        FSL mill side.
    FIB_MILL : str
        FIB mill side.
    EBEAM_NORMAL : str
        E-beam normal side.
    """

    FSL_MILL: str = "fsl_mill"
    FIB_MILL: str = "fib_mill"
    EBEAM_NORMAL: str = "ebeam_normal"


class ScanArea(NamedTuple):
    """
    Reduced scan area box, coordinate range in [0,1] from top left corner.

    Attributes
    ----------
    left : float
        The left coordinate of the scan area.
    top : float
        The top coordinate of the scan area.
    width : float
        The width of the scan area.
    height : float
        The height of the scan area.
    """

    left: float
    top: float
    width: float
    height: float


class ScanMode(IntEnum):
    """
    Enum adapter for autoscript ScanningMode enum.

    Attributes
    ----------
    FULL_FRAME : int
        Full frame scan mode.
    LINE : int
        Line scan mode.
    SPOT : int
        Spot scan mode.
    REDUCED_AREA : int
        Reduced area scan mode.
    EXTERNAL : int
        External scan mode.
    CROSSOVER : int
        Crossover scan mode.
    OTHER : int
        Other scan mode.
    """

    FULL_FRAME = as_enums.ScanningMode.FULL_FRAME
    LINE = as_enums.ScanningMode.LINE
    SPOT = as_enums.ScanningMode.SPOT
    REDUCED_AREA = as_enums.ScanningMode.REDUCED_AREA
    EXTERNAL = as_enums.ScanningMode.EXTERNAL
    CROSSOVER = as_enums.ScanningMode.CROSSOVER
    OTHER = as_enums.ScanningMode.OTHER


class SectioningAxis(Enum):
    """
    Specific sectioning directions supported for 3D collection.

    Attributes
    ----------
    X_POS : str
        Positive X direction.
    X_NEG : str
        Negative X direction.
    Y_POS : str
        Positive Y direction.
    Y_NEG : str
        Negative Y direction.
    Z : str
        Z direction.
    """

    X_POS: str = "X+"
    X_NEG: str = "X-"
    Y_POS: str = "Y+"
    Y_NEG: str = "Y-"
    Z: str = "Z"


class StageAxis(as_enums.StageAxis):
    """
    Class adapter for autoscript StageAxis enum.
    """

    pass


class StageCoordinateSystem(Enum):
    """
    Adapter enum class for autoscript CoordinateSystem.

    Attributes
    ----------
    RAW : str
        RAW coordinate system.
    SPECIMEN : str
        Specimen coordinate system.
    """

    RAW: str = as_enums.CoordinateSystem.RAW
    SPECIMEN: str = as_enums.CoordinateSystem.SPECIMEN


class StageMovementMode(Enum):
    """
    Movement mode of the stage.

    Attributes
    ----------
    IN_PLANE : str
        In-plane movement mode (for tiling operations).
    OUT_OF_PLANE : str
        Out-of-plane movement mode (for sectioning operations).
    """

    IN_PLANE: str = "in_plane"
    OUT_OF_PLANE: str = "out_of_plane"


class StagePositionEncoder(as_structs.StagePosition):
    """
    Class adapter for autoscript StagePosition.

    Attributes
    ----------
    x : float
        The x position in meters.
    y : float
        The y position in meters.
    z : float
        The z position in meters.
    r : float
        The r position in radians.
    t : float
        The t position in radians.
    coordinate_system : str
        The coordinate system.
    """

    pass


class StagePositionUser(NamedTuple):
    """
    Stage object with axis positions in units of mm and degrees.

    Attributes
    ----------
    x_mm : float
        The x position in millimeters.
    y_mm : float
        The y position in millimeters.
    z_mm : float
        The z position in millimeters.
    r_deg : float
        The r position in degrees.
    t_deg : float
        The t position in degrees.
    coordinate_system : StageCoordinateSystem
        The coordinate system (default is StageCoordinateSystem.RAW).
    """

    x_mm: float
    y_mm: float
    z_mm: float
    r_deg: float
    t_deg: float
    coordinate_system: StageCoordinateSystem = StageCoordinateSystem.RAW


class StageLimits(NamedTuple):
    """
    Limits for stage positions as determined by autoscript.

    Attributes
    ----------
    x_mm : Limit
        The x position limit in millimeters.
    y_mm : Limit
        The y position limit in millimeters.
    z_mm : Limit
        The z position limit in millimeters.
    r_deg : Limit
        The r position limit in degrees.
    t_deg : Limit
        The t position limit in degrees.
    """

    x_mm: Limit
    y_mm: Limit
    z_mm: Limit
    r_deg: Limit
    t_deg: Limit


class StageTolerance(NamedTuple):
    """
    Tolerance for stage positions.

    Attributes
    ----------
    translational_um : float
        The translational tolerance in micrometers.
    angular_deg : float
        The angular tolerance in degrees.
    """

    translational_um: float
    angular_deg: float


class StepType(Enum):
    """
    Specific step types supported for data collection.

    Attributes
    ----------
    LASER : str
        Laser step type.
    IMAGE : str
        Image step type.
    FIB : str
        FIB step type.
    EDS : str
        EDS step type.
    EBSD : str
        EBSD step type.
    CUSTOM : str
        Custom step type.
    """

    LASER: str = "laser"
    IMAGE: str = "image"
    FIB: str = "fib"
    EDS: str = "eds"
    EBSD: str = "ebsd"
    # EBSD_EDS: str = "ebsd_eds"
    CUSTOM: str = "custom"


class StreamPatternDefinition(as_structs.StreamPatternDefinition):
    """
    Adapter class for autoscript StreamPatternDefinition.
    """

    pass


class TimeStamp(NamedTuple):
    """
    Timestamp with human-readable and UNIX time formats.

    Attributes
    ----------
    human_readable : str
        The human-readable timestamp.
    unix : int
        The UNIX timestamp.
    """

    human_readable: str
    unix: int


class ViewQuad(IntEnum):
    """
    Quadrant in xTUI to select for viewing/imaging.

    Attributes
    ----------
    UPPER_LEFT : int
        Upper left quadrant.
    UPPER_RIGHT : int
        Upper right quadrant.
    LOWER_LEFT : int
        Lower left quadrant.
    LOWER_RIGHT : int
        Lower right quadrant.
    """

    UPPER_LEFT = 1
    UPPER_RIGHT = 2
    LOWER_LEFT = 3
    LOWER_RIGHT = 4


class VacuumState(Enum):
    """
    Enum adapter for autoscript VacuumState enum.

    Attributes
    ----------
    ERROR : str
        Error state.
    PUMPED : str
        Pumped state.
    PUMPED_FOR_WAFER_EXCHANGE : str
        Pumped for wafer exchange state.
    PUMPING : str
        Pumping state.
    UNKNOWN : str
        Unknown state.
    VENTED : str
        Vented state.
    VENTING : str
        Venting state.
    """

    ERROR: str = as_enums.VacuumState.ERROR
    PUMPED: str = as_enums.VacuumState.PUMPED
    PUMPED_FOR_WAFER_EXCHANGE: str = as_enums.VacuumState.PUMPED_FOR_WAFER_EXCHANGE
    PUMPING: str = as_enums.VacuumState.PUMPING
    UNKNOWN: str = as_enums.VacuumState.UNKNOWN
    VENTED: str = as_enums.VacuumState.VENTED
    VENTING: str = as_enums.VacuumState.VENTING


class EdaxMappingStatus(Enum):
    """
    Enum adapter EDAX mapping status

    Attributes
    ----------
    NOT_READY : str
        Not ready state.
    READY : str
        Ready state.
    SETUP_ACTIVE : str
        Setup active state.
    SETUP_COMPLETE : str
        Setup complete state.
    SETUP_PAUSED : str
        Setup paused state.
    SETUP_RESUMED : str
        Setup resumed state.
    SETUP_ABORTED : str
        Setup aborted state.
    SETUP_STOPPED : str
        Setup stopped state.
    SETUP_ERROR : str
        Setup error state.
    MAPPING_ACTIVE : str
        Mapping active state.
    MAPPING_COMPLETE : str
        Mapping complete state.
    MAPPING_PAUSED : str
        Mapping paused state.
    MAPPING_RESUMED : str
        Mapping resumed state.
    MAPPING_ABORTED : str
        Mapping aborted state.
    MAPPING_STOPPED : str
        Mapping stopped state.
    MAPPING_ERROR : str
        Mapping error state.
    UNKNOWN : str
        Unknown state.
    """

    NOT_READY: str = "notready"
    READY: str = "ready"
    SETUP_ACTIVE: str = "setupactive"
    SETUP_COMPLETE: str = "setupcomplete"
    SETUP_PAUSED: str = "setuppaused"
    SETUP_RESUMED: str = "setupresumed"
    SETUP_ABORTED: str = "setupaborted"
    SETUP_STOPPED: str = "setupstopped"
    SETUP_ERROR: str = "setuperror"
    MAPPING_ACTIVE: str = "mappingactive"
    MAPPING_COMPLETE: str = "mappingcomplete"
    MAPPING_PAUSED: str = "mappingpaused"
    MAPPING_RESUMED: str = "mappingresumed"
    MAPPING_ABORTED: str = "mappingaborted"
    MAPPING_STOPPED: str = "mappingstopped"
    MAPPING_ERROR: str = "mappingerror"
    UNKNOWN: str = "unknownerror"


class EdaxEbsdCameraStatus(Enum):
    """
    Enum adapter for EDAX EBSD camera status.

    Attributes
    ----------
    SLIDE_OUT : str
        Slide out state.
    SLIDE_IN : str
        Slide in state.
    SLIDE_MOVING_OUT : str
        Slide moving out state.
    SLIDE_MOVING_IN : str
        Slide moving in state.
    SLIDE_HIGH_COUNT : str
        Slide high count state.
    SLIDE_NO_POWER : str
        Slide no power state.
    SLIDE_MID : str
        Slide mid state.
    SLIDE_STOPPED : str
        Slide stopped state.
    SLIDE_ERROR : str
        Slide error state.
    SLIDE_INIT : str
        Slide init state.
    SLIDE_MOVE_MID_IN : str
        Slide move mid in state.
    SLIDE_MOVE_MID_OUT : str
        Slide move mid out state.
    SLIDE_WATCHDOG : str
        Slide watchdog state.
    SLIDE_MOVE_WDOG : str
        Slide move watchdog state.
    SLIDE_DISABLED : str
        Slide disabled state.
    SLIDE_MOVE_TOUCH : str
        Slide move touch state.
    SLIDE_TOUCH_SENSE : str
        Slide touch sense state.
    UNKNOWN : str
        Unknown state.
    """

    SLIDE_OUT: str = "slideout"
    SLIDE_IN: str = "slidein"
    SLIDE_MOVING_OUT: str = "slidemovingout"
    SLIDE_MOVING_IN: str = "slidemovingin"
    SLIDE_HIGH_COUNT: str = "slidehighcount"
    SLIDE_NO_POWER: str = "slidenopower"
    SLIDE_MID: str = "slidemid"
    SLIDE_STOPPED: str = "slidestopped"
    SLIDE_ERROR: str = "slideerror"
    SLIDE_INIT: str = "slideinit"
    SLIDE_MOVE_MID_IN: str = "slidemovemidin"
    SLIDE_MOVE_MID_OUT: str = "slidemovemidout"
    SLIDE_WATCHDOG: str = "slidewatchdog"
    SLIDE_MOVE_WDOG: str = "slidemovewdog"
    SLIDE_DISABLED: str = "slidedisabled"
    SLIDE_MOVE_TOUCH: str = "slidemovetouch"
    SLIDE_TOUCH_SENSE: str = "slidetouchsense"
    UNKNOWN: str = "unknown"


class EdaxEdsDetectorStatus(Enum):
    """
    Enum adapter for EDAX EDS detector status.

    Attributes
    ----------
    NOT_READY : str
        Not ready state.
    READY : str
        Ready state.
    """

    NOT_READY: str = "notready"
    READY: str = "ready"


class EdaxEdsDetectorSlideStatus(Enum):
    """
    Enum adapter for EDAX EDS detector slide status.

    Attributes
    ----------
    SLIDE_OUT : str
        Slide out state.
    SLIDE_IN : str
        Slide in state.
    UNKNOWN : str
        Unknown state.
    """

    SLIDE_OUT: str = "slideout"
    SLIDE_IN: str = "slidein"
    UNKNOWN: str = "unknown"


### DERIVED CLASSES ###


class Beam(NamedTuple):
    """
    A generic Beam type, used as a template for concrete beam types.

    Attributes
    ----------
    settings : BeamSettings
        The beam settings.
    type : BeamType
        The beam type.
    default_view : ViewQuad
        The default view quadrant.
    device : Device
        The beam device.
    """

    settings: BeamSettings
    type: BeamType = None
    default_view: ViewQuad = None
    device: Device = None


class BeamLimits(NamedTuple):
    """
    Limits for beam settings as determined by autoscript.

    Attributes
    ----------
    voltage_kv : Limit
        The voltage limit in kV.
    current_na : Limit
        The current limit in nA.
    hfw_mm : Limit
        The horizontal field width limit in mm.
    working_distance_mm : Limit
        The working distance limit in mm.
    """

    voltage_kv: Limit
    current_na: Limit
    hfw_mm: Limit
    working_distance_mm: Limit


class ElectronBeam(Beam):
    """
    The specific beam type 'electron'.

    Attributes
    ----------
    settings : BeamSettings
        The beam settings.
    type : BeamType
        The beam type (default is BeamType.ELECTRON).
    default_view : ViewQuad
        The default view quadrant (default is ViewQuad.UPPER_LEFT).
    device : Device
        The beam device (default is Device.ELECTRON_BEAM).
    """

    settings: BeamSettings
    type: BeamType = BeamType.ELECTRON
    default_view: ViewQuad = ViewQuad.UPPER_LEFT
    device: Device = Device.ELECTRON_BEAM


class EDAXConfig(NamedTuple):
    """General configuration for EDAX"""

    save_directory: Path  # on EDAX computer
    project_name: str
    connection: MicroscopeConnection = None


class GeneralSettings(NamedTuple):
    """
    General settings object.

    Attributes
    ----------
    yml_version : float
        The YAML version.
    slice_thickness_um : float
        The slice thickness in micrometers.
    max_slice_number : int
        The maximum slice number.
    pre_tilt_deg : float
        The pre-tilt angle in degrees.
    sectioning_axis : SectioningAxis
        The sectioning axis.
    stage_tolerance : StageTolerance
        The stage tolerance.
    connection : MicroscopeConnection
        The microscope connection settings.
    EBSD_OEM : ExternalDeviceOEM
        The EBSD OEM.
    EDS_OEM : ExternalDeviceOEM
        The EDS OEM.
    exp_dir : Path
        The experiment directory.
    h5_log_name : str
        The HDF5 log file name.
    step_count : int
        The step count.

    Properties
    ----------
    log_filepath : Path
        The log file path.
    """

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
    EDAX_settings: EDAXConfig = None

    @property
    def log_filepath(self) -> Path:
        return Path(self.exp_dir).joinpath(self.h5_log_name + ".h5")


class IonBeam(Beam):
    """
    The specific beam type 'ion'.

    Attributes
    ----------
    settings : BeamSettings
        The beam settings.
    type : BeamType
        The beam type (default is BeamType.ION).
    default_view : ViewQuad
        The default view quadrant (default is ViewQuad.UPPER_RIGHT).
    device : Device
        The beam device (default is Device.ION_BEAM).
    """

    settings: BeamSettings
    type: BeamType = BeamType.ION
    default_view: ViewQuad = ViewQuad.UPPER_RIGHT
    device: Device = Device.ION_BEAM


class Detector(NamedTuple):
    """
    Generic detector settings.

    Attributes
    ----------
    type : DetectorType
        The detector type.
    mode : DetectorMode
        The detector mode.
    brightness : float
        The brightness setting.
    contrast : float
        The contrast setting.
    auto_cb_settings : ScanArea
        The auto contrast/brightness settings.
    custom_settings : dict
        The custom settings.
    """

    type: DetectorType = None  # error check with "available_values" call
    mode: DetectorMode = None  # error check with "available_values" call
    brightness: float = None
    contrast: float = None
    auto_cb_settings: ScanArea = ScanArea(
        left=None, top=None, width=None, height=None
    )  # only reduced area supported currently
    custom_settings: dict = None


class PresetResolution(Resolution, Enum):
    """
    Enum adapter for autoscript ScanningResolution enum.

    Attributes
    ----------
    PRESET_512X442 : Resolution
        512x442 resolution.
    PRESET_768X512 : Resolution
        768x512 resolution.
    PRESET_1024X884 : Resolution
        1024x884 resolution.
    PRESET_1536X1024 : Resolution
        1536x1024 resolution.
    PRESET_2048X1768 : Resolution
        2048x1768 resolution.
    PRESET_3072X2048 : Resolution
        3072x2048 resolution.
    PRESET_4096X3536 : Resolution
        4096x3536 resolution.
    PRESET_6144X4096 : Resolution
        6144x4096 resolution.
    """

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
    """
    Generic scan settings.

    Attributes
    ----------
    rotation_deg : float
        The scan rotation in degrees.
    dwell_time_us : float
        The dwell time in microseconds.
    resolution : Resolution
        The scan resolution.
    """

    rotation_deg: float = None  # enforce resolution limit (tolerance)
    dwell_time_us: float = (
        None  # error check with "limits" call, may want tolerance too
    )
    resolution: Resolution = None
    # mode: ScanMode = None


class ImageSettings(NamedTuple):
    """
    Image settings for the microscope.

    Attributes
    ----------
    microscope : Microscope
        The microscope object.
    beam : Beam
        The beam settings.
    detector : Detector
        The detector settings.
    scan : Scan
        The scan settings.
    bit_depth : ColorDepth
        The bit depth of the image.
    """

    microscope: Microscope
    beam: Beam
    detector: Detector
    scan: Scan
    bit_depth: ColorDepth
    # TODO incorporate tiling settings
    # tiling_settings: ImageTileSettings = None


class StageSettings(NamedTuple):
    """
    Settings for high-level stage movement operation.

    Attributes
    ----------
    microscope : Microscope
        The microscope object.
    initial_position : StagePositionUser
        The initial position of the stage.
    pretilt_angle_deg : PretiltAngleDegrees
        The pretilt angle in degrees.
    sectioning_axis : SectioningAxis
        The sectioning axis.
    rotation_side : RotationSide
        The rotation side.
    movement_mode : StageMovementMode
        The movement mode of the stage (default is StageMovementMode.OUT_OF_PLANE).
    """

    microscope: Microscope
    initial_position: StagePositionUser
    pretilt_angle_deg: PretiltAngleDegrees
    sectioning_axis: SectioningAxis
    rotation_side: RotationSide  # = RotationSide.EBEAM_NORMAL
    movement_mode: StageMovementMode = StageMovementMode.OUT_OF_PLANE


class ScanLimits(NamedTuple):
    """
    Limits for beam scan settings as determined by autoscript.

    Attributes
    ----------
    rotation_deg : Limit
        The rotation limit in degrees.
    dwell_us : Limit
        The dwell time limit in microseconds.
    """

    rotation_deg: Limit
    dwell_us: Limit


class CustomSettings(NamedTuple):
    """
    Custom settings for running scripts.

    Attributes
    ----------
    script_path : Path
        The path to the script.
    executable_path : Path
        The path to the executable.
    """

    script_path: Path
    executable_path: Path


class RectanglePattern(as_dynamics.RectanglePattern):
    """
    Adapter class for autoscript RectanglePattern.
    """

    pass


class CleaningCrossSectionPattern(as_dynamics.CleaningCrossSectionPattern):
    """
    Adapter class for autoscript CleaningCrossSectionPattern.
    """

    pass


class RegularCrossSectionPattern(as_dynamics.RegularCrossSectionPattern):
    """
    Adapter class for autoscript RegularCrossSectionPattern.
    """

    pass


class StreamPattern(as_dynamics.StreamPattern):
    """
    Adapter class for autoscript StreamPattern.
    """

    pass


class FIBBoxPattern(NamedTuple):
    """
    FIB box pattern settings.

    Attributes
    ----------
    center_um : Point
        The center of the pattern in micrometers.
    width_um : float
        The width of the pattern in micrometers.
    height_um : float
        The height of the pattern in micrometers.
    depth_um : float
        The depth of the pattern in micrometers.
    scan_direction : FIBPatternScanDirection
        The scan direction of the pattern.
    scan_type : FIBPatternScanType
        The scan type of the pattern.
    """

    center_um: Point
    width_um: float
    height_um: float
    depth_um: float
    scan_direction: FIBPatternScanDirection
    scan_type: FIBPatternScanType


class FIBRectanglePattern(FIBBoxPattern):
    """
    FIB rectangle pattern settings.
    """

    pass


class FIBRegularCrossSection(FIBBoxPattern):
    """
    FIB regular cross-section pattern settings.
    """

    pass


class FIBCleaningCrossSection(FIBBoxPattern):
    """
    FIB cleaning cross-section pattern settings.
    """

    pass


class FIBStreamPattern(NamedTuple):
    """
    FIB stream pattern settings.

    Attributes
    ----------
    dwell_us : float
        The dwell time in microseconds (must be a multiple of 25 ns).
    repeats : int
        The number of repeats.
    recipe_file : Path
        The path to the recipe file.
    mask_file : Path
        The path to the mask file.
    """

    dwell_us: float  # must be multiple of 25 ns
    repeats: int
    recipe_file: Path
    mask_file: Path


class FIBPattern(NamedTuple):
    """
    FIB pattern settings.

    Attributes
    ----------
    application : str
        The application name.
    type : FIBPatternType
        The pattern type.
    geometry : Union[FIBRectanglePattern, FIBRegularCrossSection, FIBCleaningCrossSection, FIBStreamPattern]
        The pattern geometry.
    """

    application: str
    type: FIBPatternType
    geometry: Union[
        FIBRectanglePattern,
        FIBRegularCrossSection,
        FIBCleaningCrossSection,
        FIBStreamPattern,
    ]


class FIBSettings(NamedTuple):
    """
    FIB settings for the microscope.

    Attributes
    ----------
    microscope : Microscope
        The microscope object.
    image : ImageSettings
        The image settings.
    mill_beam : Beam
        The milling beam settings.
    pattern : FIBPattern
        The FIB pattern settings.
    """

    microscope: Microscope
    image: ImageSettings
    mill_beam: Beam
    pattern: FIBPattern


class EBSDGridType(IntEnum):
    """
    Enum for EBSD grid types.

    Attributes
    ----------
    SQUARE : int
        Square grid type.
    HEXAGONAL : int
        Hexagonal grid type.
    """

    SQUARE = 1
    HEXAGONAL = 0


class EBSDScanBox(NamedTuple):
    """
    EBSD scan box settings.

    Attributes
    ----------
    x_start_um : float
        The x-coordinate of the start position in micrometers.
    y_start_um : float
        The y-coordinate of the start position in micrometers.
    x_size_um : float
        The width of the scan box in micrometers.
    y_size_um : float
        The height of the scan box in micrometers.
    step_size_um : float
        The step size for the scan in micrometers.
    """

    x_start_um: float
    y_start_um: float
    x_size_um: float
    y_size_um: float
    step_size_um: float


class EBSDSettings(NamedTuple):
    """
    EBSD settings for the microscope.

    Attributes
    ----------
    image : ImageSettings
        The image settings.
    enable_eds : bool
        Whether to enable EDS.
    enable_ebsd : bool
        Whether to enable EBSD (default is True).
    """

    image: ImageSettings
    enable_eds: bool
    enable_ebsd: bool = True
    scan_box: EBSDScanBox = None
    grid_type: int = EBSDGridType.SQUARE
    save_patterns: bool = True


class EDSSettings(NamedTuple):
    """
    EDS settings for the microscope.

    Attributes
    ----------
    image : ImageSettings
        The image settings.
    enable_eds : bool
        Whether to enable EDS (default is True).
    """

    image: ImageSettings
    enable_eds: bool = True


class LaserPolarization(Enum):
    """
    Enum for laser polarization.

    Attributes
    ----------
    VERTICAL : str
        Vertical polarization.
    HORIZONTAL : str
        Horizontal polarization.
    """

    VERTICAL: str = "vertical"
    HORIZONTAL: str = "horizontal"


class LaserPulse(NamedTuple):
    """
    Laser pulse settings.

    Attributes
    ----------
    wavelength_nm : LaserWavelength
        The laser wavelength in nanometers.
    divider : int
        The pulse divider.
    energy_uj : float
        The pulse energy in microjoules.
    polarization : LaserPolarization
        The pulse polarization.
    """

    wavelength_nm: LaserWavelength
    divider: int
    energy_uj: float
    polarization: LaserPolarization


class LaserScanType(Enum):
    """
    Enum for laser scan types.

    Attributes
    ----------
    SERPENTINE : str
        Serpentine scan type.
    RASTER : str
        Raster scan type.
    SINGLE : str
        Single scan type.
    LAP : str
        Lap scan type.
    """

    SERPENTINE: str = "serpentine"
    RASTER: str = "raster"
    SINGLE: str = "single"
    LAP: str = "lap"


class LaserPatternType(Enum):
    """
    Enum for laser pattern types.

    Attributes
    ----------
    BOX : str
        Box pattern type.
    LINE : str
        Line pattern type.
    """

    BOX: str = "box"
    LINE: str = "line"


class LaserBoxPattern(NamedTuple):
    """
    Laser box pattern settings.

    Attributes
    ----------
    passes : int
        The number of passes.
    size_x_um : float
        The size in the x direction in micrometers.
    size_y_um : float
        The size in the y direction in micrometers.
    pitch_x_um : float
        The pitch in the x direction in micrometers.
    pitch_y_um : float
        The pitch in the y direction in micrometers.
    scan_type : LaserScanType
        The scan type (Serpentine or Raster).
    coordinate_ref : CoordinateReference
        The coordinate reference (Center, UpperCenter, or UpperLeft).
    """

    passes: int
    size_x_um: float
    size_y_um: float
    pitch_x_um: float
    pitch_y_um: float
    scan_type: LaserScanType  # Serpentine or Raster
    coordinate_ref: CoordinateReference  # Center, UpperCenter, or UpperLeft
    type = LaserPatternType.BOX


class LaserLinePattern(NamedTuple):
    """
    Laser line pattern settings.

    Attributes
    ----------
    passes : int
        The number of passes.
    size_um : float
        The size in micrometers.
    pitch_um : float
        The pitch in micrometers.
    scan_type : LaserScanType
        The scan type (Single or Lap).
    """

    passes: int
    size_um: float
    pitch_um: float
    scan_type: LaserScanType  # Single or Lap
    type = LaserPatternType.LINE


class LaserPattern(NamedTuple):
    """
    Laser pattern settings.

    Attributes
    ----------
    mode : LaserPatternMode
        The laser pattern mode.
    rotation_deg : float
        The rotation in degrees.
    geometry : Union[LaserBoxPattern, LaserLinePattern]
        The pattern geometry.
    pulses_per_pixel : int
        The number of pulses per pixel.
    pixel_dwell_ms : float
        The pixel dwell time in milliseconds.
    """

    mode: LaserPatternMode
    rotation_deg: float
    geometry: Union[LaserBoxPattern, LaserLinePattern]
    pulses_per_pixel: int = None
    pixel_dwell_ms: float = None


class LaserState(NamedTuple):
    """
    Settings for all readable values from TFS Laser Control.

    Attributes
    ----------
    wavelength_nm : LaserWavelength
        The laser wavelength in nanometers.
    frequency_khz : float
        The frequency in kilohertz.
    pulse_divider : int
        The pulse divider.
    pulse_energy_uj : float
        The pulse energy in microjoules.
    objective_position_mm : float
        The objective position in millimeters.
    beam_shift_um : Point
        The beam shift in micrometers.
    pattern : LaserPattern
        The laser pattern settings.
    expected_pattern_duration_s : float
        The expected pattern duration in seconds.
    """

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
    """
    Laser settings for the microscope.

    Attributes
    ----------
    microscope : Microscope
        The microscope object.
    pulse : LaserPulse
        The laser pulse settings.
    objective_position_mm : float
        The objective position in millimeters.
    beam_shift_um : Point
        The beam shift in micrometers.
    pattern : LaserPattern
        The laser pattern settings.
    """

    microscope: Microscope
    pulse: LaserPulse
    objective_position_mm: float
    beam_shift_um: Point
    pattern: LaserPattern


class Step(NamedTuple):
    """
    Step settings for the experiment.

    Attributes
    ----------
    type : StepType
        The step type.
    name : str
        The step name.
    number : int
        The step number.
    frequency : int
        The step frequency.
    stage : StageSettings
        The stage settings.
    operation_settings : Union[CustomSettings, EBSDSettings, EDSSettings, ImageSettings, FIBSettings, LaserSettings]
        The operation settings for the step.
    """

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
    """
    Experiment settings for the experiment.

    Attributes
    ----------
    microscope : Microscope
        The microscope object.
    general_settings : GeneralSettings
        The general settings for the experiment.
    step_sequence : List[Step]
        The sequence of steps for the experiment.
    enable_EBSD : bool
        Whether to enable EBSD.
    enable_EDS : bool
        Whether to enable EDS.
    """

    microscope: Microscope
    general_settings: GeneralSettings
    step_sequence: List[Step]
    enable_EBSD: bool
    enable_EDS: bool


class YMLFormat(NamedTuple):
    """
    YAML format settings.

    Attributes
    ----------
    version : float
        The version of the YAML format.
    general_section_key : str
        The key for the general section.
    non_step_section_count : int
        The number of non-step sections.
    general_exp_settings : dict
        The general experiment settings.
    step_count_key : str
        The key for the step count.
    step_section_key : str
        The key for the step section.
    step_general_settings : dict
        The general settings for the step.
    step_general_key : str
        The key for the general step settings.
    step_number_key : str
        The key for the step number.
    step_frequency_key : str
        The key for the step frequency.
    step_type_key : str
        The key for the step type.
    step_stage_settings_key : str
        The key for the step stage settings.
    image_step_settings : dict
        The settings for the image step.
    """

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


class YMLFormatVersion(YMLFormat, Enum):
    """
    Enum for YAML format versions.

    Attributes
    ----------
    V_1_0 : YMLFormat
        Version 1.0 of the YAML format.
    """

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
        #     "executable_path": Path,
        # }
    )
    V_1_1 = YMLFormat(
        version=1.1,
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
            "EDAX_settings": EDAXConfig,
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
        #     "executable_path": Path,
        # }
    )

