## python standard libraries
from pathlib import Path
import platform
import time

# 3rd party libraries
import pytest
from PIL import Image as pil_img
import yaml

# Local
import pytribeam.constants as cs
from pytribeam.constants import Conversions, Constants
import pytribeam.insertable_devices as devices
import pytribeam.factory as factory
import pytribeam.image as img
import pytribeam.types as tbt
import pytribeam.utilities as ut
import pytribeam.workflow as workflow


@pytest.fixture
def test_dir() -> str:
    """The relative path and file string locating the default yml test file."""

    return Path(__file__).parent.joinpath("files")


#### tests ####


@pytest.mark.skipif(
    not any(
        platform.uname().node.lower() in machine.lower()
        for machine in (cs.Constants.offline_machines)
    ),
    reason="Run on offline machine only",
)
def test_run_image_experiment(monkeypatch):
    """tests main experimental loop"""
    start_slice = 1
    start_step = 1
    test_dir = Path(__file__).parent.joinpath("files")
    test_yml = test_dir.joinpath("image_test_exp.yml")

    # dynamically change path in the test
    temp_dir = test_dir.joinpath("temp")
    Path(temp_dir).mkdir(
        parents=True,
        exist_ok=True,
    )
    temp_yml = temp_dir.joinpath("temp.yml")

    # edit yaml
    with open(test_yml) as f:
        db = yaml.safe_load(f)
    db["general"]["exp_dir"] = str(temp_dir)
    with open(temp_yml, "w") as f:
        yaml.dump(db, f)

    # say yes to the continue question
    monkeypatch.setattr("builtins.input", lambda _: "y")

    workflow.run_experiment_cli(
        start_slice=start_slice,
        start_step=start_step,
        yml_path=temp_yml,
    )

    ut.remove_directory(temp_dir)


@pytest.mark.skipif(
    not any(
        platform.uname().node.lower() in machine.lower()
        for machine in (cs.Constants.offline_machines)
    ),
    reason="Run on offline machine only",
)
def test_run_custom_script(monkeypatch):
    """tests main experimental loop"""
    start_slice = 1
    start_step = 1
    test_dir = Path(__file__).parent.joinpath("files")
    test_yml = test_dir.joinpath("custom_config.yml")

    temp_dir = test_dir.joinpath("temp_dir")
    Path(temp_dir).mkdir(
        parents=True,
        exist_ok=True,
    )
    temp_yml = temp_dir.joinpath("temp.yml")

    test_script = test_dir.joinpath("custom_script.py")

    # edit yaml
    with open(test_yml) as f:
        db = yaml.safe_load(f)
    db["steps"]["custom_test"]["script_path"] = str(test_script)
    db["general"]["exp_dir"] = str(temp_dir)
    with open(temp_yml, "w") as f:
        yaml.dump(db, f)

    # say yes to the continue question
    monkeypatch.setattr("builtins.input", lambda _: "y")

    workflow.run_experiment_cli(
        start_slice=start_slice,
        start_step=start_step,
        yml_path=temp_yml,
    )
    aa = 2
    # captured = capsys.readouterr()
    # assert captured.out == 2

    ut.remove_directory(temp_dir)
