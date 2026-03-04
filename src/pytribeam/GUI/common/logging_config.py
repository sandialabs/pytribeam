"""Logging configuration for GUI application.

This module provides standardized logging setup for the pytribeam GUI,
including file and console handlers with appropriate formatting.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


def setup_logging(
    log_dir: Optional[Path] = None,
    level: int = logging.INFO,
    console_level: int = logging.WARNING,
    log_prefix: str = "pytribeam_gui",
) -> logging.Logger:
    """Configure logging for the GUI application.

    Sets up both file and console logging with appropriate formatting.
    Log files are named with timestamps to avoid overwriting.

    Args:
        log_dir: Directory to store log files. If None, uses LOCALAPPDATA/pytribeam/logs
        level: Logging level for file handler (default: INFO)
        console_level: Logging level for console handler (default: WARNING)
        log_prefix: Prefix for log filenames (default: 'pytribeam_gui')

    Returns:
        Configured logger instance

    Example:
        logger = setup_logging()
        logger.info("Application started")
        logger.error("An error occurred", exc_info=True)
    """
    # Determine log directory
    if log_dir is None:
        base_dir = os.getenv("LOCALAPPDATA", os.path.expanduser("~/.local/share"))
        log_dir = Path(base_dir) / "pytribeam" / "logs"

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{log_prefix}_{timestamp}.log"

    # Create formatters
    file_formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_formatter = logging.Formatter(
        fmt="%(levelname)s: %(message)s",
    )

    # Create file handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_formatter)

    # Configure root logger for pytribeam
    logger = logging.getLogger("pytribeam.GUI")
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info(f"Logging initialized. Log file: {log_file}")

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a specific module.

    This should be called at the module level to get a properly
    namespaced logger.

    Args:
        name: Module name (typically __name__)

    Returns:
        Logger instance

    Example:
        logger = get_logger(__name__)
        logger.debug("Debug message")
    """
    return logging.getLogger(f"pytribeam.GUI.{name}")


def cleanup_old_logs(log_dir: Optional[Path] = None, keep_days: int = 30):
    """Remove log files older than specified days.

    Args:
        log_dir: Directory containing log files. If None, uses default location
        keep_days: Number of days to keep logs (default: 30)
    """
    if log_dir is None:
        base_dir = os.getenv("LOCALAPPDATA", os.path.expanduser("~/.local/share"))
        log_dir = Path(base_dir) / "pytribeam" / "logs"

    log_dir = Path(log_dir)
    if not log_dir.exists():
        return

    cutoff_time = datetime.now().timestamp() - (keep_days * 24 * 60 * 60)

    for log_file in log_dir.glob("*.log"):
        if log_file.stat().st_mtime < cutoff_time:
            try:
                log_file.unlink()
            except OSError:
                pass  # Ignore errors during cleanup
