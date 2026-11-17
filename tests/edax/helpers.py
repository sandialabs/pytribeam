#!/usr/bin/python3
"""
EDAX Test Helpers
=================

A scriptable in-memory stand-in for the EDAX IPAPI service.

:class:`FakeIpapi` implements the small part of the ``socket.socket`` interface
that :class:`pytribeam.external_oem.edax.client.EdaxClient` uses, so the client
and every controller above it can be exercised without a network, a microscope,
or an EDAX installation.

The fake records every command it receives, answers from a scripted table, and
can inject asynchronous events at chosen points, which is how the event
demultiplexing in the client is tested.

Classes
-------
FakeIpapi
    Scriptable fake EDAX IPAPI socket.

Constants
---------
NO_RESPONSE
    Sentinel payload meaning "stay silent", used to simulate a timeout.
"""

# Default python modules
import socket
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple, Union

# Local scripts
from pytribeam.external_oem.edax import protocol
from pytribeam.external_oem.edax.protocol import EXECUTION_SUCCESSFUL, UNLOCK_RESPONSE
from pytribeam.external_oem.edax.types import EdaxCommand


class _NoResponse:
    """Sentinel type for a command the fake service never answers."""

    def __repr__(self) -> str:
        return "NO_RESPONSE"


#: Payload sentinel meaning "stay silent", used to simulate a timeout.
NO_RESPONSE = _NoResponse()

PayloadSource = Union[str, _NoResponse, List[Any], Callable[[str], Any]]


class FakeIpapi:
    """
    Scriptable fake EDAX IPAPI socket.

    Parameters
    ----------
    payloads : dict, optional
        Maps a command name (or :class:`EdaxCommand`) to the payload the fake
        should answer with. A value may be:

        - a string, returned for every call;
        - a list, whose entries are consumed one call at a time, with the last
          entry repeating once the list is exhausted;
        - :data:`NO_RESPONSE`, which answers nothing so the client times out;
        - a callable taking the full command string and returning any of the
          above.

        Commands absent from the table answer ``"Execution Successful"``.
    raw : dict, optional
        Maps a command name to a complete raw message, bypassing the usual
        ``<command> RESPONSE "<payload>"`` framing. Used to test malformed or
        concatenated replies.
    events : dict, optional
        Maps a command name to raw event messages appended after that
        command's response, simulating events that arrive mid-conversation.
    delays : dict, optional
        Maps a command name to the seconds its reply is withheld before
        becoming readable. This models the EDAX application going quiet while
        it finalizes a map: the request is accepted, but nothing comes back
        until the application is free again. A value may be a single float or a
        list consumed one call at a time, as with ``payloads``.
    """

    def __init__(
        self,
        payloads: Optional[Dict[Any, PayloadSource]] = None,
        raw: Optional[Dict[Any, str]] = None,
        events: Optional[Dict[Any, List[str]]] = None,
        delays: Optional[Dict[Any, Any]] = None,
    ):
        self.payloads = {_name(key): value for key, value in (payloads or {}).items()}
        self.raw = {_name(key): value for key, value in (raw or {}).items()}
        self.events = {_name(key): value for key, value in (events or {}).items()}
        self.delays = {_name(key): value for key, value in (delays or {}).items()}

        #: Every command string the fake has received, in order.
        self.sent: List[str] = []
        #: Timeouts the client has requested, in order.
        self.timeouts: List[float] = []
        #: True once the socket has been closed.
        self.closed = False
        #: When True, the next recv reports the peer closed the connection.
        self.peer_closed = False
        #: Replies the service had not yet written when the client closed.
        #: Any value above zero is the condition that stops the IPAPI service.
        self.writes_after_close = 0

        self._outbox: Deque[Tuple[float, bytes]] = deque()
        self._call_counts: Dict[str, int] = {}
        self._delay_counts: Dict[str, int] = {}

    # -- socket interface ----------------------------------------------------

    def sendall(self, data: bytes) -> None:
        """Record a command and queue the scripted reply."""
        if self.closed:
            raise OSError("socket is closed")

        command = data.decode("ascii")
        self.sent.append(command)

        name = command.split(" ", 1)[0].strip().lower()
        available_at = time.monotonic() + self._delay_for(name)
        for message in self._reply_for(name, command):
            self._outbox.append((available_at, message.encode("ascii")))

    def settimeout(self, timeout_s: float) -> None:
        """Record the requested socket timeout."""
        self.timeouts.append(timeout_s)

    def recv(self, bufsize: int) -> bytes:
        """Return the next readable message, or raise a timeout when none is.

        A message whose delay has not yet elapsed is treated as not-yet-sent,
        which is what makes a stalled EDAX application look to the client
        exactly as it does on hardware: the socket is healthy, the request was
        accepted, and nothing comes back for a while.
        """
        if self.peer_closed:
            return b""
        if not self._outbox:
            raise socket.timeout("timed out")

        available_at, message = self._outbox[0]
        if time.monotonic() < available_at:
            raise socket.timeout("timed out")

        self._outbox.popleft()
        return message

    def close(self) -> None:
        """Mark the socket closed, recording any write the service still owes.

        A reply whose delay has not yet elapsed is one the service has not
        written yet. If the client closes now, that write lands on a dead
        socket, which is what faults the IPAPI worker thread and stops the
        Windows service. ``writes_after_close`` records how many such writes
        were abandoned, so tests can assert the client never leaves one behind.
        """
        now = time.monotonic()
        self.writes_after_close = sum(
            1 for available_at, _ in self._outbox if available_at > now
        )
        self.closed = True

    # -- test controls -------------------------------------------------------

    def push(self, message: str, delay_s: float = 0.0) -> None:
        """
        Queue a raw message for delivery on the next read.

        Parameters
        ----------
        message : str
            A complete IPAPI message, such as an event notification.
        delay_s : float, optional
            Seconds to withhold the message before it becomes readable.
        """
        self._outbox.append((time.monotonic() + delay_s, message.encode("ascii")))

    def push_event(self, event: Any, payload: str = "", delay_s: float = 0.0) -> None:
        """
        Queue an asynchronous event for delivery on the next read.

        Parameters
        ----------
        event : EdaxEvent or str
            The event to deliver.
        payload : str, optional
            The event payload.
        delay_s : float, optional
            Seconds to withhold the event before it becomes readable.
        """
        self.push(f'{_name(event).upper()} "{payload}"', delay_s=delay_s)

    def commands(self) -> List[str]:
        """Return the command names received, without their arguments."""
        return [command.split(" ", 1)[0].strip().lower() for command in self.sent]

    def arguments_for(self, command: Any) -> List[str]:
        """
        Return the argument text of every call to one command.

        Parameters
        ----------
        command : EdaxCommand or str
            The command to look up.

        Returns
        -------
        List[str]
            The argument portion of each matching command string, in order.
        """
        name = _name(command)
        found = []
        for sent in self.sent:
            head, _, tail = sent.partition(" ")
            if head.strip().lower() == name:
                found.append(tail.strip())
        return found

    # -- internals -----------------------------------------------------------

    def _reply_for(self, name: str, command: str) -> List[str]:
        """Build the list of raw messages that answer one command."""
        if name in self.raw:
            messages = [self.raw[name]]
        else:
            payload = self._payload_for(name, command)
            if isinstance(payload, _NoResponse):
                messages = []
            elif name == EdaxCommand.UNLOCK.value:
                # The unlock acknowledgement does not echo the command name.
                messages = [str(payload)]
            else:
                messages = [f'{name} RESPONSE "{payload}"']

        messages.extend(self.events.get(name, []))
        return messages

    def _delay_for(self, name: str) -> float:
        """Resolve how long to withhold a reply, advancing any scripted list."""
        source = self.delays.get(name, 0.0)
        if isinstance(source, list):
            index = self._delay_counts.get(name, 0)
            self._delay_counts[name] = index + 1
            source = source[min(index, len(source) - 1)]
        return float(source)

    def _payload_for(self, name: str, command: str) -> Any:
        """Resolve the payload for one command, advancing any scripted list."""
        if name == EdaxCommand.UNLOCK.value and name not in self.payloads:
            return UNLOCK_RESPONSE

        source = self.payloads.get(name, EXECUTION_SUCCESSFUL)

        if callable(source):
            source = source(command)

        if isinstance(source, list):
            index = self._call_counts.get(name, 0)
            self._call_counts[name] = index + 1
            source = source[min(index, len(source) - 1)]

        return source


def _name(command: Any) -> str:
    """Return the canonical lower-case wire name for a command or event."""
    return protocol.command_name(command)
