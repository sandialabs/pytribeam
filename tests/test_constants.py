## python standard libraries
from pathlib import Path
import math

# 3rd party libraries
import pytest
from schema import And, Or, Schema, SchemaError

# Local
# import pytribeam.utilities as ut
# import pytribeam.image as img
import pytribeam.constants as cs


@pytest.fixture
def test_dir() -> str:
    """The relative path and file string locating the default yml test file."""

    return Path(__file__).parent.joinpath("files")


def test_constants():
    assert all(
        [
            cs.Constants().beam_types
            == [
                "electron",
                "ion",
            ]
        ]
    )


def test_conversions():
    """Tests unit converions"""
    aa = cs.Conversions()
    float_precision = 10  # n_digits

    # length
    meter = 0.002
    millimeter = 2.0
    micron = 2.0e3
    assert meter * aa.M_TO_MM == millimeter
    assert meter * aa.M_TO_UM == micron
    assert millimeter * aa.MM_TO_M == meter
    assert millimeter * aa.MM_TO_UM == micron
    assert micron * aa.UM_TO_M == meter
    assert micron * aa.UM_TO_MM == millimeter

    # time
    second = 2.0e-6
    microsecond = 2.0
    nanosecond = 2.0e3
    assert second * aa.S_TO_NS == nanosecond
    assert second * aa.S_TO_US == microsecond
    assert microsecond * aa.US_TO_NS == nanosecond
    assert microsecond * aa.US_TO_S == second
    assert round(nanosecond * aa.NS_TO_S, float_precision) == second
    assert nanosecond * aa.NS_TO_US == microsecond

    # voltage
    volt = 10000.0
    kilovolt = 10.0
    assert volt * aa.V_TO_KV == kilovolt
    assert kilovolt * aa.KV_TO_V == volt

    # current
    picoamp = 5000.0
    nanoamp = 5.0
    microamp = 0.005
    amp = 5.0e-9
    assert round(amp * aa.A_TO_PA, float_precision) == picoamp
    assert round(amp * aa.A_TO_NA, float_precision) == nanoamp
    assert round(amp * aa.A_TO_UA, float_precision) == microamp
    assert round(microamp * aa.UA_TO_A, float_precision) == amp
    assert round(microamp * aa.UA_TO_NA, float_precision) == nanoamp
    assert round(microamp * aa.UA_TO_PA, float_precision) == picoamp
    assert round(nanoamp * aa.NA_TO_A, float_precision) == amp
    assert round(nanoamp * aa.NA_TO_PA, float_precision) == picoamp
    assert round(nanoamp * aa.NA_TO_UA, float_precision) == microamp
    assert round(picoamp * aa.PA_TO_A, float_precision) == amp
    assert round(picoamp * aa.PA_TO_NA, float_precision) == nanoamp
    assert round(picoamp * aa.PA_TO_UA, float_precision) == microamp

    # angle
    degree = 90.0
    radian = math.pi / 2
    assert degree * aa.DEG_TO_RAD == radian
