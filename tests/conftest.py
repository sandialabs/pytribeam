# conftest.py
"""
Shared pytest configuration for the pytribeam test suite.

Test capability tiers:

- detached:
    Always runnable. Does not require AutoScript or hardware.
- simulated:
    Runs only on simulated/offline microscope systems.
- hardware:
    Runs only on physical hardware systems, including laser and non-laser.
- laser_hardware:
    Runs only on physical hardware systems with a laser subsystem.

Recommended usage in tests:

    @pytest.mark.simulated
    def test_something():
        ...

    @pytest.mark.hardware
    def test_something_else():
        ...

    @pytest.mark.laser_hardware
    def test_laser_feature():
        ...

Detached tests need no marker.
"""

from __future__ import annotations

from pathlib import Path
import platform
from typing import Iterable

import pytest

import pytribeam.constants as cs
import pytribeam.utilities as ut


# ----------------------------------------------------------------------
# Shared fixtures
# ----------------------------------------------------------------------
@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the repository root."""
    return Path(__file__).resolve().parent


@pytest.fixture
def test_dir(request) -> Path:
    """Return the ``files`` directory adjacent to the requesting test module."""
    return Path(request.fspath).parent / "files"


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Return a pytest-managed temporary directory."""
    return tmp_path


# ----------------------------------------------------------------------
# Environment detection
# ----------------------------------------------------------------------
def _node_name() -> str:
    """Return the current hostname in normalized form."""
    return platform.uname().node.lower()


def _matches_machine_list(machine_names: Iterable[str]) -> bool:
    """Return True if the current hostname matches any configured machine name."""
    node = _node_name()
    return any(node in machine.lower() or machine.lower() in node for machine in machine_names)


def is_simulated_system() -> bool:
    """Return True if running on a configured simulated/offline microscope system."""
    return _matches_machine_list(cs.Constants.offline_machines)


def is_hardware_system() -> bool:
    """Return True if running on a configured physical microscope system."""
    return _matches_machine_list(cs.Constants.microscope_machines)


def has_laser_hardware() -> bool:
    """Return True if the current environment has laser hardware available."""
    return ut.get_laser_version() != "none"


# ----------------------------------------------------------------------
# Capability booleans
# ----------------------------------------------------------------------
CAN_RUN_DETACHED = True
CAN_RUN_SIMULATED = is_simulated_system()
CAN_RUN_HARDWARE = is_hardware_system()
CAN_RUN_LASER_HARDWARE = is_hardware_system() and has_laser_hardware()


# ----------------------------------------------------------------------
# Skip reasons
# ----------------------------------------------------------------------
SIMULATED_ONLY_REASON = "requires a simulated microscope environment"
HARDWARE_ONLY_REASON = "requires physical microscope hardware"
LASER_HARDWARE_ONLY_REASON = "requires physical microscope hardware with laser support"


# ----------------------------------------------------------------------
# Automatic skipping based on markers
# ----------------------------------------------------------------------
def pytest_collection_modifyitems(config, items):
    """Skip marked tests automatically based on the current environment."""
    skip_simulated = pytest.mark.skip(reason=SIMULATED_ONLY_REASON)
    skip_hardware = pytest.mark.skip(reason=HARDWARE_ONLY_REASON)
    skip_laser_hardware = pytest.mark.skip(reason=LASER_HARDWARE_ONLY_REASON)

    for item in items:
        if "simulated" in item.keywords and not CAN_RUN_SIMULATED:
            item.add_marker(skip_simulated)

        if "hardware" in item.keywords and not CAN_RUN_HARDWARE:
            item.add_marker(skip_hardware)

        if "laser_hardware" in item.keywords and not CAN_RUN_LASER_HARDWARE:
            item.add_marker(skip_laser_hardware)
