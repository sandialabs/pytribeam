"""Application configuration management.

This module provides centralized management of application-wide settings
and ensures necessary directories exist.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List


@dataclass
class AppConfig:
    """Application-wide configuration settings.

    This dataclass holds all application-level configuration that persists
    across sessions and is not specific to individual experiments.

    Attributes:
        data_dir: Directory for application data
        log_dir: Directory for log files
        default_theme: Default UI theme ('dark' or 'light')
        auto_save_interval: Seconds between auto-saves (0 to disable)
        recent_configs: List of recently opened config files
        max_recent_files: Maximum number of recent files to track
    """

    data_dir: Path
    log_dir: Path
    default_theme: str = "dark"
    auto_save_interval: int = 300  # seconds
    recent_configs: List[str] = field(default_factory=list)
    max_recent_files: int = 10

    @classmethod
    def from_env(cls, app_name: str = "pytribeam") -> "AppConfig":
        """Create configuration from environment variables.

        Uses LOCALAPPDATA on Windows or ~/.local/share on Unix-like systems.

        Args:
            app_name: Application name for directory structure

        Returns:
            AppConfig instance with paths set from environment
        """
        if os.name == "nt":
            # Windows
            base_dir = Path(os.getenv("LOCALAPPDATA", os.path.expanduser("~")))
        else:
            # Unix-like
            base_dir = Path(
                os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
            )

        app_dir = base_dir / app_name

        return cls(
            data_dir=app_dir / "data",
            log_dir=app_dir / "logs",
        )

    @classmethod
    def from_file(cls, config_file: Path) -> "AppConfig":
        """Load configuration from JSON file.

        Args:
            config_file: Path to configuration JSON file

        Returns:
            AppConfig instance loaded from file

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is invalid
        """
        import json

        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")

        with open(config_file, "r") as f:
            data = json.load(f)

        return cls(
            data_dir=Path(data["data_dir"]),
            log_dir=Path(data["log_dir"]),
            default_theme=data.get("default_theme", "dark"),
            auto_save_interval=data.get("auto_save_interval", 300),
            recent_configs=data.get("recent_configs", []),
            max_recent_files=data.get("max_recent_files", 10),
        )

    def save_to_file(self, config_file: Path):
        """Save configuration to JSON file.

        Args:
            config_file: Path where config should be saved
        """
        import json

        config_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "data_dir": str(self.data_dir),
            "log_dir": str(self.log_dir),
            "default_theme": self.default_theme,
            "auto_save_interval": self.auto_save_interval,
            "recent_configs": self.recent_configs,
            "max_recent_files": self.max_recent_files,
        }

        with open(config_file, "w") as f:
            json.dump(data, f, indent=2)

    def ensure_directories(self):
        """Create necessary directories if they don't exist.

        This should be called during application startup to ensure
        all required directories are present.
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def add_recent_config(self, config_path: Path):
        """Add configuration file to recent files list.

        Args:
            config_path: Path to configuration file to add
        """
        config_str = str(config_path.absolute())

        # Remove if already in list
        if config_str in self.recent_configs:
            self.recent_configs.remove(config_str)

        # Add to front of list
        self.recent_configs.insert(0, config_str)

        # Trim to max length
        self.recent_configs = self.recent_configs[: self.max_recent_files]

    def get_recent_configs(self) -> List[Path]:
        """Get list of recent configuration files that still exist.

        Returns:
            List of Path objects for existing recent configs
        """
        return [Path(p) for p in self.recent_configs if Path(p).exists()]

    def get_terminal_log_path(self) -> Path:
        """Get path for new terminal log file.

        Returns:
            Path for terminal log file with timestamp
        """
        import time

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        return self.log_dir / f"{timestamp}_terminal.txt"

    def get_error_log_path(self) -> Path:
        """Get path for new error traceback file.

        Returns:
            Path for error log file with timestamp
        """
        import time

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        return self.log_dir / f"{timestamp}_error_traceback.txt"
