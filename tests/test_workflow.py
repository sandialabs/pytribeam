## python standard libraries

# 3rd party libraries
import pytest

# Local
import pytribeam.workflow as workflow


@pytest.mark.simulated
def test_run_image_experiment(monkeypatch, config_factory):
    """tests main experimental loop"""
    start_slice = 1
    start_step = 1
    test_yml = config_factory("image_test_exp.yml")

    # say yes to the continue question
    monkeypatch.setattr("builtins.input", lambda _: "y")

    workflow.run_experiment_cli(
        start_slice=start_slice,
        start_step=start_step,
        yml_path=test_yml,
    )


@pytest.mark.simulated
def test_run_custom_script(monkeypatch, config_factory, tmp_path):
    """tests main experimental loop"""
    start_slice = 1
    start_step = 1
    custom_script_path = tmp_path / "custom_script.py"
    custom_script_path.write_text('if __name__ == "__main__":\n\tprint("Hello World!")\n', encoding="utf-8")
    test_yml = config_factory("custom_config.yml", overrides = {"steps": {"custom_test": {"script_path": str(custom_script_path)}}})

    # say yes to the continue question
    monkeypatch.setattr("builtins.input", lambda _: "y")

    workflow.run_experiment_cli(
        start_slice=start_slice,
        start_step=start_step,
        yml_path=test_yml,
    )
