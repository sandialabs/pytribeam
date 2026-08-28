#!/usr/bin/python3
"""
Unit tests for the EDAX IPAPI socket client.

The client's job beyond raw I/O is demultiplexing: the IPAPI pushes
asynchronous events down the same socket that carries command responses, so
these tests concentrate on what happens when events, stale responses, and
real answers are interleaved.
"""

# Third-party modules
import pytest

# Local scripts
from helpers import NO_RESPONSE, FakeIpapi
from pytribeam.external_oem.edax.client import EdaxClient
from pytribeam.external_oem.edax.errors import (
    EdaxCommandError,
    EdaxConnectionError,
    EdaxResponseError,
    EdaxTimeoutError,
)
from pytribeam.external_oem.edax.types import (
    EdaxCommand,
    EdaxEvent,
)

pytestmark = pytest.mark.detached


# ----------------------------------------------------------------------
# Connection lifecycle
# ----------------------------------------------------------------------
def test_connect_sends_the_unlock_command(connection_settings, fake_ipapi):
    """A new connection is unusable until it has been unlocked."""
    client = EdaxClient(connection_settings, sock=fake_ipapi, quiet=True)
    client.connect()

    assert fake_ipapi.commands() == [EdaxCommand.UNLOCK.value]
    assert client.unlocked is True
    assert client.connected is True


def test_connect_raises_when_the_unlock_is_refused(connection_settings):
    """A refused unlock must fail loudly rather than leave a dead client."""
    service = FakeIpapi(raw={EdaxCommand.UNLOCK: "connection refused"})
    client = EdaxClient(connection_settings, sock=service, quiet=True)

    with pytest.raises(EdaxConnectionError, match="refused the unlock"):
        client.connect()


def test_connect_raises_when_the_unlock_goes_unanswered(connection_settings):
    """A silent IPAPI produces a connection error, not a bare timeout."""
    service = FakeIpapi(payloads={EdaxCommand.UNLOCK: NO_RESPONSE})
    client = EdaxClient(connection_settings, sock=service, quiet=True)

    with pytest.raises(EdaxConnectionError):
        client.connect()


def test_context_manager_connects_and_closes(connection_settings, fake_ipapi):
    """The ``with`` form is the intended way to scope a connection."""
    with EdaxClient(connection_settings, sock=fake_ipapi, quiet=True) as client:
        assert client.connected is True

    assert fake_ipapi.closed is True
    assert client.connected is False


def test_close_is_idempotent(client, fake_ipapi):
    """Closing twice must not raise, so cleanup paths can be unconditional."""
    assert client.close() is True
    assert client.close() is True


def test_sending_without_a_connection_raises(connection_settings):
    """Commands issued before connecting fail with a clear message."""
    client = EdaxClient(connection_settings, quiet=True)

    with pytest.raises(EdaxConnectionError, match="not connected"):
        client.send(EdaxCommand.EBSD_GET_MAP_STATUS)


def test_peer_disconnect_is_reported(client, fake_ipapi):
    """A socket closed by the service must not look like an empty payload."""
    fake_ipapi.peer_closed = True

    with pytest.raises(EdaxConnectionError, match="closed the connection"):
        client.query(EdaxCommand.EBSD_GET_MAP_STATUS)


# ----------------------------------------------------------------------
# Command dispatch
# ----------------------------------------------------------------------
def test_execute_accepts_the_documented_success_payload(make_client):
    """Action commands are confirmed against 'Execution Successful'."""
    client, service = make_client()
    response = client.execute(EdaxCommand.EBSD_SET_XSIZE, 25.0)

    assert response.succeeded is True
    assert service.arguments_for(EdaxCommand.EBSD_SET_XSIZE) == ['"25.0"']


def test_execute_raises_on_an_unsuccessful_payload(make_client):
    """A command that reports anything else must raise, not return quietly."""
    client, _ = make_client(payloads={EdaxCommand.EBSD_SET_XSIZE: "Execution Failed"})

    with pytest.raises(EdaxCommandError) as error:
        client.execute(EdaxCommand.EBSD_SET_XSIZE, 25.0)

    assert error.value.command == EdaxCommand.EBSD_SET_XSIZE.value
    assert error.value.received == "Execution Failed"


def test_query_returns_the_payload_verbatim(make_client):
    """Query payloads keep their case and interior spacing."""
    client, _ = make_client(
        payloads={EdaxCommand.EBSD_GET_FOLDERPATH: r"C:\EDAX Data\run 1"}
    )
    assert client.query(EdaxCommand.EBSD_GET_FOLDERPATH) == r"C:\EDAX Data\run 1"


def test_typed_queries_convert_payloads(make_client):
    """The typed helpers exist so callers never parse payloads themselves."""
    client, _ = make_client(
        payloads={
            EdaxCommand.EBSD_GET_CAMERA_SATURATION: "0.42",
            EdaxCommand.SEM_GET_MAGNIFICATION: "1500",
            EdaxCommand.SEM_GET_EXTERNAL_BEAM_CONTROL: "True",
            EdaxCommand.EBSD_CAMERA_SNAPSHOT: "1,2,3",
            EdaxCommand.CAMERA_GET_BINNING_NAMES: "1x1,2x2",
        }
    )

    assert client.query_float(EdaxCommand.EBSD_GET_CAMERA_SATURATION) == 0.42
    assert client.query_int(EdaxCommand.SEM_GET_MAGNIFICATION) == 1500
    assert client.query_bool(EdaxCommand.SEM_GET_EXTERNAL_BEAM_CONTROL) is True
    assert client.query_int_array(EdaxCommand.EBSD_CAMERA_SNAPSHOT) == (1, 2, 3)
    assert client.query_str_array(EdaxCommand.CAMERA_GET_BINNING_NAMES) == (
        "1x1",
        "2x2",
    )


def test_typed_query_raises_on_an_unconvertible_payload(make_client):
    """A malformed numeric payload surfaces as an EDAX error, not ValueError."""
    client, _ = make_client(
        payloads={EdaxCommand.EBSD_GET_CAMERA_SATURATION: "unavailable"}
    )

    with pytest.raises(EdaxResponseError):
        client.query_float(EdaxCommand.EBSD_GET_CAMERA_SATURATION)


def test_timeout_names_the_command_that_stalled(make_client):
    """A stalled command must identify itself for the operator."""
    client, _ = make_client(payloads={EdaxCommand.EBSD_GET_MAP_STATUS: NO_RESPONSE})

    with pytest.raises(EdaxTimeoutError) as error:
        client.query(EdaxCommand.EBSD_GET_MAP_STATUS)

    assert error.value.command == EdaxCommand.EBSD_GET_MAP_STATUS.value


# ----------------------------------------------------------------------
# Event demultiplexing
# ----------------------------------------------------------------------
def test_event_arriving_before_a_response_is_buffered(make_client):
    """An event must never be mistaken for the answer to a command."""
    client, service = make_client(payloads={EdaxCommand.EBSD_GET_MAP_STATUS: "Ready"})
    service.push_event(EdaxEvent.EBSD_COLLECTION_COMPLETE, "Mapping Complete")

    assert client.query(EdaxCommand.EBSD_GET_MAP_STATUS) == "Ready"

    events = client.drain_events()
    assert len(events) == 1
    assert events[0].command == EdaxEvent.EBSD_COLLECTION_COMPLETE.value


def test_event_sharing_a_read_with_the_response_is_buffered(make_client):
    """One socket read can carry both the response and a trailing event."""
    client, _ = make_client(
        raw={
            EdaxCommand.EBSD_GET_MAP_STATUS: (
                'get_map_status_ebsd RESPONSE "MappingActive"'
                'EVENT_MAP_COLLECTION_COMPLETE_EBSD "Mapping Complete"'
            )
        }
    )

    assert client.query(EdaxCommand.EBSD_GET_MAP_STATUS) == "MappingActive"
    assert client.buffered_events[0].payload == "Mapping Complete"


def test_stale_response_for_another_command_is_discarded(make_client):
    """A late answer to an earlier command must not satisfy the current one."""
    client, service = make_client(payloads={EdaxCommand.EBSD_GET_MAP_AVG_CI: "0.85"})
    service.push('get_map_status_ebsd RESPONSE "Ready"')

    assert client.query_float(EdaxCommand.EBSD_GET_MAP_AVG_CI) == 0.85


def test_drain_events_clears_the_buffer(make_client):
    """Draining hands over the events and leaves the buffer empty."""
    client, service = make_client()
    service.push_event(EdaxEvent.EBSD_SETUP_COMPLETE, "Setup Complete")
    client.query(EdaxCommand.EBSD_GET_MAP_STATUS)

    assert len(client.drain_events()) == 1
    assert client.drain_events() == []


def test_wait_for_event_consumes_a_buffered_event(make_client):
    """An event that already arrived satisfies a later wait immediately."""
    client, service = make_client()
    service.push_event(EdaxEvent.EBSD_COLLECTION_COMPLETE, "Mapping Complete")
    client.query(EdaxCommand.EBSD_GET_MAP_STATUS)

    event = client.wait_for_event(EdaxEvent.EBSD_COLLECTION_COMPLETE, timeout_s=0.1)
    assert event is not None
    assert event.payload == "Mapping Complete"
    assert client.buffered_events == ()


def test_wait_for_event_reads_the_socket_for_a_new_event(make_client):
    """An event that has not yet arrived is read from the socket."""
    client, service = make_client()
    service.push_event(EdaxEvent.EBSD_COLLECTION_COMPLETE, "Mapping Complete")

    event = client.wait_for_event(EdaxEvent.EBSD_COLLECTION_COMPLETE, timeout_s=0.5)
    assert event is not None


def test_wait_for_event_returns_none_on_timeout(client):
    """A missing event is reported as None rather than raising."""
    assert client.wait_for_event(EdaxEvent.EBSD_SETUP_COMPLETE, timeout_s=0.05) is None


def test_wait_for_event_buffers_unrelated_events(make_client):
    """Events other than the awaited one stay available for later."""
    client, service = make_client()
    service.push_event(EdaxEvent.EBSD_SETUP_COMPLETE, "Setup Complete")
    service.push_event(EdaxEvent.EBSD_COLLECTION_COMPLETE, "Mapping Complete")

    event = client.wait_for_event(EdaxEvent.EBSD_COLLECTION_COMPLETE, timeout_s=0.5)

    assert event.payload == "Mapping Complete"
    assert client.buffered_events[0].command == EdaxEvent.EBSD_SETUP_COMPLETE.value
