from enum import Enum


class DetectorVendor(str, Enum):
    BRUKER = "bruker"
    EDAX = "edax"
    OXFORD = "oxford"
