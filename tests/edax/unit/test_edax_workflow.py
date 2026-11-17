#!/usr/bin/python3
"""
Unit tests for the AutoScript-bound EDAX glue: EDS detector motion and setup.

Moving the EDS detector over the IPAPI replaces LaserControl's insert_EDS, so
these pin down that every safeguard carried over: the CBS collision check, the
live chamber CCD view around the move, refusing while a map runs, and refusing
to insert a detector whose position cannot be read.

The IPAPI is the fake service; the microscope's CCD calls and collision check
are replaced with recorders, so no microscope is needed, but AutoScript must
import.
"""

# Default python modules
from types import SimpleNamespace

# Third-party modules
import pytest

pytest.importorskip("autoscript_sdb_microscope_client")

# Local scripts
from helpers import FakeIpapi  # noqa: E402
import pytribeam.external_oem.edax.workflow as edax_workflow  # noqa: E402
import pytribeam.insertable_devices as devices  # noqa: E402
import pytribeam.types as tbt  # noqa: E402
from pytribeam.external_oem.edax.client import EdaxClient  # noqa: E402
from pytribeam.external_oem.edax.errors import EdaxStateError  # noqa: E402
from pytribeam.external_oem.edax.types import EdaxCommand  # noqa: E402

INSERT = EdaxCommand.EDS_INSERT_DETECTOR.value
RETRACT = EdaxCommand.EDS_RETRACT_DETECTOR.value

SETTINGS = SimpleNamespace(
    EDAX_settings=SimpleNamespace(
        save_directory="D:/EDAX Data/exp1",
        project_name="exp1",
        connection=SimpleNamespace(host="edax-pc", port=8301),
    ),
    max_slice_number=200,
    slice_thickness_um=1.5,
)


@pytest.fixture
def rig(monkeypatch):
    """Wire the glue to a fake IPAPI and record CCD and collision calls.

    Returns a namespace whose ``script`` sets the fake service's payloads, and
    whose ``events`` interleave CCD view/pause with commands sent, in order.
    """
    rig = SimpleNamespace(service=None, events=[], collide=False)

    def script(**payloads):
        rig.service = FakeIpapi(payloads=payloads)
        original = rig.service.sendall

        def spy(data):
            rig.events.append(data.decode("ascii").split(" ", 1)[0])
            original(data)

        rig.service.sendall = spy

    rig.script = script
    monkeypatch.setattr(
        edax_workflow,
        "EdaxClient",
        lambda settings, quiet=False: EdaxClient(
            settings._replace(pause_s=0.0, timeout_s=0.5),
            sock=rig.service,
            quiet=True,
        ),
    )
    monkeypatch.setattr(
        devices, "CCD_view", lambda microscope, quad: rig.events.append("<ccd view>")
    )
    monkeypatch.setattr(
        devices, "CCD_pause", lambda microscope, quad: rig.events.append("<ccd pause>")
    )
    monkeypatch.setattr(
        devices,
        "detectors_will_collide",
        lambda microscope, detector_to_insert: rig.collide,
    )
    return rig


def _between_ccd(events, command):
    """Return True when a command was sent with the CCD view live."""
    index = events.index(command)
    before = [e for e in events[:index] if e.startswith("<ccd")]
    after = [e for e in events[index:] if e.startswith("<ccd")]
    return before[-1:] == ["<ccd view>"] and after[:1] == ["<ccd pause>"]


# ----------------------------------------------------------------------
# Insertion
# ----------------------------------------------------------------------
def test_insert_moves_the_detector_under_the_live_ccd(rig, no_sleep):
    # Read by the glue, re-read by the controller before moving, then polled.
    rig.script(
        get_eds_detector_status=["0", "0", "1"],
        get_map_status="Ready",
    )

    assert edax_workflow.insert_eds_detector(SETTINGS, microscope=None)
    assert _between_ccd(rig.events, INSERT)


def test_insert_refuses_a_possible_collision(rig):
    """The CBS check runs before anything reaches the IPAPI."""
    rig.collide = True
    rig.script(get_eds_detector_status="0", get_map_status="Ready")

    with pytest.raises(SystemError, match="collide"):
        edax_workflow.insert_eds_detector(SETTINGS, microscope=None)
    assert rig.events == []


def test_insert_is_a_no_op_when_already_inserted(rig):
    """No move means no CCD view either."""
    rig.script(get_eds_detector_status="1")

    assert edax_workflow.insert_eds_detector(SETTINGS, microscope=None)
    assert INSERT not in rig.events
    assert "<ccd view>" not in rig.events


def test_insert_refuses_an_unreadable_position(rig):
    """A move that cannot be confirmed is not attempted."""
    rig.script(get_eds_detector_status="100")

    with pytest.raises(EdaxStateError, match="cannot report"):
        edax_workflow.insert_eds_detector(SETTINGS, microscope=None)
    assert INSERT not in rig.events


def test_insert_refuses_while_a_map_is_running(rig):
    """Carried over from LaserControl's insert_EDS."""
    rig.script(get_eds_detector_status="0", get_map_status="MappingActive")

    with pytest.raises(EdaxStateError, match="running"):
        edax_workflow.insert_eds_detector(SETTINGS, microscope=None)
    assert INSERT not in rig.events


# ----------------------------------------------------------------------
# Retraction
# ----------------------------------------------------------------------
def test_retract_moves_the_detector_under_the_live_ccd(rig, no_sleep):
    rig.script(get_eds_detector_status=["1", "1", "0"])

    assert edax_workflow.retract_eds_detector(SETTINGS, microscope=None)
    assert _between_ccd(rig.events, RETRACT)


def test_retract_proceeds_when_the_position_is_unreadable(rig, no_sleep):
    """Retraction is the safe direction, so an unknown position does not block it."""
    rig.script(get_eds_detector_status=["100", "100", "0"])

    assert edax_workflow.retract_eds_detector(SETTINGS, microscope=None)
    assert _between_ccd(rig.events, RETRACT)


def test_retract_is_a_no_op_when_already_retracted(rig):
    rig.script(get_eds_detector_status="0")

    assert edax_workflow.retract_eds_detector(SETTINGS, microscope=None)
    assert RETRACT not in rig.events
    assert "<ccd view>" not in rig.events


def test_ccd_is_paused_when_the_move_fails(rig, no_sleep):
    """A failed retraction must not leave the CCD illumination on."""
    rig.script(
        get_eds_detector_status="1",
        do_retract_eds_detector="Execution Failed",
    )

    with pytest.raises(Exception):
        edax_workflow.retract_eds_detector(SETTINGS, microscope=None)
    assert rig.events[-1] == "<ccd pause>"


# ----------------------------------------------------------------------
# Position, setup, and mapping
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload, expected",
    [
        ("1", tbt.RetractableDeviceState.INSERTED),
        ("0", tbt.RetractableDeviceState.RETRACTED),
        ("100", tbt.RetractableDeviceState.INDERTERMINATE),
    ],
)
def test_detector_state_maps_to_the_generic_states(rig, payload, expected):
    """The workflow raises only on ERROR, so an unknown position must not be one."""
    rig.script(get_eds_detector_status=payload)
    assert edax_workflow.eds_detector_state(SETTINGS) is expected


def test_preflight_points_eds_at_the_experiment_folder(rig):
    rig.script(get_system_isappstarted="True", get_system_detector_status="Ready")

    assert edax_workflow.preflight_eds(SETTINGS)
    assert rig.service.arguments_for(EdaxCommand.EDS_SET_SYSTEM_REMOTEACCESSTYPE) == [
        '"1"'
    ]
    assert "exp1" in rig.service.arguments_for(EdaxCommand.EDS_SET_FOLDERPATH)[0]


def test_map_uses_the_eds_tag_for_the_slice(rig, no_sleep):
    rig.script(
        get_system_detector_status="Ready",
        get_map_duration="0",
        get_map_status="MappingComplete",
        # The size, frames, and dwell the EDS duration is predicted from.
        get_map_params_numpoints="64",
        get_map_params_numframes="1",
        get_map_params_presetdwell="0",
    )

    result = edax_workflow.map_eds(SETTINGS, step_settings=None, slice_number=12)

    assert result.tag == "Slice_0012_EDS"
    assert rig.service.arguments_for(EdaxCommand.EDS_COLLECTION_START) == [
        '"Slice_0012_EDS"'
    ]
