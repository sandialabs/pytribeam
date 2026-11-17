#!/usr/bin/python3
"""
Regression tests for commands an IPAPI build does not implement.

Several commands in the *EDAX IP / API Reference* are absent from shipping
IPAPI builds. ``get_ebsd_params_bytesperchannel`` is one observed on hardware:
the service answers ``Invalid Command or Invalid Syntax`` rather than failing
at connect time.

The reply carries no command prefix, which is the trap. An earlier version of
the client only accepted replies that echoed the command name, so the rejection
was discarded as a stale message and the caller waited out the full timeout for
a response that had already arrived. The symptom was a misleading
``did not respond within 15.0 s`` and a stall on every occurrence.
"""

# Third-party modules
import pytest

# Local scripts
from pytribeam.external_oem.edax.ebsd import EdaxEbsdController
from pytribeam.external_oem.edax.eds import EdaxEdsController
from pytribeam.external_oem.edax.errors import (
    EdaxTimeoutError,
    EdaxUnsupportedCommandError,
)
from pytribeam.external_oem.edax.types import EdaxCommand, EdaxEdsResolution

pytestmark = pytest.mark.detached

REJECTION = "Invalid Command or Invalid Syntax"
UNSUPPORTED = EdaxCommand.EBSD_GET_BYTESPERCHANNEL


def test_rejection_raises_immediately_rather_than_timing_out(make_client):
    """The service answered, so the client must not wait for the timeout."""
    client, _ = make_client(raw={UNSUPPORTED: REJECTION})

    with pytest.raises(EdaxUnsupportedCommandError) as error:
        client.query_int(UNSUPPORTED)

    assert error.value.command == UNSUPPORTED.value
    assert error.value.payload == REJECTION


def test_rejection_is_not_reported_as_a_timeout(make_client):
    """The old symptom was a timeout, which named the wrong problem."""
    client, _ = make_client(raw={UNSUPPORTED: REJECTION})

    with pytest.raises(EdaxUnsupportedCommandError):
        client.query_int(UNSUPPORTED)


def test_rejection_message_names_the_command_and_the_cause(make_client):
    """The operator needs to know which command the build is missing."""
    client, _ = make_client(raw={UNSUPPORTED: REJECTION})

    with pytest.raises(EdaxUnsupportedCommandError, match=UNSUPPORTED.value):
        client.query_int(UNSUPPORTED)


def test_rejection_does_not_desynchronize_the_socket(make_client):
    """The rejection is consumed, so the next command gets its own answer."""
    client, _ = make_client(
        raw={UNSUPPORTED: REJECTION},
        payloads={EdaxCommand.EBSD_GET_XSIZE: "25.0"},
    )

    with pytest.raises(EdaxUnsupportedCommandError):
        client.query_int(UNSUPPORTED)

    assert client.query_float(EdaxCommand.EBSD_GET_XSIZE) == pytest.approx(25.0)
    assert client.outstanding_command is None


def test_ebsd_map_parameters_degrades_to_none(make_client):
    """One missing command must not discard the whole parameter set."""
    client, _ = make_client(
        raw={UNSUPPORTED: REJECTION},
        payloads={
            EdaxCommand.EBSD_GET_FOLDERPATH: r"C:\EDAX Data",
            EdaxCommand.EBSD_GET_MODE: "0",
            EdaxCommand.EBSD_GET_RESOLUTION: "3",
            EdaxCommand.EBSD_GET_GRID: "1",
            EdaxCommand.EBSD_GET_SAVEHOUGHPEAKS: "False",
            EdaxCommand.EBSD_GET_SAVEPATTERNS: "True",
            EdaxCommand.EBSD_GET_SAVESPECTRA: "False",
            EdaxCommand.EBSD_GET_XSTART: "-10.0",
            EdaxCommand.EBSD_GET_YSTART: "-5.0",
            EdaxCommand.EBSD_GET_XSIZE: "25.0",
            EdaxCommand.EBSD_GET_YSIZE: "20.0",
            EdaxCommand.EBSD_GET_STEPSIZE: "0.5",
            EdaxCommand.EBSD_GET_CUSTOMSTEPSIZE: "0.5",
            EdaxCommand.EBSD_GET_EDSNUMCHAN: "1024",
        },
    )
    params = EdaxEbsdController(client).map_parameters()

    assert params.bytes_per_channel is None
    assert params.x_size_um == pytest.approx(25.0)
    assert params.eds_num_channels == 1024


def test_eds_map_parameters_degrades_to_none(make_client):
    """The EDS read-back is equally tolerant."""
    client, _ = make_client(
        raw={EdaxCommand.EDS_GET_BYTESPERCHANNEL: REJECTION},
        payloads={
            EdaxCommand.EDS_GET_FOLDERPATH: r"C:\EDAX Data",
            EdaxCommand.EDS_GET_EDSCHANNEL: "1",
            EdaxCommand.EDS_GET_NUMFRAMES: "10",
            EdaxCommand.EDS_GET_NUMPOINTS: "512",
            EdaxCommand.EDS_GET_NUMLINES: "400",
            EdaxCommand.EDS_GET_PRESETDWELL: "200.0",
            EdaxCommand.EDS_GET_EDSNUMCHAN: "1024",
            EdaxCommand.EDS_GET_IPD: "5",
            EdaxCommand.EDS_GET_NUMREADS: "1",
        },
    )
    params = EdaxEdsController(client).map_parameters()

    assert params.bytes_per_channel is None
    assert params.resolution is EdaxEdsResolution.PRESET_512X400


def test_a_genuinely_silent_command_still_times_out(make_client):
    """Silence and rejection are different faults and must stay distinct."""
    from helpers import NO_RESPONSE

    client, _ = make_client(payloads={UNSUPPORTED: NO_RESPONSE})

    with pytest.raises(EdaxTimeoutError):
        client.query_int(UNSUPPORTED, timeout_s=0.05)


def test_setters_also_surface_the_rejection(make_client):
    """An unimplemented setter must not look like a successful write."""
    client, _ = make_client(raw={EdaxCommand.EBSD_SET_BYTESPERCHANNEL: REJECTION})

    with pytest.raises(EdaxUnsupportedCommandError):
        client.execute(EdaxCommand.EBSD_SET_BYTESPERCHANNEL, 2)
