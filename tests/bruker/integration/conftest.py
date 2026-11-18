"""Bruker integration tests run against the ESPRIT simulator.

They share the ``bruker_hardware`` marker with the true-hardware tests, so they
need ESPRIT to be available. They acquire maps the simulator accepts, so they
are skipped on a machine declared as real Bruker hardware
(``PYTRIBEAM_BRUKER_TEST_ENV=hardware``), as they were before the markers were
simplified.
"""

import pytest

from tests.bruker.helpers import BRUKER_TEST_ENV_VAR, bruker_test_environment


@pytest.fixture(autouse=True)
def _simulator_only():
    if bruker_test_environment() == "hardware":
        pytest.skip(
            f"Bruker integration tests target the ESPRIT simulator; skipped with "
            f"{BRUKER_TEST_ENV_VAR}=hardware."
        )
