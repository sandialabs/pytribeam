#!/usr/bin/python3
"""
Shared fixtures for the EDAX IPAPI test suite.

Every test in this package is ``detached``: the fake IPAPI service in
:mod:`tests.edax.helpers` removes the need for AutoScript, an EDAX
installation, a network, or a microscope. Hardware tests carry the
``edax_hardware`` marker and are skipped unless the operator opts in, per
``tests/conftest.py``.
"""

# Default python modules
import sys
from pathlib import Path

# Third-party modules
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Local scripts
from helpers import FakeIpapi  # noqa: E402
from pytribeam.external_oem.edax.client import EdaxClient  # noqa: E402
from pytribeam.external_oem.edax.ebsd import EdaxEbsdController  # noqa: E402
from pytribeam.external_oem.edax.eds import EdaxEdsController  # noqa: E402
from pytribeam.external_oem.edax.sem import EdaxSemController  # noqa: E402
from pytribeam.external_oem.edax.types import EdaxConnectionSettings  # noqa: E402


@pytest.fixture
def connection_settings() -> EdaxConnectionSettings:
    """Return connection settings with timings short enough for fast tests."""
    return EdaxConnectionSettings(
        host="fake-edax-host",
        port=8301,
        timeout_s=0.5,
        pause_s=0.0,
        connect_timeout_s=0.5,
    )


@pytest.fixture
def fake_ipapi() -> FakeIpapi:
    """Return a fake IPAPI service answering every command with success."""
    return FakeIpapi()


@pytest.fixture
def client(connection_settings, fake_ipapi) -> EdaxClient:
    """Return a connected, unlocked client backed by the fake IPAPI."""
    edax_client = EdaxClient(settings=connection_settings, sock=fake_ipapi, quiet=True)
    edax_client.connect()
    return edax_client


@pytest.fixture
def make_client(connection_settings):
    """
    Return a factory that builds a connected client over a scripted service.

    The factory takes the same arguments as :class:`FakeIpapi` and returns the
    ``(client, service)`` pair so tests can inspect what was sent.
    """

    def _make(**kwargs):
        service = FakeIpapi(**kwargs)
        edax_client = EdaxClient(settings=connection_settings, sock=service, quiet=True)
        edax_client.connect()
        return edax_client, service

    return _make


@pytest.fixture
def ebsd(client) -> EdaxEbsdController:
    """Return an EBSD controller over the default fake service."""
    return EdaxEbsdController(client)


@pytest.fixture
def eds(client) -> EdaxEdsController:
    """Return an EDS controller over the default fake service."""
    return EdaxEdsController(client)


@pytest.fixture
def sem(client) -> EdaxSemController:
    """Return a SEM controller over the default fake service."""
    return EdaxSemController(client)


@pytest.fixture
def no_sleep(monkeypatch):
    """Make every controller-level sleep return immediately."""
    import pytribeam.external_oem.edax.base as base
    import pytribeam.external_oem.edax.ebsd as ebsd_module
    import pytribeam.external_oem.edax.eds as eds_module

    for module in (base, ebsd_module, eds_module):
        monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
