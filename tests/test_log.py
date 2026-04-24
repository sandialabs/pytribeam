## python standard libraries
import datetime
from pathlib import Path

# 3rd party libraries
import pytest
import h5py
import numpy as np
import yaml

# Local
import pytribeam.log as log
import pytribeam.types as tbt
from pytribeam.constants import Constants
import pytribeam.factory as factory


def test_create_file(temp_dir):
    temp_file = temp_dir.joinpath(
        "temp_log.h5",
    )
    assert not temp_file.is_file()
    log.create_file(path=temp_file)
    assert temp_file.is_file()


class TestStoreLogData:
    def test_current_time(self):
        now = datetime.datetime.now()
        unix_now = int(now.timestamp())
        time = log.current_time()
        assert time.unix - unix_now < 5

    def test_experiment_settings(self, config_factory):
        yml_path = config_factory("image_config.yml")
        yml_path_out = yml_path.parent.joinpath("test_config_out.yml")
        h5_path = yml_path.parent.joinpath("temp_log.h5")
        log.create_file(path=h5_path)

        log.experiment_settings(
            slice_number=3,
            step_number=5,
            log_filepath=h5_path,
            yml_path=yml_path,
        )

        log.yml_from_log(
            log_path_h5=h5_path,
            output_path_yml=yml_path_out,
            row=0,
        )

        import shutil

        shutil.copy(h5_path, Path("//snl/home/tribeam-team/DaaS/Downloads/1.h5"))
        shutil.copy(yml_path, Path("//snl/home/tribeam-team/DaaS/Downloads/1.yml"))
        shutil.copy(yml_path_out, Path("//snl/home/tribeam-team/DaaS/Downloads/2.yml"))

        with open(yml_path, "r") as f:
            known = yaml.safe_load(f)
        with open(yml_path_out, "r") as f:
            found = yaml.safe_load(f)
        assert known == found

    def test_position(self, temp_dir):
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
        microscope.disconnect()

    def test_laser_power(self, temp_dir):
        temp_file = temp_dir.joinpath(
            "temp_log.h5",
        )
        log.create_file(path=temp_file)

        known_power_w = 0.335

        step_number = 1
        step_name = "Laser_Step"
        slice_number = 2
        dataset_name = Constants.pre_lasing_dataset_name
        log.laser_power(
            step_number=step_number,
            step_name=step_name,
            slice_number=slice_number,
            log_filepath=temp_file,
            dataset_name=dataset_name,
            power_w=known_power_w,
        )

        with h5py.File(temp_file, "r") as file:
            data_location = f"{step_number:02d}_{step_name}/{dataset_name}"
            data = np.squeeze(file[data_location])

        assert data["Power"] == known_power_w
        assert data["Slice"] == slice_number

        # add data
        slice_number_2 = slice_number + 1
        known_power_w_2 = known_power_w * 2
        log.laser_power(
            step_number=step_number,
            step_name=step_name,
            slice_number=slice_number_2,
            log_filepath=temp_file,
            dataset_name=dataset_name,
            power_w=known_power_w_2,
        )

        with h5py.File(temp_file, "r") as file:
            data_location = f"{step_number:02d}_{step_name}/{dataset_name}"
            data = np.squeeze(file[data_location])

        assert data["Power"][0] == pytest.approx(known_power_w)
        assert data["Power"][1] == pytest.approx(known_power_w_2)

        assert data["Slice"][0] == slice_number
        assert data["Slice"][1] == slice_number_2

    def test_sample_current(self, temp_dir):
        temp_file = temp_dir.joinpath(
            "temp_log.h5",
        )
        log.create_file(path=temp_file)

        known_current_na = 0.335

        step_number = 1
        step_name = "EBSD_step"
        slice_number = 2
        dataset_name = Constants.specimen_current_dataset_name
        log.specimen_current(
            step_number=step_number,
            step_name=step_name,
            slice_number=slice_number,
            log_filepath=temp_file,
            dataset_name=dataset_name,
            specimen_current_na=known_current_na,
        )

        with h5py.File(temp_file, "r") as file:
            data_location = f"{step_number:02d}_{step_name}/{dataset_name}"
            data = np.squeeze(file[data_location])

        assert data["Current"] == known_current_na
        assert data["Slice"] == slice_number

        # add data
        slice_number_2 = slice_number + 1
        known_current_na_2 = known_current_na * 2
        log.specimen_current(
            step_number=step_number,
            step_name=step_name,
            slice_number=slice_number_2,
            log_filepath=temp_file,
            dataset_name=dataset_name,
            specimen_current_na=known_current_na_2,
        )

        with h5py.File(temp_file, "r") as file:
            data_location = f"{step_number:02d}_{step_name}/{dataset_name}"
            data = np.squeeze(file[data_location])

        assert data["Current"][0] == pytest.approx(known_current_na)
        assert data["Current"][1] == pytest.approx(known_current_na_2)

        assert data["Slice"][0] == slice_number
        assert data["Slice"][1] == slice_number_2
