# tests/test_logging_config.py
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from pytribeam.GUI.common.logging_config import setup_logging, get_logger, cleanup_old_logs


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def temp_log_dir(tmp_path: Path) -> Path:
    """Temporary directory used as log storage."""
    return tmp_path / "logs"


@pytest.fixture
def fixed_timestamp(monkeypatch):
    """Freeze datetime.now() to a predictable value."""
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2024, 1, 2, 3, 4, 5)

    monkeypatch.setattr("pytribeam.GUI.common.logging_config.datetime", FixedDatetime)
    return FixedDatetime.now()


@pytest.fixture
def clean_pytribeam_logger():
    """
    Ensure we start with no handlers attached to pytribeam logger.
    Prevents leakage between tests.
    """
    logger = logging.getLogger("pytribeam.GUI")
    logger.handlers.clear()
    yield
    logger.handlers.clear()


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _create_old_file(path: Path, days_old: int):
    """Create a file and backdate its modification time."""
    path.write_text("old log")
    old_time = datetime.now() - timedelta(days=days_old)
    os.utime(path, (old_time.timestamp(), old_time.timestamp()))


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------
class TestSetupLogging:
    """Tests for setup_logging()."""

    # ------------------------------------------------------------------
    # Directory behavior
    # ------------------------------------------------------------------
    def test_creates_log_directory(self, temp_log_dir, fixed_timestamp, clean_pytribeam_logger):
        logger = setup_logging(log_dir=temp_log_dir)

        assert temp_log_dir.exists()
        assert isinstance(logger, logging.Logger)

    def test_uses_default_directory_when_none(self, monkeypatch, tmp_path, fixed_timestamp, clean_pytribeam_logger):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

        logger = setup_logging(log_dir=None)

        expected = tmp_path / "pytribeam" / "logs"
        assert expected.exists()
        assert isinstance(logger, logging.Logger)

    # ------------------------------------------------------------------
    # File naming
    # ------------------------------------------------------------------
    def test_log_filename_contains_timestamp(self, temp_log_dir, fixed_timestamp, clean_pytribeam_logger):
        setup_logging(log_dir=temp_log_dir, log_prefix="testapp")

        files = list(temp_log_dir.glob("*.log"))
        assert len(files) == 1
        assert files[0].name == "testapp_20240102_030405.log"

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def test_logger_has_file_and_console_handlers(self, temp_log_dir, fixed_timestamp, clean_pytribeam_logger):
        logger = setup_logging(log_dir=temp_log_dir)

        assert len(logger.handlers) == 2
        assert any(isinstance(h, logging.FileHandler) for h in logger.handlers)
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)

    def test_handler_levels_respected(self, temp_log_dir, fixed_timestamp, clean_pytribeam_logger):
        logger = setup_logging(log_dir=temp_log_dir, level=logging.DEBUG, console_level=logging.ERROR)

        if isinstance(logger.handlers[0], logging.FileHandler):
            file_handler = logger.handlers[0]
            console_handler = logger.handlers[1]
        else:
            file_handler = logger.handlers[1]
            console_handler = logger.handlers[2]

        assert file_handler.level == logging.DEBUG
        assert console_handler.level == logging.ERROR

    def test_replaces_existing_handlers(self, temp_log_dir, fixed_timestamp, clean_pytribeam_logger):
        logger = logging.getLogger("pytribeam.GUI")
        logger.addHandler(logging.NullHandler())

        setup_logging(log_dir=temp_log_dir)

        assert not any(isinstance(h, logging.NullHandler) for h in logger.handlers)

    # ------------------------------------------------------------------
    # Formatter behavior
    # ------------------------------------------------------------------
    def test_file_formatter_format(self, temp_log_dir, fixed_timestamp, clean_pytribeam_logger):
        logger = setup_logging(log_dir=temp_log_dir)
        if isinstance(logger.handlers[0], logging.FileHandler):
            file_handler = logger.handlers[0]
        else:
            file_handler = logger.handlers[1]

        fmt = file_handler.formatter._fmt
        assert "%(asctime)s" in fmt
        assert "%(name)s" in fmt
        assert "%(levelname)s" in fmt

    def test_console_formatter_format(self, temp_log_dir, fixed_timestamp, clean_pytribeam_logger):
        logger = setup_logging(log_dir=temp_log_dir)
        if isinstance(logger.handlers[0], logging.FileHandler):
            console_handler = logger.handlers[1]
        else:
            console_handler = logger.handlers[2]

        fmt = console_handler.formatter._fmt
        assert fmt == "%(levelname)s: %(message)s"


class TestGetLogger:
    """Tests for get_logger()."""

    def test_returns_namespaced_logger(self):
        logger = get_logger("module.submodule")
        assert logger.name == "pytribeam.GUI.module.submodule"

    def test_same_instance_returned(self):
        l1 = get_logger("a")
        l2 = get_logger("a")
        assert l1 is l2


class TestCleanupOldLogs:
    """Tests for cleanup_old_logs()."""

    # ------------------------------------------------------------------
    # Removal behavior
    # ------------------------------------------------------------------
    def test_removes_old_logs(self, temp_log_dir):
        temp_log_dir.mkdir(parents=True)

        old_file = temp_log_dir / "old.log"
        new_file = temp_log_dir / "new.log"

        _create_old_file(old_file, days_old=60)
        new_file.write_text("recent")

        cleanup_old_logs(temp_log_dir, keep_days=30)

        assert not old_file.exists()
        assert new_file.exists()

    def test_ignores_missing_directory(self, tmp_path):
        missing_dir = tmp_path / "does_not_exist"
        cleanup_old_logs(missing_dir, keep_days=30)  # should not raise

    def test_handles_delete_errors(self, temp_log_dir, monkeypatch):
        temp_log_dir.mkdir(parents=True)
        f = temp_log_dir / "locked.log"
        _create_old_file(f, days_old=60)

        def fail_unlink(self, *args, **kwargs):
            raise OSError("locked")

        monkeypatch.setattr(Path, "unlink", fail_unlink, raising=False)

        cleanup_old_logs(temp_log_dir, keep_days=30)
        assert f.exists()

    def test_default_directory_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

        default_dir = tmp_path / "pytribeam" / "logs"
        default_dir.mkdir(parents=True)
        old_file = default_dir / "old.log"
        _create_old_file(old_file, days_old=60)

        cleanup_old_logs(None, keep_days=30)
        assert not old_file.exists()
