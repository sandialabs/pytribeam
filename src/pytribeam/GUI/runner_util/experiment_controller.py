"""Experiment execution controller.

This module handles the business logic for running experiments,
separated from the GUI presentation layer.
"""

import time
import datetime
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Dict, Any, Tuple, List

import pytribeam.types as tbt
from pytribeam import workflow, stage, insertable_devices, utilities, factory
from pytribeam.GUI.common import AppConfig, StoppableThread
from pytribeam.GUI.common.threading_utils import generate_escape_keypress


@dataclass
class ExperimentState:
    """Represents the current state of an experiment.

    This is an immutable snapshot of experiment state that can be
    passed to UI callbacks for updates.

    Attributes:
        current_slice: Current slice number being processed
        current_step: Current step name being processed
        total_slices: Total number of slices in experiment
        total_steps: Total number of steps per slice
        is_running: Whether experiment is currently running
        should_stop_step: Flag to stop after current step
        should_stop_slice: Flag to stop after current slice
        should_stop_now: Flag for immediate stop
        progress_percent: Completion percentage (0-100)
        avg_slice_time_str: Average time per slice (formatted)
        remaining_time_str: Estimated remaining time (formatted)
    """

    current_slice: int = 1
    current_step: str = "-"
    total_slices: int = 0
    total_steps: int = 0
    is_running: bool = False
    should_stop_step: bool = False
    should_stop_slice: bool = False
    should_stop_now: bool = False
    progress_percent: int = 0
    avg_slice_time_str: str = "-"
    remaining_time_str: str = "-"


@dataclass
class StageMovePlan:
    """A planned manual stage move to the starting position of a step.

    Created by `ExperimentController.plan_stage_move` so the user can confirm
    the target before `ExperimentController.move_stage_to_step` moves the stage.

    Attributes:
        slice_number: Slice to move to
        step_number: Step to move to (1-based)
        step_name: Name of the step
        current_position: Stage position when the move was planned
        target_position: Starting position of the step for the slice
        step_runs_on_slice: False if the step frequency skips this slice
        experiment_settings: Validated settings, holding the microscope connection
    """

    slice_number: int
    step_number: int
    step_name: str
    current_position: tbt.StagePositionUser
    target_position: tbt.StagePositionUser
    step_runs_on_slice: bool
    experiment_settings: tbt.ExperimentSettings


class ExperimentController:
    """Controls experiment execution without UI dependencies.

    This class handles all experiment logic including validation,
    execution, stopping, and progress tracking. It communicates with
    the UI through callbacks only.

    Attributes:
        config_path: Path to experiment configuration file
        state: Current experiment state
    """

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize experiment controller.

        Args:
            config_path: Path to configuration file (can be set later)
        """
        self.config_path = config_path
        self.state = ExperimentState()
        self._callbacks: Dict[str, Callable] = {}
        self._thread: Optional[StoppableThread] = None
        self._slice_times: List[float] = []
        self.experiment_settings: Optional[tbt.ExperimentSettings] = None
        # True while a manual stage move is being planned, confirmed, or performed
        self.is_moving = False

    def clear_experiment_settings(self):
        """Clear cached experiment settings and release resources.

        This should be called when the configuration file is edited
        to ensure old microscope connections are properly released.
        """
        if self.experiment_settings is not None:
            # Disconnect microscope before clearing
            try:
                if self.experiment_settings.microscope is not None:
                    utilities.disconnect_microscope(
                        self.experiment_settings.microscope, quiet_output=True
                    )
                    # print("Disconnected from microscope")
            except Exception as e:
                if str(e) == "Client is already disconnected.":
                    pass
                else:
                    print(f"Warning: Error disconnecting microscope: {e}")

            # Clear the reference to allow garbage collection
            self.experiment_settings = None

    def set_config_path(self, path: Path):
        """Set or update configuration file path.

        Args:
            path: Path to configuration file
        """
        self.config_path = path

    def register_callback(self, event: str, callback: Callable):
        """Register a callback for state updates.

        Args:
            event: Event name (e.g., 'state_changed', 'validation_failed')
            callback: Function to call when event occurs
        """
        self._callbacks[event] = callback

    def _notify(self, event: str, *args, **kwargs):
        """Trigger registered callback for event.

        Args:
            event: Event name
            *args: Positional arguments for callback
            **kwargs: Keyword arguments for callback
        """
        if event in self._callbacks:
            try:
                self._callbacks[event](*args, **kwargs)
            except Exception as e:
                # Don't let callback errors crash the controller
                print(f"Error in callback '{event}': {e}")

    def validate_config(
        self,
    ) -> Tuple[bool, Optional[tbt.ExperimentSettings], Optional[str]]:
        """Validate the current configuration file.

        Returns:
            Tuple of (is_valid, experiment_settings, error_message)
        """
        if self.config_path is None:
            return False, None, "No configuration file loaded"

        # Clear old experiment settings before creating new ones
        # This ensures old microscope connections are released
        self.clear_experiment_settings()

        try:
            experiment_settings = workflow.setup_experiment(self.config_path)
            # experiment_settings = workflow.pre_flight_check(self.config_path)
            return True, experiment_settings, None
        except Exception as e:
            return False, None, f"Validation failed: {e}"

    def start_experiment(
        self,
        starting_slice: int = 1,
        starting_step: str = None,
    ) -> bool:
        """Start experiment execution.

        Args:
            starting_slice: Slice number to start at
            starting_step: Step name to start at (or None for first step)

        Returns:
            True if experiment started successfully, False otherwise
        """
        if self.state.is_running:
            self._notify("error", "Experiment is already running")
            return False
        if self.is_moving:
            self._notify("error", "A stage move is in progress")
            return False

        # Validate configuration
        is_valid, experiment_settings, error = self.validate_config()
        if not is_valid:
            self._notify("validation_failed", error)
            return False
        self.experiment_settings = experiment_settings

        # Reset stop flags
        self.state = ExperimentState(
            total_slices=experiment_settings.general_settings.max_slice_number,
            total_steps=experiment_settings.general_settings.step_count,
            current_slice=starting_slice,
            is_running=True,
        )

        # Get step information
        step_names = [s.name for s in experiment_settings.step_sequence]
        if starting_step is None:
            starting_step_idx = 0
        else:
            starting_step_idx = step_names.index(starting_step)

        # Check EBSD/EDS detector status and warn user if needed
        self._check_detector_warning(experiment_settings)

        # Notify experiment start
        self._notify(
            "experiment_started", experiment_settings, starting_slice, starting_step_idx
        )

        # Run experiment in background thread (non-blocking)
        self._thread = StoppableThread(
            target=self._run_experiment_loop,
            args=(experiment_settings, starting_slice, starting_step_idx, step_names),
            name="ExperimentThread",
        )
        self._thread.start()

        return True

    def _check_detector_warning(self, experiment_settings: tbt.ExperimentSettings):
        """Check EBSD/EDS detector status and notify UI if warning needed.

        Args:
            experiment_settings: Validated experiment settings
        """
        # Check if EBSD and EDS are enabled
        if not experiment_settings.enable_EBSD or not experiment_settings.enable_EDS:
            if experiment_settings.enable_EBSD:
                message_part1 = "EDS is not enabled"
            elif experiment_settings.enable_EDS:
                message_part1 = "EBSD is not enabled"
            else:
                message_part1 = "EBSD and EDS are not enabled"

            message_part2 = (
                ", you will not have access to safety checking and these modalities "
                "during data collection. Please ensure these detectors are retracted "
                "before proceeding."
            )
            warning_message = message_part1 + message_part2

            # Notify UI to show warning
            self._notify("detector_warning", warning_message)

    def _run_experiment_loop(
        self,
        experiment_settings: tbt.ExperimentSettings,
        starting_slice: int,
        starting_step_idx: int,
        step_names: List[str],
    ):
        """Execute the main experiment loop.

        This method runs the actual experiment, calling workflow steps
        and updating progress.

        Args:
            experiment_settings: Validated experiment settings
            starting_slice: Starting slice number
            starting_step_idx: Starting step index
            step_names: List of step names
        """
        self._slice_times = []
        ending_slice = self.state.total_slices
        num_steps = self.state.total_steps

        try:
            for i in range(starting_slice, ending_slice + 1):
                if self.state.should_stop_now:
                    raise KeyboardInterrupt

                # Track slice start time
                slice_start = time.time()
                count_slice_for_time = True
                self.state.current_slice = i
                self._notify("state_changed", self.state)

                for j in range(num_steps):
                    # Skip steps if starting mid-slice
                    if i == starting_slice and j < starting_step_idx:
                        count_slice_for_time = False
                        continue

                    if self.state.should_stop_now:
                        raise KeyboardInterrupt

                    # Update current step
                    self.state.current_step = step_names[j]
                    self._notify("state_changed", self.state)

                    # Execute step
                    success = self._execute_step(i, j + 1, experiment_settings)

                    if not success or self.state.should_stop_now:
                        self.state.should_stop_now = True
                        break

                    # Update progress
                    self._update_progress(i, j + 1, ending_slice, num_steps)

                    if self.state.should_stop_step:
                        break

                # Check stop conditions
                if (
                    self.state.should_stop_step
                    or self.state.should_stop_slice
                    or self.state.should_stop_now
                ):
                    break

                # Update timing stats
                slice_end = time.time()
                if count_slice_for_time:
                    self._slice_times.append(slice_end - slice_start)
                self._update_timing_stats(i, ending_slice)

        except KeyboardInterrupt:
            self._notify("experiment_interrupted")
        finally:
            self._cleanup_experiment(
                experiment_settings, i, j if "j" in locals() else 0, num_steps
            )

    def _execute_step(
        self,
        slice_number: int,
        step_index: int,
        experiment_settings: tbt.ExperimentSettings,
    ) -> bool:
        """Execute a single workflow step.

        Args:
            slice_number: Current slice number
            step_index: Current step index (1-based)
            experiment_settings: Experiment settings

        Returns:
            True if step succeeded, False if error occurred
        """
        try:
            workflow.perform_step(slice_number, step_index, experiment_settings)
            return True
        except KeyboardInterrupt:
            self._try_stop_stage(experiment_settings.microscope)
            return False
        except Exception as e:
            message = f"Unexpected error in step {step_index} of slice {slice_number}: {e.__class__.__name__}: {e}"
            print(message)
            self._log_error(
                e,
                slice_number,
                step_index,
                exp_dir=experiment_settings.general_settings.exp_dir,
            )
            self._try_stop_stage(experiment_settings.microscope)
            return False

    def _try_stop_stage(self, microscope):
        """Attempt to stop stage movement.

        Args:
            microscope: Microscope object
        """
        try:
            stage.stop(microscope)
            print("-----> Stage stop unsuccessful")
        except SystemError:
            print("-----> Stage stop successful")

    def _log_error(
        self,
        error: Exception,
        slice_number: int,
        step_index: int,
        exp_dir: Optional[Path] = None,
    ):
        """Log error traceback to file.

        The traceback is saved in the experiment's "errors" folder. If that
        can't be written (or no experiment directory is given), it is saved
        in the application log folder instead so it is not lost.

        Args:
            error: Exception that occurred
            slice_number: Slice where error occurred
            step_index: Step where error occurred
            exp_dir: Experiment directory
        """
        app_config = AppConfig.from_env()
        directories = [app_config.log_dir]
        if exp_dir is not None:
            directories.insert(0, Path(exp_dir) / "errors")

        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                err_path = app_config.get_error_log_path(directory)
                with open(err_path, "w") as f:
                    f.write(f"Error in slice {slice_number}, step {step_index}\n")
                    f.write(f"Exception: {type(error).__name__} - {error}\n\n")
                    traceback.print_exc(file=f)
            except OSError as e:
                print(f"Warning: Could not save error details to {directory}: {e}")
                continue
            print(f"Error details saved to: {err_path}")
            return

    def _update_progress(
        self, slice_num: int, step_num: int, total_slices: int, total_steps: int
    ):
        """Update progress percentage.

        Args:
            slice_num: Current slice number
            step_num: Current step number
            total_slices: Total slices
            total_steps: Total steps per slice
        """
        completed_steps = (slice_num - 1) * total_steps + step_num
        total_work = total_slices * total_steps
        self.state.progress_percent = int((completed_steps / total_work) * 100)
        self._notify("state_changed", self.state)

    def _update_timing_stats(self, current_slice: int, total_slices: int):
        """Update timing statistics.

        Args:
            current_slice: Current slice number
            total_slices: Total number of slices
        """
        if not self._slice_times:
            return

        avg_time = sum(self._slice_times) / len(self._slice_times)
        remaining_slices = total_slices - current_slice
        remaining_time = avg_time * remaining_slices

        self.state.avg_slice_time_str = str(datetime.timedelta(seconds=int(avg_time)))
        self.state.remaining_time_str = str(
            datetime.timedelta(seconds=int(remaining_time))
        )
        self._notify("state_changed", self.state)

    def _cleanup_experiment(
        self,
        experiment_settings: tbt.ExperimentSettings,
        final_slice: int,
        final_step: int,
        total_steps: int,
    ):
        """Clean up after experiment completion or stop.

        Args:
            experiment_settings: Experiment settings
            final_slice: Last slice that was processed
            final_step: Last step that was processed
            total_steps: Total steps per slice
        """
        # Retract all devices
        try:
            insertable_devices.retract_all_devices(
                microscope=experiment_settings.microscope,
                enable_EBSD=experiment_settings.enable_EBSD,
                enable_EDS=experiment_settings.enable_EDS,
            )
        except Exception as e:
            print(f"Warning: Failed to retract devices: {e}")

        # Disconnect microscope to release resources
        try:
            if experiment_settings.microscope is not None:
                utilities.disconnect_microscope(
                    experiment_settings.microscope, quiet_output=True
                )
                # print("Disconnected from microscope")
        except Exception as e:
            if str(e) == "Client is already disconnected.":
                pass
            else:
                print(f"Warning: Failed to disconnect microscope: {e}")

        # Get whether or not last step was completed
        is_step_completed = not self.state.should_stop_now

        # Update state
        self.state.is_running = False
        self.state.should_stop_step = False
        self.state.should_stop_slice = False
        self.state.should_stop_now = False

        # Notify completion
        if final_slice == self.state.total_slices and final_step == total_steps - 1:
            self._notify("experiment_completed")
        else:
            # If step is completed, move to next step for resume
            if is_step_completed:
                if final_step + 1 < total_steps:
                    final_step += 1
                else:
                    final_slice += 1
                    final_step = 0
            # Convert to 1-based step name
            final_step_name = experiment_settings.step_sequence[final_step].name
            self._notify("experiment_stopped", final_slice, final_step_name)

    # -------- Manual stage moves -------- #

    def plan_stage_move(self, slice_number: int, step_name: str) -> StoppableThread:
        """Start planning a stage move to the starting position of a step.

        Runs on a background thread that connects to the microscope and
        calculates the target position without moving anything. The thread's
        result is a `StageMovePlan` for the user to confirm, which must then be
        passed to `move_stage_to_step` or `end_stage_move`.

        Args:
            slice_number: Slice to move to
            step_name: Name of the step to move to

        Returns:
            The started thread

        Raises:
            RuntimeError: If an experiment or another stage move is in progress
        """
        if self.state.is_running or self.is_moving:
            raise RuntimeError("An experiment or stage move is already in progress")
        self.is_moving = True
        self._thread = StoppableThread(
            target=self._plan_stage_move,
            args=(slice_number, step_name),
            name="StageMovePlanThread",
        )
        self._thread.start()
        return self._thread

    def _plan_stage_move(self, slice_number: int, step_name: str) -> StageMovePlan:
        """Validate the configuration and calculate the target stage position."""
        if self.config_path is None:
            raise ValueError("No configuration file loaded")

        # Release any old connection before making a new one
        self.clear_experiment_settings()
        experiment_settings = workflow.pre_flight_check(self.config_path)
        try:
            general_settings = experiment_settings.general_settings
            step_names = [s.name for s in experiment_settings.step_sequence]
            if step_name not in step_names:
                raise ValueError(f"Step '{step_name}' is not in the configuration")
            max_slice = general_settings.max_slice_number
            if not 1 <= slice_number <= max_slice:
                raise ValueError(
                    f"Slice {slice_number} is outside the experiment's slices (1 to {max_slice})"
                )

            step_number = step_names.index(step_name) + 1
            operation = experiment_settings.step_sequence[step_number - 1]
            return StageMovePlan(
                slice_number=slice_number,
                step_number=step_number,
                step_name=step_name,
                current_position=factory.active_stage_position_settings(
                    experiment_settings.microscope
                ),
                target_position=stage.target_position(
                    operation.stage,
                    slice_number=slice_number,
                    slice_thickness_um=general_settings.slice_thickness_um,
                ),
                step_runs_on_slice=(slice_number - 1) % operation.frequency == 0,
                experiment_settings=experiment_settings,
            )
        except BaseException:
            self._disconnect(experiment_settings.microscope)
            raise

    def move_stage_to_step(self, plan: StageMovePlan) -> StoppableThread:
        """Start moving the stage to a confirmed plan's target position.

        Runs on a background thread, so `request_stop_now` can halt the stage.
        As in an experiment step, all insertable devices are retracted before
        the stage moves. Call `end_stage_move` once the thread has finished.

        Args:
            plan: Plan from `plan_stage_move`

        Returns:
            The started thread
        """
        self._thread = StoppableThread(
            target=self._move_stage_to_step,
            args=(plan,),
            name="StageMoveThread",
        )
        self._thread.start()
        return self._thread

    def _move_stage_to_step(self, plan: StageMovePlan):
        """Retract devices and move the stage to the step's starting position."""
        settings = plan.experiment_settings
        microscope = settings.microscope
        print(
            f"Moving stage to step '{plan.step_name}' (step {plan.step_number}) of slice {plan.slice_number}"
        )
        try:
            print("\tRetracting all devices...")
            insertable_devices.retract_all_devices(
                microscope=microscope,
                enable_EBSD=settings.enable_EBSD,
                enable_EDS=settings.enable_EDS,
            )
            print("\tDevices retracted.")
            stage.step_start_position(
                microscope=microscope,
                slice_number=plan.slice_number,
                operation=settings.step_sequence[plan.step_number - 1],
                general_settings=settings.general_settings,
            )
        except KeyboardInterrupt:
            self._try_stop_stage(microscope)
            print("-----> Stage move stopped <-----")
            raise
        except Exception as e:
            print(f"Stage move failed: {e.__class__.__name__}: {e}")
            self._log_error(
                e,
                plan.slice_number,
                plan.step_number,
                exp_dir=settings.general_settings.exp_dir,
            )
            self._try_stop_stage(microscope)
            raise
        print("-----> Stage move complete <-----")

    def end_stage_move(self, plan: Optional[StageMovePlan] = None):
        """Finish a stage move: release the microscope connection and allow new moves.

        Call this after the move finishes, fails, or the user declines the plan.

        Args:
            plan: The plan whose connection should be released, if any
        """
        if plan is not None:
            self._disconnect(plan.experiment_settings.microscope)
        self.state.should_stop_now = False
        self.is_moving = False

    def _disconnect(self, microscope):
        """Disconnect from the microscope, ignoring an existing disconnection."""
        try:
            utilities.disconnect_microscope(microscope, quiet_output=True)
        except Exception as e:
            if str(e) != "Client is already disconnected.":
                print(f"Warning: Failed to disconnect microscope: {e}")

    def request_stop_after_step(self):
        """Request experiment stop after current step completes."""
        if not self.state.is_running:
            return

        self.state.should_stop_step = True
        self._notify("stop_requested", "step")
        print("-----> Stopping after current step")

    def request_stop_after_slice(self):
        """Request experiment stop after current slice completes."""
        if not self.state.is_running:
            return

        self.state.should_stop_slice = True
        self._notify("stop_requested", "slice")
        print("-----> Stopping after current slice")

    def request_stop_now(self):
        """Request immediate experiment stop (also halts a manual stage move)."""
        if not self.state.is_running and not self.is_moving:
            return

        self.state.should_stop_now = True
        self._notify("stop_requested", "now")
        if self.state.is_running:
            print("-----> Experiment stopped immediately by user")
        else:
            print("-----> Stage move stopped immediately by user")

        # Try to interrupt hardware
        try:
            generate_escape_keypress()
        except Exception as e:
            print(f"Warning: Failed to send escape keypress: {e}")

        # If there's a running thread, interrupt it
        if self._thread and self._thread.is_alive():
            try:
                count = 0
                while self._thread.is_alive():
                    self._thread.raise_exception(KeyboardInterrupt)
                    time.sleep(0.1)
                    count += 1
                    if count >= 10:
                        break
            except Exception as e:
                print(f"Warning: Failed to interrupt thread: {e}")
