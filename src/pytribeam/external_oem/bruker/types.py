from typing import Literal, NamedTuple, Optional, Tuple

BrukerConnectionMode = Literal["local", "tcp"]
BrukerEDSDetectorPositionName = Literal["park", "acquire"]


class BrukerSessionSettings(NamedTuple):
    dll_dir: str
    mode: BrukerConnectionMode
    server: str
    user: str
    password: str
    host: Optional[str]
    port: Optional[int]
    close_on_exit: bool
    keep_connection_open: bool


class BrukerEDSMapSettings(NamedTuple):
    name: str
    width_px: int
    height_px: int
    pixel_time_us: int
    real_time_s: int
    output_bcf_path: str
    output_image_path: Optional[str]
    output_image_format: Optional[str]
    spu_device: int


class BrukerEDSElementMapSetting(NamedTuple):
    atomic_number: int
    line: str  # e.g. "KA", "LA", "MA"; Bruker also seems to accept "K", etc.
    energy_keV: float = 0.0  # use 0.0 if using atomic_number + line
    width: float = 1.0  # region width scaling factor

    # Optional display hint only. If None, BrukerEDSController assigns
    # a default palette color based on element order.
    display_rgb: Optional[Tuple[int, int, int]] = None


class BrukerEDSProfileMapSettings(NamedTuple):
    name: str
    width_px: int
    height_px: int
    pixel_time_us: int
    output_bcf_path: str
    output_image_path: Optional[str]
    output_image_format: Optional[str]
    spu_device: int
    elements: Tuple[BrukerEDSElementMapSetting, ...]

    # Profile visual/processing options
    image_filter: int
    map_filter: int
    map_filter_width: int
    color_mix_method: int
    brightness: float
    gamma: float
    color_saturation: float
    absolute_scaling: bool
    normalization: bool
    deconvolution: bool


class BrukerEDSElementMapData(NamedTuple):
    atomic_number: int
    line: str
    energy_keV: float
    width: float
    element_index: int
    data_shape: Tuple[int, int]
    dtype: str


class BrukerDetectorMotionSettings(NamedTuple):
    detector_index: int
    target_position: BrukerEDSDetectorPositionName
    timeout_s: float
    poll_interval_s: float


class BrukerMapProgress(NamedTuple):
    running: bool
    percent_complete: float
    current_line: int


class BrukerMapOutputs(NamedTuple):
    output_bcf_path: str
    output_image_path: Optional[str]


class BrukerDetectorPositionState(NamedTuple):
    detector_index: int
    position_code: int
    position_name: str


class BrukerConnectionInfo(NamedTuple):
    cid: int
    query_info: str


class BrukerEBSDDetectorMotionSettings(NamedTuple):
    target_position_mm: float
    speed_mm_per_s: float
    tolerance_mm: float
    timeout_s: float
    poll_interval_s: float
    stable_polls: int


class BrukerEBSDDetectorPositionState(NamedTuple):
    position_mm: float


class BrukerEBSDDetectorMotionResult(NamedTuple):
    requested_position_mm: float
    final_position_mm: float
    error_mm: float
    within_tolerance: bool
    set_call_rc: Optional[int]


class BrukerEBSDProfileSelection(NamedTuple):
    profile_name: str


class BrukerEBSDScanAreaSettings(NamedTuple):
    width_px: int
    height_px: int
    pixel_time_us: int


class BrukerEBSDAcquisitionSettings(NamedTuple):
    profile_name: str
    scan_area: BrukerEBSDScanAreaSettings
    output_path: Optional[str]
    with_edx: bool
    with_patterns: bool
    poll_interval_s: float
    timeout_s: float


class BrukerEBSDProgress(NamedTuple):
    current_line: int
    acquisition_percent: int
    indexing_percent: int
    acquisition_running: bool
    indexing_running: bool
