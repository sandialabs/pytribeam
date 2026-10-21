#!/usr/bin/python3
"""
Capability Helpers
==================

Small pieces shared by the capability modules.

* :func:`agent_errors` turns the exceptions pytribeam raises for bad input or
  a refused operation into ``ToolError``, so their messages reach the agent.
* :func:`collect_warnings` records the ``warnings.warn`` messages pytribeam
  uses to report useful information, so a tool can return them.
"""

from __future__ import annotations

import contextlib
import warnings
from typing import Iterator, List

from mcp.server.mcpserver.exceptions import ToolError

# pytribeam raises these for invalid settings and refused operations. Their
# messages are written for a person and are safe to show the agent.
AGENT_ERRORS = (ValueError, SystemError, NotImplementedError)


@contextlib.contextmanager
def agent_errors() -> Iterator[None]:
    """Re-raise :data:`AGENT_ERRORS` as ``ToolError`` with the same message.

    ``ToolError`` passes through unchanged, and anything else propagates as a
    bug or hardware fault.
    """
    try:
        yield
    except ToolError:
        raise
    except AGENT_ERRORS as exc:
        raise ToolError(str(exc) or type(exc).__name__) from exc


@contextlib.contextmanager
def collect_warnings() -> Iterator[List[str]]:
    """Yield a list that fills with the messages of warnings raised inside.

    pytribeam writes warnings as multi-line f-strings, so each message has its
    whitespace collapsed to single spaces.
    """
    messages: List[str] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            yield messages
        finally:
            messages.extend(" ".join(str(w.message).split()) for w in caught)
