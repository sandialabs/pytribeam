"""Event helpers shared by the controllers.

.NET events fire on WCF/thread-pool threads. Handlers here must never raise back
into .NET (that can tear down the callback channel), so everything is wrapped.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Optional

from .errors import AztecError

log = logging.getLogger(__name__)


def safe(fn: Callable, label: str = "") -> Callable:
    """Wrap an event handler so exceptions are logged, not propagated into .NET."""

    def handler(*args):
        try:
            fn(*args)
        except Exception:  # pragma: no cover - logging path
            log.exception(
                "Unhandled error in %s event handler",
                label or getattr(fn, "__name__", "?"),
            )

    handler.__name__ = "safe_" + getattr(fn, "__name__", "handler")
    return handler


def subscribe(obj, event_name: str, handler: Callable) -> Callable[[], None]:
    """Attach ``handler`` to ``obj.<event_name>``; return a function that detaches it.

    Works for pythonnet event bindings and simulator events alike (both
    implement ``__iadd__`` / ``__isub__``).
    """
    getattr(obj, event_name).__iadd__(handler)

    def unsubscribe():
        try:
            getattr(obj, event_name).__isub__(handler)
        except Exception:  # connection already gone
            log.debug("Failed to unsubscribe from %s", event_name, exc_info=True)

    return unsubscribe


class EventWaiter:
    """Subscribe to an event *before* issuing a command, then wait for a matching firing.

    with EventWaiter(pdc, "ExportFinished") as w:
        pdc.ExportToH5OINA(...)
        args = w.wait(timeout=600)
    """

    def __init__(
        self, obj, event_name: str, predicate: Optional[Callable[[Any], bool]] = None
    ):
        self._obj = obj
        self._name = event_name
        self._predicate = predicate
        self._done = threading.Event()
        self._args = None
        self._unsub = None

    def _on(self, sender, args):
        if self._done.is_set():
            return
        if self._predicate is None or self._predicate(args):
            self._args = args
            self._done.set()

    def __enter__(self):
        self._unsub = subscribe(self._obj, self._name, safe(self._on, self._name))
        return self

    def __exit__(self, *exc):
        if self._unsub:
            self._unsub()
        return False

    def wait(self, timeout: Optional[float]):
        """Return the event args, or raise ``TimeoutError``."""
        if not wait_interruptibly(self._done, timeout):
            raise TimeoutError("No %s event within %s s" % (self._name, timeout))
        return self._args


def wait_interruptibly(
    event: threading.Event, timeout: Optional[float], slice_s: float = 0.5
) -> bool:
    """``event.wait(timeout)`` in short slices, so Ctrl+C is honoured on Windows
    (an untimed lock wait there can't be interrupted)."""
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        remaining = (
            slice_s if deadline is None else min(slice_s, deadline - time.monotonic())
        )
        if remaining <= 0:
            return event.is_set()
        if event.wait(remaining):
            return True


@contextmanager
def translate(api, err_cls, what: str):
    """Re-raise non-oxford_aztec exceptions (e.g. .NET ones) as ``err_cls``."""
    try:
        yield
    except AztecError:
        raise
    except Exception as e:
        raise err_cls("%s failed: %s" % (what, api.message(e))) from e
