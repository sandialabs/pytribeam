# tests/test_gui_parameter_tracker.py
"""Tests for :class:`pytribeam.GUI.config_ui.parameter_tracker.ParameterTracker`."""

import pytest

from pytribeam.GUI.config_ui.parameter_tracker import ParameterTracker
from pytribeam.GUI.config_ui.editor_controller import EditorController


# ----------------------------------------------------------------------
# Display detection
# ----------------------------------------------------------------------
try:
    import tkinter as tk
    _root = tk.Tk()
    _root.withdraw()
    _root.destroy()
    HAS_DISPLAY = True
except Exception:
    HAS_DISPLAY = False

requires_display = pytest.mark.skipif(
    not HAS_DISPLAY, reason="No display available for tkinter"
)


# ----------------------------------------------------------------------
# Fake LUT
# ----------------------------------------------------------------------
class FakeField:
    def __init__(self, dtype=str, default=""):
        self.dtype = dtype
        self.default = default


class FakeLUT(dict):
    def flatten(self):
        return self


@pytest.fixture(autouse=True)
def fake_lut(monkeypatch):
    def get_lut(step_type, version):
        return FakeLUT({
            "step_general/step_type": FakeField(str, "image"),
            "beam/voltage_kv": FakeField(float, 5.0),
            "enabled": FakeField(bool, True),
        })

    monkeypatch.setattr("pytribeam.GUI.config_ui.pipeline_model.lut.get_lut", get_lut)
    monkeypatch.setattr("pytribeam.GUI.config_ui.pipeline_model.lut.VERSIONS", [1.0])
    monkeypatch.setattr("pytribeam.GUI.config_ui.editor_controller.lut.VERSIONS", [1.0])


@pytest.fixture
def controller():
    ctrl = EditorController(version=1.0)
    ctrl.create_new_pipeline()
    return ctrl


@pytest.fixture
def tracker(controller):
    return ParameterTracker(controller)


# ----------------------------------------------------------------------
# Initialization
# ----------------------------------------------------------------------
class TestInit:

    def test_tracker_has_empty_variables(self, tracker):
        assert len(tracker.variables) == 0

    def test_tracker_has_controller(self, controller, tracker):
        assert tracker.controller is controller

    def test_repr(self, tracker):
        assert "ParameterTracker" in repr(tracker)
        assert "0" in repr(tracker)


# ----------------------------------------------------------------------
# _validate_int
# ----------------------------------------------------------------------
class TestValidateInt:

    def test_valid_integer_string(self, tracker):
        assert tracker._validate_int("42") == "42"

    def test_negative_integer(self, tracker):
        assert tracker._validate_int("-5") == "-5"

    def test_positive_sign(self, tracker):
        assert tracker._validate_int("+10") == "+10"

    def test_empty_string_returns_empty(self, tracker):
        assert tracker._validate_int("") == ""

    def test_none_returns_empty(self, tracker):
        assert tracker._validate_int(None) == ""

    def test_sign_only_allowed(self, tracker):
        assert tracker._validate_int("-") == "-"
        assert tracker._validate_int("+") == "+"

    def test_invalid_raises_value_error(self, tracker):
        with pytest.raises(ValueError, match="Invalid integer"):
            tracker._validate_int("not_a_number")

    def test_float_string_raises_value_error(self, tracker):
        with pytest.raises(ValueError, match="Invalid integer"):
            tracker._validate_int("3.14")

    def test_integer_value_as_int(self, tracker):
        # Passing actual int should work
        assert tracker._validate_int(7) == "7"


# ----------------------------------------------------------------------
# _validate_float
# ----------------------------------------------------------------------
class TestValidateFloat:

    def test_valid_float_string(self, tracker):
        assert tracker._validate_float("3.14") == "3.14"

    def test_integer_string_accepted(self, tracker):
        assert tracker._validate_float("42") == "42"

    def test_negative_float(self, tracker):
        assert tracker._validate_float("-2.5") == "-2.5"

    def test_empty_string_returns_empty(self, tracker):
        assert tracker._validate_float("") == ""

    def test_none_returns_empty(self, tracker):
        assert tracker._validate_float(None) == ""

    def test_partial_float_inputs_allowed(self, tracker):
        # Allow in-progress typing
        for partial in ["-", "+", ".", "-.", "+."]:
            assert tracker._validate_float(partial) == partial

    def test_invalid_raises_value_error(self, tracker):
        with pytest.raises(ValueError, match="Invalid float"):
            tracker._validate_float("not_a_float")

    def test_float_value(self, tracker):
        assert tracker._validate_float(1.5) == "1.5"


# ----------------------------------------------------------------------
# _validate_bool
# ----------------------------------------------------------------------
class TestValidateBool:

    def test_true_bool(self, tracker):
        assert tracker._validate_bool(True) is True

    def test_false_bool(self, tracker):
        assert tracker._validate_bool(False) is False

    @pytest.mark.parametrize("true_val", ["true", "True", "TRUE", "1", "yes", "YES"])
    def test_string_truthy(self, tracker, true_val):
        assert tracker._validate_bool(true_val) is True

    @pytest.mark.parametrize("false_val", ["false", "False", "FALSE", "0", "no", "NO", ""])
    def test_string_falsy(self, tracker, false_val):
        assert tracker._validate_bool(false_val) is False

    def test_nonzero_int_returns_true(self, tracker):
        assert tracker._validate_bool(42) is True

    def test_zero_int_returns_false(self, tracker):
        assert tracker._validate_bool(0) is False


# ----------------------------------------------------------------------
# _create_typed_variable
# ----------------------------------------------------------------------
@requires_display
class TestCreateTypedVariable:

    @pytest.fixture(autouse=True)
    def tk_root(self):
        """Provide a tk root for tkinter variable creation."""
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        yield
        self.root.destroy()

    def test_bool_creates_booleanvar(self, tracker):
        import tkinter as tk
        var = tracker._create_typed_variable(bool)
        assert isinstance(var, tk.BooleanVar)

    def test_int_creates_stringvar(self, tracker):
        import tkinter as tk
        var = tracker._create_typed_variable(int)
        assert isinstance(var, tk.StringVar)

    def test_float_creates_stringvar(self, tracker):
        import tkinter as tk
        var = tracker._create_typed_variable(float)
        assert isinstance(var, tk.StringVar)

    def test_str_creates_stringvar(self, tracker):
        import tkinter as tk
        var = tracker._create_typed_variable(str)
        assert isinstance(var, tk.StringVar)


# ----------------------------------------------------------------------
# _create_default_validator
# ----------------------------------------------------------------------
class TestCreateDefaultValidator:

    def test_int_validator_validates_int(self, tracker):
        v = tracker._create_default_validator(int)
        assert v("5") == "5"

    def test_float_validator_validates_float(self, tracker):
        v = tracker._create_default_validator(float)
        assert v("3.14") == "3.14"

    def test_bool_validator_validates_bool(self, tracker):
        v = tracker._create_default_validator(bool)
        assert v(True) is True
        assert v(False) is False

    def test_str_validator_converts_to_string(self, tracker):
        v = tracker._create_default_validator(str)
        assert v(42) == "42"

    def test_str_validator_none_returns_empty(self, tracker):
        v = tracker._create_default_validator(str)
        assert v(None) == ""


# ----------------------------------------------------------------------
# add_custom_validator
# ----------------------------------------------------------------------
class TestCustomValidator:

    def test_add_replaces_existing_validator(self, tracker):
        tracker.validators["my/path"] = lambda x: x
        tracker.add_custom_validator("my/path", lambda x: "custom")
        assert tracker.validators["my/path"]("anything") == "custom"

    def test_add_new_validator(self, tracker):
        tracker.add_custom_validator("new/path", lambda x: "new")
        assert tracker.validators["new/path"]("ignored") == "new"


# ----------------------------------------------------------------------
# get_variable
# ----------------------------------------------------------------------
class TestGetVariable:

    def test_returns_none_for_unknown_path(self, tracker):
        assert tracker.get_variable("unknown/path") is None

    @requires_display
    def test_returns_variable_for_known_path(self, tracker):
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            var = tracker.create_variable("beam/voltage_kv", float, default="5.0")
            assert tracker.get_variable("beam/voltage_kv") is var
        finally:
            root.destroy()


# ----------------------------------------------------------------------
# create_variable and clear
# ----------------------------------------------------------------------
@requires_display
class TestCreateAndClear:

    @pytest.fixture(autouse=True)
    def tk_root(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        yield
        self.root.destroy()

    def test_create_variable_stores_variable(self, tracker):
        tracker.create_variable("beam/voltage_kv", float, default="5.0")
        assert "beam/voltage_kv" in tracker.variables

    def test_create_variable_stores_trace_id(self, tracker):
        tracker.create_variable("beam/voltage_kv", float, default="5.0")
        assert "beam/voltage_kv" in tracker.trace_ids

    def test_create_variable_stores_validator(self, tracker):
        tracker.create_variable("beam/voltage_kv", float, default="5.0")
        assert "beam/voltage_kv" in tracker.validators

    def test_create_bool_variable(self, tracker):
        import tkinter as tk
        var = tracker.create_variable("enabled", bool, default=True)
        assert isinstance(var, tk.BooleanVar)

    def test_create_variable_with_custom_validator(self, tracker):
        custom = lambda v: v
        tracker.create_variable("beam/voltage_kv", float, default="5.0", validator=custom)
        assert tracker.validators["beam/voltage_kv"] is custom

    def test_clear_removes_all_variables(self, tracker):
        tracker.create_variable("beam/voltage_kv", float, default="5.0")
        tracker.create_variable("enabled", bool, default=True)
        tracker.clear()
        assert len(tracker.variables) == 0
        assert len(tracker.trace_ids) == 0
        assert len(tracker.validators) == 0

    def test_clear_on_empty_tracker_does_not_raise(self, tracker):
        tracker.clear()  # should not raise


# ----------------------------------------------------------------------
# load_from_controller
# ----------------------------------------------------------------------
@requires_display
class TestLoadFromController:

    @pytest.fixture(autouse=True)
    def tk_root(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        yield
        self.root.destroy()

    def test_load_syncs_variables(self, tracker, controller):
        # Set a value in the controller
        controller.update_parameter("beam/voltage_kv", "99.9")
        tracker.create_variable("beam/voltage_kv", float, default="0.0")

        tracker.load_from_controller()

        assert tracker.variables["beam/voltage_kv"].get() == "99.9"

    def test_load_sets_updating_flag_correctly(self, tracker):
        # After load_from_controller, the flag should be reset to False
        tracker.load_from_controller()
        assert tracker._updating_from_controller is False
