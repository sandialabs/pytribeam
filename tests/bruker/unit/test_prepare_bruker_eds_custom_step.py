from pathlib import Path

import yaml

from pytribeam.external_oem.bruker.tools.prepare_bruker_eds_custom_step import (
    prepare_config,
)


def _write_main_config(path: Path) -> None:
    data = {
        "config_file_version": 1.0,
        "general": {
            "connection_host": "localhost",
            "connection_port": None,
            "EBSD_OEM": "EDAX",
            "EDS_OEM": "EDAX",
            "exp_dir": str(path.parent),
            "h5_log_name": "log",
            "step_count": 2,
        },
        "steps": {
            "image_1": {
                "step_general": {"step_number": 1, "step_type": "image"},
                "beam": {"type": "electron"},
                "detector": {"type": "ETD"},
                "scan": {"resolution": "768x512"},
                "bit_depth": 8,
            },
            "custom_1": {
                "step_general": {"step_number": 2, "step_type": "custom"},
                "executable_path": "old_python.exe",
                "script_path": "old_script.py",
            },
        },
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_prepare_config_sets_bruker_custom_args_and_copies_imaging(tmp_path):
    main_config = tmp_path / "config.yml"
    bruker_config = tmp_path / "bruker_eds_workflow.yml"
    output_config = tmp_path / "config_bruker_custom.yml"
    python_exe = tmp_path / "python.exe"
    script_path = tmp_path / "run_bruker_eds_custom_step.py"
    log_path = tmp_path / "bruker_custom.log"

    _write_main_config(main_config)
    bruker_config.write_text("session: {}\n", encoding="utf-8")
    python_exe.touch()
    script_path.touch()

    step_name, step_number = prepare_config(
        main_config=main_config,
        bruker_config=bruker_config,
        output_main_config=output_config,
        custom_step_name="custom_1",
        custom_step_number=None,
        python_exe=python_exe,
        script_path=script_path,
        copy_imaging_from="image_1",
        log_path=log_path,
        preserve_oems=False,
    )

    assert step_name == "custom_1"
    assert step_number == 2

    result = yaml.safe_load(output_config.read_text(encoding="utf-8"))
    custom_step = result["steps"]["custom_1"]

    assert result["general"]["EBSD_OEM"] is None
    assert result["general"]["EDS_OEM"] is None
    assert custom_step["beam"] == {"type": "electron"}
    assert custom_step["detector"] == {"type": "ETD"}
    assert custom_step["scan"] == {"resolution": "768x512"}
    assert custom_step["bit_depth"] == 8
    assert custom_step["executable_path"].endswith("python.exe")
    assert custom_step["script_path"].endswith("run_bruker_eds_custom_step.py")
    assert custom_step["script_args"] == [
        "--bruker-config",
        str(bruker_config.resolve()).replace("\\", "/"),
        "--image-config",
        str(output_config.resolve()).replace("\\", "/"),
        "--image-step",
        "custom_1",
        "--image-step-number",
        "2",
        "--log-path",
        str(log_path.resolve()).replace("\\", "/"),
    ]
