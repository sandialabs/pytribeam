from typing import Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class Theme:
    """A class to manage GUI theme colors with light and dark variants."""

    def __init__(self, theme_type: str = "light"):
        """
        Initialize the theme with either light or dark color scheme.

        Args:
            theme_type (str): Either "light" or "dark". Defaults to "light".

        Raises:
            ValueError: If theme_type is not "light" or "dark"
        """
        if theme_type.lower() not in ["light", "dark"]:
            raise ValueError('Theme type must be either "light" or "dark"')

        self.theme_type = theme_type.lower()
        self._colors = self._get_theme_colors()

    def _get_theme_colors(self) -> Dict[str, str]:
        """Get the color set based on theme type."""
        if self.theme_type == "light":
            return {
                "bg": "#eeeeee",
                "fg": "#333333",
                "accent1": "#e7e614",
                "accent1_fg": "#333333",  # darker fg for light yellow
                "accent2": "#92278f",
                "accent2_fg": "#ffffff",  # light fg for purple
                "accent3": "#ed1c24",
                "accent3_fg": "#ffffff",  # light fg for red
                "green": "#2d9546",
                "green_fg": "#ffffff",  # light fg for green
                "red": "#ed1c24",
                "red_fg": "#ffffff",  # light fg for red
                "yellow": "#f7e615",
                "yellow_fg": "#333333",  # darker fg for yellow
                "black": "#000000",
                "terminal": "#3c4356",
                "terminal_fg": "#e7e614",
                "scrollbar": "#626877",
                "bg_off": "#eeeeee",
            }
        else:  # dark theme
            return {
                "bg": "#282c34",  # lighter, blueish dark background
                "fg": "#bbc1cb",
                "accent1": "#dc984d",  # lighter purple
                "accent1_fg": "#ffffff",  # light fg for purple
                "accent2": "#dc984d",  # lighter purple
                "accent2_fg": "#ffffff",  # light fg for purple
                "accent3": "#d71e26",  # lighter red
                "accent3_fg": "#ffffff",  # light fg for red
                "green": "#2a8b42",  # lighter green
                "green_fg": "#ffffff",  # light fg for green
                "red": "#d71e26",  # lighter red
                "red_fg": "#ffffff",  # light fg for red
                "yellow": "#d4d311",  # slightly darker yellow
                "yellow_fg": "#333333",  # darker fg for yellow
                "black": "#ffffff",  # inverted for dark theme
                "terminal": "#282c34",
                "terminal_fg": "#3fa0af",
                "scrollbar": "#626877",
                "bg_off": "#32363e",
            }

    def get_color(self, color_name: str) -> str:
        """
        Get a specific color by name.

        Args:
            color_name (str): Name of the color to retrieve

        Returns:
            str: Hex color code

        Raises:
            KeyError: If color_name is not found in the theme
        """
        color_name = color_name.lower()
        if color_name not in self._colors:
            raise KeyError(f"Color '{color_name}' not found in theme")
        return self._colors[color_name]

    def get_accent_pair(self, accent_name: str) -> Tuple[str, str]:
        """
        Get an accent color and its corresponding foreground color.

        Args:
            accent_name (str): Base name of the accent (e.g., 'accent1', 'green', 'red')

        Returns:
            tuple[str, str]: (accent_color, foreground_color)

        Raises:
            KeyError: If accent_name is not found in theme
        """
        accent = self.get_color(accent_name)
        fg = self.get_color(f"{accent_name}_fg")
        return accent, fg

    @property
    def colors(self) -> Dict[str, str]:
        """Get all colors in the current theme."""
        return self._colors.copy()

    def __getattr__(self, name: str) -> str:
        """
        Allow direct access to colors as attributes (e.g., theme.bg, theme.accent1).

        Args:
            name (str): Name of the color to retrieve

        Returns:
            str: Hex color code

        Raises:
            AttributeError: If color name is not found in theme
        """
        try:
            return self.get_color(name)
        except KeyError:
            raise AttributeError(
                f"'{self.__class__.__name__}' has no attribute '{name}'"
            )


# Usage examples:
if __name__ == "__main__":
    # Create light theme (default)
    light_theme = Theme()

    # Create dark theme
    dark_theme = Theme("dark")

    # Access colors using different methods
    print(f"Light theme background color: {light_theme.bg}")
    print(f"Light theme foreground color: {light_theme.fg}")

    # Get accent color with its foreground
    accent1, accent1_fg = light_theme.get_accent_pair("accent1")
    print(f"\nAccent1 color pair: {accent1}, {accent1_fg}")

    # Get all colors in a theme
    all_dark_colors = dark_theme.colors
    print("\nAll dark theme colors:")
    for name, color in all_dark_colors.items():
        print(f"{name}: {color}")
