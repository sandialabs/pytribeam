"""Editor controller for configuration UI.

This module manages the state and logic for the configuration editor,
separated from the UI presentation layer.
"""

from copy import deepcopy
from pathlib import Path
from typing import Callable, Dict, Optional, Any, Tuple, List
import tkinter as tk

import pytribeam.GUI.config_ui.lookup as lut
from pytribeam.GUI.config_ui.pipeline_model import PipelineConfig, StepConfig
from pytribeam.GUI.config_ui.validator import ConfigValidator


class EditorController:
    """Controls configuration editor state and operations.

    This class manages the pipeline configuration, step selection,
    parameter editing, and validation without UI dependencies.

    Attributes:
        pipeline: Current pipeline configuration
        current_step_index: Index of currently selected step (0 for general)
        validator: Configuration validator instance
    """

    def __init__(self, version: Optional[float] = None):
        """Initialize editor controller.

        Args:
            version: Configuration file version (uses latest if not specified)
        """
        self.pipeline: Optional[PipelineConfig] = None
        self.current_step_index: int = 0
        self._callbacks: Dict[str, Callable] = {}
        self._version = version or float(lut.VERSIONS[-1])

        # Initialize validator
        self.validator = ConfigValidator()
        self.validator.set_version(self._version)

        # Track expanded frames for UI state
        self.expanded_frames: Dict[str, bool] = {}

    def register_callback(self, event: str, callback: Callable):
        """Register callback for events.

        Args:
            event: Event name (e.g., 'pipeline_changed', 'step_selected')
            callback: Function to call when event occurs
        """
        self._callbacks[event] = callback

    def _notify(self, event: str, *args, **kwargs):
        """Trigger registered callback.

        Args:
            event: Event name
            *args: Arguments for callback
            **kwargs: Keyword arguments for callback
        """
        if event in self._callbacks:
            try:
                self._callbacks[event](*args, **kwargs)
            except Exception as e:
                print(f"Error in callback '{event}': {e}")

    def create_new_pipeline(self, version: Optional[float] = None):
        """Create new empty pipeline.

        Args:
            version: Configuration version (uses default if not specified)
        """
        if version is None:
            version = self._version

        self.pipeline = PipelineConfig.create_new(version=version)
        self.current_step_index = 0
        self._notify("pipeline_created", self.pipeline)
        # self._notify("step_selected", 0, self.pipeline.general)

    def load_pipeline(self, yaml_path: Path) -> Tuple[bool, Optional[str]]:
        """Load pipeline from YAML file.

        Args:
            yaml_path: Path to YAML file

        Returns:
            Tuple of (success, error_message)
        """
        try:
            self.pipeline = PipelineConfig.from_yaml(yaml_path)
            self.current_step_index = 0
            self.set_version(self.pipeline.version)
            self._notify("step_selected", 0, self.pipeline.general)
            self._notify("pipeline_loaded", self.pipeline)
            return True, None
        except Exception as e:
            return False, str(e)

    def save_pipeline(self, yaml_path: Path) -> Tuple[bool, Optional[str]]:
        """Save pipeline to YAML file.

        Args:
            yaml_path: Path where YAML should be saved

        Returns:
            Tuple of (success, error_message)
        """
        if self.pipeline is None:
            return False, "No pipeline to save"

        try:
            self.pipeline.to_yaml(yaml_path)
            self._notify("pipeline_saved", yaml_path)
            return True, None
        except Exception as e:
            return False, str(e)

    def add_step(self, step_type: str) -> StepConfig:
        """Add new step to pipeline.

        Args:
            step_type: Type of step to add

        Returns:
            Newly created step
        """
        if self.pipeline is None:
            raise ValueError("No pipeline loaded")

        step = self.pipeline.add_step(step_type)
        # self._notify("pipeline_changed", self.pipeline)
        self._notify("step_added", step)
        return step

    def remove_step(self, index: int) -> bool:
        """Remove step from pipeline.

        Args:
            index: Index of step to remove

        Returns:
            True if removed successfully
        """
        if self.pipeline is None:
            return False

        success = self.pipeline.remove_step(index)
        if success:
            # Adjust current selection if needed
            if self.current_step_index == index:
                self.current_step_index = max(0, index - 1)
            elif self.current_step_index > index:
                self.current_step_index -= 1

            self._notify("pipeline_changed", self.pipeline)
            self._notify("step_removed", index)
        return success

    def move_step(self, index: int, direction: int) -> bool:
        """Move step up or down in pipeline.

        Args:
            index: Index of step to move
            direction: -1 for up, +1 for down

        Returns:
            True if moved successfully
        """
        if self.pipeline is None:
            return False

        success = self.pipeline.move_step(index, direction)
        if success:
            # Update current selection if affected
            if self.current_step_index == index:
                self.current_step_index += direction
            elif abs(self.current_step_index - index) == 1:
                self.current_step_index -= direction

            self._notify("pipeline_changed", self.pipeline)
            self._notify("step_moved", index, direction)
        return success

    def duplicate_step(self, index: int) -> Optional[StepConfig]:
        """Duplicate existing step.

        Args:
            index: Index of step to duplicate

        Returns:
            Newly created step or None if failed
        """
        if self.pipeline is None:
            return None

        step = self.pipeline.duplicate_step(index)
        if step:
            self._notify("pipeline_changed", self.pipeline)
            self._notify("step_added", step)
        return step

    def select_step(self, index: int):
        """Select step for editing.

        Args:
            index: Index of step to select (0 for general)
        """
        if self.pipeline is None:
            return

        step = self.pipeline.get_step(index)
        if step:
            self.current_step_index = index
            self._notify("step_selected", index, step)

    def get_current_step(self) -> Optional[StepConfig]:
        """Get currently selected step.

        Returns:
            Current step or None
        """
        if self.pipeline is None:
            return None
        return self.pipeline.get_step(self.current_step_index)

    def update_parameter(self, path: str, value: Any):
        """Update parameter value in current step.

        Args:
            path: Parameter path (e.g., 'beam/voltage_kv')
            value: New value
        """
        step = self.get_current_step()
        if step:
            # Preserve boolean type, convert others to string
            param_value = value if isinstance(value, bool) else str(value)
            step.set_param(path, param_value)
            self._notify("parameter_changed", path, value)

    def get_parameter(self, path: str, default: Any = None) -> Any:
        """Get parameter value from current step.

        Args:
            path: Parameter path
            default: Default value if not found

        Returns:
            Parameter value
        """
        step = self.get_current_step()
        if step:
            return step.get_param(path, default)
        return default

    def validate_structure(self) -> Tuple[bool, str]:
        """Validate pipeline structure (names, step count).

        Returns:
            Tuple of (is_valid, message)
        """
        if self.pipeline is None:
            return False, "No pipeline loaded"

        results = self.validator.validate_pipeline_structure(self.pipeline)
        success, summary = ConfigValidator.get_summary(results)
        return success, summary

    def validate_full(self) -> Tuple[bool, str]:
        """Validate full pipeline configuration.

        Args:
            microscope: Optional microscope connection

        Returns:
            Tuple of (is_valid, message)
        """
        if self.pipeline is None:
            return False, "No pipeline loaded"

        results = self.validator.validate_pipeline_model(self.pipeline)
        success, summary = ConfigValidator.get_summary(results)
        self._notify("pipeline_validation_complete", success, summary)
        return success, summary

    def validate_step(self, index: int, microscope=None) -> Tuple[bool, str]:
        """Validate specific step configuration.

        Args:
            index: Index of step to validate
            microscope: Optional microscope connection

        Returns:
            Tuple of (is_valid, message)
        """
        # Make sure pipeline is loaded
        if self.pipeline is None:
            return False, "No pipeline loaded"

        # Get general settings for validation context, making sure they are valid
        result = self.validator.validate_general(
            self.pipeline.general.get_all_params(flat=False)
        )
        if not result.success:
            return False, "General configuration is invalid"
        general = result.settings

        # Get the step of interest
        step = self.pipeline.get_step(index)
        if step is None:
            return False, f"Step at index {index} not found"

        step_db = step.get_all_params(flat=False)
        result = self.validator.validate_step(microscope, step.name, step_db, general)
        success = result.success
        message = (
            "Step is valid." if success else f"Step validation failed: {result.message}"
        )
        self._notify("step_validation_complete", index, success, message)
        return success, message

    def validate_general(self) -> Tuple[bool, str]:
        """Validate general configuration.

        Returns:
            Tuple of (is_valid, message)
        """
        result = self.validator.validate_general(
            self.pipeline.general.get_all_params(flat=False)
        )
        success = result.success
        message = (
            "General configuration is valid."
            if success
            else f"General validation failed: {result.message}"
        )
        self._notify("step_validation_complete", 0, success, message)
        return success, message

    def get_step_count(self) -> int:
        """Get number of steps in pipeline.

        Returns:
            Step count (excluding general)
        """
        if self.pipeline is None:
            return 0
        return self.pipeline.get_step_count()

    def get_step_names(self) -> List[str]:
        """Get list of step names.

        Returns:
            List of step names
        """
        if self.pipeline is None:
            return []
        return [step.name for step in self.pipeline.steps]

    def rename_step(self, index: int, new_name: str) -> bool:
        """Rename a step.

        Args:
            index: Index of step to rename
            new_name: New step name

        Returns:
            True if renamed successfully
        """
        if self.pipeline is None or index == 0:
            return False

        step = self.pipeline.get_step(index)
        if step:
            step.name = new_name
            step.set_param("step_general/step_name", new_name)
            self._notify("pipeline_changed", self.pipeline)
            self._notify("step_renamed", index, new_name)
            return True
        return False

    def set_version(self, version: float):
        """Set configuration file version and migrate parameters.

        This updates the pipeline version and migrates all step parameters
        to match the new version's schema (adds new params, removes old ones).

        Args:
            version: New version number
        """
        self._version = version
        self.validator.set_version(self._version)
        if self.pipeline:
            self.pipeline.set_version(version)
            self._notify("version_changed", version)

    def get_version(self) -> float:
        """Get current configuration version.

        Returns:
            Version number
        """
        return self._version

    def is_modified(self) -> bool:
        """Check if pipeline has unsaved changes.

        Returns:
            True if there are unsaved changes
        """
        # This would need to track changes since last save
        # For now, return False (can be implemented later)
        return False

    def get_pipeline_summary(self) -> Dict[str, Any]:
        """Get summary of pipeline configuration.

        Returns:
            Dictionary with pipeline information
        """
        if self.pipeline is None:
            return {
                "version": self._version,
                "step_count": 0,
                "has_general": False,
                "step_types": [],
            }

        step_types = [step.step_type for step in self.pipeline.steps]
        return {
            "version": self.pipeline.version,
            "step_count": len(self.pipeline.steps),
            "has_general": True,
            "step_types": step_types,
            "file_path": (
                str(self.pipeline.file_path) if self.pipeline.file_path else None
            ),
        }
