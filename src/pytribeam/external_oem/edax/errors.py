#!/usr/bin/python3
"""
EDAX Error Types
================

Exception hierarchy for the EDAX IPAPI wrapper. All errors derive from
:class:`pytribeam.external_oem.core.errors.DetectorError` so callers can
catch external-OEM failures uniformly across vendors.

Classes
-------
EdaxError(DetectorError)
    Base class for all EDAX IPAPI failures.

EdaxConnectionError(EdaxError)
    Socket could not be opened, unlocked, or was closed unexpectedly.

EdaxTimeoutError(EdaxError)
    No response arrived from the IPAPI within the allotted time.

EdaxCommandError(EdaxError)
    The IPAPI returned a response other than the expected one.

EdaxResponseError(EdaxError)
    A response arrived but could not be parsed into the requested type.

EdaxUnsupportedCommandError(EdaxError)
    The service rejected a command it does not implement.

EdaxStateError(EdaxError)
    A device or map reported a state incompatible with the requested action.
"""

from pytribeam.external_oem.core.errors import DetectorError


class EdaxError(DetectorError):
    """Base class for all EDAX IPAPI failures."""


class EdaxConnectionError(EdaxError):
    """Socket could not be opened, unlocked, or was closed unexpectedly."""


class EdaxTimeoutError(EdaxError):
    """No response arrived from the IPAPI within the allotted time.

    Attributes
    ----------
    command : str
        The command awaiting a response.
    timeout_s : float
        The timeout that elapsed, in seconds.
    """

    def __init__(self, command: str, timeout_s: float):
        self.command = command
        self.timeout_s = timeout_s
        super().__init__(
            f"EDAX IPAPI command '{command}' did not respond within {timeout_s:.1f} s."
        )


class EdaxCommandError(EdaxError):
    """The IPAPI returned a response other than the expected one.

    Attributes
    ----------
    command : str
        The command that was sent.
    expected : str
        The response that was required.
    received : str
        The response that actually arrived.
    """

    def __init__(self, command: str, expected: str, received: str):
        self.command = command
        self.expected = expected
        self.received = received
        super().__init__(
            f"EDAX IPAPI command '{command}' returned an invalid response. "
            f"Expected '{expected}' but received '{received}'."
        )


class EdaxResponseError(EdaxError):
    """A response arrived but could not be parsed into the requested type.

    Attributes
    ----------
    command : str
        The command that was sent.
    payload : str
        The raw payload that could not be converted.
    expected_type : str
        Human-readable name of the requested type.
    """

    def __init__(self, command: str, payload: str, expected_type: str):
        self.command = command
        self.payload = payload
        self.expected_type = expected_type
        super().__init__(
            f"EDAX IPAPI command '{command}' returned '{payload}', "
            f"which could not be interpreted as {expected_type}."
        )


class EdaxUnsupportedCommandError(EdaxError):
    """The service rejected a command it does not implement.

    Several commands in the *EDAX IP / API Reference* are absent from shipping
    IPAPI builds, which reject them at runtime with "Invalid Command or Invalid
    Syntax" rather than failing at connect time. Which commands are missing
    varies between builds, so this is a property of the installation rather
    than a defect in the caller.

    Attributes
    ----------
    command : str
        The command the service rejected.
    payload : str
        The rejection text the service returned.
    """

    def __init__(self, command: str, payload: str):
        self.command = command
        self.payload = payload
        super().__init__(
            f"The EDAX IPAPI does not implement '{command}'; it responded "
            f"'{payload}'. This command is documented but missing from this "
            "IPAPI build."
        )


class EdaxStateError(EdaxError):
    """A device or map reported a state incompatible with the requested action."""
