# tests/test_gui.py
import pytest
from pathlib import Path

# Import the class under test
from src.pytribeam.GUI.common.resources import AppResources


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def temp_resource_root(tmp_path: Path) -> Path:
    """
    Create a temporary directory that mimics the expected layout of the
    ``docs/userguide`` folder used by :class:`AppResources`.
    """
    # └── docs/userguide/src/logos/
    logos_dir = tmp_path / "docs" / "userguide" / "src" / "logos"
    logos_dir.mkdir(parents=True)
    (logos_dir / "logo_color_alt.ico").write_text("icon")
    (logos_dir / "logo_color_dark.png").write_text("dark")
    (logos_dir / "logo_color.png").write_text("light")

    # └── docs/userguide/book/
    guide_dir = tmp_path / "docs" / "userguide" / "book"
    guide_dir.mkdir(parents=True)
    (guide_dir / "index.html").write_text("<html></html>")

    return tmp_path


@pytest.fixture
def app_resources(temp_resource_root: Path) -> AppResources:
    """
    Return an ``AppResources`` instance that points at the temporary
    resource tree created by ``temp_resource_root``.
    """
    return AppResources(base_path=temp_resource_root)


# ----------------------------------------------------------------------
# Helper
# ----------------------------------------------------------------------
def _patch_user_guide_path(monkeypatch, resources: AppResources, new_path: Path):
    """
    The original ``user_guide_path`` property returns a hard‑coded URL, which
    does not have an ``exists()`` method.  For the purpose of testing the
    ``verify_resources`` logic we replace it with a property that returns a
    ``Path`` object pointing at ``new_path``.
    """
    monkeypatch.setattr(
        type(resources),
        "user_guide_path",
        property(lambda self: new_path),
        raising=False,
    )


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------
class TestAppResources:
    """Tests for :class:`src.pytribeam.GUI.common.resources.AppResources`."""

    # ------------------------------------------------------------------
    # Basic path properties
    # ------------------------------------------------------------------
    def test_icon_path(self, app_resources: AppResources):
        expected = (
            app_resources.base_path
            / "docs"
            / "userguide"
            / "src"
            / "logos"
            / "logo_color_alt.ico"
        )
        assert app_resources.icon_path == expected

    def test_logo_paths(self, app_resources: AppResources):
        dark_expected = (
            app_resources.base_path
            / "docs"
            / "userguide"
            / "src"
            / "logos"
            / "logo_color_dark.png"
        )
        light_expected = (
            app_resources.base_path
            / "docs"
            / "userguide"
            / "src"
            / "logos"
            / "logo_color.png"
        )
        assert app_resources.logo_dark_path == dark_expected
        assert app_resources.logo_light_path == light_expected

    # ------------------------------------------------------------------
    # get_logo_path()
    # ------------------------------------------------------------------
    @pytest.mark.parametrize("theme,expected_suffix", [("dark", "dark.png"), ("light", ".png")])
    def test_get_logo_path_valid_themes(self, app_resources: AppResources, theme, expected_suffix):
        logo_path = app_resources.get_logo_path(theme)
        assert isinstance(logo_path, Path)
        assert logo_path.name.endswith(expected_suffix)

    def test_get_logo_path_invalid_theme(self, app_resources: AppResources):
        with pytest.raises(ValueError, match="Unknown theme"):
            app_resources.get_logo_path("unknown")

    # ------------------------------------------------------------------
    # verify_resources() & get_missing_resources()
    # ------------------------------------------------------------------
    def test_verify_resources_all_present(self, app_resources: AppResources, monkeypatch):
        # Patch user_guide_path to point at the temporary index.html file
        guide_path = (
            app_resources.base_path
            / "docs"
            / "userguide"
            / "book"
            / "index.html"
        )
        _patch_user_guide_path(monkeypatch, app_resources, guide_path)

        status = app_resources.verify_resources()
        assert status == {
            "icon": True,
            "logo_dark": True,
            "logo_light": True,
            "user_guide": True,
        }
        assert app_resources.get_missing_resources() == []

    def test_verify_resources_some_missing(self, app_resources: AppResources, monkeypatch):
        # Remove the dark logo to simulate a missing file
        (app_resources.logo_dark_path).unlink()
        # Patch user_guide_path to an existing file
        guide_path = (
            app_resources.base_path
            / "docs"
            / "userguide"
            / "book"
            / "index.html"
        )
        _patch_user_guide_path(monkeypatch, app_resources, guide_path)

        status = app_resources.verify_resources()
        assert status["icon"] is True
        assert status["logo_dark"] is False
        assert status["logo_light"] is True
        assert status["user_guide"] is True

        missing = app_resources.get_missing_resources()
        assert missing == ["logo_dark"]

    # ------------------------------------------------------------------
    # from_module_file()
    # ------------------------------------------------------------------
    def test_from_module_file_resolves_correct_base(self, tmp_path: Path):
        """
        Simulate the file layout ``.../src/pytribeam/GUI/common/resources.py``.
        The method should walk up four parents to reach the repository root.
        """
        # Create a dummy module file path inside the expected package layout
        module_file = tmp_path / "src" / "pytribeam" / "GUI" / "common" / "resources.py"
        module_file.parent.mkdir(parents=True)

        # The expected base path is the repository root (tmp_path)
        resources = AppResources.from_module_file(str(module_file))
        assert resources.base_path == tmp_path


