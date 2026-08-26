from pathlib import Path
from types import SimpleNamespace

import pytest

from pytribeam.external_oem.bruker.tools import run_bruker_eds_safe_workflow as tool
from pytribeam.external_oem.bruker.types import (
    BrukerConnectionInfo,
    BrukerDetectorMotionSettings,
    BrukerDetectorPositionState,
    BrukerEDSElementMapSetting,
    BrukerEDSOutputSettings,
    BrukerEDSProfileMapSettings,
    BrukerEDSReadbackSettings,
    BrukerEDSWorkflowResult,
    BrukerEDSWorkflowSettings,
    BrukerSessionSettings,
)


def _settings(tmp_path: Path, *, park_after=True, motion_enabled=True):
    detector = BrukerDetectorMotionSettings(
        detector_index=1,
        target_position="acquire",
        timeout_s=1.0,
        poll_interval_s=0.0,
        verify_park_before=motion_enabled,
        move_to_acquire_before=motion_enabled,
        park_after=park_after if motion_enabled else False,
    )
    return BrukerEDSWorkflowSettings(
        session=BrukerSessionSettings(
            dll_dir=str(tmp_path / "dll"),
            mode="local",
            server="Lokaler Server",
            user="edx",
            password="edx",
            host=None,
            port=None,
            close_on_exit=True,
            keep_connection_open=True,
        ),
        detector=detector,
        map=BrukerEDSProfileMapSettings(
            name="safe_cli_test_map",
            width_px=16,
            height_px=12,
            pixel_time_us=1024,
            output_bcf_path="__pending__",
            output_image_path=None,
            output_image_format=None,
            spu_device=1,
            elements=(BrukerEDSElementMapSetting(atomic_number=14, line="KA"),),
            image_filter=0,
            map_filter=0,
            map_filter_width=3,
            color_mix_method=0,
            brightness=0.0,
            gamma=1.0,
            color_saturation=1.0,
            absolute_scaling=False,
            normalization=True,
            deconvolution=False,
            roi=None,
        ),
        output=BrukerEDSOutputSettings(
            output_dir=str(tmp_path / "out"),
            run_name="safe_cli_test",
        ),
        readback=BrukerEDSReadbackSettings(
            enabled=True,
            save_element_npy=True,
            save_element_tiff=True,
            save_element_images=True,
            log_element_stats=True,
        ),
    )


class FakeSession:
    def __init__(self, settings):
        self.settings = settings
        self.closed = False
        self.connected = False

    def connect(self):
        self.connected = True
        return BrukerConnectionInfo(cid=123, query_info="fake")

    def check_connection(self):
        pass

    def close(self):
        self.closed = True


class FakeMotion:
    final_state = BrukerDetectorPositionState(1, 1, "park")
    raise_on_get = False
    get_calls = 0
    move_calls = 0

    def __init__(self, session):
        self.session = session

    def get_eds_detector_position(self, detector_index):
        type(self).get_calls += 1
        if type(self).raise_on_get:
            raise RuntimeError("position query failed")
        return type(self).final_state._replace(detector_index=detector_index)

    def move_eds_detector(self, settings):
        type(self).move_calls += 1
        return BrukerDetectorPositionState(
            settings.detector_index,
            1,
            "park",
        )


@pytest.fixture(autouse=True)
def _reset_fake_motion():
    FakeMotion.final_state = BrukerDetectorPositionState(1, 1, "park")
    FakeMotion.raise_on_get = False
    FakeMotion.get_calls = 0
    FakeMotion.move_calls = 0


def _install_common_mocks(monkeypatch, tmp_path, settings=None, result=None):
    if settings is None:
        settings = _settings(tmp_path)
    if result is None:
        bcf = tmp_path / "map.bcf"
        bcf.write_bytes(b"x" * 257)
        result = BrukerEDSWorkflowResult(success=True, bcf_path=str(bcf), elapsed_s=1.2)

    calls = []
    sessions = []
    workflow_settings = []

    def fake_load(path):
        calls.append("load")
        return settings

    def fake_validate(session_settings):
        calls.append("runtime")
        return {"dll_dir": session_settings.dll_dir, "esprit_dll": "fake.dll"}

    def fake_session_factory(session_settings):
        calls.append("session")
        session = FakeSession(session_settings)
        sessions.append(session)
        return session

    def fake_run_bruker_eds_workflow(**kwargs):
        calls.append("workflow")
        workflow_settings.append(kwargs["settings"])
        return result

    monkeypatch.setattr(tool, "load_bruker_eds_yaml", fake_load)
    monkeypatch.setattr(tool, "validate_bruker_runtime_environment", fake_validate)
    monkeypatch.setattr(tool, "BrukerSession", fake_session_factory)
    monkeypatch.setattr(tool, "run_bruker_eds_workflow", fake_run_bruker_eds_workflow)
    monkeypatch.setattr(tool, "BrukerDetectorMotionController", FakeMotion)

    return SimpleNamespace(
        calls=calls,
        sessions=sessions,
        workflow_settings=workflow_settings,
        result=result,
        settings=settings,
    )


def test_cli_requires_config():
    with pytest.raises(SystemExit):
        tool.main([])


def test_success_calls_core_apis_disables_readback_and_exits_zero(
    monkeypatch, tmp_path
):
    config = tmp_path / "bruker.yml"
    log_path = tmp_path / "safe.log"
    config.write_text("session: {}\n", encoding="utf-8")
    ctx = _install_common_mocks(monkeypatch, tmp_path)

    exit_code = tool.main(["--config", str(config), "--log-path", str(log_path)])

    assert exit_code == 0
    assert ctx.calls == ["load", "runtime", "session", "workflow"]
    assert ctx.sessions[0].connected is True
    assert ctx.sessions[0].closed is True
    workflow_settings = ctx.workflow_settings[0]
    assert workflow_settings.readback.enabled is False
    assert workflow_settings.readback.save_element_npy is False
    assert workflow_settings.readback.save_element_tiff is False
    assert workflow_settings.readback.save_element_images is False
    assert "Readback disabled by safe workflow CLI policy" in log_path.read_text(
        encoding="utf-8"
    )


def test_success_false_exits_nonzero_and_logs_errors(monkeypatch, tmp_path):
    config = tmp_path / "bruker.yml"
    log_path = tmp_path / "safe.log"
    config.write_text("session: {}\n", encoding="utf-8")
    result = BrukerEDSWorkflowResult(
        success=False,
        bcf_path=str(tmp_path / "missing.bcf"),
        errors=("BCF file missing after acquisition",),
        elapsed_s=2.0,
    )
    _install_common_mocks(monkeypatch, tmp_path, result=result)

    exit_code = tool.main(["--config", str(config), "--log-path", str(log_path)])

    assert exit_code == 1
    text = log_path.read_text(encoding="utf-8")
    assert "success=False" in text
    assert "BCF file missing after acquisition" in text


def test_success_with_missing_bcf_exits_nonzero(monkeypatch, tmp_path):
    config = tmp_path / "bruker.yml"
    log_path = tmp_path / "safe.log"
    config.write_text("session: {}\n", encoding="utf-8")
    result = BrukerEDSWorkflowResult(
        success=True,
        bcf_path=str(tmp_path / "missing.bcf"),
        elapsed_s=1.0,
    )
    _install_common_mocks(monkeypatch, tmp_path, result=result)

    exit_code = tool.main(["--config", str(config), "--log-path", str(log_path)])

    assert exit_code == 1
    assert "BCF file does not exist" in log_path.read_text(encoding="utf-8")


def test_success_with_tiny_bcf_exits_nonzero(monkeypatch, tmp_path):
    config = tmp_path / "bruker.yml"
    log_path = tmp_path / "safe.log"
    bcf = tmp_path / "tiny.bcf"
    config.write_text("session: {}\n", encoding="utf-8")
    bcf.write_bytes(b"x" * 256)
    result = BrukerEDSWorkflowResult(success=True, bcf_path=str(bcf), elapsed_s=1.0)
    _install_common_mocks(monkeypatch, tmp_path, result=result)

    exit_code = tool.main(["--config", str(config), "--log-path", str(log_path)])

    assert exit_code == 1
    assert "unexpectedly small" in log_path.read_text(encoding="utf-8")


def test_exception_logs_traceback_and_exits_nonzero(monkeypatch, tmp_path):
    config = tmp_path / "bruker.yml"
    log_path = tmp_path / "safe.log"
    config.write_text("session: {}\n", encoding="utf-8")

    def fake_load(path):
        raise RuntimeError("load exploded")

    monkeypatch.setattr(tool, "load_bruker_eds_yaml", fake_load)

    exit_code = tool.main(["--config", str(config), "--log-path", str(log_path)])

    assert exit_code == 1
    text = log_path.read_text(encoding="utf-8")
    assert "load exploded" in text
    assert "Traceback follows" in text


def test_workflow_exception_attempts_best_effort_park(monkeypatch, tmp_path):
    config = tmp_path / "bruker.yml"
    log_path = tmp_path / "safe.log"
    config.write_text("session: {}\n", encoding="utf-8")
    ctx = _install_common_mocks(monkeypatch, tmp_path)

    def fake_workflow(**kwargs):
        ctx.calls.append("workflow")
        raise RuntimeError("workflow exploded")

    monkeypatch.setattr(tool, "run_bruker_eds_workflow", fake_workflow)

    exit_code = tool.main(["--config", str(config), "--log-path", str(log_path)])

    assert exit_code == 1
    assert FakeMotion.move_calls == 1
    text = log_path.read_text(encoding="utf-8")
    assert "Attempting best-effort Bruker EDS detector park" in text
    assert "workflow exploded" in text


def test_final_detector_query_failure_exits_nonzero(monkeypatch, tmp_path):
    config = tmp_path / "bruker.yml"
    log_path = tmp_path / "safe.log"
    config.write_text("session: {}\n", encoding="utf-8")
    FakeMotion.raise_on_get = True
    _install_common_mocks(monkeypatch, tmp_path)

    exit_code = tool.main(["--config", str(config), "--log-path", str(log_path)])

    assert exit_code == 1
    assert "final EDS detector position query failed" in log_path.read_text(
        encoding="utf-8"
    )


def test_final_detector_not_parked_exits_nonzero_when_park_requested(
    monkeypatch,
    tmp_path,
):
    config = tmp_path / "bruker.yml"
    log_path = tmp_path / "safe.log"
    config.write_text("session: {}\n", encoding="utf-8")
    FakeMotion.final_state = BrukerDetectorPositionState(1, 2, "acquire")
    _install_common_mocks(monkeypatch, tmp_path)

    exit_code = tool.main(["--config", str(config), "--log-path", str(log_path)])

    assert exit_code == 1
    assert "final EDS detector position is 'acquire'" in log_path.read_text(
        encoding="utf-8"
    )


def test_detector_motion_disabled_skips_final_position_query(monkeypatch, tmp_path):
    config = tmp_path / "bruker.yml"
    log_path = tmp_path / "safe.log"
    config.write_text("session: {}\n", encoding="utf-8")
    settings = _settings(tmp_path, motion_enabled=False)
    _install_common_mocks(monkeypatch, tmp_path, settings=settings)

    exit_code = tool.main(["--config", str(config), "--log-path", str(log_path)])

    assert exit_code == 0
    assert FakeMotion.get_calls == 0
    assert "Detector motion disabled; final detector position check skipped" in (
        log_path.read_text(encoding="utf-8")
    )
