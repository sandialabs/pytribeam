# tests/test_gui.py

from pathlib import Path

import pytest

from pytribeam.GUI.common import AppResources


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def app_resources() -> AppResources:  # type: ignore
    """Return an AppResources instance using packaged resources."""
    resources = AppResources()
    yield resources
    resources.close()


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------
class TestAppResources:
    """Tests for pytribeam.GUI.common.resources.AppResources."""

    # ------------------------------------------------------------------
    # Basic resource path properties
    # ------------------------------------------------------------------
    def test_icon_path(self, app_resources: AppResources):
        icon_path = app_resources.icon_path

        assert isinstance(icon_path, Path)
        assert icon_path.name == "logo_color.ico"
        assert icon_path.exists()
        assert icon_path.is_file()

    def test_logo_path(self, app_resources: AppResources):
        logo_path = app_resources.logo_path

        assert isinstance(logo_path, Path)
        assert logo_path.name == "logo_color.png"
        assert logo_path.exists()
        assert logo_path.is_file()

    # ------------------------------------------------------------------
    # get_logo_path()
    # ------------------------------------------------------------------
    def test_get_logo_path(self, app_resources: AppResources):
        logo_path = app_resources.get_logo_path()

        assert isinstance(logo_path, Path)
        assert logo_path.name == "logo_color.png"
        assert logo_path.exists()
        assert logo_path.is_file()

    # ------------------------------------------------------------------
    # user guide
    # ------------------------------------------------------------------
    def test_user_guide_path(self, app_resources: AppResources):
        assert isinstance(app_resources.user_guide_path, str)
        assert app_resources.user_guide_path.startswith("https://")

    # ------------------------------------------------------------------
    # verify_resources() & get_missing_resources()
    # ------------------------------------------------------------------
    def test_verify_resources_all_present(self, app_resources: AppResources):
        status = app_resources.verify_resources()

        assert status == {
            "icon": True,
            "logo": True,
            "user_guide_path": True,
        }

    def test_get_missing_resources_all_present(self, app_resources: AppResources):
        assert app_resources.get_missing_resources() == []

    def test_verify_resources_some_missing(self, monkeypatch):
        resources = AppResources()

        original_resource = resources._resource

        def fake_resource(*parts: str):
            resource_name = parts[-1]

            if resource_name == "logo_color.png":
                return FakeMissingResource()

            return original_resource(*parts)

        monkeypatch.setattr(resources, "_resource", fake_resource)

        status = resources.verify_resources()

        assert status["icon"] is True
        assert status["logo"] is False
        assert status["user_guide_path"] is True

        missing = resources.get_missing_resources()

        assert missing == ["logo"]

        resources.close()

    # ------------------------------------------------------------------
    # from_module_file()
    # ------------------------------------------------------------------
    def test_from_module_file_returns_app_resources_instance(self):
        resources = AppResources.from_module_file(__file__)

        try:
            assert isinstance(resources, AppResources)
            assert resources.verify_resources()["icon"] is True
        finally:
            resources.close()

    # ------------------------------------------------------------------
    # Context manager behavior
    # ------------------------------------------------------------------
    def test_context_manager(self):
        with AppResources() as resources:
            logo_path = resources.get_logo_path()

            assert isinstance(logo_path, Path)
            assert logo_path.exists()
            assert logo_path.is_file()


class FakeMissingResource:
    """Small fake importlib resource object for missing-resource tests."""

    def is_file(self) -> bool:
        return False
