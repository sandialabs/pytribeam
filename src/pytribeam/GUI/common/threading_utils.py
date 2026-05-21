"""Thread management utilities for GUI operations.

This module provides thread management capabilities including stoppable threads
and Windows-specific keyboard event generation for emergency stops.
"""

import ctypes
import inspect
import threading
import time
from collections import namedtuple
from ctypes import wintypes
from typing import Any, Callable, Dict, Optional, Tuple


class StoppableThread(threading.Thread):
    """Thread that can be stopped via exception injection.

    This thread wrapper allows raising exceptions in a running thread,
    which is useful for implementing emergency stops in long-running operations.

    Attributes:
        result: Dictionary containing 'value' and 'error' from thread execution
    """

    def __init__(
        self,
        target: Callable,
        args: Tuple = (),
        kwargs: Optional[dict] = None,
        name: Optional[str] = None,
    ):
        """Initialize stoppable thread.

        Args:
            target: Function to run in thread
            args: Positional arguments for target function
            kwargs: Keyword arguments for target function
            name: Optional thread name for debugging
        """
        self._user_target = target
        self._result: Dict[str, Any] = {"value": None, "error": None}
        self._thread_id: Optional[int] = None

        super().__init__(
            target=self._wrapped_target,
            args=args,
            kwargs=kwargs or {},
            name=name,
        )

        self.daemon = False

    def _wrapped_target(self, *args, **kwargs):
        """Wrap target to capture result/errors."""
        try:
            result = self._user_target(*args, **kwargs)
            self._result["value"] = result
            return result
        except Exception as e:
            self._result["error"] = e
            raise

    @property
    def result(self) -> Dict[str, Any]:
        """Get result dictionary containing 'value' and 'error'."""
        return self._result

    def _get_thread_id(self) -> int:
        """Get thread ID for exception raising.

        Returns:
            Thread ID

        Raises:
            threading.ThreadError: If thread is not active
            AssertionError: If thread ID cannot be determined
        """
        if not self.is_alive():
            raise threading.ThreadError("the thread is not active")

        if self._thread_id is not None:
            return self._thread_id

        # Look for thread in _active dict
        for tid, tobj in threading._active.items():
            if tobj is self:
                self._thread_id = tid
                return tid

        raise AssertionError("could not determine the thread's id")

    def raise_exception(self, exc_type: type):
        """Raise exception in the context of this thread.

        Note: If thread is in a system call, exception may be ignored.
        For critical stops, repeatedly call this method until thread exits.

        Args:
            exc_type: Exception type to raise (e.g., KeyboardInterrupt)

        Raises:
            TypeError: If exc_type is not a type
            ValueError: If thread ID is invalid
            SystemError: If exception raising fails
        """
        if not inspect.isclass(exc_type):
            raise TypeError("Only types can be raised (not instances)")

        tid = self._get_thread_id()
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_long(tid), ctypes.py_object(exc_type)
        )

        if res == 0:
            raise ValueError("invalid thread id")
        elif res != 1:
            # Revert the effect if multiple threads were affected
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), None)
            raise SystemError("PyThreadState_SetAsyncExc failed")


class ThreadManager:
    """Manages lifecycle of multiple threads.

    Provides centralized thread management with named thread tracking
    and emergency stop capabilities.
    """

    def __init__(self):
        """Initialize thread manager."""
        self._threads: Dict[str, StoppableThread] = {}

    def run_async(
        self,
        name: str,
        target: Callable,
        args: Tuple = (),
        kwargs: Optional[dict] = None,
    ) -> StoppableThread:
        """Run function in managed thread.

        Args:
            name: Unique name for this thread
            target: Function to run
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Started StoppableThread instance
        """
        thread = StoppableThread(target=target, args=args, kwargs=kwargs, name=name)
        self._threads[name] = thread
        thread.start()
        return thread

    def get_thread(self, name: str) -> Optional[StoppableThread]:
        """Get thread by name.

        Args:
            name: Thread name

        Returns:
            Thread instance or None if not found
        """
        return self._threads.get(name)

    def is_running(self, name: str) -> bool:
        """Check if named thread is still running.

        Args:
            name: Thread name

        Returns:
            True if thread exists and is alive
        """
        thread = self._threads.get(name)
        return thread is not None and thread.is_alive()

    def stop_thread(self, name: str, exc_type: type = KeyboardInterrupt):
        """Stop specific thread by raising exception.

        Args:
            name: Thread name
            exc_type: Exception type to raise
        """
        thread = self._threads.get(name)
        if thread and thread.is_alive():
            thread.raise_exception(exc_type)

    def stop_all(self, exc_type: type = KeyboardInterrupt):
        """Stop all managed threads.

        Args:
            exc_type: Exception type to raise in all threads
        """
        for thread in self._threads.values():
            if thread.is_alive():
                try:
                    thread.raise_exception(exc_type)
                except (ValueError, SystemError):
                    # Thread may have already stopped
                    pass

    def wait_for_thread(self, name: str, timeout: Optional[float] = None) -> bool:
        """Wait for specific thread to complete.

        Args:
            name: Thread name
            timeout: Maximum time to wait in seconds

        Returns:
            True if thread completed, False if timeout occurred
        """
        thread = self._threads.get(name)
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def cleanup(self):
        """Clean up stopped threads from tracking."""
        self._threads = {
            name: thread for name, thread in self._threads.items() if thread.is_alive()
        }


class TextRedirector:
    """Redirect stdout/stderr to a Tkinter Text widget.

    This allows capturing print statements and displaying them in the GUI
    while optionally logging to a file. Thread-safe for use with background threads.
    """

    def __init__(self, widget, tag: str = "stdout", log_path: Optional[str] = None):
        """Initialize text redirector.

        Args:
            widget: Tkinter Text widget to write to
            tag: Tag for text styling (e.g., 'stdout', 'stderr')
            log_path: Optional file path to also log output
        """
        self.widget = widget
        self.tag = tag
        self.log_path = log_path
        self._main_thread_id = threading.current_thread().ident

        if self.log_path is not None:
            import os

            if not os.path.exists(self.log_path):
                os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
                with open(self.log_path, "w") as f:
                    f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")

    def write(self, text: str):
        """Write text to widget and optional log file.

        Args:
            text: Text to write
        """
        import tkinter as tk

        # Write to log file FIRST to ensure it always happens
        # even if widget access fails
        if self.log_path is not None:
            try:
                with open(self.log_path, "a") as f:
                    f.write(text)
            except Exception:
                # Ignore file write errors to avoid breaking stdout
                pass

        # Write to widget using thread-safe approach
        # If we're on the main thread, write directly
        # If we're on a background thread, schedule on main thread
        if threading.current_thread().ident == self._main_thread_id:
            self._write_to_widget(text)
        else:
            # Schedule widget update on main thread using after()
            try:
                self.widget.after(0, self._write_to_widget, text)
            except Exception:
                # If after() fails (widget destroyed), fall back to direct write
                self._write_to_widget(text)

    def _write_to_widget(self, text: str):
        """Internal method to write text to widget.

        Args:
            text: Text to write
        """
        import tkinter as tk

        # Protect ALL widget access in try/except
        try:
            # Check if we should autoscroll
            autoscroll = getattr(self.widget, "autoscroll", True)
            if autoscroll:
                bottom = self.widget.yview()[1]

            # Write to widget
            self.widget.config(state=tk.NORMAL)
            self.widget.insert(tk.END, text, (self.tag,))
            self.widget.config(state=tk.DISABLED)

            # Autoscroll if at bottom
            if autoscroll and bottom == 1:
                self.widget.see(tk.END)

            # Force GUI update to show text immediately
            self.widget.update_idletasks()
        except tk.TclError:
            # Widget may have been destroyed or is not accessible
            # This can happen when writing from a background thread
            pass
        except Exception:
            # Catch any other widget-related errors to prevent
            # breaking stdout/stderr redirection
            pass

    def flush(self):
        """Flush output (required for file-like interface)."""
        pass


def generate_escape_keypress():
    """Generate escape keypress for Windows microscope control.

    This function finds the microscope control window and sends escape
    and F6 key presses to stop ongoing operations.

    Note: This is Windows-specific and uses ctypes to interact with Win32 API.

    Raises:
        OSError: If on non-Windows platform
    """
    import sys

    if sys.platform != "win32":
        raise OSError("generate_escape_keypress only works on Windows")

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    # Window enumeration setup
    def check_zero(result, func, args):
        if not result:
            err = ctypes.get_last_error()
            if err:
                raise ctypes.WinError(err)
        return args

    if not hasattr(wintypes, "LPDWORD"):
        wintypes.LPDWORD = ctypes.POINTER(wintypes.DWORD)

    WindowInfo = namedtuple("WindowInfo", "pid title")

    WNDENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HWND,
        wintypes.LPARAM,
    )

    user32.EnumWindows.errcheck = check_zero
    user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, wintypes.LPDWORD)
    user32.GetWindowTextLengthW.errcheck = check_zero
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextW.errcheck = check_zero
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)

    # Enumerate windows
    result = []

    @WNDENUMPROC
    def enum_proc(hWnd, lParam):
        if user32.IsWindowVisible(hWnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hWnd, ctypes.byref(pid))
            length = user32.GetWindowTextLengthW(hWnd) + 1
            title = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hWnd, title, length)
            result.append(WindowInfo(pid.value, title.value))
        return True

    user32.EnumWindows(enum_proc, 0)

    # Input simulation setup
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    MAPVK_VK_TO_VSC = 0

    wintypes.ULONG_PTR = wintypes.WPARAM

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = (
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", wintypes.ULONG_PTR),
        )

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = (
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", wintypes.ULONG_PTR),
        )

        def __init__(self, *args, **kwds):
            super(KEYBDINPUT, self).__init__(*args, **kwds)
            if not self.dwFlags & KEYEVENTF_UNICODE:
                self.wScan = user32.MapVirtualKeyExW(self.wVk, MAPVK_VK_TO_VSC, 0)

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = (
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        )

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = (("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT))

        _anonymous_ = ("_input",)
        _fields_ = (("type", wintypes.DWORD), ("_input", _INPUT))

    LPINPUT = ctypes.POINTER(INPUT)

    def _check_count(result, func, args):
        if result == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        return args

    user32.SendInput.errcheck = _check_count
    user32.SendInput.argtypes = (wintypes.UINT, LPINPUT, ctypes.c_int)

    def press_key(hex_key_code):
        """Press a key."""
        x = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=hex_key_code))
        user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))

    def release_key(hex_key_code):
        """Release a key."""
        x = INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(wVk=hex_key_code, dwFlags=KEYEVENTF_KEYUP),
        )
        user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))

    # Find and activate microscope window
    VK_ESC = 0x1B
    VK_F6 = 0x75
    VKs = [VK_ESC, VK_F6, VK_F6]

    for window_info in result:
        if "Microscope Control" in window_info.title:
            window = user32.FindWindowW(None, window_info.title)
            if window:
                user32.ShowWindow(window, 9)  # SW_RESTORE
                user32.SetForegroundWindow(window)
                for vk in VKs:
                    press_key(vk)
                    time.sleep(0.05)
                    release_key(vk)
                break
