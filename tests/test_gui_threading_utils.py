# tests/test_threading_utils.py
import sys
import time
import threading
from pathlib import Path

import pytest

from pytribeam.GUI.common.threading_utils import (
    StoppableThread,
    ThreadManager,
    TextRedirector,
    generate_escape_keypress,
)

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def short_task():
    def task(x, y):
        return x + y
    return task


@pytest.fixture
def error_task():
    def task():
        raise RuntimeError("boom")
    return task


@pytest.fixture
def sleep_task():
    def task():
        time.sleep(5)
    return task

# ----------------------------------------------------------------------
# StoppableThread
# ----------------------------------------------------------------------
class TestStoppableThread:

    def test_returns_result(self, short_task):
        t = StoppableThread(target=short_task, args=(2, 3))
        t.start()
        t.join()

        assert t.result["value"] == 5
        assert t.result["error"] is None

    def test_captures_exception(self, error_task):
        t = StoppableThread(target=error_task)
        t.start()
        t.join()

        assert isinstance(t.result["error"], RuntimeError)

    def test_get_thread_id_inactive(self, short_task):
        t = StoppableThread(target=short_task, args=(1, 1))
        with pytest.raises(threading.ThreadError):
            t._get_thread_id()

    def test_raise_exception_type_validation(self, short_task):
        t = StoppableThread(target=short_task, args=(1, 1))
        t.start()

        with pytest.raises(TypeError):
            t.raise_exception(RuntimeError("instance not type"))

        t.join()

    def test_raise_exception_calls_pythonapi(self, monkeypatch, short_task):
        t = StoppableThread(target=lambda: time.sleep(0.2))
        t.start()

        called = {}

        def fake_async_exc(tid, exc):
            called["hit"] = True
            return 1

        monkeypatch.setattr(
            "pytribeam.GUI.common.threading_utils.ctypes.pythonapi.PyThreadState_SetAsyncExc",
            fake_async_exc,
        )

        t.raise_exception(KeyboardInterrupt)
        t.join()

        assert called["hit"]


# ----------------------------------------------------------------------
# ThreadManager
# ----------------------------------------------------------------------
class TestThreadManager:

    def test_run_async_and_get_thread(self, short_task):
        tm = ThreadManager()
        t = tm.run_async("worker", short_task, args=(1, 2))

        assert tm.get_thread("worker") is t
        t.join()

    def test_is_running(self, sleep_task):
        tm = ThreadManager()
        t = tm.run_async("sleep", sleep_task)

        assert tm.is_running("sleep") is True
        t.raise_exception(SystemExit)
        t.join()

    def test_wait_for_thread(self, short_task):
        tm = ThreadManager()
        tm.run_async("calc", short_task, args=(3, 4))

        assert tm.wait_for_thread("calc", timeout=1) is True

    def test_wait_for_missing_thread(self):
        tm = ThreadManager()
        assert tm.wait_for_thread("missing") is True

    def test_cleanup_removes_finished(self, short_task):
        tm = ThreadManager()
        t = tm.run_async("done", short_task, args=(1, 1))
        t.join()

        tm.cleanup()
        assert tm.get_thread("done") is None

# ----------------------------------------------------------------------
# Fake widget
# ----------------------------------------------------------------------
class DummyWidget:
    def __init__(self):
        self.content = ""
        self.autoscroll = True

    def after(self, delay, func, text):
        func(text)

    def config(self, **kwargs):
        pass

    def insert(self, pos, text, tag):
        self.content += text

    def yview(self):
        return (0, 1)

    def see(self, pos):
        pass

    def update_idletasks(self):
        pass


# ----------------------------------------------------------------------
# TextRedirector
# ----------------------------------------------------------------------
class TestTextRedirector:

    def test_write_to_widget(self):
        widget = DummyWidget()
        r = TextRedirector(widget)

        r.write("hello")
        assert "hello" in widget.content

    def test_write_to_file(self, tmp_path):
        log = tmp_path / "out.log"
        widget = DummyWidget()
        r = TextRedirector(widget, log_path=str(log))

        r.write("abc")
        assert log.read_text().endswith("abc")

    def test_background_thread_write(self):
        widget = DummyWidget()
        r = TextRedirector(widget)

        def worker():
            r.write("thread")

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert "thread" in widget.content

    def test_file_write_error_ignored(self, monkeypatch, tmp_path):
        widget = DummyWidget()
        log = tmp_path / "out.log"
        r = TextRedirector(widget, log_path=str(log))

        def fail_open(*a, **k):
            raise OSError

        monkeypatch.setattr("builtins.open", fail_open)
        r.write("safe")  # should not crash

# ----------------------------------------------------------------------
# generate_escape_keypress
# ----------------------------------------------------------------------
class TestGenerateEscapeKeypress:

    def test_non_windows_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        with pytest.raises(OSError):
            generate_escape_keypress()
