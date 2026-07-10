import builtins
from importlib import metadata as md

import pytest

import pytribeam._package_metadata as pm

pytestmark = pytest.mark.detached


def test_get_version_or_none_returns_version(monkeypatch):
    def fake_version(dist_name):
        assert dist_name == "some-package"
        return "1.2.3"

    monkeypatch.setattr(pm.md, "version", fake_version)

    assert pm.get_version_or_none("some-package") == "1.2.3"


def test_get_version_or_none_returns_none_when_package_missing(monkeypatch):
    def fake_version(dist_name):
        raise md.PackageNotFoundError(dist_name)

    monkeypatch.setattr(pm.md, "version", fake_version)

    assert pm.get_version_or_none("missing-package") is None


def test_import_available_returns_true_when_spec_exists(monkeypatch):
    def fake_find_spec(import_name):
        assert import_name == "some_module"
        return object()

    monkeypatch.setattr(pm, "find_spec", fake_find_spec)

    assert pm.import_available("some_module") is True


def test_import_available_returns_false_when_spec_is_none(monkeypatch):
    def fake_find_spec(import_name):
        assert import_name == "missing_module"
        return None

    monkeypatch.setattr(pm, "find_spec", fake_find_spec)

    assert pm.import_available("missing_module") is False


@pytest.mark.parametrize(
    "exception",
    [
        ImportError("import failed"),
        ModuleNotFoundError("module not found"),
        AttributeError("bad attribute"),
        ValueError("bad value"),
    ],
)
def test_import_available_returns_false_on_import_discovery_errors(
    monkeypatch, exception
):
    def fake_find_spec(import_name):
        raise exception

    monkeypatch.setattr(pm, "find_spec", fake_find_spec)

    assert pm.import_available("bad_module") is False


def test_get_pytribeam_version_prefers_generated_version_file():
    version = pm.get_pytribeam_version()

    assert version is None or isinstance(version, str)


def test_get_pytribeam_version_falls_back_to_distribution_metadata(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pytribeam._version":
            raise ImportError("simulated missing _version.py")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(pm, "get_version_or_none", lambda dist_name: "9.9.9")

    assert pm.get_pytribeam_version() == "9.9.9"


def test_get_pytribeam_commit_id_prefers_commit_id(monkeypatch):
    import pytribeam._version as version_mod

    monkeypatch.setattr(version_mod, "commit_id", "abc123", raising=False)
    monkeypatch.setattr(version_mod, "__commit_id__", "def456", raising=False)
    monkeypatch.setattr(version_mod, "__git_commit__", "ghi789", raising=False)

    assert pm.get_pytribeam_commit_id() == "abc123"


def test_get_pytribeam_commit_id_uses_dunder_commit_id(monkeypatch):
    import pytribeam._version as version_mod

    monkeypatch.setattr(version_mod, "commit_id", None, raising=False)
    monkeypatch.setattr(version_mod, "__commit_id__", "def456", raising=False)
    monkeypatch.setattr(version_mod, "__git_commit__", "ghi789", raising=False)

    assert pm.get_pytribeam_commit_id() == "def456"


def test_get_pytribeam_commit_id_uses_git_commit(monkeypatch):
    import pytribeam._version as version_mod

    monkeypatch.setattr(version_mod, "commit_id", None, raising=False)
    monkeypatch.setattr(version_mod, "__commit_id__", None, raising=False)
    monkeypatch.setattr(version_mod, "__git_commit__", "ghi789", raising=False)

    assert pm.get_pytribeam_commit_id() == "ghi789"


def test_get_pytribeam_commit_id_returns_none_when_unavailable(monkeypatch):
    import pytribeam._version as version_mod

    monkeypatch.setattr(version_mod, "commit_id", None, raising=False)
    monkeypatch.setattr(version_mod, "__commit_id__", None, raising=False)
    monkeypatch.setattr(version_mod, "__git_commit__", None, raising=False)

    assert pm.get_pytribeam_commit_id() is None


def test_get_pytribeam_commit_id_returns_none_when_version_import_fails(monkeypatch):
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pytribeam._version":
            raise ImportError("simulated missing _version.py")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert pm.get_pytribeam_commit_id() is None


def test_get_autoscript_version_uses_expected_distribution(monkeypatch):
    calls = []

    def fake_get_version_or_none(dist_name):
        calls.append(dist_name)
        return "4.8.1"

    monkeypatch.setattr(pm, "get_version_or_none", fake_get_version_or_none)

    assert pm.get_autoscript_version() == "4.8.1"
    assert calls == ["autoscript-sdb-microscope-client"]


def test_get_laser_api_version_uses_expected_distribution(monkeypatch):
    calls = []

    def fake_get_version_or_none(dist_name):
        calls.append(dist_name)
        return "2.0.0"

    monkeypatch.setattr(pm, "get_version_or_none", fake_get_version_or_none)

    assert pm.get_laser_api_version() == "2.0.0"
    assert calls == ["Laser"]


def test_autoscript_available_uses_expected_import_name(monkeypatch):
    calls = []

    def fake_import_available(import_name):
        calls.append(import_name)
        return True

    monkeypatch.setattr(pm, "import_available", fake_import_available)

    assert pm.autoscript_available() is True
    assert calls == ["autoscript_sdb_microscope_client"]


def test_laser_api_available_uses_expected_import_name(monkeypatch):
    calls = []

    def fake_import_available(import_name):
        calls.append(import_name)
        return False

    monkeypatch.setattr(pm, "import_available", fake_import_available)

    assert pm.laser_api_available() is False
    assert calls == ["Laser"]


def test_laser_pythoncontrol_available_uses_expected_import_name(monkeypatch):
    calls = []

    def fake_import_available(import_name):
        calls.append(import_name)
        return False

    monkeypatch.setattr(pm, "import_available", fake_import_available)

    assert pm.laser_pythoncontrol_available() is False
    assert calls == ["Laser.PythonControl"]
