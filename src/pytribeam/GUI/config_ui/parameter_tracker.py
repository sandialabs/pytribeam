"""Parameter tracker for managing UI variable bindings to EditorController.

This module provides a clean interface for tracking parameter changes in the UI
and synchronizing them with the EditorController.
"""

import tkinter as tk
from typing import Any, Callable, Dict, Optional

import pytribeam.GUI.config_ui.lookup as lut
from pytribeam.GUI.config_ui.editor_controller import EditorController


class ParameterTracker:
    """Manages tkinter variables and their connection to EditorController.

    This class provides:
    - Automatic variable creation based on parameter type
    - Input validation based on LUT dtype
    - Direct updates to controller when UI changes
    - Automatic UI updates when controller state changes

    Attributes:
        controller: EditorController instance
        variables: Dict mapping parameter paths to tkinter variables
        trace_ids: Dict mapping parameter paths to trace IDs
        validators: Dict mapping parameter paths to validation functions
    """

    def __init__(self, controller: EditorController):
        """Initialize parameter tracker.

        Args:
            controller: EditorController instance to bind to
        """
        self.controller = controller
        self.variables: Dict[str, tk.Variable] = {}
        self.trace_ids: Dict[str, str] = {}
        self.validators: Dict[str, Callable] = {}
        self._updating_from_controller = False

    def create_variable(
        self,
        param_path: str,
        dtype: type,
        default: Any = None,
        validator: Optional[Callable] = None,
    ) -> tk.Variable:
        """Create a traced variable for a parameter.

        Args:
            param_path: Parameter path (e.g., 'beam/voltage_kv')
            dtype: Data type from LUT
            default: Default value if parameter not set
            validator: Optional custom validator function

        Returns:
            Tkinter variable with trace attached
        """
        # Create appropriate variable type based on dtype
        var = self._create_typed_variable(dtype)

        # Set initial value from controller
        value = self.controller.get_parameter(param_path, default)
        if value is not None:
            try:
                var.set(value)
            except tk.TclError:
                # If value is incompatible with var type, use default
                if default is not None:
                    var.set(default)

        # Add trace to update controller when variable changes
        trace_id = var.trace_add('write', lambda *args: self._on_variable_changed(param_path, var, dtype))

        # Store variable and trace info
        self.variables[param_path] = var
        self.trace_ids[param_path] = trace_id

        # Store custom validator if provided
        if validator:
            self.validators[param_path] = validator
        else:
            # Create default validator based on dtype
            self.validators[param_path] = self._create_default_validator(dtype)

        return var

    def _create_typed_variable(self, dtype: type) -> tk.Variable:
        """Create appropriate tkinter variable based on dtype.

        Args:
            dtype: Python type (int, float, bool, str, etc.)

        Returns:
            Appropriate tkinter variable
        """
        # Note: We use StringVar for most types and do validation in callbacks
        # This allows better control over input validation and error handling
        if dtype == bool:
            return tk.BooleanVar()
        else:
            # Use StringVar for int, float, str - gives us more control
            return tk.StringVar()

    def _create_default_validator(self, dtype: type) -> Callable:
        """Create default validator function based on dtype.

        Args:
            dtype: Python type

        Returns:
            Validator function
        """
        if dtype == int:
            return lambda value: self._validate_int(value)
        elif dtype == float:
            return lambda value: self._validate_float(value)
        elif dtype == bool:
            return lambda value: self._validate_bool(value)
        else:
            return lambda value: str(value) if value is not None else ""

    def _validate_int(self, value: Any) -> str:
        """Validate integer input.

        Args:
            value: Value to validate

        Returns:
            Validated string representation
        """
        if value == "" or value is None:
            return ""
        try:
            # Allow negative sign and digits
            str_val = str(value).strip()
            if str_val in ["-", "+"]:
                return str_val
            int(str_val)  # Test if valid
            return str_val
        except ValueError:
            raise ValueError(f"Invalid integer: {value}")

    def _validate_float(self, value: Any) -> str:
        """Validate float input.

        Args:
            value: Value to validate

        Returns:
            Validated string representation
        """
        if value == "" or value is None:
            return ""
        try:
            # Allow negative sign, digits, and decimal point
            str_val = str(value).strip()
            if str_val in ["-", "+", ".", "-.", "+."]:
                return str_val
            float(str_val)  # Test if valid
            return str_val
        except ValueError:
            raise ValueError(f"Invalid float: {value}")

    def _validate_bool(self, value: Any) -> bool:
        """Validate boolean input.

        Args:
            value: Value to validate

        Returns:
            Boolean value
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.lower() in ["true", "1", "yes"]:
                return True
            elif value.lower() in ["false", "0", "no", ""]:
                return False
        return bool(value)

    def _on_variable_changed(self, param_path: str, var: tk.Variable, dtype: type):
        """Handle variable change from UI.

        Args:
            param_path: Parameter path
            var: Tkinter variable that changed
            dtype: Expected data type
        """
        # Avoid recursive updates
        if self._updating_from_controller:
            return

        try:
            value = var.get()

            # Apply validation
            if param_path in self.validators:
                validated_value = self.validators[param_path](value)
            else:
                validated_value = value

            # Update variable with validated value if it changed
            if value != validated_value:
                self._updating_from_controller = True
                var.set(validated_value)
                self._updating_from_controller = False

            # Update controller
            self.controller.update_parameter(param_path, validated_value)

        except (ValueError, tk.TclError) as e:
            # Validation failed - revert to previous value from controller
            old_value = self.controller.get_parameter(param_path)
            if old_value is not None:
                self._updating_from_controller = True
                try:
                    var.set(old_value)
                except tk.TclError:
                    pass  # If revert fails, just leave it
                self._updating_from_controller = False

    def load_from_controller(self):
        """Update all UI variables from current controller state.

        This is called when a new step is selected to sync the UI.
        """
        self._updating_from_controller = True
        try:
            for param_path, var in self.variables.items():
                value = self.controller.get_parameter(param_path)
                if value is not None:
                    try:
                        var.set(value)
                    except tk.TclError:
                        pass  # Skip if incompatible
        finally:
            self._updating_from_controller = False

    def clear(self):
        """Clear all traced variables and cleanup."""
        # Remove all traces
        for param_path in list(self.trace_ids.keys()):
            if param_path in self.variables:
                try:
                    self.variables[param_path].trace_remove('write', self.trace_ids[param_path])
                except (KeyError, tk.TclError):
                    pass  # Already removed or invalid

        # Clear all storage
        self.variables.clear()
        self.trace_ids.clear()
        self.validators.clear()

    def get_variable(self, param_path: str) -> Optional[tk.Variable]:
        """Get tracked variable for parameter.

        Args:
            param_path: Parameter path

        Returns:
            Tkinter variable or None if not found
        """
        return self.variables.get(param_path)

    def add_custom_validator(self, param_path: str, validator: Callable):
        """Add or replace custom validator for parameter.

        Args:
            param_path: Parameter path
            validator: Validator function
        """
        self.validators[param_path] = validator

    def __repr__(self) -> str:
        return f"ParameterTracker(variables={len(self.variables)})"
