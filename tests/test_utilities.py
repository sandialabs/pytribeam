## python standard libraries
from pathlib import Path
import math


# 3rd party libraries
import pytest
import platform
from schema import And, Or, Schema, SchemaError


# Local
import pytribeam.utilities as ut

# import pytribeam.image as img
import pytribeam.constants as cs
import pytribeam.insertable_devices as devices
import pytribeam.types as tbt


@pytest.fixture
def test_dir() -> str:
    """The relative path and file string locating the default yml test file."""

    return Path(__file__).parent.joinpath("files")


#### tests ####


@ut.hardware_movement
def test_decorator_hardware_movement():
    microscope = tbt.Microscope()
    microscope.connect()
    devices.device_access(microscope=microscope)
    microscope.detector.type.value = tbt.DetectorType.CBS.value
    assert microscope.detector.state == tbt.RetractableDeviceState.RETRACTED.value
    microscope.disconnect()


@ut.run_on_microscope_machine
def test_decorator_online():
    try:
        assert 4 == 1
    except AssertionError:
        pass


@ut.run_on_standalone_machine
def test_decorator_standalone():
    try:
        assert 4 == 1
    except AssertionError:
        pass


def test_nested_dictionary_location(test_dir):
    test_file = test_dir.joinpath("image_config.yml")
    yml_version = 1.0
    yml_format = ut.yml_format(version=yml_version)

    db = ut.yml_to_dict(
        yml_path_file=test_file,
        version=yml_version,
        required_keys=(
            "general",
            "config_file_version",
        ),
    )

    found_pair_loc = ut.nested_dictionary_location(db, "step_number", 1)
    known_pair_loc = ["steps", "image_test", "step_general", "step_number"]
    assert found_pair_loc == known_pair_loc

    with pytest.raises(KeyError) as err:
        ut.nested_dictionary_location(db, "step_number", 5)
    assert err.type == KeyError
    assert (
        err.value.args[0]
        == 'Key : value pair of "step_number : 5" not found in the provided dictionary.'
    )


def test_general_settings(test_dir):
    test_file = test_dir.joinpath("general_config.yml")
    yml_version = 1.0
    yml_format = ut.yml_format(version=yml_version)

    db = ut.yml_to_dict(
        yml_path_file=test_file,
        version=yml_version,
        required_keys=(
            "general",
            "config_file_version",
        ),
    )

    found_db = ut.general_settings(db, yml_format=yml_format)

    known_db = {
        "slice_thickness_um": 2.0,
        "max_slice_num": 400,
        "pre_tilt_deg": 36.0,
        "sectioning_axis": "Z",
        "stage_translational_tol_um": 0.5,
        "stage_angular_tol_deg": 0.02,
        "connection_host": "localhost",
        "connection_port": None,
        "EBSD_OEM": None,
        "EDS_OEM": None,
        "exp_dir": None,
        "h5_log_name": "log",
        "step_count": 1,
    }

    assert known_db == found_db


def test_in_interval():
    """Tests whether values are within limits."""
    a, b = 2.0, 4.0
    limit = tbt.Limit(min=a, max=b)

    x_out_of_limits = [-1.1, 0.0, 2.0, 4.0, 5.1]
    for x in x_out_of_limits:
        assert not ut.in_interval(x, limit, type=tbt.IntervalType.OPEN)

    x_in_limits = [2.1, 3.0, 3.9, 4.0, 2.0]
    for x in x_in_limits:
        assert ut.in_interval(x, limit, type=tbt.IntervalType.CLOSED)

    assert not ut.in_interval(b, limit, type=tbt.IntervalType.RIGHT_OPEN)
    assert not ut.in_interval(a, limit, type=tbt.IntervalType.LEFT_OPEN)
    assert ut.in_interval(a, limit, type=tbt.IntervalType.RIGHT_OPEN)
    assert ut.in_interval(b, limit, type=tbt.IntervalType.LEFT_OPEN)


# https://stackoverflow.com/questions/16039463/how-to-access-the-py-test-capsys-from-inside-a-test
# @pytest.fixture(autouse=True)
# def capsys(capsys):
#     capsys = capsys
# @cs.run_on_standalone_machine
# TODO get custom fixutre working with arg capsys, see above function
@pytest.mark.skipif(
    not any(
        platform.uname().node.lower() in machine.lower()
        for machine in (
            cs.Constants.offline_machines + cs.Constants.microscope_machines
        )
    ),
    reason="Run only on machines prescribed in Constants module.",
)
def test_microscope_connection(capsys):
    microscope = tbt.Microscope()

    connect_msg = "Client connecting to [localhost:7520]...\nClient connected to [localhost:7520]\n"
    disconnect_msg = "Client disconnected\n"

    # API Usage
    microscope.connect("localhost")
    captured = capsys.readouterr()
    assert captured.out == connect_msg
    microscope.disconnect()
    captured = capsys.readouterr()  # overwrite
    assert captured.out == disconnect_msg

    # pytribeam noisy connect and disconnect:
    ut.connect_microscope(
        microscope=microscope,
        quiet_output=False,
        connection_host="localhost",
    )
    captured = capsys.readouterr()  # overwrite
    assert captured.out == connect_msg
    ut.disconnect_microscope(
        microscope=microscope,
        quiet_output=False,
    )
    captured = capsys.readouterr()  # overwrite
    assert captured.out == disconnect_msg

    # pytribeam quiet connect and disconnect:
    ut.connect_microscope(
        microscope=microscope,
        quiet_output=True,
        connection_host="localhost",
    )
    captured = capsys.readouterr()  # overwrite
    assert captured.out == ""
    ut.disconnect_microscope(
        microscope=microscope,
        quiet_output=True,
    )
    captured = capsys.readouterr()  # overwrite
    assert captured.out == ""


def test_step_settings(test_dir):
    test_file = test_dir.joinpath("image_config.yml")
    yml_version = 1.0
    yml_format = ut.yml_format(version=yml_version)

    db = ut.yml_to_dict(
        yml_path_file=test_file,
        version=yml_version,
        required_keys=(
            "general",
            "config_file_version",
        ),
    )
    step_name, step_settings = ut.step_settings(
        exp_settings=db,
        step_number_key="step_number",
        step_number_val=1,
        yml_format=yml_format,
    )
    assert step_name == "image_test"

    known_step_settings = {
        "step_general": {
            "step_number": 1,
            "step_type": "image",
            "frequency": 1,
            "stage": {
                "rotation_side": "fsl_mill",
                "initial_position": {
                    "x_mm": 1.0,
                    "y_mm": 2.0,
                    "z_mm": 5.0,
                    "t_deg": 0.0,
                    "r_deg": -50.0,
                },
            },
        },
        "beam": {
            "type": "electron",
            "voltage_kv": 5.0,
            "voltage_tol_kv": 0.5,
            "current_na": 5.0,
            "current_tol_na": 0.5,
            "hfw_mm": 0.9,
            "working_dist_mm": 4.093,
            "dynamic_focus": False,
            "tilt_correction": False,
        },
        "detector": {
            "type": "ETD",
            "mode": "SecondaryElectrons",
            "brightness": 0.2,
            "contrast": 0.3,
            "auto_cb": {
                "left": None,
                "top": None,
                "width": None,
                "height": None,
            },
        },
        "scan": {
            "rotation_deg": 180,
            "dwell_time_us": 1.0,
            "resolution": "768x512",
        },
        "bit_depth": 8,
    }
    assert step_settings == known_step_settings


def test_valid_enum_entry():
    aa = ut.valid_enum_entry("Oxford", tbt.ExternalDeviceOEM)
    bb = ut.valid_enum_entry("pxx", tbt.ExternalDeviceOEM)
    cc = ut.valid_enum_entry(8, tbt.ColorDepth)
    dd = ut.valid_enum_entry("8", tbt.ColorDepth)
    assert aa == True
    assert bb == False
    assert cc == True
    assert dd == False


def test_yml_format(test_dir):
    test_file = test_dir.joinpath("image_config.yml")
    yml_version = 1.0
    yml_format = ut.yml_format(version=yml_version)
    assert type(yml_format) == tbt.YMLFormatVersion


def test_yaml_to_dict(test_dir):
    """Tests that the yaml file is converted to the dict."""

    test_file = test_dir.joinpath("test_config.yml")

    aa = test_file
    known_db = {
        "config_file_version": 1.0,
        "general": {
            "slice_thickness_um": 2.0,
            "max_slice_num": 400,
        },
        "image_test": {
            "step_type": "image",
            "beam_type": "electron",
            "auto_cb": True,
            "dwell_time_us": 0.45,
        },
    }

    found_db = ut.yml_to_dict(
        yml_path_file=aa,
        version=1.0,
        required_keys=(
            "general",
            "config_file_version",
        ),
    )
    assert known_db == found_db
