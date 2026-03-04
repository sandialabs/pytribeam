"""Resource path management for GUI application.

This module provides centralized management of application resources like
images, icons, and documentation files.
"""

from pathlib import Path
from typing import Optional, Dict, List


class AppResources:
    """Manages paths to application resources.

    This class provides a single point of access for all resource files,
    making it easy to update paths and avoid hard-coded path strings throughout
    the codebase.

    Attributes:
        base_path: Root directory of the pytribeam package
    """

    def __init__(self, base_path: Path):
        """Initialize resource manager.

        Args:
            base_path: Root directory containing docs, src, etc.
        """
        self.base_path = Path(base_path)

    @classmethod
    def from_module_file(cls, module_file: str) -> "AppResources":
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
        # From GUI/module.py, go up to pytribeam root
        module_path = Path(module_file)
        # module.py -> GUI -> pytribeam -> src -> pytribeam_root
        if module_path.parent.name == "GUI":
            base = module_path.parent.parent.parent.parent
        elif (
            module_path.parent.name == "common"
            or module_path.parent.name == "config_ui"
        ):
            base = module_path.parent.parent.parent.parent.parent
        return cls(base_path=base)

    @property
    def icon_path(self) -> Path:
        """Path to application icon (.ico file)."""
        return self.base_path / "docs/userguide/src/logos/logo_color_alt.ico"

    @property
    def logo_dark_path(self) -> Path:
        """Path to dark theme logo image."""
        return self.base_path / "docs/userguide/src/logos/logo_color_dark.png"

    @property
    def logo_light_path(self) -> Path:
        """Path to light theme logo image."""
        return self.base_path / "docs/userguide/src/logos/logo_color.png"

    @property
    def user_guide_path(self) -> Path:
        """Path to user guide HTML index."""
        # return self.base_path / "docs" / "userguide" / "book" / "index.html"
        return "https://github.com/sandialabs/pytribeam/blob/main/docs/userguide/src/SUMMARY.md"

    def get_logo_path(self, theme: str = "dark") -> Path:
        """Get logo path for specified theme.

        Args:
            theme: Theme name ('dark' or 'light')

        Returns:
            Path to appropriate logo file

        Raises:
            ValueError: If theme is not 'dark' or 'light'
        """
        if theme.lower() == "dark":
            return self.logo_dark_path
        elif theme.lower() == "light":
            return self.logo_light_path
        else:
            raise ValueError(f"Unknown theme: {theme}. Must be 'dark' or 'light'")

    def verify_resources(self) -> Dict[str, bool]:
        """Check which resources exist on filesystem.

        Returns:
            Dictionary mapping resource names to existence status
        """
        return {
            "icon": self.icon_path.exists(),
            "logo_dark": self.logo_dark_path.exists(),
            "logo_light": self.logo_light_path.exists(),
            "user_guide": self.user_guide_path.exists(),
        }

    def get_missing_resources(self) -> List[str]:
        """Get list of missing resource files.

        Returns:
            List of resource names that don't exist on filesystem
        """
        status = self.verify_resources()
        return [name for name, exists in status.items() if not exists]
