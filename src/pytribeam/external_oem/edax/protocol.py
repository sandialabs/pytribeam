#!/usr/bin/python3
"""
EDAX IPAPI Protocol Module
==========================

Pure functions for building EDAX IPAPI command strings and parsing the ASCII
messages the service sends back. Nothing here touches a socket, so the entire
wire protocol is unit-testable without hardware.

Wire format, per the *EDAX IP / API Reference* revision 2.3.8:

- Commands are ASCII, case-insensitive, with every argument wrapped in double
  quotes and multiple arguments separated by commas::

      set_system_projectinfo_ext_ebsd "<guid>","<name>","10","2.5"

- Responses echo the command name followed by the ``RESPONSE`` keyword and a
  quoted payload::

      do_map_collection_start RESPONSE "Execution Successful"

- Asynchronous events may arrive at any time on the same socket, prefixed with
  ``EVENT_``::

      EVENT_MAP_COLLECTION_COMPLETE "Mapping Complete"

- A single ``recv`` may carry several concatenated messages.

Functions
---------
format_value(value) -> str
    Render a Python value the way the IPAPI expects it.

format_command(command, *args) -> str
    Build a complete command string with quoted, comma-separated arguments.

success_response(command) -> str
    Build the canonical "execution successful" response for a command.

split_messages(raw) -> List[str]
    Split a raw socket read into individual messages.

parse_message(raw) -> EdaxResponse
    Parse one message into its command name, payload, and event flag.

parse_messages(raw) -> List[EdaxResponse]
    Split and parse every message in a raw socket read.

matches_command(response, command) -> bool
    Report whether a parsed response answers a given command.

to_bool(response) / to_int(response) / to_float(response) / to_int_array(response)
    Convert a parsed payload into a Python value, raising EdaxResponseError on
    malformed input.
"""

# Default python modules
import re
from enum import Enum
from pathlib import Path
from typing import Any, List, Tuple, Union

# Local scripts
from pytribeam.external_oem.edax.errors import EdaxResponseError
from pytribeam.external_oem.edax.types import EdaxCommand, EdaxResponse

# Payload reported by every command that performs an action rather than
# returning a value.
EXECUTION_SUCCESSFUL = "execution successful"

# The unlock command is the one command that does not echo its own name.
UNLOCK_RESPONSE = "client connection accepted"

# Boolean literals the IPAPI accepts and returns.
_TRUE_LITERALS = frozenset({"true", "1", "yes", "on"})
_FALSE_LITERALS = frozenset({"false", "0", "no", "off"})

# A message begins either with an EVENT_ prefix or with "<name> response".
# The IPAPI does not guarantee a separator between concatenated messages, so a
# closing quote is accepted as a boundary alongside whitespace.
_MESSAGE_START = re.compile(
    r'(?i)(?:(?<=\s)|(?<=^)|(?<="))(?:event_[a-z0-9_]+|[a-z0-9_]+\s+response\b)'
)

# Splits a parsed message into its "<name> response" prefix and its payload.
_RESPONSE_SPLIT = re.compile(r"(?i)^\s*([a-z0-9_]+)\s+response\b\s*(.*)$", re.DOTALL)
_EVENT_SPLIT = re.compile(r"(?i)^\s*(event_[a-z0-9_]+)\s*(.*)$", re.DOTALL)

CommandLike = Union[EdaxCommand, str]


def command_name(command: CommandLike) -> str:
    """
    Return the canonical lower-case wire name for a command or event.

    Any enum is reduced to its value rather than its ``str``, because a
    ``str``-mixin enum stringifies as ``ClassName.MEMBER`` rather than as the
    wire name.

    Parameters
    ----------
    command : EdaxCommand, EdaxEvent, or str
        The command or event to normalize.

    Returns
    -------
    str
        The lower-cased wire name.
    """
    if isinstance(command, Enum):
        return str(command.value).strip().lower()
    return str(command).strip().lower()


def format_value(value: Any) -> str:
    """
    Render a Python value the way the IPAPI expects it.

    Booleans become ``True``/``False``, enums contribute their value, paths are
    rendered as strings, and everything else uses ``str``. Floats keep their
    repr so that step sizes are not silently rounded.

    Parameters
    ----------
    value : Any
        The value to render.

    Returns
    -------
    str
        The rendered value, without surrounding quotes.
    """
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, Enum):
        return format_value(value.value)
    if isinstance(value, Path):
        return str(value)
    return str(value)


def format_command(command: CommandLike, *args: Any) -> str:
    """
    Build a complete command string with quoted, comma-separated arguments.

    Parameters
    ----------
    command : EdaxCommand or str
        The command to send.
    *args : Any
        Command arguments, rendered by :func:`format_value` and wrapped in
        double quotes as the IPAPI requires.

    Returns
    -------
    str
        The command string ready to encode as ASCII and send.

    Examples
    --------
    >>> format_command(EdaxCommand.EBSD_SET_XSIZE, 25.0)
    'set_ebsd_params_xsize "25.0"'
    """
    name = command_name(command)
    if not args:
        return name
    rendered = ",".join(f'"{format_value(arg)}"' for arg in args)
    return f"{name} {rendered}"


def success_response(command: CommandLike) -> str:
    """
    Build the canonical "execution successful" response for a command.

    Parameters
    ----------
    command : EdaxCommand or str
        The command whose success response is wanted.

    Returns
    -------
    str
        A response string such as ``set_ebsd_params_xsize response "execution
        successful"``.
    """
    return f'{command_name(command)} response "{EXECUTION_SUCCESSFUL}"'


def split_messages(raw: str) -> List[str]:
    """
    Split a raw socket read into individual messages.

    A single read may contain a command response immediately followed by an
    asynchronous event, or several events in a row.

    Parameters
    ----------
    raw : str
        Text decoded from one or more socket reads.

    Returns
    -------
    List[str]
        The individual messages, whitespace-trimmed. Text that carries no
        recognizable prefix is returned as a single message so that unlock
        acknowledgements and error strings survive.
    """
    if raw is None:
        return []
    text = raw.strip()
    if not text:
        return []

    starts = [match.start() for match in _MESSAGE_START.finditer(text)]
    if not starts:
        return [text]

    # Text before the first recognized prefix belongs to a message of its own,
    # such as the unlock acknowledgement.
    if starts[0] != 0:
        starts.insert(0, 0)

    bounds = starts + [len(text)]
    messages = []
    for start, end in zip(bounds[:-1], bounds[1:]):
        message = text[start:end].strip()
        if message:
            messages.append(message)
    return messages


def parse_message(raw: str) -> EdaxResponse:
    """
    Parse one message into its command name, payload, and event flag.

    Parameters
    ----------
    raw : str
        A single message, as produced by :func:`split_messages`.

    Returns
    -------
    EdaxResponse
        The parsed message. Interior payload spacing is preserved so that
        values such as folder paths survive intact; only the prefix, the
        ``RESPONSE`` keyword, and enclosing quotes are removed.
    """
    text = "" if raw is None else raw.strip()

    event_match = _EVENT_SPLIT.match(text)
    if event_match:
        name, payload = event_match.groups()
        return EdaxResponse(
            raw=text,
            command=name.lower(),
            payload=_strip_quotes(payload),
            is_event=True,
        )

    response_match = _RESPONSE_SPLIT.match(text)
    if response_match:
        name, payload = response_match.groups()
        return EdaxResponse(
            raw=text,
            command=name.lower(),
            payload=_strip_quotes(payload),
            is_event=False,
        )

    return EdaxResponse(
        raw=text,
        command="",
        payload=_strip_quotes(text),
        is_event=False,
    )


def parse_messages(raw: str) -> List[EdaxResponse]:
    """
    Split and parse every message in a raw socket read.

    Parameters
    ----------
    raw : str
        Text decoded from one or more socket reads.

    Returns
    -------
    List[EdaxResponse]
        One parsed response per message, in arrival order.
    """
    return [parse_message(message) for message in split_messages(raw)]


def matches_command(response: EdaxResponse, command: CommandLike) -> bool:
    """
    Report whether a parsed response answers a given command.

    Parameters
    ----------
    response : EdaxResponse
        A parsed message.
    command : EdaxCommand or str
        The command awaiting a response.

    Returns
    -------
    bool
        True when the response echoes the command name, or when it is the
        unlock acknowledgement and the unlock command was sent.
    """
    if response.is_event:
        return False
    name = command_name(command)
    if response.command == name:
        return True
    if name == EdaxCommand.UNLOCK.value:
        return UNLOCK_RESPONSE in response.payload.lower()
    return False


def to_bool(response: EdaxResponse) -> bool:
    """
    Convert a parsed payload into a boolean.

    Parameters
    ----------
    response : EdaxResponse
        A parsed response carrying a boolean payload.

    Returns
    -------
    bool
        The converted value.

    Raises
    ------
    EdaxResponseError
        If the payload is not a recognized boolean literal.
    """
    payload = response.payload.strip().lower()
    if payload in _TRUE_LITERALS:
        return True
    if payload in _FALSE_LITERALS:
        return False
    raise EdaxResponseError(response.command, response.payload, "a boolean")


def to_int(response: EdaxResponse) -> int:
    """
    Convert a parsed payload into an integer.

    Values that arrive with a decimal point, which some IPAPI builds do for
    pixel counts, are truncated rather than rejected.

    Parameters
    ----------
    response : EdaxResponse
        A parsed response carrying an integer payload.

    Returns
    -------
    int
        The converted value.

    Raises
    ------
    EdaxResponseError
        If the payload is not numeric.
    """
    payload = response.payload.strip()
    try:
        return int(payload)
    except ValueError:
        pass
    try:
        return int(float(payload))
    except ValueError as error:
        raise EdaxResponseError(
            response.command, response.payload, "an integer"
        ) from error


def to_float(response: EdaxResponse) -> float:
    """
    Convert a parsed payload into a float.

    Parameters
    ----------
    response : EdaxResponse
        A parsed response carrying a numeric payload.

    Returns
    -------
    float
        The converted value.

    Raises
    ------
    EdaxResponseError
        If the payload is not numeric.
    """
    payload = response.payload.strip()
    try:
        return float(payload)
    except ValueError as error:
        raise EdaxResponseError(
            response.command, response.payload, "a float"
        ) from error


def to_int_array(response: EdaxResponse) -> Tuple[int, ...]:
    """
    Convert a comma-delimited payload into a tuple of integers.

    Used by the camera capture commands, which return one unsigned integer per
    image pixel.

    Parameters
    ----------
    response : EdaxResponse
        A parsed response carrying a comma-delimited integer list.

    Returns
    -------
    Tuple[int, ...]
        The converted values, empty when the payload is empty.

    Raises
    ------
    EdaxResponseError
        If any element is not numeric.
    """
    payload = response.payload.strip()
    if not payload:
        return ()
    try:
        return tuple(
            int(item.strip()) for item in payload.split(",") if item.strip() != ""
        )
    except ValueError as error:
        raise EdaxResponseError(
            response.command, response.payload, "a comma-delimited integer list"
        ) from error


def to_str_array(response: EdaxResponse) -> Tuple[str, ...]:
    """
    Convert a comma-delimited payload into a tuple of strings.

    Used by ``get_camera_params_binning_names``.

    Parameters
    ----------
    response : EdaxResponse
        A parsed response carrying a comma-delimited string list.

    Returns
    -------
    Tuple[str, ...]
        The converted values, empty when the payload is empty.
    """
    payload = response.payload.strip()
    if not payload:
        return ()
    return tuple(item.strip() for item in payload.split(",") if item.strip() != "")


def _strip_quotes(text: str) -> str:
    """Remove one layer of enclosing double quotes and surrounding whitespace."""
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] == '"' and stripped[-1] == '"':
        return stripped[1:-1]
    return stripped.strip('"')
