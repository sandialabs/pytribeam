# tests/test_gui_editor_controller.py
"""Tests for :class:`pytribeam.GUI.config_ui.editor_controller.EditorController`."""

from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

from pytribeam.GUI.config_ui.editor_controller import EditorController
from pytribeam.GUI.config_ui.pipeline_model import StepConfig, PipelineConfig


# ----------------------------------------------------------------------
# Fake LUT infrastructure  (mirrors test_gui_pipeline_model.py)
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
    """Monkeypatch LUT access so no real schema is required."""
    def get_lut(step_type, version):
        return FakeLUT({
            "step_general/step_type": FakeField(str, "image"),
            "step_general/step_name": FakeField(str, "step"),
            "step_general/step_number": FakeField(int, 1),
            "beam/voltage_kv": FakeField(float, 5.0),
            "enabled": FakeField(bool, True),
            "step_count": FakeField(int, 0),
        })

    monkeypatch.setattr("pytribeam.GUI.config_ui.pipeline_model.lut.get_lut", get_lut)
    monkeypatch.setattr("pytribeam.GUI.config_ui.pipeline_model.lut.VERSIONS", [1.0])
    monkeypatch.setattr("pytribeam.GUI.config_ui.editor_controller.lut.VERSIONS", [1.0])


@pytest.fixture
def controller():
    """Return a fresh EditorController with a version set."""
    return EditorController(version=1.0)


@pytest.fixture
def controller_with_pipeline(controller):
    """Return a controller that already has a pipeline loaded."""
    controller.create_new_pipeline()
    return controller


# ----------------------------------------------------------------------
# Initialization
# ----------------------------------------------------------------------
class TestInit:

    def test_default_state(self, controller):
        assert controller.pipeline is None
        assert controller.current_step_index == 0
        assert controller._version == 1.0

    def test_version_uses_lut_latest_when_none(self):
        ctrl = EditorController()  # no version arg
        assert ctrl._version == 1.0

    def test_validator_initialized(self, controller):
        assert controller.validator is not None


# ----------------------------------------------------------------------
# Callback system
# ----------------------------------------------------------------------
class TestCallbacks:

    def test_register_and_fire_callback(self, controller):
        received = {}

        def cb(arg):
            received["arg"] = arg

        controller.register_callback("test_event", cb)
        controller._notify("test_event", "hello")
        assert received["arg"] == "hello"

    def test_notify_unknown_event_does_not_raise(self, controller):
        controller._notify("nonexistent_event")  # should not raise

    def test_callback_exception_does_not_propagate(self, controller):
        def bad_cb():
            raise RuntimeError("boom")

        controller.register_callback("bad", bad_cb)
        controller._notify("bad")  # should not raise

    def test_callback_replaced_on_reregister(self, controller):
        results = []
        controller.register_callback("ev", lambda: results.append(1))
        controller.register_callback("ev", lambda: results.append(2))
        controller._notify("ev")
        assert results == [2]

    def test_callback_receives_multiple_args(self, controller):
        received = {}

        def cb(*args, **kwargs):
            received["args"] = args
            received["kwargs"] = kwargs

        controller.register_callback("multi", cb)
        controller._notify("multi", 1, 2, x=3)
        assert received["args"] == (1, 2)
        assert received["kwargs"] == {"x": 3}


# ----------------------------------------------------------------------
# Pipeline creation
# ----------------------------------------------------------------------
class TestCreateNewPipeline:

    def test_creates_pipeline(self, controller):
        controller.create_new_pipeline()
        assert controller.pipeline is not None

    def test_step_index_reset_to_zero(self, controller):
        controller.current_step_index = 5
        controller.create_new_pipeline()
        assert controller.current_step_index == 0

    def test_pipeline_created_callback_fired(self, controller):
        received = {}
        controller.register_callback("pipeline_created", lambda p: received.update({"pipeline": p}))
        controller.create_new_pipeline()
        assert "pipeline" in received

    def test_version_propagated_to_pipeline(self, controller):
        controller.create_new_pipeline(version=1.0)
        assert controller.pipeline.version == 1.0


# ----------------------------------------------------------------------
# Load pipeline
# ----------------------------------------------------------------------
class TestLoadPipeline:

    def test_load_success(self, controller, tmp_path):
        fake_path = tmp_path / "test.yml"
        fake_pipeline = PipelineConfig.create_new(version=1.0)
        fake_pipeline.file_path = fake_path

        with patch.object(PipelineConfig, "from_yaml", return_value=fake_pipeline):
            success, err = controller.load_pipeline(fake_path)

        assert success is True
        assert err is None
        assert controller.pipeline is fake_pipeline

    def test_load_failure_returns_error(self, controller, tmp_path):
        fake_path = tmp_path / "missing.yml"

        with patch.object(PipelineConfig, "from_yaml", side_effect=FileNotFoundError("not found")):
            success, err = controller.load_pipeline(fake_path)

        assert success is False
        assert "not found" in err

    def test_load_resets_step_index(self, controller, tmp_path):
        fake_path = tmp_path / "test.yml"
        controller.current_step_index = 3
        fake_pipeline = PipelineConfig.create_new(version=1.0)

        with patch.object(PipelineConfig, "from_yaml", return_value=fake_pipeline):
            controller.load_pipeline(fake_path)

        assert controller.current_step_index == 0

    def test_load_fires_pipeline_loaded_callback(self, controller, tmp_path):
        fake_path = tmp_path / "test.yml"
        fake_pipeline = PipelineConfig.create_new(version=1.0)
        received = {}

        controller.register_callback("pipeline_loaded", lambda p: received.update({"p": p}))

        with patch.object(PipelineConfig, "from_yaml", return_value=fake_pipeline):
            controller.load_pipeline(fake_path)

        assert "p" in received


# ----------------------------------------------------------------------
# Save pipeline
# ----------------------------------------------------------------------
class TestSavePipeline:

    def test_save_no_pipeline_returns_error(self, controller, tmp_path):
        success, err = controller.save_pipeline(tmp_path / "out.yml")
        assert success is False
        assert err == "No pipeline to save"

    def test_save_success(self, controller_with_pipeline, tmp_path):
        out_path = tmp_path / "out.yml"

        with patch.object(PipelineConfig, "to_yaml"):
            success, err = controller_with_pipeline.save_pipeline(out_path)

        assert success is True
        assert err is None

    def test_save_fires_callback(self, controller_with_pipeline, tmp_path):
        out_path = tmp_path / "out.yml"
        received = {}

        controller_with_pipeline.register_callback(
            "pipeline_saved", lambda p: received.update({"p": p})
        )

        with patch.object(PipelineConfig, "to_yaml"):
            controller_with_pipeline.save_pipeline(out_path)

        assert "p" in received

    def test_save_io_error_returns_error(self, controller_with_pipeline, tmp_path):
        out_path = tmp_path / "out.yml"

        with patch.object(PipelineConfig, "to_yaml", side_effect=IOError("disk full")):
            success, err = controller_with_pipeline.save_pipeline(out_path)

        assert success is False
        assert "disk full" in err


# ----------------------------------------------------------------------
# Step management
# ----------------------------------------------------------------------
class TestStepManagement:

    def test_add_step_increments_count(self, controller_with_pipeline):
        controller_with_pipeline.add_step("image")
        assert controller_with_pipeline.get_step_count() == 1

    def test_add_step_without_pipeline_raises(self, controller):
        with pytest.raises(ValueError, match="No pipeline loaded"):
            controller.add_step("image")

    def test_add_step_fires_callback(self, controller_with_pipeline):
        received = {}
        controller_with_pipeline.register_callback(
            "step_added", lambda s: received.update({"step": s})
        )
        controller_with_pipeline.add_step("image")
        assert "step" in received

    def test_remove_step_decrements_count(self, controller_with_pipeline):
        controller_with_pipeline.add_step("image")
        controller_with_pipeline.remove_step(1)
        assert controller_with_pipeline.get_step_count() == 0

    def test_remove_step_no_pipeline_returns_false(self, controller):
        assert controller.remove_step(1) is False

    def test_remove_adjusts_current_index_when_selected(self, controller_with_pipeline):
        controller_with_pipeline.add_step("image")
        controller_with_pipeline.add_step("image")
        controller_with_pipeline.current_step_index = 2

        controller_with_pipeline.remove_step(2)

        assert controller_with_pipeline.current_step_index == 1

    def test_remove_adjusts_current_index_when_above(self, controller_with_pipeline):
        controller_with_pipeline.add_step("image")
        controller_with_pipeline.add_step("image")
        controller_with_pipeline.current_step_index = 2

        controller_with_pipeline.remove_step(1)

        assert controller_with_pipeline.current_step_index == 1

    def test_move_step_no_pipeline_returns_false(self, controller):
        assert controller.move_step(1, -1) is False

    def test_move_step_success(self, controller_with_pipeline):
        controller_with_pipeline.add_step("image")
        controller_with_pipeline.add_step("image")
        result = controller_with_pipeline.move_step(2, -1)
        assert result is True

    def test_duplicate_step_no_pipeline_returns_none(self, controller):
        assert controller.duplicate_step(1) is None

    def test_duplicate_step_increments_count(self, controller_with_pipeline):
        controller_with_pipeline.add_step("image")
        dup = controller_with_pipeline.duplicate_step(1)
        assert dup is not None
        assert controller_with_pipeline.get_step_count() == 2


# ----------------------------------------------------------------------
# Step selection
# ----------------------------------------------------------------------
class TestStepSelection:

    def test_select_step_updates_index(self, controller_with_pipeline):
        controller_with_pipeline.add_step("image")
        controller_with_pipeline.select_step(1)
        assert controller_with_pipeline.current_step_index == 1

    def test_select_step_no_pipeline_does_nothing(self, controller):
        controller.select_step(1)  # should not raise
        assert controller.current_step_index == 0

    def test_select_step_fires_callback(self, controller_with_pipeline):
        controller_with_pipeline.add_step("image")
        received = {}
        controller_with_pipeline.register_callback(
            "step_selected", lambda idx, step: received.update({"idx": idx})
        )
        controller_with_pipeline.select_step(1)
        assert received["idx"] == 1

    def test_get_current_step_no_pipeline(self, controller):
        assert controller.get_current_step() is None

    def test_get_current_step_general(self, controller_with_pipeline):
        step = controller_with_pipeline.get_current_step()
        assert step is not None
        assert step.step_type == "general"


# ----------------------------------------------------------------------
# Parameter read/write
# ----------------------------------------------------------------------
class TestParameterAccess:

    def test_update_and_get_parameter(self, controller_with_pipeline):
        controller_with_pipeline.update_parameter("beam/voltage_kv", "10.0")
        value = controller_with_pipeline.get_parameter("beam/voltage_kv")
        assert value == "10.0"

    def test_update_preserves_bool_true(self, controller_with_pipeline):
        controller_with_pipeline.update_parameter("enabled", True)
        value = controller_with_pipeline.get_parameter("enabled")
        assert value is True

    def test_update_preserves_bool_false(self, controller_with_pipeline):
        controller_with_pipeline.update_parameter("enabled", False)
        value = controller_with_pipeline.get_parameter("enabled")
        assert value is False

    def test_update_converts_non_bool_to_string(self, controller_with_pipeline):
        controller_with_pipeline.update_parameter("beam/voltage_kv", 10.5)
        value = controller_with_pipeline.get_parameter("beam/voltage_kv")
        assert value == "10.5"

    def test_get_parameter_default_when_missing(self, controller_with_pipeline):
        value = controller_with_pipeline.get_parameter("missing/path", default="fallback")
        assert value == "fallback"

    def test_update_no_current_step_does_nothing(self, controller):
        # No pipeline - should not raise
        controller.update_parameter("any/path", "value")

    def test_update_fires_callback(self, controller_with_pipeline):
        received = {}
        controller_with_pipeline.register_callback(
            "parameter_changed",
            lambda path, val: received.update({"path": path, "val": val})
        )
        controller_with_pipeline.update_parameter("beam/voltage_kv", "5.0")
        assert received["path"] == "beam/voltage_kv"


# ----------------------------------------------------------------------
# Step names and count
# ----------------------------------------------------------------------
class TestStepNamesAndCount:

    def test_step_count_no_pipeline(self, controller):
        assert controller.get_step_count() == 0

    def test_step_names_no_pipeline(self, controller):
        assert controller.get_step_names() == []

    def test_step_names_with_steps(self, controller_with_pipeline):
        controller_with_pipeline.add_step("image")
        controller_with_pipeline.add_step("image")
        names = controller_with_pipeline.get_step_names()
        assert len(names) == 2


# ----------------------------------------------------------------------
# Renaming
# ----------------------------------------------------------------------
class TestRenaming:

    def test_rename_step_success(self, controller_with_pipeline):
        controller_with_pipeline.add_step("image")
        result = controller_with_pipeline.rename_step(1, "new_name")
        assert result is True
        assert controller_with_pipeline.pipeline.get_step(1).name == "new_name"

    def test_rename_general_step_returns_false(self, controller_with_pipeline):
        result = controller_with_pipeline.rename_step(0, "anything")
        assert result is False

    def test_rename_no_pipeline_returns_false(self, controller):
        assert controller.rename_step(1, "new") is False

    def test_rename_fires_callback(self, controller_with_pipeline):
        controller_with_pipeline.add_step("image")
        received = {}
        controller_with_pipeline.register_callback(
            "step_renamed",
            lambda idx, name: received.update({"idx": idx, "name": name})
        )
        controller_with_pipeline.rename_step(1, "renamed")
        assert received["name"] == "renamed"


# ----------------------------------------------------------------------
# Versioning
# ----------------------------------------------------------------------
class TestVersioning:

    def test_get_version(self, controller):
        assert controller.get_version() == 1.0

    def test_set_version_updates_internal_version(self, controller_with_pipeline):
        controller_with_pipeline.set_version(1.0)
        assert controller_with_pipeline.get_version() == 1.0

    def test_set_version_fires_callback(self, controller_with_pipeline):
        received = {}
        controller_with_pipeline.register_callback(
            "version_changed", lambda v: received.update({"v": v})
        )
        controller_with_pipeline.set_version(1.0)
        assert received["v"] == 1.0

    def test_set_version_without_pipeline_does_not_raise(self, controller):
        controller.set_version(1.0)
        assert controller.get_version() == 1.0

    def test_set_invalid_version(self, controller: EditorController):
        with pytest.raises(NotImplementedError):
            controller.set_version(controller._version + 100)


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------
class TestValidation:

    def test_validate_structure_no_pipeline(self, controller):
        success, msg = controller.validate_structure()
        assert success is False
        assert "No pipeline" in msg

    def test_validate_full_no_pipeline(self, controller):
        success, msg = controller.validate_full()
        assert success is False
        assert "No pipeline" in msg

    def test_validate_step_no_pipeline(self, controller):
        success, msg = controller.validate_step(1)
        assert success is False
        assert "No pipeline" in msg

    def test_validate_structure_empty_pipeline(self, controller_with_pipeline):
        # Pipeline has 0 steps, which fails structure validation
        success, msg = controller_with_pipeline.validate_structure()
        assert success is False

    def test_validate_general_fires_callback(self, controller_with_pipeline, monkeypatch):
        received = {}
        controller_with_pipeline.register_callback(
            "step_validation_complete",
            lambda idx, ok, msg: received.update({"ok": ok})
        )
        # Use a validator that returns failure (no real schema)
        from pytribeam.GUI.config_ui.validator import ValidationResult
        mock_result = ValidationResult(success=False, step_name="general", message="fail")
        monkeypatch.setattr(
            controller_with_pipeline.validator,
            "validate_general",
            lambda d: mock_result
        )
        controller_with_pipeline.validate_general()
        assert "ok" in received


# ----------------------------------------------------------------------
# Pipeline summary
# ----------------------------------------------------------------------
class TestPipelineSummary:

    def test_summary_no_pipeline(self, controller):
        summary = controller.get_pipeline_summary()
        assert summary["step_count"] == 0
        assert summary["has_general"] is False

    def test_summary_with_pipeline(self, controller_with_pipeline):
        controller_with_pipeline.add_step("image")
        summary = controller_with_pipeline.get_pipeline_summary()
        assert summary["step_count"] == 1
        assert summary["has_general"] is True
        assert "image" in summary["step_types"]

    def test_summary_version(self, controller_with_pipeline):
        summary = controller_with_pipeline.get_pipeline_summary()
        assert summary["version"] == 1.0


# ----------------------------------------------------------------------
# is_modified
# ----------------------------------------------------------------------
class TestIsModified:

    def test_always_returns_false(self, controller):
        assert controller.is_modified() is False

    def test_returns_false_after_changes(self, controller_with_pipeline):
        controller_with_pipeline.add_step("image")
        assert controller_with_pipeline.is_modified() is False
