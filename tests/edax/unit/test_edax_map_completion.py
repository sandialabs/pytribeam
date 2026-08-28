#!/usr/bin/python3
"""
Regression tests for EDAX map completion.

Map completion is where the IPAPI is least well behaved, and where the first
implementation lost experiments. Three observed behaviors drive these tests:

1. **The application goes quiet while it finalizes a map.** Finalization writes
   patterns, OIM data, and the project database, so the pause scales with map
   size: measured on a TriBeam, a 30 minute map goes quiet for under 2 minutes,
   while a map of under a minute answers immediately. A status query issued in
   that window is accepted but not answered until the application is free.

2. **Completion is announced inconsistently.** Sometimes the terminal status
   arrives, sometimes ``EVENT_MAP_COLLECTION_COMPLETE_EBSD``, sometimes both,
   and the event can share a single socket read with a status response.

3. **An abandoned response corrupts the session.** The IPAPI has one command
   socket and no request/response correlation. Sending a second command while
   one is outstanding means every later reply answers the previous request, and
   the service is left writing into a connection nobody is reading.

The invariant that makes all of this safe is: *never issue a command while one
is outstanding, and always collect the response, however late it arrives.*
These tests pin that invariant down.

The fake service models the stall with per-command delays, which reproduce what
the client sees on hardware: a healthy socket, an accepted request, and nothing
coming back for a while.
"""

# Third-party modules
import pytest

# Local scripts
from pytribeam.external_oem.edax.ebsd import EdaxEbsdController
from pytribeam.external_oem.edax.eds import EdaxEdsController
from pytribeam.external_oem.edax.errors import EdaxTimeoutError
from pytribeam.external_oem.edax.types import (
    EdaxCommand,
    EdaxEvent,
    EdaxMappingStatus,
)

pytestmark = pytest.mark.detached

STATUS = EdaxCommand.EBSD_GET_MAP_STATUS
COMPLETE_EVENT = EdaxEvent.EBSD_COLLECTION_COMPLETE


def _status_queries(service) -> int:
    """Return how many map-status commands the service received."""
    return service.commands().count(STATUS.value)


# ----------------------------------------------------------------------
# Slow finalization
# ----------------------------------------------------------------------
def test_slow_finalization_does_not_abort_the_wait(make_client, no_sleep):
    """A status response slower than the per-query timeout is not a failure.

    This is the large-map case: the application stops answering while it
    finalizes, and the reply lands long after the poll timeout has passed.
    """
    client, _ = make_client(
        payloads={STATUS: "MappingComplete"},
        delays={STATUS: 0.3},
    )

    status = EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=10.0, poll_interval_s=0.0, status_timeout_s=0.02
    )

    assert status is EdaxMappingStatus.MAPPING_COMPLETE


def test_slow_finalization_issues_exactly_one_status_query(make_client, no_sleep):
    """The outstanding request is waited on, never re-sent.

    Re-sending is what desynchronizes the command socket: with no
    request/response correlation, the second reply answers the first query and
    every subsequent read is off by one. The per-query timeout elapses many
    times here, and exactly one command may leave the client.
    """
    client, service = make_client(
        payloads={STATUS: "MappingComplete"},
        delays={STATUS: 0.3},
    )

    EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=10.0, poll_interval_s=0.0, status_timeout_s=0.02
    )

    assert _status_queries(service) == 1


def test_late_response_is_collected_rather_than_abandoned(make_client, no_sleep):
    """The delayed reply is the one acted on, not a stale or invented value."""
    client, service = make_client(
        payloads={STATUS: ["MappingActive", "MappingComplete"]},
        delays={STATUS: [0.0, 0.25]},
    )

    status = EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=10.0, poll_interval_s=0.0, status_timeout_s=0.02
    )

    assert status is EdaxMappingStatus.MAPPING_COMPLETE
    # One prompt poll, then one that stalls through finalization.
    assert _status_queries(service) == 2
    assert client.buffered_events == ()


def test_delay_scaling_with_map_size_is_absorbed(make_client, no_sleep):
    """A longer stall costs more waiting, not more commands.

    Finalization time grows with map size, so the loop must be indifferent to
    how many poll timeouts elapse before the reply lands.
    """
    client, service = make_client(
        payloads={STATUS: "MappingComplete"},
        delays={STATUS: 0.5},
    )

    status = EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=10.0, poll_interval_s=0.0, status_timeout_s=0.01
    )

    assert status is EdaxMappingStatus.MAPPING_COMPLETE
    assert _status_queries(service) == 1


# ----------------------------------------------------------------------
# Inconsistent completion signalling
# ----------------------------------------------------------------------
def test_completion_by_status_only(make_client, no_sleep):
    """Some runs report a terminal status and never raise an event."""
    client, _ = make_client(
        payloads={STATUS: ["MappingActive", "MappingActive", "MappingComplete"]}
    )

    status = EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=5.0, poll_interval_s=0.0
    )

    assert status is EdaxMappingStatus.MAPPING_COMPLETE


def test_completion_by_ready_status(make_client, no_sleep):
    """Some runs settle straight to Ready without passing through Complete."""
    client, _ = make_client(payloads={STATUS: ["MappingActive", "Ready"]})

    status = EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=5.0, poll_interval_s=0.0
    )

    assert status is EdaxMappingStatus.READY


def test_completion_by_event_only(make_client, no_sleep):
    """Other runs raise the event while the status still reads active.

    Without the event channel this wait would run to its full timeout, which is
    how a finished map used to look like a hung one.
    """
    client, service = make_client(payloads={STATUS: "MappingActive"})
    service.push_event(COMPLETE_EVENT, "Mapping Complete")

    status = EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=5.0, poll_interval_s=0.0
    )

    assert status is EdaxMappingStatus.MAPPING_COMPLETE


def test_completion_by_both_channels(make_client, no_sleep):
    """Both signals together resolve once, without hanging on the extra one."""
    client, service = make_client(payloads={STATUS: "MappingComplete"})
    service.push_event(COMPLETE_EVENT, "Mapping Complete")

    status = EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=5.0, poll_interval_s=0.0
    )

    assert status is EdaxMappingStatus.MAPPING_COMPLETE


def test_event_sharing_the_final_read_is_not_lost(make_client, no_sleep):
    """The event and the status response can arrive in one socket read.

    The old single-read parser mangled this into one unrecognizable string.
    """
    client, _ = make_client(
        raw={
            STATUS: (
                'get_map_status_ebsd RESPONSE "MappingActive"'
                'EVENT_MAP_COLLECTION_COMPLETE_EBSD "Mapping Complete"'
            )
        }
    )

    status = EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=5.0, poll_interval_s=0.0
    )

    assert status is EdaxMappingStatus.MAPPING_COMPLETE


def test_event_arriving_during_finalization_stall(make_client, no_sleep):
    """The completion event may land while a status query is still outstanding."""
    client, service = make_client(
        payloads={STATUS: "MappingActive"},
        delays={STATUS: 0.2},
    )
    service.push_event(COMPLETE_EVENT, "Mapping Complete", delay_s=0.1)

    status = EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=10.0, poll_interval_s=0.0, status_timeout_s=0.02
    )

    assert status is EdaxMappingStatus.MAPPING_COMPLETE


# ----------------------------------------------------------------------
# Stream integrity
# ----------------------------------------------------------------------
def test_unrelated_status_response_does_not_satisfy_the_wait(make_client, no_sleep):
    """An EDS status reply must not be read as an EBSD one.

    A desynchronized stream shows up as replies echoing the wrong command. They
    are discarded rather than acted on or raised over.
    """
    client, service = make_client(
        payloads={STATUS: ["MappingActive", "MappingComplete"]}
    )
    service.push('get_map_status RESPONSE "Ready"')

    status = EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=5.0, poll_interval_s=0.0
    )

    assert status is EdaxMappingStatus.MAPPING_COMPLETE


def test_next_command_after_a_stall_gets_its_own_answer(make_client, no_sleep):
    """The command following the wait must not be served a leftover reply.

    This is the second-order damage from re-sending during finalization. Every
    timed-out poll leaves an unread reply queued, so the next command in the
    workflow reads the previous one's answer. In the original implementation
    the map-status payload landed in ``average_ci``, where it failed to parse
    as a float, one step removed from the actual fault.
    """
    client, service = make_client(
        payloads={
            STATUS: "MappingComplete",
            EdaxCommand.EBSD_GET_MAP_AVG_CI: "0.85",
        },
        delays={STATUS: 0.25},
    )
    controller = EdaxEbsdController(client)

    controller.wait_for_map_complete(
        timeout_s=10.0, poll_interval_s=0.0, status_timeout_s=0.01
    )

    assert controller.average_ci() == pytest.approx(0.85)
    assert _status_queries(service) == 1


def test_timed_out_poll_does_not_raise_a_type_error(make_client, no_sleep):
    """A poll that returns nothing must not crash the run.

    The first implementation tested ``"..." in map_status`` before its None
    guard, so a single timed-out poll raised TypeError and ended the
    experiment. A stalled reply must simply be waited out.
    """
    client, _ = make_client(
        payloads={STATUS: "MappingComplete"},
        delays={STATUS: 0.2},
    )

    status = EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=10.0, poll_interval_s=0.0, status_timeout_s=0.01
    )

    assert status is EdaxMappingStatus.MAPPING_COMPLETE


def test_hung_application_is_still_bounded(make_client, no_sleep):
    """A genuinely hung application must end the wait, without command spam.

    The overall deadline still applies. Distinguishing this from a slow
    finalization is a matter of the overall timeout, which the caller sizes
    from the expected map duration.
    """
    client, service = make_client(
        payloads={STATUS: "MappingComplete"},
        delays={STATUS: 30.0},
    )

    with pytest.raises(EdaxTimeoutError):
        EdaxEbsdController(client).wait_for_map_complete(
            timeout_s=0.15, poll_interval_s=0.0, status_timeout_s=0.01
        )

    assert _status_queries(service) == 1


def test_socket_stays_open_after_a_stalled_poll(make_client, no_sleep):
    """Giving up on the wait must not tear the connection down.

    Closing the socket under an outstanding request leaves the service writing
    into a dead connection. Teardown is the caller's decision, made after the
    session is quiesced.
    """
    client, service = make_client(
        payloads={STATUS: "MappingComplete"},
        delays={STATUS: 30.0},
    )

    with pytest.raises(EdaxTimeoutError):
        EdaxEbsdController(client).wait_for_map_complete(
            timeout_s=0.15, poll_interval_s=0.0, status_timeout_s=0.01
        )

    assert client.connected is True
    assert service.closed is False


# ----------------------------------------------------------------------
# Protecting the IPAPI Windows service
# ----------------------------------------------------------------------
# The service runs each connection on its own worker thread and stays blocked
# in the EDAX application for the whole finalization pause. If the client has
# closed by the time the application returns, the service's write lands on a
# dead socket and the resulting SocketException on that background thread
# terminates the .NET process: the Windows service stops and has to be
# restarted by hand. The fake records the condition as writes_after_close.
def test_closing_waits_for_an_outstanding_response(make_client, no_sleep):
    """Closing must not abandon a write the service has yet to make."""
    client, service = make_client(
        payloads={STATUS: "MappingComplete"},
        delays={STATUS: 0.25},
    )

    with pytest.raises(EdaxTimeoutError):
        client.query(STATUS, timeout_s=0.01)

    assert client.outstanding_command == STATUS.value
    client.close()

    assert service.writes_after_close == 0
    assert client.outstanding_command is None


def test_context_manager_exit_quiesces_on_an_error_path(make_client, no_sleep):
    """Leaving the block on an exception must not strand a pending write.

    This is the shape of a real failure: something raises mid-collection while
    a status query is still blocked inside map finalization.
    """
    client, service = make_client(
        payloads={STATUS: "MappingComplete"},
        delays={STATUS: 0.25},
    )

    with pytest.raises(RuntimeError):
        with client:
            try:
                client.query(STATUS, timeout_s=0.01)
            except EdaxTimeoutError:
                pass
            raise RuntimeError("something else went wrong mid-collection")

    assert service.writes_after_close == 0


def test_giving_up_on_a_map_still_closes_cleanly(make_client, no_sleep):
    """Even an aborted collection must leave the service in one piece."""
    client, service = make_client(
        payloads={STATUS: "MappingComplete"},
        delays={STATUS: 0.3},
    )

    with pytest.raises(EdaxTimeoutError):
        EdaxEbsdController(client).wait_for_map_complete(
            timeout_s=0.05, poll_interval_s=0.0, status_timeout_s=0.01
        )

    client.close()
    assert service.writes_after_close == 0


def test_quiesce_reports_whether_the_socket_is_safe_to_close(make_client, no_sleep):
    """Callers can check rather than block, when they need to decide."""
    client, _ = make_client(
        payloads={STATUS: "MappingComplete"},
        delays={STATUS: 0.3},
    )

    with pytest.raises(EdaxTimeoutError):
        client.query(STATUS, timeout_s=0.01)

    # Too little time for the stalled reply to land.
    assert client.quiesce(timeout_s=0.01) is False
    # Enough time, so the response is collected and the socket is safe.
    assert client.quiesce(timeout_s=5.0) is True
    assert client.outstanding_command is None


def test_close_can_skip_quiescing_when_explicitly_asked(make_client, no_sleep):
    """The unsafe close stays available for a connection already known dead."""
    client, service = make_client(
        payloads={STATUS: "MappingComplete"},
        delays={STATUS: 5.0},
    )

    with pytest.raises(EdaxTimeoutError):
        client.query(STATUS, timeout_s=0.01)

    client.close(quiesce_s=0.0)

    # Documents the hazard the default close exists to avoid.
    assert service.writes_after_close == 1


def test_completed_wait_leaves_nothing_outstanding(make_client, no_sleep):
    """A normal completion ends with an idle socket, safe to close at once."""
    client, service = make_client(
        payloads={STATUS: "MappingComplete"},
        delays={STATUS: 0.2},
    )

    EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=10.0, poll_interval_s=0.0, status_timeout_s=0.01
    )

    assert client.outstanding_command is None
    client.close(quiesce_s=0.0)
    assert service.writes_after_close == 0


def test_progress_callback_is_quiet_during_a_stall(make_client, no_sleep):
    """Progress is reported per answered poll, not per timed-out read.

    A busy-wait through finalization would otherwise flood the experiment log.
    """
    client, _ = make_client(
        payloads={STATUS: "MappingComplete"},
        delays={STATUS: 0.25},
    )
    seen = []

    EdaxEbsdController(client).wait_for_map_complete(
        timeout_s=10.0,
        poll_interval_s=0.0,
        status_timeout_s=0.01,
        progress_fn=lambda status, elapsed: seen.append(status),
    )

    assert seen == [EdaxMappingStatus.MAPPING_COMPLETE]


# ----------------------------------------------------------------------
# The EDS half behaves identically
# ----------------------------------------------------------------------
def test_eds_completion_survives_a_finalization_stall(make_client, no_sleep):
    """EDS shares the base class, so it inherits the same guarantees."""
    client, service = make_client(
        payloads={EdaxCommand.EDS_GET_MAP_STATUS: "MappingComplete"},
        delays={EdaxCommand.EDS_GET_MAP_STATUS: 0.25},
    )

    status = EdaxEdsController(client).wait_for_map_complete(
        timeout_s=10.0, poll_interval_s=0.0, status_timeout_s=0.01
    )

    assert status is EdaxMappingStatus.MAPPING_COMPLETE
    assert service.commands().count(EdaxCommand.EDS_GET_MAP_STATUS.value) == 1


def test_eds_completion_by_its_own_event(make_client, no_sleep):
    """The EDS event name differs, and must not be confused with the EBSD one."""
    client, service = make_client(
        payloads={EdaxCommand.EDS_GET_MAP_STATUS: "MappingActive"}
    )
    service.push_event(EdaxEvent.EBSD_COLLECTION_COMPLETE, "Mapping Complete")

    with pytest.raises(EdaxTimeoutError):
        EdaxEdsController(client).wait_for_map_complete(
            timeout_s=0.2, poll_interval_s=0.0, status_timeout_s=0.05
        )
