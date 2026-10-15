import pytest
import yaml

from pytribeam.external_oem.bruker.config import (
    load_bruker_eds_yaml,
    parse_detector_motion_settings,
    parse_output_settings,
    parse_readback_settings,
    parse_roi_settings,
    parse_session_settings,
    validate_bruker_eds_config,
)
from pytribeam.external_oem.bruker.types import (
    BrukerEDSProfileMapSettings,
)


@pytest.fixture
def minimal_valid_config():
    """Minimal valid Bruker EDS YAML config as a dictionary."""
    return {
        "session": {
            "dll_dir": "C:/Program Files/Bruker/Esprit API",
            "mode": "local",
        },
        "output": {
            "root_dir": "C:/tmp/output",
            "run_name": "test_run",
        },
        "detector": {
            "detector_index": 1,
            "move_timeout_s": 30.0,
            "poll_interval_s": 0.5,
        },
        "map": {
            "mode": "profile",
            "name": "test_map",
            "width_px": 64,
            "height_px": 48,
            "pixel_time_us": 1024,
            "profile": {
                "elements": [
                    {"atomic_number": 14, "line": "KA"},
                    {"atomic_number": 26, "line": "KA"},
                ],
            },
        },
    }


@pytest.fixture
def minimal_config_file(tmp_path, minimal_valid_config):
    """Write minimal valid config to a temp YAML file."""
    config_path = tmp_path / "test_config.yml"
    config_path.write_text(yaml.dump(minimal_valid_config), encoding="utf-8")
    return config_path


def test_validate_config_minimal(minimal_valid_config):
    assert validate_bruker_eds_config(minimal_valid_config) is True


def test_validate_config_missing_session(minimal_valid_config):
    del minimal_valid_config["session"]
    with pytest.raises(Exception):
        validate_bruker_eds_config(minimal_valid_config)


def test_validate_config_missing_map(minimal_valid_config):
    del minimal_valid_config["map"]
    with pytest.raises(Exception):
        validate_bruker_eds_config(minimal_valid_config)


def test_validate_config_invalid_width(minimal_valid_config):
    minimal_valid_config["map"]["width_px"] = 0
    with pytest.raises(Exception, match="map.width_px must be a positive integer"):
        validate_bruker_eds_config(minimal_valid_config)


def test_validate_config_negative_pixel_time(minimal_valid_config):
    minimal_valid_config["map"]["pixel_time_us"] = -1
    with pytest.raises(Exception, match="map.pixel_time_us must be a positive integer"):
        validate_bruker_eds_config(minimal_valid_config)


def test_validate_config_empty_elements(minimal_valid_config):
    minimal_valid_config["map"]["profile"]["elements"] = []
    with pytest.raises(Exception):
        validate_bruker_eds_config(minimal_valid_config)


def test_validate_config_too_many_elements(minimal_valid_config):
    minimal_valid_config["map"]["profile"]["elements"] = [
        {"atomic_number": i, "line": "KA"} for i in range(1, 53)
    ]
    with pytest.raises(Exception):
        validate_bruker_eds_config(minimal_valid_config)


def test_validate_config_invalid_atomic_number(minimal_valid_config):
    minimal_valid_config["map"]["profile"]["elements"] = [
        {"atomic_number": 0, "line": "KA"}
    ]
    with pytest.raises(Exception):
        validate_bruker_eds_config(minimal_valid_config)


def test_validate_config_roi_valid(minimal_valid_config):
    minimal_valid_config["map"]["roi"] = {
        "x_start_px": 5,
        "y_start_px": 5,
        "width_px": 20,
        "height_px": 30,
    }
    assert validate_bruker_eds_config(minimal_valid_config) is True


def test_validate_config_roi_exceeds_width(minimal_valid_config):
    minimal_valid_config["map"]["roi"] = {
        "x_start_px": 50,
        "y_start_px": 0,
        "width_px": 20,
        "height_px": 10,
    }
    with pytest.raises(Exception, match="map.roi exceeds map width"):
        validate_bruker_eds_config(minimal_valid_config)


def test_validate_config_roi_exceeds_height(minimal_valid_config):
    minimal_valid_config["map"]["roi"] = {
        "x_start_px": 0,
        "y_start_px": 40,
        "width_px": 10,
        "height_px": 20,
    }
    with pytest.raises(Exception):
        validate_bruker_eds_config(minimal_valid_config)


def test_validate_config_invalid_session_mode_message(minimal_valid_config):
    minimal_valid_config["session"]["mode"] = "serial"
    with pytest.raises(Exception, match="session.mode must be one of"):
        validate_bruker_eds_config(minimal_valid_config)


def test_validate_config_simple_mode(minimal_valid_config):
    minimal_valid_config["map"]["mode"] = "simple"
    del minimal_valid_config["map"]["profile"]
    minimal_valid_config["map"]["real_time_s"] = 0
    assert validate_bruker_eds_config(minimal_valid_config) is True


def test_load_yaml_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_bruker_eds_yaml("/nonexistent/path.yml")


def test_load_yaml_success(minimal_config_file):
    settings = load_bruker_eds_yaml(minimal_config_file)
    assert settings.session.dll_dir == "C:/Program Files/Bruker/Esprit API"
    assert settings.session.mode == "local"
    assert isinstance(settings.map, BrukerEDSProfileMapSettings)
    assert len(settings.map.elements) == 2
    assert settings.map.width_px == 64


def test_parse_session_settings_defaults(minimal_valid_config):
    # Remove optional fields
    minimal_valid_config["session"] = {"dll_dir": "C:/dll"}
    settings = parse_session_settings(minimal_valid_config)
    assert settings.dll_dir == "C:/dll"
    assert settings.mode == "local"
    assert settings.server == "Lokaler Server"
    assert settings.user == "edx"
    assert settings.close_on_exit is False


def test_parse_detector_motion_settings_defaults_to_hardware_safety(
    minimal_valid_config,
):
    settings = parse_detector_motion_settings(minimal_valid_config)
    assert settings.verify_park_before is True
    assert settings.move_to_acquire_before is True
    assert settings.park_after is True


def test_parse_detector_motion_settings_move_detector_false_disables_all_motion(
    minimal_valid_config,
):
    minimal_valid_config["detector"]["move_detector"] = False
    settings = parse_detector_motion_settings(minimal_valid_config)
    assert settings.verify_park_before is False
    assert settings.move_to_acquire_before is False
    assert settings.park_after is False


def test_parse_detector_motion_settings_explicit_flags_override_move_detector(
    minimal_valid_config,
):
    minimal_valid_config["detector"].update(
        {
            "move_detector": False,
            "verify_park_before": True,
            "move_to_acquire_before": False,
            "park_after": True,
        }
    )
    settings = parse_detector_motion_settings(minimal_valid_config)
    assert settings.verify_park_before is True
    assert settings.move_to_acquire_before is False
    assert settings.park_after is True


def test_parse_output_settings_with_slice(minimal_valid_config):
    minimal_valid_config["output"]["slice_number"] = 7
    minimal_valid_config["output"]["repeat_index"] = 1
    settings = parse_output_settings(minimal_valid_config)
    assert settings.slice_number == 7
    assert settings.repeat_index == 1


def test_parse_output_settings_no_slice(minimal_valid_config):
    settings = parse_output_settings(minimal_valid_config)
    assert settings.slice_number is None
    assert settings.repeat_index is None


def test_parse_readback_settings_defaults(minimal_valid_config):
    settings = parse_readback_settings(minimal_valid_config)
    assert settings.enabled is True
    assert settings.dtype == "uint16"
    assert settings.save_element_tiff is False
    assert settings.log_element_stats is True


def test_parse_readback_settings_disabled(minimal_valid_config):
    minimal_valid_config["readback"] = {"save_element_npy": False}
    settings = parse_readback_settings(minimal_valid_config)
    assert settings.enabled is False


def test_parse_roi_settings_none(minimal_valid_config):
    roi = parse_roi_settings(minimal_valid_config)
    assert roi is None


def test_parse_roi_settings_present(minimal_valid_config):
    minimal_valid_config["map"]["roi"] = {
        "x_start_px": 10,
        "y_start_px": 5,
        "width_px": 30,
        "height_px": 20,
    }
    roi = parse_roi_settings(minimal_valid_config)
    assert roi is not None
    assert roi.x_start_px == 10
    assert roi.width_px == 30
