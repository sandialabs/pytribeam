"""Resource path management for GUI application.

This module provides centralized management of application resources like
images, icons, and documentation files.
"""
from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from typing import Dict, List
try:
    from importlib.resources import as_file, files
except ImportError:
    from importlib_resources import as_file, files

class AppResources:
    """Manages paths to application resources.

    This class provides a single point of access for all resource files,
    making it easy to update paths and avoid hard-coded path strings throughout
    the codebase.

    Attributes:
        base_path: Root directory of the pytribeam package
    """

    package_name = "pytribeam.GUI"

    def __init__(self):
        """Initialize resource manager.

        Args:
            base_path: Root directory containing docs, src, etc.
        """
        self._exit_stack = ExitStack()

    def close(self) -> None:
        """Release any temporary extracted resource files."""
        self._exit_stack.close()

    def __enter__(self) -> "AppResources":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    @classmethod
    def from_module_file(cls, module_file: str | None = None) -> "AppResources":
        """Create AppResources from a module's __file__ path.

        This is the preferred way to initialize AppResources from within
        the GUI module, as it automatically determines the correct base path.

        Args:
            module_file: The __file__ attribute from a module

        Returns:
            AppResources instance with correct base path

        Example:
            resources = AppResources.from_module_file(__file__)
        """
        return cls()

    def _resource(self, *parts: str):
        """Return an importlib resource object."""
        return files(self.package_name).joinpath("resources", *parts)

    def _resource_path(self, *parts: str) -> Path:
        """Return a real filesystem path for a packaged resource.

        The returned path remains valid until this AppResources instance is
        closed.
        """
        resource = self._resource(*parts)
        return self._exit_stack.enter_context(as_file(resource))

    @property
    def icon_path(self) -> Path:
        """Path to application icon file."""
        return self._resource_path("logo_color.ico")

    @property
    def logo_path(self) -> Path:
        """Path to dark theme logo image."""
        return self._resource_path("logo_color.png")

    @property
    def user_guide_path(self) -> str:
        """Path to user guide HTML index."""
        # return self.base_path / "docs" / "userguide" / "book" / "index.html"
        return "https://github.com/sandialabs/pytribeam/blob/main/docs/userguide/src/SUMMARY.md"

    def get_logo_path(self) -> Path:
        """Get logo path.

        Returns:
            Path to appropriate logo file
        """
        return self.logo_path

    def verify_resources(self) -> Dict[str, bool]:
        """Check which resources exist on filesystem.

        Returns:
            Dictionary mapping resource names to existence status
        """
        return {
            "icon": self._resource("logo_color.ico").is_file(),
            "logo": self._resource("logo_color.png").is_file(),
            "user_guide_path": bool(self.user_guide_path),
        }

    def get_missing_resources(self) -> List[str]:
        """Get list of missing resource files.

        Returns:
            List of resource names that don't exist on filesystem
        """
        status = self.verify_resources()
        return [name for name, exists in status.items() if not exists]
