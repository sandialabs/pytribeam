#!/usr/bin/python3
"""
EDAX Types Module
=================

Enumerated and named-tuple types for the EDAX IPAPI (TEAM/APEX) TCP command
interface, as described in the *EDAX IP / API Reference*, revision 2.3.8.

This module deliberately depends only on the standard library. AutoScript is
not required to import it, so the whole EDAX wrapper and its unit tests run on
machines without a licensed AutoScript installation, matching the convention
established by :mod:`pytribeam.external_oem.bruker.types`.

Several EDAX status enums also appear in :mod:`pytribeam.types` for historical
reasons. The definitions here are the protocol-level source of truth; the
string values are identical, so the two interoperate directly.

Classes
-------
EdaxCommand(str, Enum)
    Every command name supported by the EDAX IPAPI.

EdaxEvent(str, Enum)
    Asynchronous event names pushed by the IPAPI over the same socket.

EdaxAccessType(IntEnum)
    Remote access source type (Normal, NoWait, None).

EdaxEbsdMode(IntEnum)
    EBSD mapping mode.

EdaxEbsdResolution(IntEnum)
    EBSD mapping resolution preset (Fine, Medium, Coarse, Custom).

EdaxGridType(IntEnum)
    EBSD sampling grid (hexagonal or square).

EdaxMappingStatus(str, Enum)
    EDS and EBSD mapping status.

EdaxCameraStatus(str, Enum)
    EBSD camera slide status.

EdaxDetectorStatus(str, Enum)
    EDS detector readiness.

EdaxDetectorSlideStatus(str, Enum)
    EDS detector slide position status.

EdaxLimit(NamedTuple)
    Inclusive min/max range for a scalar parameter.

EdaxConnectionSettings(NamedTuple)
    Socket connection and default timing settings for an IPAPI client.

EdaxResponse(NamedTuple)
    A single parsed message received from the IPAPI.

EdaxProjectInfo(NamedTuple)
    Project identity and 3D slice information.

EdaxEbsdMapParams(NamedTuple)
    Complete EBSD mapping parameter set (IPAPI section 2.5).

EdaxEdsMapParams(NamedTuple)
    Complete EDS mapping parameter set (IPAPI section 2.3).

EdaxCameraParams(NamedTuple)
    Writable EBSD camera parameters (IPAPI section 2.6 setters).

EdaxCameraLimits(NamedTuple)
    Read-only min/max limits for the writable camera parameters.

EdaxCameraCapabilities(NamedTuple)
    Read-only camera feature-support flags.

EdaxCameraInfo(NamedTuple)
    Read-only camera frame geometry and rate.

EdaxCameraSlidePositions(NamedTuple)
    Camera slide travel limits and current position, in millimeters.

EdaxSemState(NamedTuple)
    SEM state as reported through the IPAPI.

EdaxSettings(NamedTuple)
    Top-level EDAX settings bundle for vendor-dispatched mapping operations.
"""

# Default python modules
from enum import Enum, IntEnum
from pathlib import Path
from typing import NamedTuple, Optional, Tuple


### ENUMERATED TYPES ###


class EdaxCommand(str, Enum):
    """
    Every command name supported by the EDAX IPAPI.

    Commands are case-insensitive on the wire; the canonical lower-case form is
    stored here so that command strings and response prefixes compare directly.
    Section numbers refer to the *EDAX IP / API Reference*, revision 2.3.8.
    """

    # --- 2.1 Security unlock -------------------------------------------------
    UNLOCK = "edax_unlock"

    # --- 2.2 EDS mapping commands --------------------------------------------
    EDS_SETUP_START = "do_map_setup_start"
    EDS_SETUP_STOP = "do_map_setup_stop"
    EDS_SETUP_ABORT = "do_map_setup_abort"
    EDS_COLLECTION_START = "do_map_collection_start"
    EDS_COLLECTION_STOP = "do_map_collection_stop"
    EDS_COLLECTION_RESUME = "do_map_collection_resume"
    EDS_COLLECTION_PAUSE = "do_map_collection_pause"
    EDS_GET_MAP_DURATION = "get_map_duration"
    EDS_GET_MAP_SETUP_DURATION = "get_map_setup_duration"  # not implemented by EDAX
    EDS_GET_SYSTEM_DETECTOR_STATUS = "get_system_detector_status"
    EDS_GET_MAP_STATUS = "get_map_status"
    EDS_GET_SYSTEM_ISAPPSTARTED = "get_system_isappstarted"
    EDS_SET_SYSTEM_REMOTEACCESSTYPE = "set_system_remoteaccesstype"
    EDS_SET_SYSTEM_PROJECTINFO = "set_system_projectinfo"
    EDS_SET_SYSTEM_PROJECTINFO_EXT = "set_system_projectinfo_ext"
    EDS_INSERT_DETECTOR = "do_insert_eds_detector"
    EDS_RETRACT_DETECTOR = "do_retract_eds_detector"
    EDS_SET_DETECTOR_COOLING = "set_eds_detector_cooling"
    EDS_GET_DETECTOR_COOLING_STATUS = "get_eds_detector_cooling_status"
    EDS_GET_DETECTOR_STATUS = "get_eds_detector_status"

    # --- 2.3 EDS mapping parameters ------------------------------------------
    EDS_SET_FOLDERPATH = "set_map_params_folderpath"
    EDS_GET_FOLDERPATH = "get_map_params_folderpath"
    EDS_SET_EDSCHANNEL = "set_map_params_edschannel"
    EDS_GET_EDSCHANNEL = "get_map_params_edschannel"
    EDS_SET_NUMFRAMES = "set_map_params_numframes"
    EDS_GET_NUMFRAMES = "get_map_params_numframes"
    EDS_SET_NUMPOINTS = "set_map_params_numpoints"
    EDS_GET_NUMPOINTS = "get_map_params_numpoints"
    EDS_SET_NUMLINES = "set_map_params_numlines"
    EDS_GET_NUMLINES = "get_map_params_numlines"
    EDS_SET_PRESETDWELL = "set_map_params_presetdwell"
    EDS_GET_PRESETDWELL = "get_map_params_presetdwell"
    EDS_SET_EDSNUMCHAN = "set_map_params_edsnumchan"
    EDS_GET_EDSNUMCHAN = "get_map_params_edsnumchan"
    EDS_SET_BYTESPERCHANNEL = "set_map_params_bytesperchannel"
    EDS_GET_BYTESPERCHANNEL = "get_map_params_bytesperchannel"
    EDS_SET_IPD = "set_map_params_ipd"
    EDS_GET_IPD = "get_map_params_ipd"
    EDS_SET_NUMREADS = "set_map_params_numreads"
    EDS_GET_NUMREADS = "get_map_params_numreads"

    # --- 2.4 EBSD mapping commands -------------------------------------------
    EBSD_SETUP_START = "do_map_setup_start_ebsd"
    EBSD_SETUP_STOP = "do_map_setup_stop_ebsd"
    EBSD_SETUP_ABORT = "do_map_setup_abort_ebsd"
    EBSD_COLLECTION_START = "do_map_collection_start_ebsd"
    EBSD_COLLECTION_STOP = "do_map_collection_stop_ebsd"
    EBSD_COLLECTION_RESUME = "do_map_collection_resume_ebsd"
    EBSD_COLLECTION_PAUSE = "do_map_collection_pause_ebsd"
    EBSD_INSERT_CAMERA = "do_map_insert_camera"
    EBSD_RETRACT_CAMERA = "do_map_retract_camera"
    EBSD_RETRACT_CAMERA_DISTANCE = "do_map_retract_camera_distance"
    EBSD_GET_MAP_DURATION = "get_map_duration_ebsd"
    EBSD_GET_MAP_SETUP_DURATION = "get_map_setup_duration_ebsd"  # not implemented
    EBSD_GET_CAMERA_STATUS = "get_camera_status"
    EBSD_GET_MAP_STATUS = "get_map_status_ebsd"
    EBSD_GET_SYSTEM_ISAPPSTARTED = "get_system_isappstarted_ebsd"
    EBSD_SET_SYSTEM_REMOTEACCESSTYPE = "set_system_remoteaccesstype_ebsd"
    EBSD_SET_SYSTEM_PROJECTINFO = "set_system_projectinfo_ebsd"
    EBSD_SET_SYSTEM_PROJECTINFO_EXT = "set_system_projectinfo_ext_ebsd"
    EBSD_GET_SLIDE_POSITION_INSERTED = "get_camera_slide_position_inserted"
    EBSD_GET_SLIDE_POSITION_RETRACTED = "get_camera_slide_position_retracted"
    EBSD_GET_SLIDE_POSITION = "get_camera_slide_position"
    EBSD_SET_SLIDE_POSITION = "set_camera_slide_position"
    EBSD_GET_CAMERA_SATURATION = "get_camera_saturation"
    EBSD_GET_MAP_AVG_CI = "get_map_avg_ci"
    EBSD_CAMERA_SNAPSHOT = "do_camera_snapshot"
    EBSD_CAMERA_CAPTURE_SCAN = "do_camera_capture_scan"
    EBSD_CAMERA_CAPTURE_BACKGROUND = "do_camera_capture_background"
    EBSD_CAMERA_CAPTURE_BACKGROUND_AUTO = "do_camera_capture_background_auto"
    EBSD_CAMERA_CAPTURE_BACKGROUND_SMART = "do_camera_capture_background_smart"
    EBSD_CAMERA_BLACK_REFERENCE = "do_camera_black_reference"
    EBSD_CAMERA_SAVE_PRESET = "do_camera_save_preset"
    EBSD_CAMERA_LOAD_PRESET = "do_camera_load_preset"
    EBSD_CAMERA_DELETE_PRESET = "do_camera_delete_preset"

    # --- 2.4 SEM commands (shared, exposed through the EBSD interface) -------
    SEM_GET_MAGNIFICATION = "get_sem_magnification"
    SEM_SET_MAGNIFICATION = "set_sem_magnification"
    SEM_GET_EXTERNAL_BEAM_CONTROL = "get_sem_external_beam_control"
    SEM_SET_EXTERNAL_BEAM_CONTROL = "set_sem_external_beam_control"
    SEM_GET_IMAGE_WIDTH = "get_sem_image_width"
    SEM_GET_IMAGE_HEIGHT = "get_sem_image_height"
    SEM_GET_PRETILT_ANGLE = "get_pretilt_angle"
    SEM_SET_PRETILT_ANGLE = "set_pretilt_angle"
    SEM_SET_BEAM_LOCATION = "set_beam_location"

    # --- 2.5 EBSD mapping parameters -----------------------------------------
    EBSD_SET_FOLDERPATH = "set_ebsd_params_folderpath"
    EBSD_GET_FOLDERPATH = "get_ebsd_params_folderpath"
    EBSD_SET_MODE = "set_ebsd_params_mode"
    EBSD_GET_MODE = "get_ebsd_params_mode"
    EBSD_SET_RESOLUTION = "set_ebsd_params_resolution"
    EBSD_GET_RESOLUTION = "get_ebsd_params_resolution"
    EBSD_SET_GRID = "set_ebsd_params_grid"
    EBSD_GET_GRID = "get_ebsd_params_grid"
    EBSD_SET_SAVEHOUGHPEAKS = "set_ebsd_params_savehoughpeaks"
    EBSD_GET_SAVEHOUGHPEAKS = "get_ebsd_params_savehoughpeaks"
    EBSD_SET_SAVEPATTERNS = "set_ebsd_params_savepatterns"
    EBSD_GET_SAVEPATTERNS = "get_ebsd_params_savepatterns"
    EBSD_SET_SAVESPECTRA = "set_ebsd_params_savespectra"
    EBSD_GET_SAVESPECTRA = "get_ebsd_params_savespectra"
    EBSD_SET_XSTART = "set_ebsd_params_xstart"
    EBSD_GET_XSTART = "get_ebsd_params_xstart"
    EBSD_SET_YSTART = "set_ebsd_params_ystart"
    EBSD_GET_YSTART = "get_ebsd_params_ystart"
    EBSD_SET_XSIZE = "set_ebsd_params_xsize"
    EBSD_GET_XSIZE = "get_ebsd_params_xsize"
    EBSD_SET_YSIZE = "set_ebsd_params_ysize"
    EBSD_GET_YSIZE = "get_ebsd_params_ysize"
    EBSD_SET_STEPSIZE = "set_ebsd_params_stepsize"
    EBSD_GET_STEPSIZE = "get_ebsd_params_stepsize"
    EBSD_SET_CUSTOMSTEPSIZE = "set_ebsd_params_customstepsize"
    EBSD_GET_CUSTOMSTEPSIZE = "get_ebsd_params_customstepsize"
    EBSD_SET_EDSNUMCHAN = "set_ebsd_params_edsnumchan"
    EBSD_GET_EDSNUMCHAN = "get_ebsd_params_edsnumchan"
    EBSD_SET_BYTESPERCHANNEL = "set_ebsd_params_bytesperchannel"
    EBSD_GET_BYTESPERCHANNEL = "get_ebsd_params_bytesperchannel"

    # --- 2.6 EBSD camera parameters ------------------------------------------
    CAMERA_GET_BINNING = "get_camera_params_binning"
    CAMERA_SET_BINNING = "set_camera_params_binning"
    CAMERA_GET_BINNING_NAMES = "get_camera_params_binning_names"
    CAMERA_GET_BINNINGCUMULATIVE = "get_camera_params_binningcumulative"
    CAMERA_SET_BINNINGCUMULATIVE = "set_camera_params_binningcumulative"
    CAMERA_GET_DOUBLESCANRATE = "get_camera_params_doublescanrate"
    CAMERA_SET_DOUBLESCANRATE = "set_camera_params_doublescanrate"
    CAMERA_GET_DUALTAP = "get_camera_params_dualtap"
    CAMERA_SET_DUALTAP = "set_camera_params_dualtap"
    CAMERA_GET_EXPOSURE = "get_camera_params_exposure"
    CAMERA_SET_EXPOSURE = "set_camera_params_exposure"
    CAMERA_GET_EXPOSURE_MAX = "get_camera_params_exposure_max"
    CAMERA_GET_EXPOSURE_MIN = "get_camera_params_exposure_min"
    CAMERA_GET_FRAMEAVGBACKGROUND = "get_camera_params_frameavgbackground"
    CAMERA_SET_FRAMEAVGBACKGROUND = "set_camera_params_frameavgbackground"
    CAMERA_GET_FRAMEAVGBACKGROUND_MAX = "get_camera_params_frameavgbackground_max"
    CAMERA_GET_FRAMEAVGBACKGROUND_MIN = "get_camera_params_frameavgbackground_min"
    CAMERA_GET_FRAMEAVGSCAN = "get_camera_params_frameavgscan"
    CAMERA_SET_FRAMEAVGSCAN = "set_camera_params_frameavgscan"
    CAMERA_GET_FRAMEAVGSCAN_MAX = "get_camera_params_frameavgscan_max"
    CAMERA_GET_FRAMEAVGSCAN_MIN = "get_camera_params_frameavgscan_min"
    CAMERA_GET_FRAMEAVGSNAPSHOT = "get_camera_params_frameavgsnapshot"
    CAMERA_SET_FRAMEAVGSNAPSHOT = "set_camera_params_frameavgsnapshot"
    CAMERA_GET_FRAMEAVGSNAPSHOT_MAX = "get_camera_params_frameavgsnapshot_max"
    CAMERA_GET_FRAMEAVGSNAPSHOT_MIN = "get_camera_params_frameavgsnapshot_min"
    CAMERA_GET_FRAME_BITDEPTH = "get_camera_params_frame_bitdepth"
    CAMERA_GET_FRAME_HEIGHT = "get_camera_params_frame_height"
    CAMERA_GET_FRAME_WIDTH = "get_camera_params_frame_width"
    CAMERA_GET_FRAME_RATE = "get_camera_params_frame_rate"
    CAMERA_GET_GAIN = "get_camera_params_gain"
    CAMERA_SET_GAIN = "set_camera_params_gain"
    CAMERA_GET_GAIN_MAX = "get_camera_params_gain_max"
    CAMERA_GET_GAIN_MIN = "get_camera_params_gain_min"
    CAMERA_SET_HIGHGAIN = "set_camera_params_highgain"
    CAMERA_GET_IMAGEPROCESSINGMODEINT = "get_camera_params_imageprocessingmodeint"
    CAMERA_SET_IMAGEPROCESSINGMODEINT = "set_camera_params_imageprocessingmodeint"
    CAMERA_GET_REDUCEDBITDEPTH = "get_camera_params_reducedbitdepth"
    CAMERA_SET_REDUCEDBITDEPTH = "set_camera_params_reducedbitdepth"
    CAMERA_ISSUPPORT_BINNINGCUMULATIVE = "get_camera_params_issupport_binningcumulative"
    CAMERA_ISSUPPORT_BLACKREFERENCE = "get_camera_params_issupport_blackreference"
    CAMERA_ISSUPPORT_DOUBLESCANRATE = "get_camera_params_issupport_doublescanrate"
    CAMERA_ISSUPPORT_DUALTAP = "get_camera_params_issupport_dualtap"
    CAMERA_ISSUPPORT_GAIN = "get_camera_params_issupport_gain"
    CAMERA_ISSUPPORT_HIGHGAIN = "get_camera_params_issupport_highgain"
    CAMERA_ISSUPPORT_REDUCEDBITDEPTH = "get_camera_params_issupport_reducedbitdepth"


class EdaxEvent(str, Enum):
    """
    Asynchronous event names pushed by the IPAPI over the command socket.

    Events may arrive at any time, interleaved with command responses, so the
    client buffers them rather than treating them as protocol errors.

    Attributes
    ----------
    EDS_SETUP_COMPLETE : str
        EDS mapping setup finished.
    EDS_COLLECTION_COMPLETE : str
        EDS map collection finished.
    EBSD_SETUP_COMPLETE : str
        EBSD mapping setup finished.
    EBSD_COLLECTION_COMPLETE : str
        EBSD map collection finished.
    """

    EDS_SETUP_COMPLETE = "event_map_setup_complete"
    EDS_COLLECTION_COMPLETE = "event_map_collection_complete"
    EBSD_SETUP_COMPLETE = "event_map_setup_complete_ebsd"
    EBSD_COLLECTION_COMPLETE = "event_map_collection_complete_ebsd"


class EdaxAccessType(IntEnum):
    """
    Remote access source type, IPAPI section 3.3.

    Attributes
    ----------
    NORMAL : int
        The operator selects the map folder during setup.
    NO_WAIT : int
        The folder path must be set over the IPAPI before mapping begins.
    NONE : int
        The EDAX application behaves as though no client is connected.
    """

    NORMAL = 0
    NO_WAIT = 1
    NONE = 2


class EdaxEbsdMode(IntEnum):
    """
    EBSD mapping mode, IPAPI section 2.5.3.

    Attributes
    ----------
    NORMAL : int
        The only mode EDAX currently supports.
    """

    NORMAL = 0


class EdaxEbsdResolution(IntEnum):
    """
    EBSD mapping resolution preset, IPAPI section 2.5.5.

    Step size is only honored when the resolution is ``CUSTOM``.

    Attributes
    ----------
    FINE : int
        Fine preset resolution.
    MEDIUM : int
        Medium preset resolution.
    COARSE : int
        Coarse preset resolution.
    CUSTOM : int
        Step size taken from the custom step size parameter.
    """

    FINE = 0
    MEDIUM = 1
    COARSE = 2
    CUSTOM = 3


class EdaxGridType(IntEnum):
    """
    EBSD sampling grid, IPAPI section 2.5.7.

    Attributes
    ----------
    HEXAGONAL : int
        Hexagonal sampling grid.
    SQUARE : int
        Square sampling grid.
    """

    HEXAGONAL = 0
    SQUARE = 1


class EdaxMappingStatus(str, Enum):
    """
    EDS and EBSD mapping status, IPAPI sections 3.2 and 3.5.

    Both mapping status enumerations share the same members. Values are the
    lower-cased string representations returned by the IPAPI.
    """

    NOT_READY = "notready"
    READY = "ready"
    SETUP_ACTIVE = "setupactive"
    SETUP_COMPLETE = "setupcomplete"
    SETUP_PAUSED = "setuppaused"
    SETUP_RESUMED = "setupresumed"
    SETUP_ABORTED = "setupaborted"
    SETUP_STOPPED = "setupstopped"
    SETUP_ERROR = "setuperror"
    MAPPING_ACTIVE = "mappingactive"
    MAPPING_COMPLETE = "mappingcomplete"
    MAPPING_PAUSED = "mappingpaused"
    MAPPING_RESUMED = "mappingresumed"
    MAPPING_ABORTED = "mappingaborted"
    MAPPING_STOPPED = "mappingstopped"
    MAPPING_ERROR = "mappingerror"
    UNKNOWN = "unknownerror"

    @property
    def is_terminal(self) -> bool:
        """Return True when no further mapping progress is expected."""
        return self in _TERMINAL_MAPPING_STATUSES

    @property
    def is_error(self) -> bool:
        """Return True for statuses that indicate a failed operation."""
        return self in _ERROR_MAPPING_STATUSES


_TERMINAL_MAPPING_STATUSES = frozenset(
    {
        EdaxMappingStatus.READY,
        EdaxMappingStatus.MAPPING_COMPLETE,
        EdaxMappingStatus.MAPPING_ABORTED,
        EdaxMappingStatus.MAPPING_STOPPED,
        EdaxMappingStatus.MAPPING_ERROR,
        EdaxMappingStatus.UNKNOWN,
    }
)

_ERROR_MAPPING_STATUSES = frozenset(
    {
        EdaxMappingStatus.SETUP_ERROR,
        EdaxMappingStatus.MAPPING_ERROR,
        EdaxMappingStatus.UNKNOWN,
    }
)


class EdaxCameraStatus(str, Enum):
    """
    EBSD camera slide status, IPAPI section 3.4.

    Values are the lower-cased string representations returned by the IPAPI.
    """

    SLIDE_OUT = "slideout"
    SLIDE_IN = "slidein"
    SLIDE_MOVING_OUT = "slidemovingout"
    SLIDE_MOVING_IN = "slidemovingin"
    SLIDE_HIGH_COUNT = "slidehighcount"
    SLIDE_NO_POWER = "slidenopower"
    SLIDE_MID = "slidemid"
    SLIDE_STOPPED = "slidestopped"
    SLIDE_ERROR = "slideerror"
    SLIDE_INIT = "slideinit"
    SLIDE_MOVE_MID_IN = "slidemovemidin"
    SLIDE_MOVE_MID_OUT = "slidemovemidout"
    SLIDE_WATCHDOG = "slidewatchdog"
    SLIDE_MOVE_WDOG = "slidemovewdog"
    SLIDE_DISABLED = "slidedisabled"
    SLIDE_MOVE_TOUCH = "slidemovetouch"
    SLIDE_TOUCH_SENSE = "slidetouchsense"
    UNKNOWN = "unknown"

    @property
    def is_moving(self) -> bool:
        """Return True while the slide is in transit."""
        return self in _MOVING_CAMERA_STATUSES

    @property
    def is_error(self) -> bool:
        """Return True for statuses that require operator intervention."""
        return self in _ERROR_CAMERA_STATUSES


_MOVING_CAMERA_STATUSES = frozenset(
    {
        EdaxCameraStatus.SLIDE_MOVING_IN,
        EdaxCameraStatus.SLIDE_MOVING_OUT,
        EdaxCameraStatus.SLIDE_MOVE_MID_IN,
        EdaxCameraStatus.SLIDE_MOVE_MID_OUT,
        EdaxCameraStatus.SLIDE_MOVE_TOUCH,
    }
)

_ERROR_CAMERA_STATUSES = frozenset(
    {
        EdaxCameraStatus.SLIDE_ERROR,
        EdaxCameraStatus.SLIDE_NO_POWER,
        EdaxCameraStatus.SLIDE_WATCHDOG,
        EdaxCameraStatus.SLIDE_DISABLED,
    }
)


class EdaxDetectorStatus(str, Enum):
    """
    EDS detector readiness, IPAPI section 3.1.

    Attributes
    ----------
    NOT_READY : str
        Detector is not ready for collection.
    READY : str
        Detector is ready for collection.
    """

    NOT_READY = "notready"
    READY = "ready"


class EdaxDetectorSlideStatus(str, Enum):
    """
    EDS detector slide position status, IPAPI section 3.6.

    Attributes
    ----------
    SLIDE_OUT : str
        Detector slide is retracted.
    SLIDE_IN : str
        Detector slide is inserted.
    UNKNOWN : str
        Detector slide position is indeterminate.
    """

    SLIDE_OUT = "slideout"
    SLIDE_IN = "slidein"
    UNKNOWN = "unknown"


### NAMED TUPLE TYPES ###


class EdaxLimit(NamedTuple):
    """
    Inclusive min/max range for a scalar parameter.

    Mirrors :class:`pytribeam.types.Limit` without requiring AutoScript.

    Attributes
    ----------
    min : float
        Minimum allowed value.
    max : float
        Maximum allowed value.
    """

    min: float
    max: float

    def contains(self, value: float) -> bool:
        """Return True when ``value`` falls within the closed interval."""
        return self.min <= value <= self.max


class EdaxConnectionSettings(NamedTuple):
    """
    Socket connection and default timing settings for an IPAPI client.

    Attributes
    ----------
    host : str
        Hostname or IP address of the machine running the EDAX IPAPI service.
    port : int
        TCP port of the IPAPI service (default is 8301).
    timeout_s : float
        Default per-command response timeout in seconds.
    pause_s : float
        Default settling pause after sending a command, in seconds.
    connect_timeout_s : float
        Timeout for establishing the TCP connection, in seconds.
    """

    host: str
    port: int = 8301
    timeout_s: float = 10.0
    pause_s: float = 0.2
    connect_timeout_s: float = 10.0


class EdaxResponse(NamedTuple):
    """
    A single parsed message received from the IPAPI.

    Attributes
    ----------
    raw : str
        The message exactly as received, with surrounding whitespace removed.
    command : str
        The command name or event name that prefixes the message, lower-cased.
        Empty when the message carries no recognizable prefix.
    payload : str
        The message body with the prefix, the ``RESPONSE`` keyword, and any
        enclosing double quotes removed. Interior spacing is preserved so that
        values such as file paths survive intact.
    is_event : bool
        True when the message is an asynchronous ``EVENT_*`` notification
        rather than a response to a command.
    """

    raw: str
    command: str
    payload: str
    is_event: bool = False

    @property
    def succeeded(self) -> bool:
        """Return True when the payload reports successful execution."""
        return self.payload.strip().lower() == "execution successful"


class EdaxProjectInfo(NamedTuple):
    """
    Project identity and 3D slice information, IPAPI sections 2.2.15 / 2.4.18.

    Attributes
    ----------
    guid : str
        String representation of a saved project GUID.
    name : str
        Project name. An existing name loads that project instead of creating
        a new one.
    num_slices : int
        Number of slices to map, for 3D collections.
    slice_thickness_um : float
        Slice thickness in micrometers, for 3D collections.
    """

    guid: str
    name: str
    num_slices: Optional[int] = None
    slice_thickness_um: Optional[float] = None


class EdaxEbsdMapParams(NamedTuple):
    """
    Complete EBSD mapping parameter set, IPAPI section 2.5.

    Every field is optional; ``None`` means "leave the current value alone"
    when the parameter set is applied to a connected system.

    Attributes
    ----------
    folder_path : Path
        Folder on the EDAX computer where map data is stored.
    mode : EdaxEbsdMode
        EBSD mapping mode.
    resolution : EdaxEbsdResolution
        Resolution preset. Step size only applies when ``CUSTOM``.
    grid : EdaxGridType
        Hexagonal or square sampling grid.
    save_hough_peaks : bool
        Whether to save Hough peaks during mapping.
    save_patterns : bool
        Whether to save EBSD patterns during mapping.
    save_spectra : bool
        Whether to save spectra during combined EDS/EBSD mapping.
    x_start_um : float
        X coordinate of the mapping area, with 0 at the center of the field
        of view.
    y_start_um : float
        Y coordinate of the mapping area, with 0 at the center of the field
        of view.
    x_size_um : float
        Width of the mapping area in micrometers.
    y_size_um : float
        Height of the mapping area in micrometers.
    step_size_um : float
        Step size in micrometers, honored only for custom resolution.
    custom_step_size_um : float
        Custom step size in micrometers, honored only for custom resolution.
    eds_num_channels : int
        Spectrum channels per point for combined EDS/EBSD mapping.
    bytes_per_channel : int
        Bytes per spectrum channel for combined EDS/EBSD mapping.
    """

    folder_path: Optional[Path] = None
    mode: Optional[EdaxEbsdMode] = None
    resolution: Optional[EdaxEbsdResolution] = None
    grid: Optional[EdaxGridType] = None
    save_hough_peaks: Optional[bool] = None
    save_patterns: Optional[bool] = None
    save_spectra: Optional[bool] = None
    x_start_um: Optional[float] = None
    y_start_um: Optional[float] = None
    x_size_um: Optional[float] = None
    y_size_um: Optional[float] = None
    step_size_um: Optional[float] = None
    custom_step_size_um: Optional[float] = None
    eds_num_channels: Optional[int] = None
    bytes_per_channel: Optional[int] = None


class EdaxEdsMapParams(NamedTuple):
    """
    Complete EDS mapping parameter set, IPAPI section 2.3.

    Every field is optional; ``None`` means "leave the current value alone"
    when the parameter set is applied to a connected system.

    Attributes
    ----------
    folder_path : Path
        Folder on the EDAX computer where map data is stored.
    eds_channel : int
        Channel number of the EDS detector.
    num_frames : int
        Number of frames in the map.
    num_points : int
        Number of points in one line of the map.
    num_lines : int
        Number of lines in one frame of the map.
    preset_dwell_us : float
        Dwell time per point in microseconds.
    eds_num_channels : int
        Spectrum channels per point.
    bytes_per_channel : int
        Bytes per spectrum channel.
    inter_pixel_delay : int
        Inter-pixel delay for the scan generator board.
    num_reads : int
        Number of reads of the video signal.
    """

    folder_path: Optional[Path] = None
    eds_channel: Optional[int] = None
    num_frames: Optional[int] = None
    num_points: Optional[int] = None
    num_lines: Optional[int] = None
    preset_dwell_us: Optional[float] = None
    eds_num_channels: Optional[int] = None
    bytes_per_channel: Optional[int] = None
    inter_pixel_delay: Optional[int] = None
    num_reads: Optional[int] = None


class EdaxCameraParams(NamedTuple):
    """
    Writable EBSD camera parameters, IPAPI section 2.6 setters.

    Every field is optional; ``None`` means "leave the current value alone"
    when the parameter set is applied to a connected system.

    Attributes
    ----------
    binning : str
        Name of the binning mode, one of the values reported by the camera.
    binning_cumulative : bool
        Whether cumulative binning is enabled.
    double_scan_rate : bool
        Whether double scan rate is enabled.
    dual_tap : bool
        Whether dual tap readout is enabled.
    exposure_ms : float
        Camera exposure in milliseconds.
    frame_avg_background : int
        Frames averaged when capturing a background image.
    frame_avg_scan : int
        Frames averaged when capturing a mapping image.
    frame_avg_snapshot : int
        Frames averaged when capturing a snapshot image.
    gain : float
        Camera gain.
    high_gain : bool
        Whether high gain mode is enabled.
    image_processing_mode : int
        Camera image processing mode, as an integer.
    reduced_bit_depth : bool
        Whether reduced bit depth mode is enabled.
    """

    binning: Optional[str] = None
    binning_cumulative: Optional[bool] = None
    double_scan_rate: Optional[bool] = None
    dual_tap: Optional[bool] = None
    exposure_ms: Optional[float] = None
    frame_avg_background: Optional[int] = None
    frame_avg_scan: Optional[int] = None
    frame_avg_snapshot: Optional[int] = None
    gain: Optional[float] = None
    high_gain: Optional[bool] = None
    image_processing_mode: Optional[int] = None
    reduced_bit_depth: Optional[bool] = None


class EdaxCameraLimits(NamedTuple):
    """
    Read-only min/max limits for the writable camera parameters.

    Attributes
    ----------
    exposure_ms : EdaxLimit
        Allowed camera exposure range in milliseconds.
    gain : EdaxLimit
        Allowed camera gain range.
    frame_avg_background : EdaxLimit
        Allowed background frame-averaging range.
    frame_avg_scan : EdaxLimit
        Allowed mapping frame-averaging range.
    frame_avg_snapshot : EdaxLimit
        Allowed snapshot frame-averaging range.
    """

    exposure_ms: EdaxLimit
    gain: EdaxLimit
    frame_avg_background: EdaxLimit
    frame_avg_scan: EdaxLimit
    frame_avg_snapshot: EdaxLimit


class EdaxCameraCapabilities(NamedTuple):
    """
    Read-only camera feature-support flags, IPAPI sections 2.6.26 - 2.6.32.

    Attributes
    ----------
    binning_cumulative : bool
        Camera supports cumulative binning.
    black_reference : bool
        Camera supports black reference capture.
    double_scan_rate : bool
        Camera supports double scan rate.
    dual_tap : bool
        Camera supports dual tap readout.
    gain : bool
        Camera supports gain adjustment.
    high_gain : bool
        Camera supports high gain mode.
    reduced_bit_depth : bool
        Camera supports reduced bit depth mode.
    """

    binning_cumulative: bool
    black_reference: bool
    double_scan_rate: bool
    dual_tap: bool
    gain: bool
    high_gain: bool
    reduced_bit_depth: bool


class EdaxCameraInfo(NamedTuple):
    """
    Read-only camera frame geometry and rate.

    Attributes
    ----------
    width_px : int
        Frame width in pixels.
    height_px : int
        Frame height in pixels.
    bit_depth : int
        Frame bit depth.
    frame_rate_hz : float
        Camera frame rate.
    binning_names : Tuple[str, ...]
        Names of the binning modes the camera supports.
    """

    width_px: int
    height_px: int
    bit_depth: int
    frame_rate_hz: float
    binning_names: Tuple[str, ...] = ()


class EdaxCameraSlidePositions(NamedTuple):
    """
    Camera slide travel limits and current position, in millimeters.

    Attributes
    ----------
    current_mm : float
        Current slide position.
    inserted_mm : float
        Slide position when fully inserted.
    retracted_mm : float
        Slide position when fully retracted.
    """

    current_mm: float
    inserted_mm: float
    retracted_mm: float


class EdaxSemState(NamedTuple):
    """
    SEM state as reported through the IPAPI, sections 2.4.34 - 2.4.41.

    Attributes
    ----------
    magnification : int
        SEM magnification.
    external_beam_control : bool
        Whether the SEM is under external beam control.
    image_width_px : int
        SEM image width in pixels.
    image_height_px : int
        SEM image height in pixels.
    pretilt_deg : float
        Pretilt holder angle in degrees.
    """

    magnification: int
    external_beam_control: bool
    image_width_px: int
    image_height_px: int
    pretilt_deg: float


class EdaxSettings(NamedTuple):
    """
    Top-level EDAX settings bundle for vendor-dispatched mapping operations.

    This is the EDAX member of the settings union consumed by the external-OEM
    dispatcher, alongside the equivalent Bruker and Oxford bundles.

    Attributes
    ----------
    connection : EdaxConnectionSettings
        IPAPI socket connection settings.
    save_directory : Path
        Folder on the EDAX computer where map data is stored.
    project_name : str
        Name of the EDAX project.
    project_guid : str
        GUID of a previously saved EDAX project.
    access_type : EdaxAccessType
        Remote access source type used during map setup.
    ebsd_params : EdaxEbsdMapParams
        EBSD mapping parameters, when EBSD collection is enabled.
    eds_params : EdaxEdsMapParams
        EDS mapping parameters, when EDS collection is enabled.
    camera_params : EdaxCameraParams
        EBSD camera parameters to apply before mapping.
    """

    connection: EdaxConnectionSettings
    save_directory: Path
    project_name: str
    project_guid: Optional[str] = None
    access_type: EdaxAccessType = EdaxAccessType.NO_WAIT
    ebsd_params: Optional[EdaxEbsdMapParams] = None
    eds_params: Optional[EdaxEdsMapParams] = None
    camera_params: Optional[EdaxCameraParams] = None
