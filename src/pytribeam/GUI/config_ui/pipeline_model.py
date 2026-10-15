"""Pipeline configuration data model.

This module provides data structures for representing and manipulating
pipeline configurations, separating data concerns from UI concerns.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple

import pytribeam.GUI.config_ui.lookup as lut
import pytribeam.utilities as ut


def _check_value_type(value: Any, dtype: type) -> Any:
    """Convert value to correct type based on dtype.

    Handles conversion from string representations to proper Python types.
    Converts '', 'null', 'None' to None, 'True'/'true' to True, etc.

    Args:
        value: Value to convert (usually a string)
        dtype: Target data type

    Returns:
        Converted value with correct type
    """
    # Handle None values
    if value in ["", "null", "None", None]:
        return None

    # If value is already the correct type, return as-is (especially for booleans)
    if dtype is not None and isinstance(value, dtype):
        return value

    if isinstance(value, str):
        value = value.strip()

    # If no dtype specified, return as-is
    if dtype is None:
        return value

    # Handle boolean strings
    if value in ["True", "true"]:
        return True
    elif value in ["False", "false"]:
        return False

    # Convert to target type
    try:
        return dtype(value)
    except (ValueError, TypeError):
        # If conversion fails, return original value
        return value


def _apply_type_conversion(
    params: Dict[str, Any], step_type: str, version: float
) -> Dict[str, Any]:
    """Apply type conversion to parameters based on LUT.

    Args:
        params: Flattened parameter dictionary (with "/" separators)
        step_type: Step type (e.g., "general", "image", "fib")
        version: Configuration version

    Returns:
        Dictionary with type-converted values
    """
    # Get LUT for this step type
    try:
        step_lut = lut.get_lut(step_type.lower(), version)
        step_lut.flatten()
    except Exception:
        # If LUT not found, return params as-is
        return params

    converted = {}
    for key, value in params.items():
        if key in step_lut.keys():
            # Get dtype from LUT and convert
            dtype = step_lut[key].dtype
            converted[key] = _check_value_type(value, dtype)
        else:
            # Keep parameters not in LUT as-is (they'll be filtered out later)
            converted[key] = value

    return converted


@dataclass
class StepConfig:
    """Configuration for a single pipeline step.

    Represents one step in the experiment pipeline with all its parameters.
    Parameters are stored in a flattened dictionary with '/' separators.

    Attributes:
        index: Position in pipeline (0 for general, 1+ for steps)
        step_type: Type of step (e.g., 'image', 'fib', 'laser')
        name: Unique name for this step
        parameters: Flattened dictionary of step parameters
        version: Configuration file version
    """

    index: int
    step_type: str
    name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    version: float = field(default=float(lut.VERSIONS[-1]))

    def get_param(self, path: str, default: Any = None) -> Any:
        """Get parameter value by path.

        Args:
            path: Parameter path with '/' separators (e.g., 'beam/voltage_kv')
            default: Value to return if parameter not found

        Returns:
            Parameter value or default
        """
        return self.parameters.get(path, default)

    def set_param(self, path: str, value: Any):
        """Set parameter value by path.

        Args:
            path: Parameter path with '/' separators
            value: Value to set
        """
        self.parameters[path] = value
        if path == "step_general/step_name":
            self.name = str(value)

    def has_param(self, path: str) -> bool:
        """Check if parameter exists.

        Args:
            path: Parameter path with '/' separators

        Returns:
            True if parameter exists
        """
        return path in self.parameters

    def get_all_params(self, flat: bool = True) -> Dict[str, Any]:
        """Get all parameters as dictionary.

        Returns:
            Copy of parameters dictionary
        """
        db = _apply_type_conversion(
            deepcopy(self.parameters), self.step_type, self.version
        )
        if flat:
            return db
        else:
            return unflatten_dict(db, sep="/")

    def update_params(self, params: Dict[str, Any]):
        """Update multiple parameters at once.

        Args:
            params: Dictionary of parameters to update
        """
        self.parameters.update(params)

    def clear_params(self):
        """Remove all parameters."""
        self.parameters.clear()

    def __repr__(self) -> str:
        return f"StepConfig(index={self.index}, type={self.step_type}, name={self.name}), version={self.version}"


@dataclass
class PipelineConfig:
    """Complete pipeline configuration.

    Represents the entire experiment configuration including general settings
    and all pipeline steps.

    Attributes:
        version: Configuration file version
        general: General configuration step
        steps: List of pipeline steps
        file_path: Path to configuration file (if loaded from file)
    """

    version: float
    general: StepConfig
    steps: List[StepConfig] = field(default_factory=list)
    file_path: Optional[Path] = None

    @classmethod
    def create_new(cls, version: float = None) -> "PipelineConfig":
        """Create new empty pipeline configuration.

        Initializes general step with all parameters from LUT with default values.

        Args:
            version: Config file version (uses latest if not specified)

        Returns:
            New PipelineConfig with only general step
        """
        if version is None:
            version = float(lut.VERSIONS[-1])

        # Create temporary instance to use helper method
        temp_pipeline = cls(
            version=version,
            general=StepConfig(
                index=0,
                step_type="general",
                name="general",
                parameters={},
                version=version,
            ),
            steps=[],
        )

        # Get all default parameters from general LUT
        general_params = temp_pipeline._populate_default_parameters("general")

        # Ensure step_count is set to 0
        general_params["step_count"] = "0"

        general = StepConfig(
            index=0,
            step_type="general",
            name="general",
            parameters=general_params,
        )

        return cls(version=version, general=general, steps=[])

    def _update_step_count(self):
        """Update step_count parameter in general step to reflect current step count."""
        self.general.set_param("step_count", str(len(self.steps)))

    def _populate_default_parameters(self, step_type: str) -> Dict[str, Any]:
        """Populate parameters with default values from LUT.

        Args:
            step_type: Type of step (e.g., 'general', 'image', 'fib')

        Returns:
            Dictionary of parameter paths to default values (preserves booleans)
        """
        try:
            # Get LUT for this step type and version
            step_lut = lut.get_lut(step_type.lower(), self.version)
            step_lut_flat = deepcopy(step_lut)
            step_lut_flat.flatten()

            # Extract all parameters with their defaults
            params = {}
            for key, field in step_lut_flat.items():
                # Get default value, preserving type (especially booleans)
                default_value = field.default if field.default is not None else ""
                # Preserve boolean type, convert others to string
                if isinstance(default_value, bool):
                    params[key] = default_value
                else:
                    params[key] = str(default_value)

            return params
        except Exception as e:
            # If LUT lookup fails, return empty dict
            print(f"Warning: Failed to get LUT defaults for {step_type}: {e}")
            return {}

    def add_step(self, step_type: str, name: Optional[str] = None) -> StepConfig:
        """Add new step to pipeline.

        Initializes step with all parameters from LUT with default values.

        Args:
            step_type: Type of step to add (e.g., 'image', 'fib')
            name: Optional custom name (auto-generated if not provided)

        Returns:
            Newly created StepConfig
        """
        index = len(self.steps) + 1

        # Auto-generate name if not provided
        if name is None:
            count = sum(1 for s in self.steps if s.step_type == step_type)
            name = f"{step_type}_{count + 1}"

        # Get all default parameters from LUT
        parameters = self._populate_default_parameters(step_type)

        # Override with step-specific values
        parameters.update(
            {
                "step_general/step_type": step_type,
                "step_general/step_name": name,
                "step_general/step_number": str(index),
            }
        )

        step = StepConfig(
            index=index,
            step_type=step_type,
            name=name,
            parameters=parameters,
            version=self.version,
        )

        self.steps.append(step)

        # Update step count in general
        self._update_step_count()

        return step

    def remove_step(self, index: int) -> bool:
        """Remove step at specified index.

        Re-indexes remaining steps to maintain sequential ordering.

        Args:
            index: Index of step to remove (1-based, not 0 which is general)

        Returns:
            True if step was removed, False if index invalid
        """
        if index == 0 or index > len(self.steps):
            return False

        # Remove step
        self.steps = [s for s in self.steps if s.index != index]

        # Reindex remaining steps
        for i, step in enumerate(self.steps, 1):
            step.index = i
            step.set_param("step_general/step_number", str(i))

        # Update step count in general
        self._update_step_count()

        return True

    def move_step(self, index: int, direction: int) -> bool:
        """Move step up or down in pipeline.

        Args:
            index: Index of step to move (1-based)
            direction: -1 to move up, +1 to move down

        Returns:
            True if step was moved, False if move invalid
        """
        if index == 0 or index > len(self.steps):
            return False

        new_index = index + direction
        if new_index < 1 or new_index > len(self.steps):
            return False

        # Swap steps in list (convert to 0-based indices)
        idx1 = index - 1
        idx2 = new_index - 1
        self.steps[idx1], self.steps[idx2] = self.steps[idx2], self.steps[idx1]

        # Update indices
        self.steps[idx1].index = index
        self.steps[idx2].index = new_index
        self.steps[idx1].set_param("step_general/step_number", str(index))
        self.steps[idx2].set_param("step_general/step_number", str(new_index))

        return True

    def duplicate_step(self, index: int) -> Optional[StepConfig]:
        """Duplicate an existing step.

        Creates a copy of the step and adds it to the end of the pipeline
        with an auto-generated name.

        Args:
            index: Index of step to duplicate

        Returns:
            Newly created StepConfig or None if index invalid
        """
        if index == 0 or index > len(self.steps):
            return None

        original = self.steps[index - 1]
        new_step = deepcopy(original)
        new_step.index = len(self.steps) + 1

        # Generate new name
        count = sum(1 for s in self.steps if s.step_type == original.step_type)
        new_step.name = f"{original.step_type}_{count + 1}"
        new_step.set_param("step_general/step_name", new_step.name)
        new_step.set_param("step_general/step_number", str(new_step.index))

        self.steps.append(new_step)

        # Update step count in general
        self._update_step_count()

        return new_step

    def get_step(self, index: int) -> Optional[StepConfig]:
        """Get step by index.

        Args:
            index: Step index (0 for general, 1+ for pipeline steps)

        Returns:
            StepConfig or None if index invalid
        """
        if index == 0:
            return self.general
        elif 1 <= index <= len(self.steps):
            return self.steps[index - 1]
        return None

    def get_step_by_name(self, name: str) -> Optional[StepConfig]:
        """Get step by name.

        Args:
            name: Step name to search for

        Returns:
            StepConfig or None if not found
        """
        if name == "general":
            return self.general

        for step in self.steps:
            if step.name == name:
                return step
        return None

    def get_step_count(self) -> int:
        """Get number of steps (excluding general).

        Returns:
            Number of pipeline steps
        """
        return len(self.steps)

    def validate_step_names(self) -> Tuple[bool, List[str]]:
        """Check for duplicate step names.

        Returns:
            Tuple of (is_valid, list_of_duplicate_names)
        """
        names = [s.name for s in self.steps]
        duplicates = [name for name in set(names) if names.count(name) > 1]
        return len(duplicates) == 0, duplicates

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "PipelineConfig":
        """Load pipeline configuration from YAML file.

        Args:
            yaml_path: Path to YAML configuration file

        Returns:
            PipelineConfig instance

        Raises:
            FileNotFoundError: If YAML file doesn't exist
            ValueError: If YAML is invalid or missing required fields
        """
        if not yaml_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {yaml_path}")

        # Read YAML file
        yml_version = ut.yml_version(yaml_path)
        db = ut.yml_to_dict(
            yml_path_file=yaml_path,
            version=yml_version,
            required_keys=("general", "config_file_version"),
        )

        # Extract general settings
        general_dict = db["general"]
        general_dict["step_type"] = "general"
        general_flat = flatten_dict(general_dict, sep="/")

        general = StepConfig(
            index=0,
            step_type="general",
            name="general",
            parameters={k: _value_to_string(v) for k, v in general_flat.items()},
            version=float(yml_version),
        )

        # Extract steps
        steps_list = []
        if "steps" in db:
            steps_dict = db["steps"]
            step_order = []

            for step_name, step_data in steps_dict.items():
                step_type = step_data["step_general"]["step_type"]
                step_number = step_data["step_general"]["step_number"]
                step_order.append((step_name, step_type, step_number))

                # Flatten and convert to strings
                flat_step = flatten_dict(step_data, sep="/")
                flat_step["step_general/step_name"] = step_name

                step = StepConfig(
                    index=step_number,
                    step_type=step_type,
                    name=step_name,
                    parameters={k: _value_to_string(v) for k, v in flat_step.items()},
                    version=float(yml_version),
                )
                steps_list.append(step)

            # Sort by step number
            steps_list.sort(key=lambda s: s.index)

        # Create pipeline instance
        pipeline = cls(
            version=float(yml_version),
            general=general,
            steps=steps_list,
            file_path=yaml_path,
        )

        # Ensure step_count in general is accurate
        pipeline._update_step_count()

        return pipeline

    def to_yaml(self, yaml_path: Path):
        """Save pipeline configuration to YAML file.

        Args:
            yaml_path: Path where YAML should be saved
        """
        config_dict = self.to_dict()
        ut.dict_to_yml(config_dict, str(yaml_path))
        self.file_path = yaml_path

    def to_dict(self) -> Dict:
        """Convert pipeline to dictionary suitable for YAML export.

        Applies type conversion based on LUT to ensure parameters have
        correct types (int, float, str, bool) instead of all being strings.

        Returns:
            Dictionary with version, general, and steps
        """
        # Convert general parameters with type checking
        general_params = {}
        for key, value in self.general.parameters.items():
            if key != "step_type":
                general_params[key] = value

        # Apply type conversion based on LUT
        general_params = _apply_type_conversion(general_params, "general", self.version)

        # Remove any parameters not in LUT
        general_lut = lut.get_lut("general", self.version)
        general_lut.flatten()
        general_params = {
            k: v for k, v in general_params.items() if k in general_lut.keys()
        }
        general_params = _apply_type_conversion(general_params, "general", self.version)

        general_dict = unflatten_dict(general_params, sep="/")

        # Convert steps with type checking
        steps_dict = {}
        for step in self.steps:
            step_params = {}
            for key, value in step.parameters.items():
                if key not in ["step_general/step_name", "step_general/step_number"]:
                    step_params[key] = value

            # Add step number
            step_params["step_general/step_number"] = step.index

            # Apply type conversion based on LUT
            step_params = _apply_type_conversion(
                step_params, step.step_type, self.version
            )

            # Remove any parameters not in LUT
            step_lut = lut.get_lut(step.step_type.lower(), self.version)
            step_lut.flatten()
            step_params = {
                k: v
                for k, v in step_params.items()
                if k in step_lut.keys() or k == "step_general/step_number"
            }

            steps_dict[step.name] = unflatten_dict(step_params, sep="/")

        return {
            "config_file_version": self.version,
            "general": general_dict,
            "steps": steps_dict,
        }

    def set_version(self, new_version: float):
        """Update pipeline version and migrate all parameters to new version.

        This method:
        1. Updates version for pipeline and all steps
        2. Adds new parameters introduced in new version (with defaults)
        3. Removes parameters that don't exist in new version
        4. Preserves existing parameter values where applicable

        Args:
            new_version: Target version to migrate to
        """
        if new_version == self.version:
            return  # No change needed

        # Update general step
        self._migrate_step_to_version(self.general, new_version)

        # Update all pipeline steps
        for step in self.steps:
            self._migrate_step_to_version(step, new_version)

        # Update pipeline version
        self.version = new_version

    def _migrate_step_to_version(self, step: StepConfig, new_version: float):
        """Migrate a single step to a new version.

        Args:
            step: Step to migrate
            new_version: Target version
        """
        old_version = step.version
        step_type = step.step_type

        # Get LUTs for old and new versions
        try:
            old_lut = lut.get_lut(step_type.lower(), old_version)
            old_lut.flatten()
        except Exception:
            # If old LUT doesn't exist, use empty dict
            old_lut = lut.LUT()
            old_lut.flatten()

        try:
            new_lut = lut.get_lut(step_type.lower(), new_version)
            new_lut.flatten()
        except Exception:
            # If new LUT doesn't exist, can't migrate
            print(f"Warning: Cannot get LUT for {step_type} version {new_version}")
            step.version = new_version
            return

        # Get current parameters
        current_params = deepcopy(step.parameters)

        # Build new parameter set
        new_params = {}

        # Process all parameters in new LUT
        for param_key, field in new_lut.items():
            if param_key in current_params:
                # Parameter exists in both - keep current value
                new_params[param_key] = current_params[param_key]
            else:
                # New parameter - use default from LUT
                default_value = field.default if field.default is not None else ""
                new_params[param_key] = str(default_value)

        # Note: Parameters that exist in old but not new are automatically dropped
        # by not adding them to new_params

        # Update step with migrated parameters
        step.parameters = new_params
        step.version = new_version

    def __repr__(self) -> str:
        return f"PipelineConfig(version={self.version}, steps={len(self.steps)})"


def _value_to_string(value: Any) -> str:
    """Convert value to string, handling None/null as empty string.

    Special handling:
    - None/null → empty string
    - Booleans → keep as boolean (not converted to string)
    - Everything else → string

    Args:
        value: Value to convert

    Returns:
        String representation (empty string for None, bool for booleans)
    """
    if value is None or value == "null":
        return ""
    # Preserve boolean type for checkbuttons
    if isinstance(value, bool):
        return value
    return str(value)


def flatten_dict(d: Dict, parent_key: str = "", sep: str = "/") -> Dict:
    """Flatten nested dictionary to single level with separator.

    Args:
        d: Dictionary to flatten
        parent_key: Parent key prefix
        sep: Separator for nested keys

    Returns:
        Flattened dictionary

    Example:
        {'a': {'b': 1}} -> {'a/b': 1}
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def unflatten_dict(d: Dict, sep: str = "/") -> Dict:
    """Unflatten dictionary with separators to nested structure.

    Args:
        d: Flattened dictionary
        sep: Separator used in keys

    Returns:
        Nested dictionary

    Example:
        {'a/b': 1} -> {'a': {'b': 1}}
    """
    result = {}
    for key, value in d.items():
        parts = key.split(sep)
        current = result
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value
    return result
