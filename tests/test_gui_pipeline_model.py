import pytest
from pathlib import Path

from pytribeam.GUI.config_ui.pipeline_model import (
    StepConfig,
    PipelineConfig,
    flatten_dict,
    unflatten_dict,
    _check_value_type,
)


# ----------------------------------------------------------------------
# Fake LUT infrastructure
# ----------------------------------------------------------------------
class FakeField:
    def __init__(self, dtype=str, default=""):
        self.dtype = dtype
        self.default = default


class FakeLUT(dict):
    def flatten(self):
        return self


@pytest.fixture
def fake_lut(monkeypatch):
    def get_lut(step_type, version):
        lut = FakeLUT({
            "step_general/step_type": FakeField(str, "image"),
            "step_general/step_name": FakeField(str, "step"),
            "step_general/step_number": FakeField(int, 1),
            "beam/voltage_kv": FakeField(float, 5.0),
            "enabled": FakeField(bool, True),
            "step_count": FakeField(int, 0),
        })
        return lut

    monkeypatch.setattr("pytribeam.GUI.config_ui.pipeline_model.lut.get_lut", get_lut)
    monkeypatch.setattr("pytribeam.GUI.config_ui.pipeline_model.lut.VERSIONS", [1.0])

# ----------------------------------------------------------------------
# StepConfig
# ----------------------------------------------------------------------
class TestStepConfig:

    def test_set_and_get_param(self):
        step = StepConfig(1, "image", "img")
        step.set_param("beam/voltage_kv", "5")
        assert step.get_param("beam/voltage_kv") == "5"

    def test_name_updates(self):
        step = StepConfig(1, "image", "old")
        step.set_param("step_general/step_name", "new")
        assert step.name == "new"

    def test_has_param(self):
        step = StepConfig(1, "image", "img", {"a": 1})
        assert step.has_param("a")
        assert not step.has_param("b")

    def test_clear_params(self):
        step = StepConfig(1, "image", "img", {"a": 1})
        step.clear_params()
        assert step.parameters == {}

# ----------------------------------------------------------------------
# Type conversion
# ----------------------------------------------------------------------
class TestTypeConversion:

    def test_bool_conversion(self):
        assert _check_value_type("True", bool) is True
        assert _check_value_type("false", bool) is False

    def test_none_conversion(self):
        assert _check_value_type("", int) is None
        assert _check_value_type("null", int) is None

    def test_numeric_conversion(self):
        assert _check_value_type("5", int) == 5
        assert _check_value_type("2.5", float) == 2.5

    def test_invalid_conversion_returns_original(self):
        assert _check_value_type("abc", int) == "abc"

# ----------------------------------------------------------------------
# Pipeline creation
# ----------------------------------------------------------------------
class TestPipelineCreation:

    def test_create_new(self, fake_lut):
        pipeline = PipelineConfig.create_new()

        assert pipeline.get_step_count() == 0
        assert pipeline.general.get_param("step_count") == "0"

# ----------------------------------------------------------------------
# Step manipulation
# ----------------------------------------------------------------------
class TestPipelineSteps:

    def test_add_step(self, fake_lut):
        p = PipelineConfig.create_new()
        step = p.add_step("image")

        assert step.index == 1
        assert p.get_step_count() == 1

    def test_remove_step(self, fake_lut):
        p = PipelineConfig.create_new()
        p.add_step("image")
        assert p.remove_step(1) is True
        assert p.get_step_count() == 0

    def test_move_step(self, fake_lut):
        p = PipelineConfig.create_new()
        p.add_step("image")
        p.add_step("image")

        assert p.move_step(2, -1)
        assert p.steps[0].index == 1

    def test_duplicate_step(self, fake_lut):
        p = PipelineConfig.create_new()
        p.add_step("image")

        dup = p.duplicate_step(1)
        assert dup is not None
        assert p.get_step_count() == 2

# ----------------------------------------------------------------------
# Name validation
# ----------------------------------------------------------------------
class TestValidation:

    def test_duplicate_names(self, fake_lut):
        p = PipelineConfig.create_new()
        p.add_step("image", name="same")
        p.add_step("image", name="same")

        valid, dup = p.validate_step_names()
        assert not valid
        assert "same" in dup

# ----------------------------------------------------------------------
# flatten/unflatten
# ----------------------------------------------------------------------
class TestDictUtilities:

    def test_flatten(self):
        d = {"a": {"b": 1}}
        assert flatten_dict(d) == {"a/b": 1}

    def test_unflatten(self):
        d = {"a/b": 1}
        assert unflatten_dict(d) == {"a": {"b": 1}}

# ----------------------------------------------------------------------
# Version migration
# ----------------------------------------------------------------------
class TestVersionMigration:

    def test_set_version_updates_steps(self, fake_lut):
        p = PipelineConfig.create_new(version=1.0)
        p.add_step("image")

        p.set_version(2.0)
        assert p.version == 2.0
        assert all(s.version == 2.0 for s in p.steps)
