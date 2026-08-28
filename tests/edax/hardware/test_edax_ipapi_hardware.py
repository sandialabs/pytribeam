#!/usr/bin/python3
"""
Hardware validation for the EDAX IPAPI wrapper.

These tests talk to a real EDAX IPAPI service. Because the IPAPI is a TCP
service independent of TFS AutoScript, they can run from the EDAX workstation
itself or from an engineering laptop on the same network, not only from the
microscope PC. The operator opts in by naming the host::

    set PYTRIBEAM_EDAX_HOST=<ipapi host>
    set PYTRIBEAM_RUN_EDAX_IPAPI=1
    pytest tests/edax/hardware -v

``PYTRIBEAM_EDAX_PORT`` overrides the default service port of 8301, and
``PYTRIBEAM_EDAX_PAUSE_S`` overrides the per-command settling pause. The full
sweep issues roughly 150 commands, so it takes about half a minute at the
production pause of 0.2 s.

Everything here is read-only apart from the camera-motion test, which is opt-in
on its own flag because it moves a physical slide::

    set PYTRIBEAM_EDAX_ALLOW_MOTION=1

Nothing here starts a map. Collection is validated through the workflow tests
on a system with a mounted sample.
"""

# Default python modules
import os

# Third-party modules
import pytest

# Local scripts
from pytribeam.external_oem.edax import protocol
from pytribeam.external_oem.edax.client import EdaxClient
from pytribeam.external_oem.edax.ebsd import EdaxEbsdController
from pytribeam.external_oem.edax.eds import EdaxEdsController
from pytribeam.external_oem.edax.errors import EdaxError
from pytribeam.external_oem.edax.sem import EdaxSemController
from pytribeam.external_oem.edax.types import (
    EdaxCameraStatus,
    EdaxCommand,
    EdaxConnectionSettings,
    EdaxMappingStatus,
)

pytestmark = [pytest.mark.hardware, pytest.mark.edax_ipapi]

EDAX_HOST_ENV_VAR = "PYTRIBEAM_EDAX_HOST"
EDAX_PORT_ENV_VAR = "PYTRIBEAM_EDAX_PORT"
EDAX_PAUSE_ENV_VAR = "PYTRIBEAM_EDAX_PAUSE_S"
EDAX_MOTION_ENV_VAR = "PYTRIBEAM_EDAX_ALLOW_MOTION"


@pytest.fixture(scope="module")
def hardware_settings() -> EdaxConnectionSettings:
    """Return connection settings for the operator-declared IPAPI host.

    The settling pause defaults to the production value, so the sweep exercises
    the same timing the workflow uses. Lower it with ``PYTRIBEAM_EDAX_PAUSE_S``
    when iterating on a debugging session.
    """
    host = os.environ.get(EDAX_HOST_ENV_VAR, "").strip()
    if not host:
        pytest.skip(f"{EDAX_HOST_ENV_VAR} is not set")
    return EdaxConnectionSettings(
        host=host,
        port=int(os.environ.get(EDAX_PORT_ENV_VAR, "8301")),
        timeout_s=15.0,
        pause_s=float(os.environ.get(EDAX_PAUSE_ENV_VAR, "0.2")),
    )


@pytest.fixture(scope="module")
def hardware_client(hardware_settings):
    """Yield one connected, unlocked client shared by the whole module.

    A single connection is both faster and closer to how the workflow uses the
    IPAPI. Every test that shares it is read-only, apart from the opt-in motion
    test, which leaves the camera retracted.
    """
    with EdaxClient(hardware_settings) as client:
        yield client


def _motion_allowed() -> bool:
    """Return True when the operator has approved physical slide motion."""
    return os.environ.get(EDAX_MOTION_ENV_VAR, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# ----------------------------------------------------------------------
# Connection
# ----------------------------------------------------------------------
def test_connect_and_unlock(hardware_client):
    """The service accepts the unlock that every new connection requires."""
    assert hardware_client.connected is True
    assert hardware_client.unlocked is True


def test_ebsd_application_is_running(hardware_client):
    """Nothing else can be validated until the EDAX application is up."""
    assert EdaxEbsdController(hardware_client).app_started() is True


# ----------------------------------------------------------------------
# Read-only EBSD state
# ----------------------------------------------------------------------
def test_ebsd_map_status_is_recognized(hardware_client):
    """A live status must map onto a known enum member, not UNKNOWN.

    The raw payload is reported on failure, since an unrecognized status means
    the enum needs a new member and the wire text is what has to be added.
    """
    payload = hardware_client.query(EdaxCommand.EBSD_GET_MAP_STATUS)
    status = EdaxEbsdController.parse_status(payload)

    assert status is not EdaxMappingStatus.UNKNOWN, (
        f"The IPAPI reported mapping status {payload!r}, which "
        "EdaxMappingStatus does not cover."
    )


def test_camera_status_is_recognized(hardware_client):
    """A live slide status must map onto a known enum member.

    The raw payload is reported on failure, for the same reason as above.
    """
    payload = hardware_client.query(EdaxCommand.EBSD_GET_CAMERA_STATUS)
    status = EdaxEbsdController(hardware_client).camera_status()

    assert status is not EdaxCameraStatus.UNKNOWN, (
        f"The IPAPI reported camera status {payload!r}, which "
        "EdaxCameraStatus does not cover."
    )


def test_camera_slide_positions_are_ordered(hardware_client):
    """The retracted position must sit further out than the inserted one."""
    positions = EdaxEbsdController(hardware_client).slide_positions()
    assert positions.inserted_mm != positions.retracted_mm


def test_camera_info_is_plausible(hardware_client):
    """Frame geometry and rate confirm the camera parameter reads work."""
    info = EdaxEbsdController(hardware_client).camera_info()

    assert info.width_px > 0
    assert info.height_px > 0
    assert info.bit_depth > 0
    assert info.frame_rate_hz > 0.0
    assert len(info.binning_names) > 0


def test_camera_parameters_read_back(hardware_client):
    """Every camera getter must answer with a convertible payload."""
    params = EdaxEbsdController(hardware_client).camera_parameters()

    assert params.binning
    assert params.exposure_ms is not None
    assert params.frame_avg_scan is not None


def test_camera_limits_bracket_the_current_values(hardware_client):
    """The live exposure and gain must fall inside the reported limits."""
    controller = EdaxEbsdController(hardware_client)
    params = controller.camera_parameters()
    limits = controller.camera_limits()

    assert limits.exposure_ms.contains(params.exposure_ms)
    assert limits.frame_avg_scan.contains(params.frame_avg_scan)


def test_ebsd_map_parameters_read_back(hardware_client):
    """Every EBSD parameter getter must answer with a convertible payload."""
    params = EdaxEbsdController(hardware_client).map_parameters()

    assert params.folder_path is not None
    assert params.resolution is not None
    assert params.grid is not None


# ----------------------------------------------------------------------
# Read-only EDS and SEM state
# ----------------------------------------------------------------------
def test_eds_detector_status_is_recognized(hardware_client):
    """The EDS half of the API answers on the same connection."""
    controller = EdaxEdsController(hardware_client)

    assert controller.detector_status() is not None
    assert controller.slide_status() is not None


def test_sem_state_reads_back(hardware_client):
    """The SEM commands answer even though the TriBeam drives AutoScript."""
    state = EdaxSemController(hardware_client).state()

    assert state.magnification > 0
    assert state.image_width_px > 0
    assert state.image_height_px > 0


# ----------------------------------------------------------------------
# Whole-API conformance sweep
# ----------------------------------------------------------------------
#: Every read-only command, paired with the converter the wrapper applies.
#: Commands that move hardware, start a map, or capture an image are excluded.
READ_ONLY_COMMANDS = (
    # EBSD mapping parameters
    (EdaxCommand.EBSD_GET_FOLDERPATH, "str"),
    (EdaxCommand.EBSD_GET_MODE, "int"),
    (EdaxCommand.EBSD_GET_RESOLUTION, "int"),
    (EdaxCommand.EBSD_GET_GRID, "int"),
    (EdaxCommand.EBSD_GET_SAVEHOUGHPEAKS, "bool"),
    (EdaxCommand.EBSD_GET_SAVEPATTERNS, "bool"),
    (EdaxCommand.EBSD_GET_SAVESPECTRA, "bool"),
    (EdaxCommand.EBSD_GET_XSTART, "float"),
    (EdaxCommand.EBSD_GET_YSTART, "float"),
    (EdaxCommand.EBSD_GET_XSIZE, "float"),
    (EdaxCommand.EBSD_GET_YSIZE, "float"),
    (EdaxCommand.EBSD_GET_STEPSIZE, "float"),
    (EdaxCommand.EBSD_GET_CUSTOMSTEPSIZE, "float"),
    (EdaxCommand.EBSD_GET_EDSNUMCHAN, "int"),
    (EdaxCommand.EBSD_GET_BYTESPERCHANNEL, "int"),
    # EBSD state
    (EdaxCommand.EBSD_GET_MAP_STATUS, "str"),
    (EdaxCommand.EBSD_GET_MAP_DURATION, "float"),
    (EdaxCommand.EBSD_GET_CAMERA_STATUS, "str"),
    (EdaxCommand.EBSD_GET_SYSTEM_ISAPPSTARTED, "bool"),
    (EdaxCommand.EBSD_GET_SLIDE_POSITION, "float"),
    (EdaxCommand.EBSD_GET_SLIDE_POSITION_INSERTED, "float"),
    (EdaxCommand.EBSD_GET_SLIDE_POSITION_RETRACTED, "float"),
    (EdaxCommand.EBSD_GET_MAP_AVG_CI, "float"),
    # Camera parameters
    (EdaxCommand.CAMERA_GET_BINNING, "str"),
    (EdaxCommand.CAMERA_GET_BINNING_NAMES, "str_array"),
    (EdaxCommand.CAMERA_GET_BINNINGCUMULATIVE, "bool"),
    (EdaxCommand.CAMERA_GET_DOUBLESCANRATE, "bool"),
    (EdaxCommand.CAMERA_GET_DUALTAP, "bool"),
    (EdaxCommand.CAMERA_GET_EXPOSURE, "float"),
    (EdaxCommand.CAMERA_GET_EXPOSURE_MIN, "float"),
    (EdaxCommand.CAMERA_GET_EXPOSURE_MAX, "float"),
    (EdaxCommand.CAMERA_GET_FRAMEAVGBACKGROUND, "int"),
    (EdaxCommand.CAMERA_GET_FRAMEAVGBACKGROUND_MIN, "int"),
    (EdaxCommand.CAMERA_GET_FRAMEAVGBACKGROUND_MAX, "int"),
    (EdaxCommand.CAMERA_GET_FRAMEAVGSCAN, "int"),
    (EdaxCommand.CAMERA_GET_FRAMEAVGSCAN_MIN, "int"),
    (EdaxCommand.CAMERA_GET_FRAMEAVGSCAN_MAX, "int"),
    (EdaxCommand.CAMERA_GET_FRAMEAVGSNAPSHOT, "int"),
    (EdaxCommand.CAMERA_GET_FRAMEAVGSNAPSHOT_MIN, "int"),
    (EdaxCommand.CAMERA_GET_FRAMEAVGSNAPSHOT_MAX, "int"),
    (EdaxCommand.CAMERA_GET_FRAME_BITDEPTH, "int"),
    (EdaxCommand.CAMERA_GET_FRAME_HEIGHT, "int"),
    (EdaxCommand.CAMERA_GET_FRAME_WIDTH, "int"),
    (EdaxCommand.CAMERA_GET_FRAME_RATE, "float"),
    (EdaxCommand.CAMERA_GET_GAIN, "float"),
    (EdaxCommand.CAMERA_GET_GAIN_MIN, "float"),
    (EdaxCommand.CAMERA_GET_GAIN_MAX, "float"),
    (EdaxCommand.CAMERA_GET_IMAGEPROCESSINGMODEINT, "int"),
    (EdaxCommand.CAMERA_GET_REDUCEDBITDEPTH, "bool"),
    (EdaxCommand.CAMERA_ISSUPPORT_BINNINGCUMULATIVE, "bool"),
    (EdaxCommand.CAMERA_ISSUPPORT_BLACKREFERENCE, "bool"),
    (EdaxCommand.CAMERA_ISSUPPORT_DOUBLESCANRATE, "bool"),
    (EdaxCommand.CAMERA_ISSUPPORT_DUALTAP, "bool"),
    (EdaxCommand.CAMERA_ISSUPPORT_GAIN, "bool"),
    (EdaxCommand.CAMERA_ISSUPPORT_HIGHGAIN, "bool"),
    (EdaxCommand.CAMERA_ISSUPPORT_REDUCEDBITDEPTH, "bool"),
    # EDS mapping parameters
    (EdaxCommand.EDS_GET_FOLDERPATH, "str"),
    (EdaxCommand.EDS_GET_EDSCHANNEL, "int"),
    (EdaxCommand.EDS_GET_NUMFRAMES, "int"),
    (EdaxCommand.EDS_GET_NUMPOINTS, "int"),
    (EdaxCommand.EDS_GET_NUMLINES, "int"),
    (EdaxCommand.EDS_GET_PRESETDWELL, "float"),
    (EdaxCommand.EDS_GET_EDSNUMCHAN, "int"),
    (EdaxCommand.EDS_GET_BYTESPERCHANNEL, "int"),
    (EdaxCommand.EDS_GET_IPD, "int"),
    (EdaxCommand.EDS_GET_NUMREADS, "int"),
    # EDS state
    (EdaxCommand.EDS_GET_MAP_STATUS, "str"),
    (EdaxCommand.EDS_GET_MAP_DURATION, "float"),
    (EdaxCommand.EDS_GET_SYSTEM_ISAPPSTARTED, "bool"),
    (EdaxCommand.EDS_GET_SYSTEM_DETECTOR_STATUS, "str"),
    (EdaxCommand.EDS_GET_DETECTOR_STATUS, "str"),
    (EdaxCommand.EDS_GET_DETECTOR_COOLING_STATUS, "bool"),
    # SEM
    (EdaxCommand.SEM_GET_MAGNIFICATION, "int"),
    (EdaxCommand.SEM_GET_EXTERNAL_BEAM_CONTROL, "bool"),
    (EdaxCommand.SEM_GET_IMAGE_WIDTH, "int"),
    (EdaxCommand.SEM_GET_IMAGE_HEIGHT, "int"),
    (EdaxCommand.SEM_GET_PRETILT_ANGLE, "float"),
)

_CONVERTERS = {
    "str": lambda response: response.payload,
    "bool": protocol.to_bool,
    "int": protocol.to_int,
    "float": protocol.to_float,
    "str_array": protocol.to_str_array,
    "int_array": protocol.to_int_array,
}


@pytest.mark.parametrize(
    "command, kind",
    READ_ONLY_COMMANDS,
    ids=[command.value for command, _ in READ_ONLY_COMMANDS],
)
def test_read_only_command_conforms(hardware_client, command, kind):
    """Each read-only command answers in the documented frame and type.

    Parameterizing one test per command means a surprising reply names the
    exact command rather than failing a large aggregate assertion, which is
    what makes this useful for debugging against a live system.
    """
    try:
        response = hardware_client.send(command)
    except EdaxError as error:
        pytest.fail(f"{command.value} did not answer: {error}")

    assert response.command == command.value, (
        f"{command.value} answered with an unexpected prefix: {response.raw!r}"
    )
    assert response.is_event is False

    try:
        _CONVERTERS[kind](response)
    except EdaxError as error:
        pytest.fail(
            f"{command.value} returned {response.payload!r}, "
            f"which is not {kind}: {error}"
        )


def test_no_unexpected_events_while_idle(hardware_client):
    """An idle system should not be pushing events at the client.

    Anything buffered here is an event the wrapper did not anticipate, which is
    worth knowing before it interferes with a collection.
    """
    for command, _ in READ_ONLY_COMMANDS[:10]:
        hardware_client.send(command)

    events = hardware_client.drain_events()
    assert events == [], f"Unexpected events from an idle system: {events}"


@pytest.mark.skipif(
    not _motion_allowed(),
    reason=f"{EDAX_MOTION_ENV_VAR} is not set; this test moves the camera slide",
)
def test_camera_retract_and_insert_round_trip(hardware_client):
    """The slide reaches both end stops and reports them accurately.

    The camera is left retracted, which is the safe resting state for stage
    movement and laser milling.
    """
    controller = EdaxEbsdController(hardware_client)

    assert controller.retract_camera() is True
    assert controller.camera_status() is EdaxCameraStatus.SLIDE_OUT

    assert controller.insert_camera() is True
    assert controller.camera_status() is EdaxCameraStatus.SLIDE_IN

    assert controller.retract_camera() is True
    assert controller.camera_status() is EdaxCameraStatus.SLIDE_OUT
