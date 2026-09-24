# tests/test_gui_experiment_controller.py
"""Tests for :class:`pytribeam.GUI.runner_util.experiment_controller.ExperimentController`
and :class:`pytribeam.GUI.runner_util.experiment_controller.ExperimentState`.
"""

import datetime
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

from pytribeam.GUI.runner_util.experiment_controller import (
    ExperimentController,
    ExperimentState,
)


# ----------------------------------------------------------------------
# ExperimentState
# ----------------------------------------------------------------------
class TestExperimentState:
    def test_default_values(self):
        s = ExperimentState()
        assert s.current_slice == 1
        assert s.current_step == "-"
        assert s.total_slices == 0
        assert s.total_steps == 0
        assert s.is_running is False
        assert s.should_stop_step is False
        assert s.should_stop_slice is False
        assert s.should_stop_now is False
        assert s.progress_percent == 0
        assert s.avg_slice_time_str == "-"
        assert s.remaining_time_str == "-"

    def test_custom_values(self):
        s = ExperimentState(
            current_slice=5,
            current_step="image_step",
            total_slices=100,
            is_running=True,
        )
        assert s.current_slice == 5
        assert s.current_step == "image_step"
        assert s.total_slices == 100
        assert s.is_running is True

    def test_stop_flags_independent(self):
        s = ExperimentState(should_stop_step=True)
        assert s.should_stop_step is True
        assert s.should_stop_slice is False
        assert s.should_stop_now is False


# ----------------------------------------------------------------------
# Initialization
# ----------------------------------------------------------------------
class TestInit:
    def test_default_init(self):
        ctrl = ExperimentController()
        assert ctrl.config_path is None
        assert ctrl.state.is_running is False
        assert ctrl._thread is None
        assert ctrl.experiment_settings is None

    def test_init_with_config_path(self, tmp_path):
        path = tmp_path / "config.yml"
        ctrl = ExperimentController(config_path=path)
        assert ctrl.config_path == path


# ----------------------------------------------------------------------
# set_config_path
# ----------------------------------------------------------------------
class TestSetConfigPath:
    def test_set_path(self, tmp_path):
        ctrl = ExperimentController()
        path = tmp_path / "new.yml"
        ctrl.set_config_path(path)
        assert ctrl.config_path == path

    def test_overwrite_existing_path(self, tmp_path):
        old = tmp_path / "old.yml"
        new = tmp_path / "new.yml"
        ctrl = ExperimentController(config_path=old)
        ctrl.set_config_path(new)
        assert ctrl.config_path == new


# ----------------------------------------------------------------------
# Callback system
# ----------------------------------------------------------------------
class TestCallbacks:
    def test_register_and_fire(self):
        ctrl = ExperimentController()
        received = {}
        ctrl.register_callback("test", lambda x: received.update({"x": x}))
        ctrl._notify("test", 42)
        assert received["x"] == 42

    def test_unknown_event_does_not_raise(self):
        ctrl = ExperimentController()
        ctrl._notify("unknown_event")  # should not raise

    def test_callback_exception_does_not_propagate(self):
        ctrl = ExperimentController()
        ctrl.register_callback(
            "bad", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        ctrl._notify("bad")  # should not raise

    def test_callback_replaced(self):
        ctrl = ExperimentController()
        results = []
        ctrl.register_callback("ev", lambda: results.append(1))
        ctrl.register_callback("ev", lambda: results.append(2))
        ctrl._notify("ev")
        assert results == [2]

    def test_callback_receives_multiple_args(self):
        ctrl = ExperimentController()
        received = {}
        ctrl.register_callback(
            "multi", lambda *a, **kw: received.update({"a": a, "kw": kw})
        )
        ctrl._notify("multi", 1, 2, k="v")
        assert received["a"] == (1, 2)
        assert received["kw"] == {"k": "v"}


# ----------------------------------------------------------------------
# clear_experiment_settings
# ----------------------------------------------------------------------
class TestClearExperimentSettings:
    def test_clears_when_none(self):
        ctrl = ExperimentController()
        ctrl.clear_experiment_settings()  # should not raise
        assert ctrl.experiment_settings is None

    def test_clears_with_fake_settings_no_microscope(self):
        ctrl = ExperimentController()
        fake_settings = MagicMock()
        fake_settings.microscope = None
        ctrl.experiment_settings = fake_settings
        ctrl.clear_experiment_settings()
        assert ctrl.experiment_settings is None

    def test_clears_and_disconnects_microscope(self, monkeypatch):
        ctrl = ExperimentController()
        fake_settings = MagicMock()
        fake_microscope = MagicMock()
        fake_settings.microscope = fake_microscope

        disconnect_calls = []
        monkeypatch.setattr(
            "pytribeam.GUI.runner_util.experiment_controller.utilities.disconnect_microscope",
            lambda m, **kw: disconnect_calls.append(m),
        )

        ctrl.experiment_settings = fake_settings
        ctrl.clear_experiment_settings()

        assert ctrl.experiment_settings is None
        assert fake_microscope in disconnect_calls

    def test_handles_already_disconnected_error(self, monkeypatch):
        ctrl = ExperimentController()
        fake_settings = MagicMock()
        fake_microscope = MagicMock()
        fake_settings.microscope = fake_microscope

        monkeypatch.setattr(
            "pytribeam.GUI.runner_util.experiment_controller.utilities.disconnect_microscope",
            lambda m, **kw: (_ for _ in ()).throw(
                Exception("Client is already disconnected.")
            ),
        )

        ctrl.experiment_settings = fake_settings
        ctrl.clear_experiment_settings()  # should not raise
        assert ctrl.experiment_settings is None


# ----------------------------------------------------------------------
# validate_config
# ----------------------------------------------------------------------
class TestValidateConfig:
    def test_no_path_returns_failure(self):
        ctrl = ExperimentController()
        ok, settings, err = ctrl.validate_config()
        assert ok is False
        assert settings is None
        assert "No configuration" in err

    def test_success(self, monkeypatch, tmp_path):
        path = tmp_path / "config.yml"
        fake_settings = MagicMock()
        monkeypatch.setattr(
            "pytribeam.GUI.runner_util.experiment_controller.workflow.setup_experiment",
            lambda p: fake_settings,
        )

        ctrl = ExperimentController(config_path=path)
        ok, settings, err = ctrl.validate_config()
        assert ok is True
        assert settings is fake_settings
        assert err is None

    def test_failure_returns_error_message(self, monkeypatch, tmp_path):
        path = tmp_path / "config.yml"
        monkeypatch.setattr(
            "pytribeam.GUI.runner_util.experiment_controller.workflow.setup_experiment",
            lambda p: (_ for _ in ()).throw(ValueError("bad config")),
        )

        ctrl = ExperimentController(config_path=path)
        ok, settings, err = ctrl.validate_config()
        assert ok is False
        assert settings is None
        assert "bad config" in err

    def test_clears_old_settings_before_validation(self, monkeypatch, tmp_path):
        path = tmp_path / "config.yml"
        ctrl = ExperimentController(config_path=path)
        ctrl.experiment_settings = MagicMock()
        ctrl.experiment_settings.microscope = None

        monkeypatch.setattr(
            "pytribeam.GUI.runner_util.experiment_controller.workflow.setup_experiment",
            lambda p: MagicMock(),
        )

        ctrl.validate_config()
        # Old settings reference should have been replaced by validate_config flow
        # (clear is called before, so no crash)


# ----------------------------------------------------------------------
# Stop requests (while not running)
# ----------------------------------------------------------------------
class TestStopRequests:
    def test_request_stop_step_when_not_running(self):
        ctrl = ExperimentController()
        ctrl.request_stop_after_step()  # should be a no-op
        assert ctrl.state.should_stop_step is False

    def test_request_stop_slice_when_not_running(self):
        ctrl = ExperimentController()
        ctrl.request_stop_after_slice()  # should be a no-op
        assert ctrl.state.should_stop_slice is False

    def test_request_stop_now_when_not_running(self):
        ctrl = ExperimentController()
        ctrl.request_stop_now()  # should be a no-op
        assert ctrl.state.should_stop_now is False

    def test_request_stop_step_sets_flag_when_running(self):
        ctrl = ExperimentController()
        ctrl.state.is_running = True
        ctrl.request_stop_after_step()
        assert ctrl.state.should_stop_step is True

    def test_request_stop_slice_sets_flag_when_running(self):
        ctrl = ExperimentController()
        ctrl.state.is_running = True
        ctrl.request_stop_after_slice()
        assert ctrl.state.should_stop_slice is True

    def test_request_stop_step_fires_callback(self):
        ctrl = ExperimentController()
        ctrl.state.is_running = True
        received = {}
        ctrl.register_callback(
            "stop_requested", lambda kind: received.update({"kind": kind})
        )
        ctrl.request_stop_after_step()
        assert received["kind"] == "step"

    def test_request_stop_slice_fires_callback(self):
        ctrl = ExperimentController()
        ctrl.state.is_running = True
        received = {}
        ctrl.register_callback(
            "stop_requested", lambda kind: received.update({"kind": kind})
        )
        ctrl.request_stop_after_slice()
        assert received["kind"] == "slice"

    def test_request_stop_now_sets_flag_and_fires_callback(self, monkeypatch):
        monkeypatch.setattr(
            "pytribeam.GUI.runner_util.experiment_controller.generate_escape_keypress",
            lambda: None,
        )
        ctrl = ExperimentController()
        ctrl.state.is_running = True
        received = {}
        ctrl.register_callback(
            "stop_requested", lambda kind: received.update({"kind": kind})
        )
        ctrl.request_stop_now()
        assert ctrl.state.should_stop_now is True
        assert received["kind"] == "now"


# ----------------------------------------------------------------------
# _update_progress
# ----------------------------------------------------------------------
class TestUpdateProgress:
    def test_progress_calculation(self):
        ctrl = ExperimentController()
        state_updates = []
        ctrl.register_callback(
            "state_changed", lambda s: state_updates.append(s.progress_percent)
        )

        ctrl._update_progress(slice_num=1, step_num=5, total_slices=10, total_steps=10)
        # (1-1)*10 + 5 = 5 / (10*10) * 100 = 5%
        assert ctrl.state.progress_percent == 5
        assert 5 in state_updates

    def test_progress_at_completion(self):
        ctrl = ExperimentController()
        ctrl._update_progress(
            slice_num=10, step_num=10, total_slices=10, total_steps=10
        )
        assert ctrl.state.progress_percent == 100

    def test_progress_first_step(self):
        ctrl = ExperimentController()
        ctrl._update_progress(slice_num=1, step_num=1, total_slices=5, total_steps=4)
        # (1-1)*4 + 1 = 1 / 20 * 100 = 5%
        assert ctrl.state.progress_percent == 5

    def test_state_changed_callback_fired(self):
        ctrl = ExperimentController()
        fired = []
        ctrl.register_callback("state_changed", lambda s: fired.append(True))
        ctrl._update_progress(1, 1, 5, 5)
        assert fired


# ----------------------------------------------------------------------
# _update_timing_stats
# ----------------------------------------------------------------------
class TestUpdateTimingStats:
    def test_no_slice_times_is_no_op(self):
        ctrl = ExperimentController()
        ctrl._slice_times = []
        ctrl._update_timing_stats(1, 10)
        assert ctrl.state.avg_slice_time_str == "-"

    def test_computes_average_and_remaining(self):
        ctrl = ExperimentController()
        ctrl._slice_times = [60.0, 60.0]  # 1 min each

        ctrl._update_timing_stats(current_slice=2, total_slices=5)

        assert ctrl.state.avg_slice_time_str == str(datetime.timedelta(seconds=60))
        # remaining = (5 - 2) * 60 = 180s
        assert ctrl.state.remaining_time_str == str(datetime.timedelta(seconds=180))

    def test_fires_state_changed_callback(self):
        ctrl = ExperimentController()
        ctrl._slice_times = [30.0]
        fired = []
        ctrl.register_callback("state_changed", lambda s: fired.append(True))

        ctrl._update_timing_stats(1, 5)
        assert fired

    def test_zero_remaining_slices(self):
        ctrl = ExperimentController()
        ctrl._slice_times = [120.0]
        ctrl._update_timing_stats(current_slice=5, total_slices=5)
        # remaining_slices = 5 - 5 = 0, so remaining_time = 0
        assert ctrl.state.remaining_time_str == str(datetime.timedelta(seconds=0))


# ----------------------------------------------------------------------
# _check_detector_warning
# ----------------------------------------------------------------------
class TestCheckDetectorWarning:
    def _make_settings(self, enable_ebsd: bool, enable_eds: bool):
        settings = MagicMock()
        settings.enable_EBSD = enable_ebsd
        settings.enable_EDS = enable_eds
        return settings

    def test_no_warning_when_both_enabled(self):
        ctrl = ExperimentController()
        warnings = []
        ctrl.register_callback("detector_warning", lambda m: warnings.append(m))
        ctrl._check_detector_warning(self._make_settings(True, True))
        assert warnings == []

    def test_warning_when_both_disabled(self):
        ctrl = ExperimentController()
        warnings = []
        ctrl.register_callback("detector_warning", lambda m: warnings.append(m))
        ctrl._check_detector_warning(self._make_settings(False, False))
        assert len(warnings) == 1
        assert "EBSD and EDS are not enabled" in warnings[0]

    def test_warning_when_only_ebsd_enabled(self):
        ctrl = ExperimentController()
        warnings = []
        ctrl.register_callback("detector_warning", lambda m: warnings.append(m))
        ctrl._check_detector_warning(self._make_settings(True, False))
        assert len(warnings) == 1
        assert "EDS is not enabled" in warnings[0]

    def test_warning_when_only_eds_enabled(self):
        ctrl = ExperimentController()
        warnings = []
        ctrl.register_callback("detector_warning", lambda m: warnings.append(m))
        ctrl._check_detector_warning(self._make_settings(False, True))
        assert len(warnings) == 1
        assert "EBSD is not enabled" in warnings[0]

    def test_warning_message_contains_safety_text(self):
        ctrl = ExperimentController()
        warnings = []
        ctrl.register_callback("detector_warning", lambda m: warnings.append(m))
        ctrl._check_detector_warning(self._make_settings(False, False))
        assert "retracted" in warnings[0]


# ----------------------------------------------------------------------
# start_experiment (state management, no hardware)
# ----------------------------------------------------------------------
class TestStartExperiment:
    def test_already_running_returns_false(self):
        ctrl = ExperimentController()
        ctrl.state.is_running = True
        result = ctrl.start_experiment()
        assert result is False

    def test_already_running_fires_error_callback(self):
        ctrl = ExperimentController()
        ctrl.state.is_running = True
        errors = []
        ctrl.register_callback("error", lambda m: errors.append(m))
        ctrl.start_experiment()
        assert errors

    def test_invalid_config_fires_validation_failed(self, monkeypatch):
        ctrl = ExperimentController()
        monkeypatch.setattr(
            ctrl, "validate_config", lambda: (False, None, "bad config")
        )
        failures = []
        ctrl.register_callback("validation_failed", lambda m: failures.append(m))
        result = ctrl.start_experiment()
        assert result is False
        assert "bad config" in failures


# ----------------------------------------------------------------------
# _log_error
# ----------------------------------------------------------------------
class TestLogError:
    def test_creates_error_log(self, monkeypatch, tmp_path):
        from pytribeam.GUI.common.config_manager import AppConfig

        fake_cfg = AppConfig(data_dir=tmp_path / "data", log_dir=tmp_path / "logs")

        monkeypatch.setattr(
            "pytribeam.GUI.runner_util.experiment_controller.AppConfig.from_env",
            lambda: fake_cfg,
        )

        ctrl = ExperimentController()
        ctrl._log_error(ValueError("test error"), slice_number=2, step_index=3)

        log_files = list((tmp_path / "logs").glob("*.txt"))
        assert len(log_files) == 1
        content = log_files[0].read_text()
        assert "slice 2" in content
        assert "step 3" in content
        assert "ValueError" in content

    @pytest.fixture
    def fake_app_config(self, monkeypatch, tmp_path):
        from pytribeam.GUI.common.config_manager import AppConfig

        fake_cfg = AppConfig(data_dir=tmp_path / "data", log_dir=tmp_path / "logs")
        monkeypatch.setattr(
            "pytribeam.GUI.runner_util.experiment_controller.AppConfig.from_env",
            lambda: fake_cfg,
        )
        return fake_cfg

    def test_saves_to_experiment_errors_folder(self, fake_app_config, tmp_path):
        exp_dir = tmp_path / "experiment"
        ctrl = ExperimentController()
        ctrl._log_error(ValueError("test error"), 2, 3, exp_dir=exp_dir)

        log_files = list((exp_dir / "errors").glob("*_error_traceback.txt"))
        assert len(log_files) == 1
        assert "ValueError" in log_files[0].read_text()
        assert not fake_app_config.log_dir.exists()

    def test_falls_back_to_app_log_dir(self, fake_app_config, tmp_path):
        # A file where the experiment directory should be makes "errors" unwritable
        exp_dir = tmp_path / "experiment"
        exp_dir.write_text("not a directory")
        ctrl = ExperimentController()
        ctrl._log_error(ValueError("test error"), 2, 3, exp_dir=exp_dir)

        log_files = list(fake_app_config.log_dir.glob("*_error_traceback.txt"))
        assert len(log_files) == 1
        assert "ValueError" in log_files[0].read_text()

    def test_execute_step_saves_traceback_in_experiment(
        self, fake_app_config, monkeypatch, tmp_path
    ):
        def failing_step(slice_number, step_index, settings):
            raise RuntimeError("step failed")

        monkeypatch.setattr(
            "pytribeam.GUI.runner_util.experiment_controller.workflow.perform_step",
            failing_step,
        )
        monkeypatch.setattr(
            "pytribeam.GUI.runner_util.experiment_controller.stage.stop",
            lambda m: None,
        )
        settings = MagicMock()
        settings.general_settings.exp_dir = tmp_path / "experiment"

        ctrl = ExperimentController()
        assert ctrl._execute_step(4, 1, settings) is False

        log_files = list((tmp_path / "experiment" / "errors").glob("*.txt"))
        assert len(log_files) == 1
        content = log_files[0].read_text()
        assert "slice 4, step 1" in content
        assert "RuntimeError: step failed" in content


# ----------------------------------------------------------------------
# Manual stage moves
# ----------------------------------------------------------------------
MODULE = "pytribeam.GUI.runner_util.experiment_controller"


class TestStageMove:
    @pytest.fixture
    def settings(self, tmp_path):
        settings = MagicMock()
        laser_step, image_step = MagicMock(), MagicMock()
        laser_step.name, laser_step.frequency = "laser", 1
        image_step.name, image_step.frequency = "image_bse", 2
        settings.step_sequence = [laser_step, image_step]
        settings.general_settings.max_slice_number = 200
        settings.general_settings.slice_thickness_um = 1.5
        settings.general_settings.exp_dir = tmp_path / "experiment"
        return settings

    @pytest.fixture
    def scope(self, monkeypatch, settings):
        """Patch hardware calls, recording them in order."""
        calls = []
        monkeypatch.setattr(f"{MODULE}.workflow.pre_flight_check", lambda p: settings)
        monkeypatch.setattr(
            f"{MODULE}.factory.active_stage_position_settings", lambda m: "current"
        )

        def target_position(stage_settings, slice_number, slice_thickness_um):
            calls.append(("target", stage_settings, slice_number, slice_thickness_um))
            return "target"

        monkeypatch.setattr(f"{MODULE}.stage.target_position", target_position)
        monkeypatch.setattr(
            f"{MODULE}.utilities.disconnect_microscope",
            lambda m, quiet_output=False: calls.append(("disconnect", m)),
        )
        monkeypatch.setattr(
            f"{MODULE}.insertable_devices.retract_all_devices",
            lambda **kw: calls.append(("retract", kw)),
        )
        monkeypatch.setattr(
            f"{MODULE}.stage.step_start_position",
            lambda **kw: calls.append(("move", kw)),
        )
        monkeypatch.setattr(
            f"{MODULE}.stage.stop", lambda m: calls.append(("stop", m))
        )
        return calls

    @pytest.fixture
    def ctrl(self, tmp_path):
        ctrl = ExperimentController(config_path=tmp_path / "config.yml")
        yield ctrl
        if ctrl._thread is not None:
            ctrl._thread.join(timeout=5)

    def _plan(self, ctrl, slice_number, step_name):
        thread = ctrl.plan_stage_move(slice_number, step_name)
        thread.join(timeout=5)
        return thread.result

    def test_plan_calculates_target(self, ctrl, scope, settings):
        result = self._plan(ctrl, 100, "image_bse")
        assert result["error"] is None
        plan = result["value"]
        assert (plan.slice_number, plan.step_number, plan.step_name) == (
            100,
            2,
            "image_bse",
        )
        assert plan.current_position == "current"
        assert plan.target_position == "target"
        assert plan.experiment_settings is settings
        assert scope == [("target", settings.step_sequence[1].stage, 100, 1.5)]
        assert ctrl.is_moving is True

    @pytest.mark.parametrize("slice_number, runs", [(1, True), (100, False), (101, True)])
    def test_plan_notes_step_frequency(self, ctrl, scope, slice_number, runs):
        plan = self._plan(ctrl, slice_number, "image_bse")["value"]
        assert plan.step_runs_on_slice is runs

    @pytest.mark.parametrize(
        "slice_number, step_name", [(0, "laser"), (201, "laser"), (5, "missing")]
    )
    def test_plan_rejects_bad_choice_and_disconnects(
        self, ctrl, scope, settings, slice_number, step_name
    ):
        result = self._plan(ctrl, slice_number, step_name)
        assert isinstance(result["error"], ValueError)
        assert ("disconnect", settings.microscope) in scope

    def test_plan_refused_while_running_or_moving(self, ctrl, scope):
        ctrl.state.is_running = True
        with pytest.raises(RuntimeError):
            ctrl.plan_stage_move(1, "laser")
        ctrl.state.is_running = False
        ctrl.is_moving = True
        with pytest.raises(RuntimeError):
            ctrl.plan_stage_move(1, "laser")

    def test_move_retracts_then_moves(self, ctrl, scope, settings):
        plan = self._plan(ctrl, 100, "image_bse")["value"]
        scope.clear()
        thread = ctrl.move_stage_to_step(plan)
        thread.join(timeout=5)
        assert thread.result["error"] is None
        assert [c[0] for c in scope] == ["retract", "move"]
        assert scope[0][1]["microscope"] is settings.microscope
        move_kwargs = scope[1][1]
        assert move_kwargs["slice_number"] == 100
        assert move_kwargs["operation"] is settings.step_sequence[1]
        assert move_kwargs["general_settings"] is settings.general_settings

    def test_move_failure_logs_error_and_stops_stage(
        self, ctrl, scope, settings, monkeypatch, tmp_path
    ):
        def failing_move(**kw):
            raise ValueError("Destination position is unsafe")

        monkeypatch.setattr(f"{MODULE}.stage.step_start_position", failing_move)
        plan = self._plan(ctrl, 3, "laser")["value"]
        thread = ctrl.move_stage_to_step(plan)
        thread.join(timeout=5)
        assert isinstance(thread.result["error"], ValueError)
        assert ("stop", settings.microscope) in scope
        log_files = list((tmp_path / "experiment" / "errors").glob("*.txt"))
        assert len(log_files) == 1
        assert "unsafe" in log_files[0].read_text()

    def test_end_stage_move_disconnects_and_allows_new_moves(
        self, ctrl, scope, settings
    ):
        plan = self._plan(ctrl, 1, "laser")["value"]
        ctrl.end_stage_move(plan)
        assert ("disconnect", settings.microscope) in scope
        assert ctrl.is_moving is False
        ctrl.plan_stage_move(1, "laser").join(timeout=5)  # allowed again

    def test_start_experiment_blocked_while_moving(self, ctrl):
        ctrl.is_moving = True
        errors = []
        ctrl.register_callback("error", errors.append)
        assert ctrl.start_experiment() is False
        assert errors

    def test_hard_stop_interrupts_move(self, ctrl, scope, settings, monkeypatch):
        started = []

        def slow_move(**kw):
            started.append(True)
            for _ in range(200):
                time.sleep(0.01)

        monkeypatch.setattr(f"{MODULE}.stage.step_start_position", slow_move)
        plan = self._plan(ctrl, 1, "laser")["value"]
        thread = ctrl.move_stage_to_step(plan)
        while not started:
            time.sleep(0.01)
        ctrl.request_stop_now()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert thread.result["stopped"] is True
        assert ("stop", settings.microscope) in scope
        ctrl.end_stage_move(plan)
        assert ctrl.state.should_stop_now is False


# ----------------------------------------------------------------------
# _try_stop_stage
# ----------------------------------------------------------------------
class TestTryStopStage:
    def test_stops_stage_without_crash(self, monkeypatch):
        # stage.stop raises SystemError on successful stop (by design in the code)
        monkeypatch.setattr(
            "pytribeam.GUI.runner_util.experiment_controller.stage.stop",
            lambda m: (_ for _ in ()).throw(SystemError("stopped")),
        )
        ctrl = ExperimentController()
        ctrl._try_stop_stage(MagicMock())  # should not raise

    def test_handles_stop_failure(self, monkeypatch):
        monkeypatch.setattr(
            "pytribeam.GUI.runner_util.experiment_controller.stage.stop",
            lambda m: None,
        )
        ctrl = ExperimentController()
        ctrl._try_stop_stage(MagicMock())  # should not raise
