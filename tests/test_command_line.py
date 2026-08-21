import pytest

import pytribeam._package_metadata as pm
import pytribeam.command_line as cli

pytestmark = pytest.mark.detached


def test_pytribeam_prints_cli_docs(capsys):
    cli.pytribeam()

    out = capsys.readouterr().out

    assert "pytribeam" in out
    assert "pytribeam_info" in out
    assert "pytribeam_gui" in out
    assert "pytribeam_exp" in out


def test_module_info_output_with_detected_autoscript_and_laser_metadata(
    monkeypatch, capsys
):
    monkeypatch.setattr(pm, "MODULE_SHORT_NAME", "pytribeam")
    monkeypatch.setattr(pm, "YML_SCHEMA_VERSION", "1.2.3")
    monkeypatch.setattr(
        pm,
        "SUPPORTED_AUTOSCRIPT_VERSIONS",
        ("4.8.1", "4.10.0", "4.11.0", "4.13.1"),
    )
    monkeypatch.setattr(pm, "SUPPORTED_LASER_API_VERSIONS", ("2_2.1",))

    monkeypatch.setattr(pm, "get_pytribeam_version", lambda: "0.0.9.dev167")
    monkeypatch.setattr(pm, "get_pytribeam_commit_id", lambda: "abc1234")
    monkeypatch.setattr(pm, "get_autoscript_version", lambda: "4.8.1")
    monkeypatch.setattr(pm, "get_laser_api_version", lambda: "2.0.0")

    monkeypatch.setattr(pm, "autoscript_available", lambda: True)
    monkeypatch.setattr(pm, "laser_api_available", lambda: False)
    monkeypatch.setattr(pm, "laser_pythoncontrol_available", lambda: False)

    cli.module_info()

    out = capsys.readouterr().out

    assert "pytribeam module version: v0.0.9.dev167" in out
    assert "Git commit: abc1234" in out
    assert "Maximum supported .yml schema version: v1.2.3" in out

    assert (
        "Supported Thermo Fisher AutoScript versions: v4.8.1, v4.10.0, v4.11.0, v4.13.1"
    ) in out

    assert "Supported Laser API versions: v2_2.1" in out

    assert "Installed environment:" in out

    assert "AutoScript:" in out
    assert "Distribution metadata: detected, version: 4.8.1" in out
    assert "Import package autoscript_sdb_microscope_client: available" in out

    assert "Laser API:" in out
    assert "Distribution metadata: detected, version: 2.0.0" in out
    assert "Import package Laser: not importable" in out
    assert "Import package Laser.PythonControl: not importable" in out


def test_module_info_output_when_versions_are_missing(monkeypatch, capsys):
    monkeypatch.setattr(pm, "MODULE_SHORT_NAME", "pytribeam")
    monkeypatch.setattr(pm, "YML_SCHEMA_VERSION", "1.2.3")
    monkeypatch.setattr(pm, "SUPPORTED_AUTOSCRIPT_VERSIONS", ("4.8.1",))
    monkeypatch.setattr(pm, "SUPPORTED_LASER_API_VERSIONS", ("2_2.1",))

    monkeypatch.setattr(pm, "get_pytribeam_version", lambda: None)
    monkeypatch.setattr(pm, "get_pytribeam_commit_id", lambda: None)
    monkeypatch.setattr(pm, "get_autoscript_version", lambda: None)
    monkeypatch.setattr(pm, "get_laser_api_version", lambda: None)

    monkeypatch.setattr(pm, "autoscript_available", lambda: False)
    monkeypatch.setattr(pm, "laser_api_available", lambda: False)
    monkeypatch.setattr(pm, "laser_pythoncontrol_available", lambda: False)

    cli.module_info()

    out = capsys.readouterr().out

    assert "pytribeam module version: vunknown" in out
    assert "Git commit:" not in out
    assert "Maximum supported .yml schema version: v1.2.3" in out

    assert "AutoScript:" in out
    assert "Distribution metadata: not detected, version: not detected" in out
    assert "Import package autoscript_sdb_microscope_client: not importable" in out

    assert "Laser API:" in out
    assert "Import package Laser: not importable" in out
    assert "Import package Laser.PythonControl: not importable" in out


def test_build_experiment_parser_help(capsys):
    parser = cli.build_experiment_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--help"])

    assert exc_info.value.code == 0

    out = capsys.readouterr().out

    assert "usage:" in out
    assert "file_path" in out
    assert "Path to the experiment configuration .yml file." in out
