"""Configuration validation.

This module provides validation logic for pipeline configurations,
separating validation concerns from UI concerns.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple, Union

import pytribeam.factory as factory
import pytribeam.types as tbt
import pytribeam.utilities as ut
from pytribeam.GUI.common.errors import ValidationError
from pytribeam.GUI.config_ui.pipeline_model import PipelineConfig


@dataclass
class ValidationResult:
    """Result of a validation check.

    Attributes:
        success: Whether validation passed
        step_name: Name of step validated
        message: Detailed message (usually for failures)
        exception: Original exception if validation failed
        settings: Validated settings object (if applicable)
    """

    success: bool
    step_name: str
    message: str = ""
    exception: Optional[Exception] = None
    settings: Union[
        tbt.CustomSettings,
        tbt.EBSDSettings,
        tbt.EDSSettings,
        tbt.ImageSettings,
        tbt.FIBSettings,
        tbt.LaserSettings,
    ] = None

    def __str__(self) -> str:
        """Get human-readable string representation."""
        status = "passed" if self.success else "failed"
        msg = f": {self.message}" if self.message else ""
        return f"{self.step_name} - {status}{msg}"

    def __bool__(self) -> bool:
        """Allow using result in boolean context."""
        return self.success


class ConfigValidator:
    """Validates pipeline configurations against schema.

    This class handles validation of configuration files, checking that
    all required fields are present and values are valid according to
    the pytribeam schema.
    """

    def __init__(self):
        """Initialize validator."""
        self._yml_format = ut.yml_format(version=1.0)

    def set_version(self, version: float):
        """Set configuration version for validation.

        Args:
            version: Configuration version number
        """
        self._yml_format = ut.yml_format(version=version)

    def validate_general(self, config_dict: Dict) -> ValidationResult:
        """Validate general configuration section.

        Args:
            config_dict: Dictionary containing at least 'general' key

        Returns:
            ValidationResult indicating success or failure
        """
        try:
            general_set = factory.general(
                config_dict,
                yml_format=self._yml_format,
            )
            return ValidationResult(
                success=True,
                step_name="general",
                settings=general_set,
            )
        except KeyError as e:
            return ValidationResult(
                success=False,
                step_name="general",
                message=f"Missing required field: {e}",
                exception=e,
            )
        except Exception as e:
            return ValidationResult(
                success=False,
                step_name="general",
                message=f"{type(e).__name__}: {str(e)}",
                exception=e,
            )

    def validate_step(
        self,
        microscope: tbt.Microscope,
        step_name: str,
        step_config: Dict,
        general_settings,
    ) -> ValidationResult:
        """Validate a single pipeline step.

        Args:
            microscope: Connected microscope object
            step_name: Name of step being validated
            step_config: Step configuration dictionary
            general_settings: Validated general settings

        Returns:
            ValidationResult indicating success or failure
        """
        try:
            step_settings = factory.step(
                microscope,
                step_name=step_name,
                step_settings=step_config,
                general_settings=general_settings,
                yml_format=self._yml_format,
            )
            return ValidationResult(
                success=True, step_name=step_name, settings=step_settings
            )
        except KeyError as e:
            return ValidationResult(
                success=False,
                step_name=step_name,
                message=f"Missing required field: {e}",
                exception=e,
            )
        except Exception as e:
            return ValidationResult(
                success=False,
                step_name=step_name,
                message=f"{type(e).__name__}: {str(e)}",
                exception=e,
            )

    def validate_full_pipeline(
        self,
        config_dict: Dict,
        microscope: Optional[tbt.Microscope] = None,
    ) -> List[ValidationResult]:
        """Validate complete pipeline configuration.

        Args:
            config_dict: Complete configuration dictionary
            microscope: Optional connected microscope (created if not provided)

        Returns:
            List of ValidationResult objects, one per validated component
        """
        results = []

        # Validate general first
        general_db = config_dict.get("general", {})
        general_result = self.validate_general(general_db)
        results.append(general_result)

        if not general_result.success:
            return results

        # If no steps, we're done
        if "steps" not in config_dict or not config_dict["steps"]:
            return results

        # Get general settings for step validation
        try:
            general_set = factory.general(
                config_dict["general"],
                yml_format=self._yml_format,
            )
        except Exception as e:
            # This shouldn't happen since we validated above
            results.append(
                ValidationResult(
                    success=False,
                    step_name="General (re-validation)",
                    message=f"Failed to re-load general settings: {e}",
                    exception=e,
                )
            )
            return results

        # Create or use provided microscope connection
        should_disconnect = False
        if microscope is None:
            try:
                microscope = tbt.Microscope()
                ut.connect_microscope(
                    microscope,
                    quiet_output=True,
                    connection_host=general_set.connection.host,
                    connection_port=general_set.connection.port,
                )
                should_disconnect = True
            except Exception as e:
                results.append(
                    ValidationResult(
                        success=False,
                        step_name="Microscope Connection",
                        message=f"Failed to connect: {e}",
                        exception=e,
                    )
                )
                return results

        # Validate each step
        try:
            for step_name, step_config in config_dict["steps"].items():
                result = self.validate_step(
                    microscope,
                    step_name,
                    step_config,
                    general_set,
                )
                results.append(result)
        finally:
            # Clean up microscope connection if we created it
            if should_disconnect and microscope:
                try:
                    ut.disconnect_microscope(microscope)
                except Exception:
                    pass  # Ignore disconnection errors

        return results

    def validate_pipeline_model(
        self,
        pipeline: PipelineConfig,
    ) -> List[ValidationResult]:
        """Validate a PipelineConfig model.

        Convenience method that converts model to dictionary and validates.

        Args:
            pipeline: PipelineConfig to validate
            microscope: Optional connected microscope

        Returns:
            List of ValidationResult objects
        """
        config_dict = pipeline.to_dict()
        return self.validate_full_pipeline(config_dict)

    def check_duplicate_names(self, pipeline: PipelineConfig) -> ValidationResult:
        """Check for duplicate step names.

        Args:
            pipeline: PipelineConfig to check

        Returns:
            ValidationResult indicating if names are unique
        """
        is_valid, duplicates = pipeline.validate_step_names()

        if is_valid:
            return ValidationResult(
                success=True,
                step_name="Step Names",
            )
        else:
            dup_list = ", ".join(duplicates)
            return ValidationResult(
                success=False,
                step_name="Step Names",
                message=f"Duplicate names found: {dup_list}",
            )

    def check_has_steps(self, pipeline: PipelineConfig) -> ValidationResult:
        """Check that pipeline has at least one step.

        Args:
            pipeline: PipelineConfig to check

        Returns:
            ValidationResult indicating if pipeline has steps
        """
        if pipeline.get_step_count() > 0:
            return ValidationResult(
                success=True,
                step_name="Step Count",
            )
        else:
            return ValidationResult(
                success=False,
                step_name="Step Count",
                message="Pipeline must have at least one step",
            )

    def validate_pipeline_structure(
        self,
        pipeline: PipelineConfig,
    ) -> List[ValidationResult]:
        """Validate pipeline structure without schema validation.

        Checks basic requirements like unique names and presence of steps.
        This is faster than full validation and doesn't require microscope connection.

        Args:
            pipeline: PipelineConfig to validate

        Returns:
            List of ValidationResult objects
        """
        results = []

        # Check step count
        results.append(self.check_has_steps(pipeline))

        # Check duplicate names
        results.append(self.check_duplicate_names(pipeline))

        return results

    @staticmethod
    def get_summary(results: List[ValidationResult]) -> Tuple[bool, str]:
        """Get summary of validation results.

        Args:
            results: List of ValidationResult objects

        Returns:
            Tuple of (all_passed, summary_message)
        """
        all_passed = all(r.success for r in results)
        lines = [str(r) for r in results]
        summary = "\n".join(lines)

        if all_passed:
            summary = f"✓ All checks passed\n\n{summary}"
        else:
            failed_count = sum(1 for r in results if not r.success)
            summary = f"✗ {failed_count} check(s) failed\n\n{summary}"

        return all_passed, summary
