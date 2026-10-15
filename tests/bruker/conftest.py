import pytest

from pytribeam.external_oem.bruker.types import BrukerSessionSettings
from tests.bruker.helpers import require_esprit, require_hardware


@pytest.fixture
def bruker_session_settings():
    return BrukerSessionSettings(
        dll_dir=r"C:\Users\User\Documents\Esprit API",
        mode="tcp",
        server="Lokaler Server",
        user="edx",
        password="edx",
        host="192.168.0.3",
        port=5328,
        close_on_exit=False,
        keep_connection_open=True,
    )


@pytest.fixture
def connected_bruker_session(bruker_session_settings):
    session = require_esprit(bruker_session_settings)
    yield session
    if bruker_session_settings.close_on_exit:
        session.close()


@pytest.fixture
def connected_bruker_hardware_session(bruker_session_settings):
    session = require_hardware(bruker_session_settings, detector_index=1)
    yield session
    if bruker_session_settings.close_on_exit:
        session.close()
