# tests/gui_tests/test_config_manager.py
"""Tests for :class:`src.pytribeam.GUI.common.config_manager.AppConfig`."""

import json
import os
import time
from pathlib import Path
import pathlib
pathlib.PosixPath = pathlib.WindowsPath

import pytest

from src.pytribeam.GUI.common.config_manager import AppConfig


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def temp_base_dir(tmp_path: Path) -> Path:
    """Create a temporary base directory to act as the application root.

    The fixture returns the path that should be used as ``base_dir`` for the
    ``AppConfig.from_env`` method.  Individual tests can monkeypatch environment
    variables to point to this directory.
    """
    return tmp_path


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def write_config_json(path: Path, data: dict):
    """Write a JSON config file to *path* with the supplied *data*.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------
class TestAppConfigFromEnv:
    """Tests for the ``AppConfig.from_env`` class method."""

    @pytest.mark.parametrize(
        "os_name, env_var, expected_subdir",
        [
            ("nt", "LOCALAPPDATA", "AppData"),
            ("posix", "XDG_DATA_HOME", ".local/share"),
        ],
    )
    def test_respects_environment(self, monkeypatch, tmp_path, os_name, env_var, expected_subdir):
        # Arrange – set environment to a known temporary location
        fake_base = tmp_path / "fake_base"
        fake_base.mkdir()
        monkeypatch.setenv(env_var, str(fake_base))
        # monkeypatch os.name – it is read‑only, so we replace the attribute on the os module
        monkeypatch.setattr(os, "name", os_name, raising=False)

        # Act
        cfg = AppConfig.from_env(app_name="myapp")

        # Assert – the data_dir and log_dir should be sub‑directories of the fake base
        assert cfg.data_dir == Path(fake_base) / "myapp" / "data"
        assert cfg.log_dir == Path(fake_base) / "myapp" / "logs"

    def test_default_values(self, monkeypatch, tmp_path):
        # Ensure defaults are set correctly when only the base paths are provided.
        fake_base = tmp_path / "base"
        fake_base.mkdir()
        monkeypatch.setenv("LOCALAPPDATA", str(fake_base))
        monkeypatch.setattr(os, "name", "nt", raising=False)

        cfg = AppConfig.from_env(app_name="app")
        assert cfg.default_theme == "dark"
        assert cfg.auto_save_interval == 300
        assert cfg.recent_configs == []
        assert cfg.max_recent_files == 10


class TestAppConfigFileIO:
    """Tests for ``from_file`` and ``save_to_file`` methods."""

    def test_save_and_load_round_trip(self, tmp_path):
        config_path = tmp_path / "config.json"
        cfg_original = AppConfig(
            data_dir=tmp_path / "data",
            log_dir=tmp_path / "logs",
            default_theme="light",
            auto_save_interval=60,
            recent_configs=["a.cfg", "b.cfg"],
            max_recent_files=5,
        )

        # Save to file
        cfg_original.save_to_file(config_path)
        assert config_path.exists()

        # Load back
        cfg_loaded = AppConfig.from_file(config_path)
        assert cfg_loaded == cfg_original

    def test_from_file_missing_raises(self, tmp_path):
        missing_path = tmp_path / "does_not_exist.json"
        with pytest.raises(FileNotFoundError):
            AppConfig.from_file(missing_path)

    def test_from_file_invalid_json(self, tmp_path):
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("{ not valid json }")
        with pytest.raises(json.JSONDecodeError):
            AppConfig.from_file(bad_path)


class TestAppConfigDirectoryManagement:
    def test_ensure_directories_creates_missing(self, tmp_path):
        cfg = AppConfig(data_dir=tmp_path / "data", log_dir=tmp_path / "logs")
        # Directories should not exist initially
        assert not cfg.data_dir.exists()
        assert not cfg.log_dir.exists()
        cfg.ensure_directories()
        assert cfg.data_dir.is_dir()
        assert cfg.log_dir.is_dir()


class TestAppConfigRecentHandling:
    def test_add_recent_config_updates_order_and_trims(self, tmp_path):
        cfg = AppConfig(data_dir=tmp_path, log_dir=tmp_path, max_recent_files=3)
        # Add three distinct paths
        a = tmp_path / Path("/tmp/a.cfg")
        b = tmp_path / Path("/tmp/b.cfg")
        c = tmp_path / Path("/tmp/c.cfg")
        d = tmp_path / Path("/tmp/d.cfg")
        cfg.add_recent_config(a)
        cfg.add_recent_config(b)
        cfg.add_recent_config(c)
        assert cfg.recent_configs == [str(c), str(b), str(a)]
        # Adding an existing entry moves it to the front
        cfg.add_recent_config(b)
        assert cfg.recent_configs == [str(b), str(c), str(a)]
        # Adding a new entry when max is reached drops the oldest
        cfg.add_recent_config(d)
        assert cfg.recent_configs == [str(d), str(b), str(c)]
        # Ensure length never exceeds max_recent_files
        assert len(cfg.recent_configs) == cfg.max_recent_files

    def test_get_recent_configs_filters_nonexistent(self, tmp_path):
        cfg = AppConfig(data_dir=tmp_path, log_dir=tmp_path, max_recent_files=5)
        existing = tmp_path / "exists.cfg"
        existing.touch()
        missing = tmp_path / "missing.cfg"
        cfg.recent_configs = [str(existing), str(missing)]
        result = cfg.get_recent_configs()
        assert result == [existing]


class TestAppConfigLogPaths:
    def test_terminal_and_error_log_paths_use_timestamp(self, monkeypatch, tmp_path):
        # Force a deterministic timestamp
        monkeypatch.setattr(time, "strftime", lambda fmt: "20230101-123000")
        cfg = AppConfig(data_dir=tmp_path, log_dir=tmp_path)
        term_path = cfg.get_terminal_log_path()
        err_path = cfg.get_error_log_path()
        assert term_path.name == "20230101-123000_terminal.txt"
        assert err_path.name == "20230101-123000_error_traceback.txt"
        # Both should be located inside the log_dir
        assert term_path.parent == cfg.log_dir
        assert err_path.parent == cfg.log_dir
