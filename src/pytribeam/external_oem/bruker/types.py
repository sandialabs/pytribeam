from typing import Literal, NamedTuple, Optional, Tuple, Union

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


class BrukerRectROI(NamedTuple):
    """Rectangular region of interest in pixel coordinates.

    Origin (0, 0) is the top-left corner of the full scan area.
    """

    x_start_px: int
    y_start_px: int
    width_px: int
    height_px: int


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
    roi: Optional[BrukerRectROI] = None


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
    roi: Optional[BrukerRectROI] = None


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


# ---------------------------------------------------------------------------
# EDS readback result types
# ---------------------------------------------------------------------------


class BrukerElementReadbackResult(NamedTuple):
    """Result of reading back one element plane from a HyperMap.

    If readback succeeded, ``error`` is None and data fields are populated.
    If readback failed, ``error`` contains the error description and data
    fields may be None.
    """

    element_index: int
    atomic_number: int
    line: str
    path: Optional[str] = None
    shape: Optional[Tuple[int, int]] = None
    dtype: Optional[str] = None
    min_val: Optional[int] = None
    max_val: Optional[int] = None
    sum_val: Optional[int] = None
    nonzero: Optional[int] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Image configuration readback types
# ---------------------------------------------------------------------------


class BrukerImageConfiguration(NamedTuple):
    """Image device configuration as read back from Esprit."""

    width_px: int
    height_px: int
    average: int
    ch1: bool
    ch2: bool


class BrukerFieldWidth(NamedTuple):
    """Scan field width from SEM magnification settings."""

    field_width_um: float


# ---------------------------------------------------------------------------
# Spectrometer status types
# ---------------------------------------------------------------------------


class BrukerSpectrometerDetectorStatus(NamedTuple):
    """Status of a single EDS detector on the spectrometer.

    Attributes
    ----------
    status : int
        -1 = not present, 0 = present but inactive, 1 = active.
    count_rate_cps : int
        Current input count rate in counts per second.
    temperature_c : int
        Current detector temperature in degrees Celsius.
    cooling_mode : int
        0 = off, 1 = on, 2 = max, 3 = heating, 4 = unknown.
    """

    version: int
    status: int
    count_rate_cps: int
    temperature_c: int
    cooling_mode: int


class BrukerSpectrometerStatus(NamedTuple):
    """Full spectrometer status including up to 4 detectors."""

    version: int
    detector_statuses: Tuple[BrukerSpectrometerDetectorStatus, ...]
    status: int
    ready: bool


class BrukerDetectorRanges(NamedTuple):
    """Spectrometer detector range information."""

    max_energy: Tuple[int, ...]
    pulse_throughput: Tuple[int, ...]
    energy_index_count: int
    pulse_index_count: int


# ---------------------------------------------------------------------------
# Workflow settings and result types
# ---------------------------------------------------------------------------


class BrukerEDSOutputSettings(NamedTuple):
    """Output configuration for a Bruker EDS workflow run."""

    output_dir: str
    run_name: str
    save_bcf: bool = True
    save_image: bool = True
    image_format: str = "bmp"


class BrukerEDSReadbackSettings(NamedTuple):
    """Readback configuration for a Bruker EDS workflow run."""

    enabled: bool = True
    dtype: str = "uint16"
    save_element_npy: bool = True
    save_element_images: bool = False
    log_element_stats: bool = True


class BrukerEDSWorkflowSettings(NamedTuple):
    """Complete settings for a Bruker EDS mapping workflow."""

    session: BrukerSessionSettings
    detector: BrukerDetectorMotionSettings
    map: Union["BrukerEDSMapSettings", "BrukerEDSProfileMapSettings"]
    output: BrukerEDSOutputSettings
    readback: BrukerEDSReadbackSettings


class BrukerEDSWorkflowResult(NamedTuple):
    """Result of a Bruker EDS mapping workflow run."""

    success: bool
    bcf_path: Optional[str] = None
    image_path: Optional[str] = None
    element_readback_results: Optional[Tuple[BrukerElementReadbackResult, ...]] = None
    errors: Tuple[str, ...] = ()
    elapsed_s: float = 0.0


# ---------------------------------------------------------------------------
# EBSD types
# ---------------------------------------------------------------------------


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
