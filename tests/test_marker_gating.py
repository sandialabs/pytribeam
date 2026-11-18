"""The capability-marker gating in tests/conftest.py."""

from types import SimpleNamespace

import pytest

from tests import conftest

pytestmark = pytest.mark.detached

VENDOR_MARKERS = ("edax_hardware", "oxford_hardware", "bruker_hardware")
GATE_ENV_VARS = (
    conftest.TEST_OEM_ENV_VAR,
    conftest.RUN_HARDWARE_ENV_VAR,
    conftest.RUN_EDAX_IPAPI_ENV_VAR,
    conftest.BRUKER_TEST_ENV_VAR,
)


@pytest.fixture
def env(monkeypatch):
    """Start from no gate variables and no listed vendor hosts."""
    for name in GATE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(conftest, "is_vendor_host", lambda gate: False)

    def set_env(**values):
        for name, value in values.items():
            monkeypatch.setenv(name, value)

    return set_env


def gate(marker):
    return next(g for g in conftest.VENDOR_GATES if g.marker == marker)


def test_the_vendor_markers_are_exactly_the_three():
    assert tuple(g.marker for g in conftest.VENDOR_GATES) == VENDOR_MARKERS


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", set()),
        ("edax", {"edax"}),
        (" EDAX , bruker ", {"edax", "bruker"}),
        ("oxford bruker", {"oxford", "bruker"}),
    ],
)
def test_declared_test_oems(env, raw, expected):
    env(PYTRIBEAM_TEST_OEM=raw)
    assert conftest.declared_test_oems() == expected


class TestVendorGate:
    @pytest.mark.parametrize("marker", VENDOR_MARKERS)
    def test_off_by_default(self, env, marker):
        allowed, reason = conftest.vendor_gate(gate(marker))

        assert not allowed
        assert conftest.TEST_OEM_ENV_VAR in reason

    @pytest.mark.parametrize("marker", VENDOR_MARKERS)
    def test_declaring_the_vendor_enables_only_it(self, env, marker):
        oem = gate(marker).oem
        env(PYTRIBEAM_TEST_OEM=oem)

        enabled = {m for m in VENDOR_MARKERS if conftest.vendor_gate(gate(m))[0]}
        assert enabled == {marker}

    def test_a_listed_host_needs_the_run_flag(self, env, monkeypatch):
        monkeypatch.setattr(
            conftest, "is_vendor_host", lambda g: g.marker == "oxford_hardware"
        )

        assert not conftest.vendor_gate(gate("oxford_hardware"))[0]
        env(PYTRIBEAM_RUN_HARDWARE="1")
        assert conftest.vendor_gate(gate("oxford_hardware"))[0]
        assert not conftest.vendor_gate(gate("edax_hardware"))[0]

    @pytest.mark.parametrize(
        "variables, marker",
        [
            ({"PYTRIBEAM_RUN_EDAX_IPAPI": "1"}, "edax_hardware"),
            ({"PYTRIBEAM_BRUKER_TEST_ENV": "simulator"}, "bruker_hardware"),
            ({"PYTRIBEAM_BRUKER_TEST_ENV": "hardware"}, "bruker_hardware"),
        ],
    )
    def test_older_declarations_still_count(self, env, variables, marker):
        env(**variables)
        assert conftest.vendor_gate(gate(marker))[0]


class FakeItem:
    def __init__(self, markers, keywords=()):
        self._markers = [SimpleNamespace(name=name) for name in markers]
        self.keywords = {name: 1 for name in (*markers, *keywords)}
        self.added = []

    def iter_markers(self):
        return iter(self._markers)

    def add_marker(self, marker, append=True):
        self.added.append(marker)
        self.prepended = not append


class TestCollection:
    def skips(self, item):
        assert all(m.name == "skipif" and m.args == (True,) for m in item.added)
        return [m.kwargs["reason"] for m in item.added]

    def test_unavailable_marker_skips(self, env):
        item = FakeItem(["edax_hardware"])

        conftest.pytest_collection_modifyitems(None, [item])

        assert len(self.skips(item)) == 1
        # ahead of the test's own skipif marks, so this reason is reported
        assert item.prepended

    def test_declared_vendor_runs(self, env):
        env(PYTRIBEAM_TEST_OEM="edax")
        item = FakeItem(["edax_hardware"])

        conftest.pytest_collection_modifyitems(None, [item])

        assert self.skips(item) == []

    def test_every_marker_must_be_available(self, env, monkeypatch):
        """A vendor declaration does not stand in for the TriBeam."""
        env(PYTRIBEAM_TEST_OEM="edax")
        monkeypatch.setattr(conftest, "is_hardware_system", lambda: False)
        item = FakeItem(["hardware", "edax_hardware"])

        conftest.pytest_collection_modifyitems(None, [item])

        assert self.skips(item) == ["requires physical microscope hardware"]

    def test_keywords_alone_never_skip(self, env):
        """Regression: a parametrize id equal to a marker name used to skip."""
        item = FakeItem(["detached"], keywords=["edax_hardware", "bruker_hardware"])

        conftest.pytest_collection_modifyitems(None, [item])

        assert self.skips(item) == []

    def test_unmarked_tests_run(self, env):
        item = FakeItem([])

        conftest.pytest_collection_modifyitems(None, [item])

        assert self.skips(item) == []
