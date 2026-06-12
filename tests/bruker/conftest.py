import pytest

from pytribeam.external_oem.bruker.types import BrukerSessionSettings
from tests.bruker.helpers import require_esprit, require_hardware


@pytest.fixture
def bruker_session_settings():
    return BrukerSessionSettings(
        dll_dir=r"C:\Program Files\Bruker\Esprit API",
        mode="local",
        server="Lokaler Server",
        user="edx",
        password="edx",
        host=None,
        port=None,
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
