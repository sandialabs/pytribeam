import pytest

from pytribeam.external_oem.bruker.runtime import (
    OPTIONAL_LOGGING_DLL,
    REQUIRED_ESPRIT_DLL,
    validate_bruker_runtime_environment,
)
from pytribeam.external_oem.bruker.types import BrukerSessionSettings


def _session_settings(dll_dir: str) -> BrukerSessionSettings:
    return BrukerSessionSettings(
        dll_dir=dll_dir,
        mode="tcp",
        server="Lokaler Server",
        user="edx",
        password="edx",
        host="127.0.0.1",
        port=9090,
        close_on_exit=False,
        keep_connection_open=True,
    )


def test_runtime_preflight_missing_dll_dir_is_actionable(tmp_path):
    missing_dir = tmp_path / "missing"

    with pytest.raises(FileNotFoundError) as exc:
        validate_bruker_runtime_environment(_session_settings(str(missing_dir)))

    message = str(exc.value)
    assert "Bruker DLL directory does not exist" in message
    assert str(missing_dir) in message
    assert "ctypes" in message


def test_runtime_preflight_missing_esprit_dll_is_actionable(tmp_path):
    dll_dir = tmp_path / "bruker_api"
    dll_dir.mkdir()

    with pytest.raises(FileNotFoundError) as exc:
        validate_bruker_runtime_environment(_session_settings(str(dll_dir)))

    message = str(exc.value)
    assert REQUIRED_ESPRIT_DLL in message
    assert "session.dll_dir" in message


def test_runtime_preflight_reports_required_and_optional_dlls(tmp_path):
    dll_dir = tmp_path / "bruker_api"
    dll_dir.mkdir()
    esprit_dll = dll_dir / REQUIRED_ESPRIT_DLL
    logging_dll = dll_dir / OPTIONAL_LOGGING_DLL
    esprit_dll.touch()
    logging_dll.touch()

    dll_info = validate_bruker_runtime_environment(_session_settings(str(dll_dir)))

    assert dll_info["dll_dir"] == str(dll_dir)
    assert dll_info["esprit_dll"] == str(esprit_dll)
    assert dll_info["logging_dll"] == str(logging_dll)
