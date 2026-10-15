# tests/test_gui_errors.py
"""Tests for :mod:`pytribeam.GUI.common.errors` exception hierarchy."""

import pytest

from pytribeam.GUI.common.errors import (
    TriBeamGUIError,
    ConfigurationError,
    MicroscopeConnectionError,
    ValidationError,
    ResourceError,
    ExperimentError,
    ThreadError,
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
ALL_EXCEPTION_CLASSES = [
    ConfigurationError,
    MicroscopeConnectionError,
    ValidationError,
    ResourceError,
    ExperimentError,
    ThreadError,
]


# ----------------------------------------------------------------------
# Inheritance
# ----------------------------------------------------------------------
class TestInheritance:
    """Verify the exception hierarchy is correct."""

    def test_base_inherits_from_exception(self):
        assert issubclass(TriBeamGUIError, Exception)

    @pytest.mark.parametrize("exc_class", ALL_EXCEPTION_CLASSES)
    def test_subclass_inherits_from_base(self, exc_class):
        assert issubclass(exc_class, TriBeamGUIError)

    @pytest.mark.parametrize("exc_class", ALL_EXCEPTION_CLASSES)
    def test_subclass_inherits_from_exception(self, exc_class):
        assert issubclass(exc_class, Exception)


# ----------------------------------------------------------------------
# Raising and catching
# ----------------------------------------------------------------------
class TestRaiseAndCatch:
    """Verify exceptions can be raised and caught as expected."""

    def test_raise_base(self):
        with pytest.raises(TriBeamGUIError):
            raise TriBeamGUIError("base error")

    @pytest.mark.parametrize("exc_class", ALL_EXCEPTION_CLASSES)
    def test_raise_subclass(self, exc_class):
        with pytest.raises(exc_class):
            raise exc_class("error")

    @pytest.mark.parametrize("exc_class", ALL_EXCEPTION_CLASSES)
    def test_catch_as_base(self, exc_class):
        """Subclass exceptions can be caught as TriBeamGUIError."""
        with pytest.raises(TriBeamGUIError):
            raise exc_class("caught as base")

    @pytest.mark.parametrize("exc_class", ALL_EXCEPTION_CLASSES)
    def test_catch_as_exception(self, exc_class):
        """Subclass exceptions can be caught as the generic Exception."""
        with pytest.raises(Exception):
            raise exc_class("caught as Exception")

    def test_subclasses_dont_catch_each_other(self):
        """Different subclasses are separate types."""
        with pytest.raises(ConfigurationError):
            raise ConfigurationError("config")

        # ValidationError should NOT catch ConfigurationError
        try:
            raise ConfigurationError("test")
        except ValidationError:
            pytest.fail("ValidationError caught ConfigurationError incorrectly")
        except ConfigurationError:
            pass  # expected


# ----------------------------------------------------------------------
# Message preservation
# ----------------------------------------------------------------------
class TestMessagePreservation:
    """Verify exception messages are preserved."""

    @pytest.mark.parametrize("exc_class", ALL_EXCEPTION_CLASSES)
    def test_message_preserved(self, exc_class):
        msg = f"Specific error from {exc_class.__name__}"
        try:
            raise exc_class(msg)
        except exc_class as e:
            assert str(e) == msg

    def test_base_message_preserved(self):
        msg = "base error message"
        try:
            raise TriBeamGUIError(msg)
        except TriBeamGUIError as e:
            assert str(e) == msg

    def test_no_message(self):
        """Exceptions can be raised without a message."""
        exc = ConfigurationError()
        assert str(exc) == ""

    def test_multiple_args(self):
        """Exceptions support multiple arguments."""
        exc = ValidationError("part1", "part2")
        assert "part1" in str(exc)


# ----------------------------------------------------------------------
# Chaining / cause
# ----------------------------------------------------------------------
class TestChaining:
    """Verify exception chaining works with all custom exceptions."""

    @pytest.mark.parametrize("exc_class", ALL_EXCEPTION_CLASSES)
    def test_raise_from(self, exc_class):
        original = ValueError("original error")
        try:
            raise exc_class("wrapped") from original
        except exc_class as e:
            assert e.__cause__ is original

    def test_suppress_context(self):
        """Exceptions can suppress the implicit exception context."""
        try:
            try:
                raise ValueError("inner")
            except ValueError:
                raise MicroscopeConnectionError("outer") from None
        except MicroscopeConnectionError as e:
            assert e.__cause__ is None
            assert e.__suppress_context__ is True


# ----------------------------------------------------------------------
# isinstance checks
# ----------------------------------------------------------------------
class TestInstanceChecks:
    """Verify isinstance behaves correctly with the hierarchy."""

    def test_subclass_instance_of_base(self):
        exc = ConfigurationError("test")
        assert isinstance(exc, TriBeamGUIError)
        assert isinstance(exc, Exception)
        assert isinstance(exc, ConfigurationError)

    def test_base_not_instance_of_subclass(self):
        exc = TriBeamGUIError("test")
        assert not isinstance(exc, ConfigurationError)
        assert not isinstance(exc, ValidationError)
