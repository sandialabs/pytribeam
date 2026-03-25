import pytest
from copy import deepcopy

from pytribeam.GUI.config_ui.lookup import LUT, LUTField, VersionedLUT

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
class DummyWidget:
    pass


@pytest.fixture
def field_int():
    return LUTField(
        label="Voltage",
        default=5,
        widget=DummyWidget,
        widget_kwargs={},
        help_text="kV",
        dtype=int,
        version=(0, 10),
    )


@pytest.fixture
def field_bool():
    return LUTField(
        label="Enabled",
        default=True,
        widget=DummyWidget,
        widget_kwargs={},
        help_text="flag",
        dtype=bool,
        version=(0, 10),
    )


@pytest.fixture
def nested_lut(field_int, field_bool):
    root = LUT("root")
    beam = LUT("beam")

    beam["voltage"] = field_int
    beam["enabled"] = field_bool
    root["beam"] = beam

    return root

# ----------------------------------------------------------------------
# Basic behavior
# ----------------------------------------------------------------------
class TestLUTBasics:

    def test_add_and_get_entry(self, field_int):
        lut = LUT("test")
        lut["a"] = field_int
        assert lut["a"] == field_int

    def test_remove_entry(self, field_int):
        lut = LUT()
        lut["a"] = field_int
        lut.remove_entry("a")
        assert "a" not in lut.keys()

    def test_repr(self, field_int):
        lut = LUT("abc")
        assert "abc" in repr(lut)

    def test_equality(self, nested_lut):
        copy = deepcopy(nested_lut)
        assert nested_lut == copy

# ----------------------------------------------------------------------
# Flattening
# ----------------------------------------------------------------------
class TestFlattening:

    def test_flatten_produces_paths(self, nested_lut):
        nested_lut.flatten()
        keys = nested_lut.entries.keys()
        assert "beam/voltage" in keys
        assert "beam/enabled" in keys

    def test_unflatten_restores_structure(self, nested_lut):
        nested_lut.flatten()
        nested_lut.unflatten()

        assert isinstance(nested_lut["beam"], LUT)
        assert "voltage" in nested_lut["beam"].entries

    def test_roundtrip_equality(self, nested_lut):
        original = deepcopy(nested_lut)
        nested_lut.flatten()
        nested_lut.unflatten()
        assert nested_lut == original

# ----------------------------------------------------------------------
# Dict-like behavior
# ----------------------------------------------------------------------
class TestMappingInterface:

    def test_items_keys_values(self, nested_lut):
        assert list(nested_lut.keys()) == ["beam"]
        assert len(list(nested_lut.values())) == 1
        assert len(list(nested_lut.items())) == 1

# ----------------------------------------------------------------------
# VersionedLUT
# ----------------------------------------------------------------------
class DummyInterval:
    CLOSED = "closed"


def always_true(version, interval, mode):
    return True


def always_false(version, interval, mode):
    return False

class TestVersionedLUT:

    def test_invalid_version(self, monkeypatch):
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.VERSIONS", [1])
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.LUTs", {"image": LUT("x")})

        vlut = VersionedLUT()
        with pytest.raises(ValueError):
            vlut.get_lut("image", 999)

    def test_invalid_step_type(self, monkeypatch):
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.VERSIONS", [1])
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.LUTs", {"image": LUT("x")})

        vlut = VersionedLUT()
        with pytest.raises(ValueError):
            vlut.get_lut("unknown", 1)

    def test_filters_out_of_range_fields(
        self, monkeypatch, field_int
    ):
        lut = LUT("image")
        lut["a"] = field_int

        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.VERSIONS", [1])
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.LUTs", {"image": lut})
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.ut.in_interval", always_false)
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.tbt.IntervalType", DummyInterval)

        vlut = VersionedLUT()
        filtered = vlut.get_lut("image", 1)

        assert filtered.entries == {}

    def test_keeps_valid_fields(
        self, monkeypatch, field_int
    ):
        lut = LUT("image")
        lut["a"] = field_int

        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.VERSIONS", [1])
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.LUTs", {"image": lut})
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.ut.in_interval", always_true)
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.tbt.IntervalType", DummyInterval)

        vlut = VersionedLUT()
        filtered = vlut.get_lut("image", 1)

        assert "a" in filtered.entries

    def test_partial_nested_removal_preserves_structure(
        self, monkeypatch, field_int, field_bool
    ):
        """
        Removing only some nested fields must:
        - keep the parent LUT
        - keep remaining siblings
        - not flatten hierarchy
        """

        # Make versions distinguishable
        field_int = field_int._replace(version=(0, 5))
        field_bool = field_bool._replace(version=(6, 10))

        # Build nested structure
        root = LUT("root")
        beam = LUT("beam")
        beam["voltage"] = field_int
        beam["enabled"] = field_bool
        root["beam"] = beam

        # Only voltage survives filtering
        def selective_interval(version, interval, mode):
            start, end = interval
            return start <= version <= end


        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.VERSIONS", [1])
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.LUTs", {"image": root})
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.ut.in_interval", selective_interval)

        class DummyInterval:
            CLOSED = "closed"

        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.tbt.IntervalType", DummyInterval)

        vlut = VersionedLUT()
        filtered = vlut.get_lut("image", 1)

        # Parent must still exist
        assert "beam" in filtered.entries
        assert isinstance(filtered["beam"], LUT)

        # Only one child remains
        assert list(filtered["beam"].entries.keys()) == ["voltage"]

    def test_empty_nested_groups_removed(
        self, monkeypatch, field_int
    ):
        """
        If all children of a nested LUT are filtered out,
        the parent container must also be removed.
        """

        # nested structure: root -> beam -> voltage
        root = LUT("root")
        beam = LUT("beam")
        beam["voltage"] = field_int
        root["beam"] = beam

        # Filter EVERYTHING out
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.VERSIONS", [1])
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.LUTs", {"image": root})
        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.ut.in_interval", lambda *a: False)

        class DummyInterval:
            CLOSED = "closed"

        monkeypatch.setattr("pytribeam.GUI.config_ui.lookup.tbt.IntervalType", DummyInterval)

        vlut = VersionedLUT()
        filtered = vlut.get_lut("image", 1)

        # Entire structure should disappear
        assert filtered.entries == {}

