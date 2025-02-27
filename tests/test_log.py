import pytest
import datetime
from pathlib import Path
import h5py
import numpy as np
import yaml
import time

import pytribeam.insertable_devices as devices
import pytribeam.log as log
import pytribeam.types as tbt
import pytribeam.utilities as ut
from pytribeam.constants import Constants
import pytribeam.factory as factory


def test_create_file():
    temp_dir = Path.cwd().joinpath("tests", "temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir.joinpath(
        "temp_log.h5",
    )
    assert not temp_file.is_file()
    log.create_file(path=temp_file)
    assert temp_file.is_file()
    temp_file.unlink()
    assert not temp_file.is_file()
    ut.remove_directory(directory=temp_dir)


def test_current_time():
    now = datetime.datetime.now()
    unix_now = int(now.timestamp())
    time = log.current_time()
    assert time.unix - unix_now < 5


def test_experiment_settings():
    temp_dir = Path.cwd().joinpath("tests", "temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir.joinpath(
        "temp_log.h5",
    )
    log.create_file(path=temp_file)

    known_yml = Path.cwd().joinpath(
        "tests",
        "files",
        "image_config.yml",
    )
    log.experiment_settings(
        slice_number=3,
        step_number=5,
        log_filepath=temp_file,
        yml_path=known_yml,
    )

    found_yml = temp_dir.joinpath("test_settings.yml")
    log.yml_from_log(
        log_path_h5=temp_file,
        output_path_yml=found_yml,
        row=0,
    )

    with open(known_yml, "r") as f:
        known = yaml.safe_load(f)
    with open(found_yml, "r") as f:
        found = yaml.safe_load(f)
    assert known == found

    ut.remove_directory(directory=temp_dir)


def test_position():
    temp_dir = Path.cwd().joinpath("tests", "temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir.joinpath(
        "temp_log.h5",
    )
    log.create_file(path=temp_file)
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    known_position = factory.active_stage_position_settings(
        microscope=microscope,
    )
    step_number = 5
    step_name = "This_test"
    dataset_name = Constants.pre_position_dataset_name
    log.position(
        step_number=step_number,
        step_name=step_name,
        slice_number=7,
        log_filepath=temp_file,
        dataset_name=dataset_name,
        current_position=factory.active_stage_position_settings(
            microscope=microscope,
        ),
    )
    with h5py.File(temp_file, "r") as file:
        data = np.array(file[f"{step_number:02d}_{step_name}"][dataset_name][:])

    found_position = data[-1]
    assert found_position["X"] == pytest.approx(
        known_position.x_mm, abs=Constants.default_stage_tolerance.translational_um
    )
    assert found_position["Y"] == pytest.approx(
        known_position.y_mm, abs=Constants.default_stage_tolerance.translational_um
    )
    assert found_position["Z"] == pytest.approx(
        known_position.z_mm, abs=Constants.default_stage_tolerance.translational_um
    )
    assert found_position["T"] == pytest.approx(
        known_position.t_deg, abs=Constants.default_stage_tolerance.angular_deg
    )
    assert found_position["R"] == pytest.approx(
        known_position.r_deg, abs=Constants.default_stage_tolerance.angular_deg
    )
    ut.remove_directory(directory=temp_dir)
    microscope.disconnect()


@ut.run_on_microscope_machine
def test_read_power():
    log.power()


@ut.run_on_microscope_machine
def test_log_current():
    pass
