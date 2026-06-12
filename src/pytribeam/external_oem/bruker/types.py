from typing import NamedTuple, Optional, Literal

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
    timeout_s: float
    poll_interval_s: float


class BrukerEBSDProfileSelection(NamedTuple):
    profile_name: str


class BrukerEBSDAcquisitionSettings(NamedTuple):
    profile_name: str
    output_bcf_path: str
    export_base_path: Optional[str]


class BrukerEBSDProgress(NamedTuple):
    current_line: int
    acquisition_percent: int
    indexing_percent: int
    acquisition_running: bool
    indexing_running: bool
