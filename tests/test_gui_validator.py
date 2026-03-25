# tests/test_gui_validator.py
"""Tests for :class:`pytribeam.GUI.config_ui.validator.ConfigValidator`
and :class:`pytribeam.GUI.config_ui.validator.ValidationResult`.
"""

from unittest.mock import MagicMock, patch
import pytest

from pytribeam.GUI.config_ui.validator import ConfigValidator, ValidationResult
from pytribeam.GUI.config_ui.pipeline_model import PipelineConfig


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


@pytest.fixture(autouse=True)
def fake_lut(monkeypatch):
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


@pytest.fixture
def validator():
    return ConfigValidator()


@pytest.fixture
def pipeline():
    p = PipelineConfig.create_new(version=1.0)
    return p


# ----------------------------------------------------------------------
# ValidationResult
# ----------------------------------------------------------------------
class TestValidationResult:

    def test_success_result_str(self):
        r = ValidationResult(success=True, step_name="general")
        assert "general" in str(r)
        assert "passed" in str(r)

    def test_failure_result_str(self):
        r = ValidationResult(success=False, step_name="image_step", message="Missing field")
        text = str(r)
        assert "image_step" in text
        assert "failed" in text
        assert "Missing field" in text

    def test_empty_message_omitted_from_str(self):
        r = ValidationResult(success=True, step_name="step", message="")
        assert ":" not in str(r)  # no colon appended for empty message

    def test_bool_context_true(self):
        r = ValidationResult(success=True, step_name="s")
        assert bool(r) is True
        assert r  # truthy

    def test_bool_context_false(self):
        r = ValidationResult(success=False, step_name="s")
        assert bool(r) is False
        assert not r  # falsy

    def test_default_fields(self):
        r = ValidationResult(success=True, step_name="s")
        assert r.message == ""
        assert r.exception is None
        assert r.settings is None

    def test_exception_stored(self):
        exc = ValueError("bad value")
        r = ValidationResult(success=False, step_name="s", exception=exc)
        assert r.exception is exc


# ----------------------------------------------------------------------
# ConfigValidator.set_version
# ----------------------------------------------------------------------
class TestSetVersion:

    def test_set_version_changes_format(self, validator):
        # Calling set_version should not raise
        validator.set_version(1.0)

    def test_validator_initializes_with_version_1(self, validator):
        # Should default to 1.0
        assert validator._yml_format is not None


# ----------------------------------------------------------------------
# check_has_steps
# ----------------------------------------------------------------------
class TestCheckHasSteps:

    def test_empty_pipeline_fails(self, validator, pipeline):
        result = validator.check_has_steps(pipeline)
        assert result.success is False
        assert "at least one step" in result.message.lower()

    def test_pipeline_with_steps_passes(self, validator, pipeline):
        pipeline.add_step("image")
        result = validator.check_has_steps(pipeline)
        assert result.success is True

    def test_step_name_is_set(self, validator, pipeline):
        result = validator.check_has_steps(pipeline)
        assert result.step_name == "Step Count"


# ----------------------------------------------------------------------
# check_duplicate_names
# ----------------------------------------------------------------------
class TestCheckDuplicateNames:

    def test_unique_names_passes(self, validator, pipeline):
        pipeline.add_step("image", name="alpha")
        pipeline.add_step("image", name="beta")
        result = validator.check_duplicate_names(pipeline)
        assert result.success is True

    def test_duplicate_names_fails(self, validator, pipeline):
        pipeline.add_step("image", name="same")
        pipeline.add_step("image", name="same")
        result = validator.check_duplicate_names(pipeline)
        assert result.success is False
        assert "same" in result.message

    def test_step_name_is_set(self, validator, pipeline):
        result = validator.check_duplicate_names(pipeline)
        assert result.step_name == "Step Names"


# ----------------------------------------------------------------------
# validate_pipeline_structure
# ----------------------------------------------------------------------
class TestValidatePipelineStructure:

    def test_empty_pipeline_returns_two_results(self, validator, pipeline):
        results = validator.validate_pipeline_structure(pipeline)
        assert len(results) == 2

    def test_empty_pipeline_fails_step_count(self, validator, pipeline):
        results = validator.validate_pipeline_structure(pipeline)
        step_count_result = next(r for r in results if r.step_name == "Step Count")
        assert step_count_result.success is False

    def test_valid_pipeline_passes(self, validator, pipeline):
        pipeline.add_step("image", name="alpha")
        results = validator.validate_pipeline_structure(pipeline)
        assert all(r.success for r in results)

    def test_duplicate_names_detected(self, validator, pipeline):
        pipeline.add_step("image", name="dup")
        pipeline.add_step("image", name="dup")
        results = validator.validate_pipeline_structure(pipeline)
        name_result = next(r for r in results if r.step_name == "Step Names")
        assert name_result.success is False


# ----------------------------------------------------------------------
# get_summary
# ----------------------------------------------------------------------
class TestGetSummary:

    def test_all_passed_summary(self):
        results = [
            ValidationResult(success=True, step_name="s1"),
            ValidationResult(success=True, step_name="s2"),
        ]
        ok, summary = ConfigValidator.get_summary(results)
        assert ok is True
        assert "All checks passed" in summary
        assert "s1" in summary
        assert "s2" in summary

    def test_some_failed_summary(self):
        results = [
            ValidationResult(success=True, step_name="s1"),
            ValidationResult(success=False, step_name="s2", message="oops"),
        ]
        ok, summary = ConfigValidator.get_summary(results)
        assert ok is False
        assert "1 check(s) failed" in summary

    def test_all_failed_summary(self):
        results = [
            ValidationResult(success=False, step_name="s1"),
            ValidationResult(success=False, step_name="s2"),
        ]
        ok, summary = ConfigValidator.get_summary(results)
        assert ok is False
        assert "2 check(s) failed" in summary

    def test_empty_results(self):
        ok, summary = ConfigValidator.get_summary([])
        assert ok is True  # vacuously true

    def test_summary_contains_all_step_names(self):
        results = [
            ValidationResult(success=True, step_name="general"),
            ValidationResult(success=False, step_name="step1", message="error"),
        ]
        _, summary = ConfigValidator.get_summary(results)
        assert "general" in summary
        assert "step1" in summary


# ----------------------------------------------------------------------
# validate_general (mocked factory)
# ----------------------------------------------------------------------
class TestValidateGeneral:

    def test_success_case(self, validator, monkeypatch):
        fake_settings = MagicMock()
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.validator.factory.general",
            lambda config, yml_format: fake_settings,
        )
        result = validator.validate_general({"general": {}})
        assert result.success is True
        assert result.settings is fake_settings

    def test_key_error_returns_failure(self, validator, monkeypatch):
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.validator.factory.general",
            lambda config, yml_format: (_ for _ in ()).throw(KeyError("missing_key")),
        )
        result = validator.validate_general({"general": {}})
        assert result.success is False
        assert "missing_key" in result.message

    def test_generic_exception_returns_failure(self, validator, monkeypatch):
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.validator.factory.general",
            lambda config, yml_format: (_ for _ in ()).throw(ValueError("bad value")),
        )
        result = validator.validate_general({})
        assert result.success is False
        assert "ValueError" in result.message

    def test_step_name_is_general(self, validator, monkeypatch):
        fake_settings = MagicMock()
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.validator.factory.general",
            lambda config, yml_format: fake_settings,
        )
        result = validator.validate_general({})
        assert result.step_name == "general"


# ----------------------------------------------------------------------
# validate_step (mocked factory)
# ----------------------------------------------------------------------
class TestValidateStep:

    def test_success_case(self, validator, monkeypatch):
        fake_settings = MagicMock()
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.validator.factory.step",
            lambda *a, **kw: fake_settings,
        )
        result = validator.validate_step(
            microscope=None,
            step_name="my_step",
            step_config={},
            general_settings=MagicMock(),
        )
        assert result.success is True
        assert result.step_name == "my_step"
        assert result.settings is fake_settings

    def test_key_error_returns_failure(self, validator, monkeypatch):
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.validator.factory.step",
            lambda *a, **kw: (_ for _ in ()).throw(KeyError("field")),
        )
        result = validator.validate_step(
            microscope=None,
            step_name="bad_step",
            step_config={},
            general_settings=MagicMock(),
        )
        assert result.success is False
        assert result.step_name == "bad_step"

    def test_generic_exception_returns_failure(self, validator, monkeypatch):
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.validator.factory.step",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("something broke")),
        )
        result = validator.validate_step(
            microscope=None,
            step_name="bad_step",
            step_config={},
            general_settings=MagicMock(),
        )
        assert result.success is False
        assert "RuntimeError" in result.message


# ----------------------------------------------------------------------
# validate_pipeline_model
# ----------------------------------------------------------------------
class TestValidatePipelineModel:

    def test_delegates_to_validate_full_pipeline(self, validator, pipeline, monkeypatch):
        """validate_pipeline_model converts to dict and delegates."""
        called_with = {}

        def fake_validate(config_dict, microscope=None):
            called_with["config"] = config_dict
            return [ValidationResult(success=True, step_name="general")]

        monkeypatch.setattr(validator, "validate_full_pipeline", fake_validate)
        results = validator.validate_pipeline_model(pipeline)

        assert len(results) == 1
        assert "config" in called_with


# ----------------------------------------------------------------------
# validate_full_pipeline (mocked)
# ----------------------------------------------------------------------
class TestValidateFullPipeline:

    def test_general_failure_stops_early(self, validator, monkeypatch):
        # Make validate_general fail
        monkeypatch.setattr(
            validator,
            "validate_general",
            lambda d: ValidationResult(success=False, step_name="general", message="fail"),
        )
        results = validator.validate_full_pipeline({"general": {}, "steps": {"s": {}}})
        # Should only have one result (general) and not proceed to steps
        assert len(results) == 1
        assert results[0].step_name == "general"

    def test_no_steps_returns_general_only(self, validator, monkeypatch):
        fake_settings = MagicMock()
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.validator.factory.general",
            lambda config, yml_format: fake_settings,
        )
        results = validator.validate_full_pipeline({"general": {}})
        assert len(results) == 1
        assert results[0].success is True
