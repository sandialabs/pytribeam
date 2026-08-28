#!/usr/bin/python3
"""
EDAX IPAPI Client Module
========================

Socket transport for the EDAX IPAPI. :class:`EdaxClient` owns the TCP
connection, sends commands, and returns typed values.

The client's main job beyond raw I/O is demultiplexing. The IPAPI pushes
asynchronous ``EVENT_*`` notifications down the same socket that carries
command responses, so a read issued for one command can return an unrelated
event, a response to an earlier command, or several messages at once. The
client buffers events, discards stale responses, and keeps reading until the
response that matches the outstanding command arrives or the deadline passes.
Buffered events remain available through :meth:`EdaxClient.drain_events` and
:meth:`EdaxClient.wait_for_event`.

Classes
-------
EdaxClient
    Connection to a single EDAX IPAPI service.
"""

# Default python modules
import socket
import time
from collections import deque
from typing import Any, Deque, List, Optional, Tuple

# Local scripts
from pytribeam.external_oem.edax import protocol
from pytribeam.external_oem.edax.errors import (
    EdaxCommandError,
    EdaxConnectionError,
    EdaxTimeoutError,
)
from pytribeam.external_oem.edax.types import (
    EdaxCommand,
    EdaxConnectionSettings,
    EdaxResponse,
)

# Size of a single socket read. Camera capture commands return one integer per
# pixel, so reads are chunked and reassembled rather than sized to the payload.
_RECV_BYTES = 65536

#: Default time allowed for an in-flight response to land before closing.
#:
#: Sized from measured behavior on a TriBeam: a map of about 30 minutes goes
#: quiet for under 2 minutes while it finalizes, and a map of under a minute
#: answers essentially immediately. Finalization therefore costs on the order
#: of a few percent of the collection time. Five minutes covers the observed
#: worst case with wide headroom; raise it for collections much longer than
#: half an hour, where the pause scales up with the amount of data written.
DEFAULT_QUIESCE_S = 300.0


class EdaxClient:
    """
    Connection to a single EDAX IPAPI service.

    The client is usable as a context manager, which connects and unlocks on
    entry and closes on exit::

        with EdaxClient(settings) as client:
            status = client.query(EdaxCommand.EBSD_GET_MAP_STATUS)

    Parameters
    ----------
    settings : EdaxConnectionSettings
        Host, port, and default timing settings.
    sock : socket.socket, optional
        An already-connected socket to adopt instead of opening one. Used by
        tests and by callers that manage their own connections.
    quiet : bool, optional
        Suppress the informational connect/disconnect messages.
    """

    def __init__(
        self,
        settings: EdaxConnectionSettings,
        sock: Optional[socket.socket] = None,
        quiet: bool = False,
    ):
        self._settings = settings
        self._socket = sock
        self._quiet = quiet
        self._unlocked = False
        self._buffer = ""
        self._pending: Deque[EdaxResponse] = deque()
        self._events: Deque[EdaxResponse] = deque()
        # Name of a command that has been sent but not yet answered.
        self._outstanding: Optional[str] = None

    # -- properties ---------------------------------------------------------

    @property
    def settings(self) -> EdaxConnectionSettings:
        """Return the connection settings this client was built with."""
        return self._settings

    @property
    def connected(self) -> bool:
        """Return True when a socket is open."""
        return self._socket is not None

    @property
    def unlocked(self) -> bool:
        """Return True when the IPAPI has accepted the unlock command."""
        return self._unlocked

    @property
    def buffered_events(self) -> Tuple[EdaxResponse, ...]:
        """Return the events received but not yet consumed, in arrival order."""
        return tuple(self._events)

    @property
    def outstanding_command(self) -> Optional[str]:
        """
        Return the command awaiting a response, or None when the socket is idle.

        Non-None means the service may still write to this connection, so it
        must not be closed without quiescing first.
        """
        return self._outstanding

    # -- lifecycle ----------------------------------------------------------

    def connect(self) -> "EdaxClient":
        """
        Open the TCP connection and unlock the IPAPI.

        Returns
        -------
        EdaxClient
            This client, to allow chaining.

        Raises
        ------
        EdaxConnectionError
            If the socket cannot be opened or the unlock is refused.
        """
        if self._socket is None:
            try:
                self._socket = socket.create_connection(
                    (self._settings.host, self._settings.port),
                    timeout=self._settings.connect_timeout_s,
                )
            except OSError as error:
                raise EdaxConnectionError(
                    f"Could not connect to the EDAX IPAPI at "
                    f"{self._settings.host}:{self._settings.port}: {error}"
                )
            if not self._quiet:
                print(f"\tConnected to {self._settings.host}:{self._settings.port}")

        self.unlock()
        return self

    def unlock(self) -> EdaxResponse:
        """
        Send the security unlock required when opening a new connection.

        Returns
        -------
        EdaxResponse
            The unlock acknowledgement.

        Raises
        ------
        EdaxConnectionError
            If the IPAPI does not acknowledge the unlock.
        """
        try:
            response = self.send(EdaxCommand.UNLOCK)
        except (EdaxTimeoutError, EdaxCommandError) as error:
            raise EdaxConnectionError(f"EDAX IPAPI refused the unlock command: {error}")

        if protocol.UNLOCK_RESPONSE not in response.payload.lower():
            raise EdaxConnectionError(
                f"EDAX IPAPI refused the unlock command, responding '{response.raw}'."
            )
        self._unlocked = True
        return response

    def close(self, quiesce_s: float = DEFAULT_QUIESCE_S) -> bool:
        """
        Close the connection, first letting any in-flight response land.

        Closing while a request is outstanding is the one client behavior known
        to take down the IPAPI Windows service. The service is still blocked
        inside the EDAX application; when the application finally returns, the
        service writes the response to a socket that is no longer there and
        takes a ``SocketException`` on its per-connection worker thread. An
        unhandled exception on a background thread terminates a .NET process,
        so the service stops and has to be restarted by hand.

        Waiting for the response first lets the service complete its write and
        retire the thread normally.

        Parameters
        ----------
        quiesce_s : float, optional
            How long to wait for an outstanding response before closing. Pass
            ``0`` to close immediately, which is only safe when no request is
            in flight or the connection is already known to be broken.

        Returns
        -------
        bool
            True once the socket is closed.
        """
        if self._socket is not None:
            if quiesce_s > 0.0 and self._outstanding is not None:
                self.quiesce(timeout_s=quiesce_s)
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        self._unlocked = False
        self._outstanding = None
        self._buffer = ""
        self._pending.clear()
        self._events.clear()
        return True

    def quiesce(self, timeout_s: float = DEFAULT_QUIESCE_S) -> bool:
        """
        Wait for an outstanding response so the service can finish its write.

        Safe to call at any time; it returns immediately when nothing is in
        flight. Use it before closing a connection whose last command may still
        be blocked inside a map finalization.

        Parameters
        ----------
        timeout_s : float, optional
            Maximum time to wait, in seconds.

        Returns
        -------
        bool
            True when nothing is outstanding any more, False when the response
            still has not arrived and closing would abandon it.
        """
        if self._outstanding is None:
            return True
        try:
            self._await_response(self._outstanding, timeout_s=timeout_s)
        except (EdaxTimeoutError, EdaxConnectionError):
            return False
        return True

    def __enter__(self) -> "EdaxClient":
        """Connect and unlock on entry to a ``with`` block."""
        return self.connect()

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        """Close the connection on exit from a ``with`` block.

        The close quiesces first, so leaving the block on an error path does
        not abandon a response the service is still preparing.
        """
        self.close()
        return False

    # -- command interface --------------------------------------------------

    def send(
        self,
        command: protocol.CommandLike,
        *args: Any,
        timeout_s: Optional[float] = None,
        pause_s: Optional[float] = None,
        expect: Optional[str] = None,
    ) -> EdaxResponse:
        """
        Send a command and return the response that matches it.

        Events that arrive while waiting are buffered rather than treated as
        the response. Responses that echo a different command are discarded as
        stale.

        Parameters
        ----------
        command : EdaxCommand or str
            The command to send.
        *args : Any
            Command arguments, quoted and comma-separated automatically.
        timeout_s : float, optional
            Response timeout. Defaults to the connection setting.
        pause_s : float, optional
            Settling pause after sending. Defaults to the connection setting.
        expect : str, optional
            Required payload, compared case-insensitively.

        Returns
        -------
        EdaxResponse
            The matching response.

        Raises
        ------
        EdaxConnectionError
            If the client is not connected or the peer closed the socket.
        EdaxTimeoutError
            If no matching response arrives before the timeout.
        EdaxCommandError
            If ``expect`` is given and the payload does not match.
        """
        if self._socket is None:
            raise EdaxConnectionError(
                f"Cannot send '{protocol.command_name(command)}': "
                "the EDAX IPAPI client is not connected."
            )

        timeout_s = self._settings.timeout_s if timeout_s is None else timeout_s
        pause_s = self._settings.pause_s if pause_s is None else pause_s
        name = protocol.command_name(command)
        message = protocol.format_command(command, *args)

        try:
            self._socket.sendall(message.encode("ascii"))
        except OSError as error:
            raise EdaxConnectionError(
                f"Could not send '{name}' to the EDAX IPAPI: {error}"
            )
        self._outstanding = name

        if pause_s:
            time.sleep(pause_s)

        response = self._await_response(command=command, timeout_s=timeout_s)

        if expect is not None and response.payload.strip().lower() != expect.lower():
            raise EdaxCommandError(
                command=name, expected=expect, received=response.payload
            )
        return response

    def execute(
        self,
        command: protocol.CommandLike,
        *args: Any,
        timeout_s: Optional[float] = None,
        pause_s: Optional[float] = None,
    ) -> EdaxResponse:
        """
        Send an action command and require that it reports success.

        Parameters
        ----------
        command : EdaxCommand or str
            The command to send.
        *args : Any
            Command arguments.
        timeout_s : float, optional
            Response timeout. Defaults to the connection setting.
        pause_s : float, optional
            Settling pause after sending. Defaults to the connection setting.

        Returns
        -------
        EdaxResponse
            The success response.

        Raises
        ------
        EdaxCommandError
            If the IPAPI reports anything other than execution success.
        """
        return self.send(
            command,
            *args,
            timeout_s=timeout_s,
            pause_s=pause_s,
            expect=protocol.EXECUTION_SUCCESSFUL,
        )

    def query(
        self,
        command: protocol.CommandLike,
        *args: Any,
        timeout_s: Optional[float] = None,
        pause_s: Optional[float] = None,
    ) -> str:
        """
        Send a query command and return its payload as a string.

        Parameters
        ----------
        command : EdaxCommand or str
            The command to send.
        *args : Any
            Command arguments.
        timeout_s : float, optional
            Response timeout. Defaults to the connection setting.
        pause_s : float, optional
            Settling pause after sending. Defaults to the connection setting.

        Returns
        -------
        str
            The response payload, with quotes removed and interior spacing
            preserved.
        """
        response = self.send(command, *args, timeout_s=timeout_s, pause_s=pause_s)
        return response.payload

    def query_bool(self, command: protocol.CommandLike, *args: Any, **kwargs) -> bool:
        """Send a query command and return its payload as a boolean."""
        return protocol.to_bool(self.send(command, *args, **kwargs))

    def query_int(self, command: protocol.CommandLike, *args: Any, **kwargs) -> int:
        """Send a query command and return its payload as an integer."""
        return protocol.to_int(self.send(command, *args, **kwargs))

    def query_float(self, command: protocol.CommandLike, *args: Any, **kwargs) -> float:
        """Send a query command and return its payload as a float."""
        return protocol.to_float(self.send(command, *args, **kwargs))

    def query_int_array(
        self, command: protocol.CommandLike, *args: Any, **kwargs
    ) -> Tuple[int, ...]:
        """Send a query command and return its payload as a tuple of integers."""
        return protocol.to_int_array(self.send(command, *args, **kwargs))

    def query_str_array(
        self, command: protocol.CommandLike, *args: Any, **kwargs
    ) -> Tuple[str, ...]:
        """Send a query command and return its payload as a tuple of strings."""
        return protocol.to_str_array(self.send(command, *args, **kwargs))

    # -- event interface ----------------------------------------------------

    def drain_events(self, timeout_s: float = 0.0) -> List[EdaxResponse]:
        """
        Return and clear the buffered events.

        Parameters
        ----------
        timeout_s : float, optional
            Time to spend reading the socket for further events before
            returning. Zero returns only what is already buffered.

        Returns
        -------
        List[EdaxResponse]
            The buffered events, in arrival order.
        """
        if timeout_s > 0.0:
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                if not self._pump(timeout_s=deadline - time.time()):
                    break

        events = list(self._events)
        self._events.clear()
        return events

    def wait_for_event(
        self,
        event: protocol.CommandLike,
        timeout_s: float,
    ) -> Optional[EdaxResponse]:
        """
        Wait for a named event, consuming it from the buffer.

        Parameters
        ----------
        event : EdaxEvent or str
            The event to wait for.
        timeout_s : float
            Maximum time to wait, in seconds.

        Returns
        -------
        EdaxResponse or None
            The event, or None if it did not arrive before the timeout.
        """
        name = protocol.command_name(event)

        buffered = self._take_buffered_event(name)
        if buffered is not None:
            return buffered

        deadline = time.time() + timeout_s
        while True:
            remaining = deadline - time.time()
            if remaining <= 0.0:
                return None
            self._pump(timeout_s=remaining)
            buffered = self._take_buffered_event(name)
            if buffered is not None:
                return buffered

    def await_response(
        self,
        command: protocol.CommandLike,
        timeout_s: float,
    ) -> EdaxResponse:
        """
        Keep waiting for the response to a command that was already sent.

        This exists for one specific situation. The EDAX application blocks
        while it finalizes a map, and a status query issued in that window can
        take far longer to answer than any sensible per-command timeout. The
        correct recovery is to keep waiting for the response already in flight,
        never to send the command again: the IPAPI has one socket and no way to
        correlate replies, so a second command while one is outstanding
        desynchronizes the stream and every later read is answered by the
        previous request.

        Parameters
        ----------
        command : EdaxCommand or str
            The command whose response is still outstanding.
        timeout_s : float
            Additional time to wait, in seconds.

        Returns
        -------
        EdaxResponse
            The matching response.

        Raises
        ------
        EdaxTimeoutError
            If the response still has not arrived. The caller may call this
            again to extend the wait; the request stays outstanding.
        """
        return self._await_response(command=command, timeout_s=timeout_s)

    # -- internals ----------------------------------------------------------

    def _await_response(
        self, command: protocol.CommandLike, timeout_s: float
    ) -> EdaxResponse:
        """Read until the response matching ``command`` arrives or time runs out."""
        name = protocol.command_name(command)
        deadline = time.time() + timeout_s

        while True:
            while self._pending:
                message = self._pending.popleft()
                if protocol.matches_command(message, command):
                    self._outstanding = None
                    return message
                # A response echoing some other command answers a request that
                # has already timed out, so it is dropped as stale.

            remaining = deadline - time.time()
            if remaining <= 0.0:
                raise EdaxTimeoutError(command=name, timeout_s=timeout_s)

            self._pump(timeout_s=remaining)

    def _pump(self, timeout_s: float) -> bool:
        """
        Read one chunk from the socket and sort what it carries.

        Events are filed into the event buffer as soon as they are parsed, so
        an event that shares a read with a command response is visible to
        :meth:`drain_events` immediately rather than only after the next read.

        Parameters
        ----------
        timeout_s : float
            Time to wait for data, in seconds.

        Returns
        -------
        bool
            True when at least one message was parsed.
        """
        chunk = self._recv(timeout_s=timeout_s)
        if not chunk:
            return False

        self._buffer += chunk
        messages = protocol.parse_messages(self._buffer)
        self._buffer = ""

        for message in messages:
            if message.is_event:
                self._events.append(message)
            else:
                self._pending.append(message)

        return bool(messages)

    def _recv(self, timeout_s: float) -> Optional[str]:
        """Read one chunk from the socket, returning None on timeout."""
        if self._socket is None:
            raise EdaxConnectionError("The EDAX IPAPI client is not connected.")

        self._socket.settimeout(max(timeout_s, 0.0))
        try:
            data = self._socket.recv(_RECV_BYTES)
        except socket.timeout:
            return None
        except OSError as error:
            raise EdaxConnectionError(f"EDAX IPAPI socket read failed: {error}")

        if data == b"":
            raise EdaxConnectionError(
                "The EDAX IPAPI closed the connection unexpectedly."
            )
        return data.decode("ascii", errors="replace")

    def _take_buffered_event(self, name: str) -> Optional[EdaxResponse]:
        """Remove and return a buffered event by name, if present."""
        for index, event in enumerate(self._events):
            if event.command == name:
                del self._events[index]
                return event
        return None
