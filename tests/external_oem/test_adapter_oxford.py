"""Oxford AZtec adapter, end to end against the in-process AZtec simulator.

No AZtec, .NET or Windows needed: `oxford.simulator` mimics the plugin API,
including detector motion, cooling, profiles, acquisitions and faults.
"""

import time

import pytest

pytest.importorskip("autoscript_sdb_microscope_client")

import pytribeam.external_oem.dispatch as external_devices  # noqa: E402
import pytribeam.types as tbt  # noqa: E402
from pytribeam.external_oem.adapters import oxford as oxford_adapter  # noqa: E402
from pytribeam.external_oem.core.errors import (  # noqa: E402
    ConfigurationError,
    DetectorError,
)
from pytribeam.external_oem.oxford.enums import (  # noqa: E402
    AcquisitionType,
    InsertionActivity,
    InsertionPositionState,
)
from pytribeam.external_oem.oxford.models import EdInsertionState  # noqa: E402
from pytribeam.external_oem.oxford.session import AztecSession  # noqa: E402
from pytribeam.external_oem.oxford.simulator import Simulator  # noqa: E402
from tests.external_oem.helpers import (  # noqa: E402
    EBSD,
    EDS,
    MICROSCOPE,
    OEM,
    STATE,
    general_settings,
)

EBSD_PROFILE = "EBSD 1um step"
EDS_PROFILE = "EDS 512px 50us"


SETTINGS = general_settings(
    OEM.OXFORD,
    OEM.OXFORD,
    Oxford_settings=tbt.OxfordConfig(
        connection=tbt.MicroscopeConnection(host="aztec-pc", port=22201)
    ),
)


def _oxford(profile):
    return None if profile is None else tbt.OxfordStepSettings(profile=profile)


def ebsd_settings(enable_eds=False, profile=EBSD_PROFILE) -> tbt.EBSDSettings:
    """An EBSD step naming its AZtec profile (the simulator has this one)."""
    return tbt.EBSDSettings(image=None, enable_eds=enable_eds, oxford=_oxford(profile))


def eds_settings(profile=EDS_PROFILE) -> tbt.EDSSettings:
    """An EDS step naming its AZtec profile (the simulator has this one)."""
    return tbt.EDSSettings(image=None, oxford=_oxford(profile))


@pytest.fixture
def sim(monkeypatch, chamber):
    """A fast simulator; every adapter call opens a new session on it."""
    simulator = Simulator(
        acquisition_seconds=0.05,
        progress_steps=2,
        event_delay_s=0.001,
        ebsd_speed_mm_s=100000.0,
        eds_move_s=0.01,
        eds_cool_s=0.01,
    )
    sessions = []

    def factory(general_settings):
        session = AztecSession.simulated(simulator)
        sessions.append(session)
        return session

    monkeypatch.setattr(oxford_adapter, "session_factory", factory)
    simulator.sessions = sessions
    simulator.chamber = chamber
    return simulator


def all_disconnected(sim):
    return all(not session.is_connected for session in sim.sessions)


class TestFullFlow:
    """What the dispatcher does for one slice, in order."""

    def test_ebsd_with_concurrent_eds(self, sim):
        step = ebsd_settings(enable_eds=True)

        assert oxford_adapter.test_connection(SETTINGS, EBSD)
        assert oxford_adapter.get_ebsd_camera_state(SETTINGS) == STATE.RETRACTED
        assert oxford_adapter.preflight_ebsd(SETTINGS, [step])
        assert oxford_adapter.set_ebsd_parameters(SETTINGS, step)
        assert sim.loaded_profile == EBSD_PROFILE

        assert oxford_adapter.insert_ebsd_camera(MICROSCOPE, SETTINGS)
        assert oxford_adapter.insert_eds_detector(MICROSCOPE, SETTINGS)
        assert oxford_adapter.get_ebsd_camera_state(SETTINGS) == STATE.INSERTED
        assert oxford_adapter.get_eds_detector_state(SETTINGS) == STATE.INSERTED

        assert oxford_adapter.map_ebsd(SETTINGS, step, 7, print)

        assert oxford_adapter.retract_ebsd_camera(MICROSCOPE, SETTINGS)
        assert oxford_adapter.retract_eds_detector(MICROSCOPE, SETTINGS)
        assert oxford_adapter.get_ebsd_camera_state(SETTINGS) == STATE.RETRACTED
        assert oxford_adapter.get_eds_detector_state(SETTINGS) == STATE.RETRACTED

        # Motion safety is the dispatcher's job; the adapter only moves.
        assert sim.chamber.events == []
        assert sim.chamber.checked == []
        assert all_disconnected(sim)

    def test_eds(self, sim):
        step = eds_settings()

        assert oxford_adapter.preflight_eds(SETTINGS, [step])
        assert oxford_adapter.set_eds_parameters(SETTINGS, step)
        assert sim.loaded_profile == EDS_PROFILE
        assert oxford_adapter.insert_eds_detector(MICROSCOPE, SETTINGS)
        assert oxford_adapter.map_eds(SETTINGS, step, 1, print)
        assert oxford_adapter.retract_eds_detector(MICROSCOPE, SETTINGS)
        assert all_disconnected(sim)


class TestThroughTheDispatcher:
    """The dispatcher guards the adapter's moves: collision check and CCD."""

    def test_insert_and_retract_are_guarded(self, sim):
        assert external_devices.insert_ebsd_camera(MICROSCOPE, SETTINGS)
        assert external_devices.retract_ebsd_camera(MICROSCOPE, SETTINGS)

        assert sim.chamber.events == ["ccd_on", "ccd_off"] * 2
        assert [detector for detector, _ in sim.chamber.checked] == [
            tbt.DetectorType.EBSD
        ]

    def test_a_possible_collision_never_reaches_the_adapter(self, sim):
        sim.chamber.collide = True

        with pytest.raises(DetectorError, match="collide"):
            external_devices.insert_ebsd_camera(MICROSCOPE, SETTINGS)
        assert oxford_adapter.get_ebsd_camera_state(SETTINGS) == STATE.RETRACTED
        assert sim.chamber.events == []

    def test_touch_during_insert_still_closes_the_ccd(self, sim):
        sim.ebsd.touch_at_mm = 50.0

        with pytest.raises(DetectorError):
            external_devices.insert_ebsd_camera(MICROSCOPE, SETTINGS)
        assert sim.chamber.events == ["ccd_on", "ccd_off"]
        assert all_disconnected(sim)

    def test_stage_guard_sees_an_inserted_camera(self, sim):
        external_devices.insert_ebsd_camera(MICROSCOPE, SETTINGS)

        with pytest.raises(DetectorError, match="EBSD is INSERTED"):
            external_devices.check_safe_for_stage_motion(SETTINGS)
        external_devices.retract_ebsd_camera(MICROSCOPE, SETTINGS)
        assert external_devices.check_safe_for_stage_motion(SETTINGS)


class TestMotion:
    def test_already_inserted_does_not_move(self, sim):
        oxford_adapter.insert_eds_detector(MICROSCOPE, SETTINGS)
        sim.chamber.events.clear()

        assert oxford_adapter.insert_eds_detector(MICROSCOPE, SETTINGS)
        assert sim.chamber.events == []

    def test_touch_during_insert_raises_and_stops(self, sim):
        sim.ebsd.touch_at_mm = 50.0

        with pytest.raises(DetectorError):
            oxford_adapter.insert_ebsd_camera(MICROSCOPE, SETTINGS)
        assert all_disconnected(sim)

    def test_faulted_camera_reads_error_and_is_not_inserted(self, sim):
        sim.ebsd.fault = True

        assert oxford_adapter.get_ebsd_camera_state(SETTINGS) == STATE.ERROR
        with pytest.raises(DetectorError, match="will not be inserted"):
            oxford_adapter.insert_ebsd_camera(MICROSCOPE, SETTINGS)
        assert sim.chamber.events == []

    def test_insert_refused_while_acquiring(self, sim, monkeypatch):
        monkeypatch.setattr(
            oxford_adapter, "_require_idle", _raise(DetectorError("already running"))
        )

        with pytest.raises(DetectorError, match="already running"):
            oxford_adapter.insert_ebsd_camera(MICROSCOPE, SETTINGS)
        assert sim.chamber.events == []


def _raise(error):
    def fail(*args, **kwargs):
        raise error

    return fail


class TestStateTranslation:
    @pytest.mark.parametrize(
        "position, activity, expected",
        [
            (InsertionPositionState.IN, InsertionActivity.NOT_MOVING, STATE.INSERTED),
            (InsertionPositionState.OUT, InsertionActivity.NOT_MOVING, STATE.RETRACTED),
            (
                InsertionPositionState.AUTO_RETRACTED,
                InsertionActivity.NOT_MOVING,
                STATE.RETRACTED,
            ),
            (InsertionPositionState.OUT, InsertionActivity.MOVING_IN, STATE.BUSY),
            (InsertionPositionState.FAULT, InsertionActivity.MOVING_IN, STATE.ERROR),
            (
                InsertionPositionState.INTERMEDIATE,
                InsertionActivity.NOT_MOVING,
                STATE.INDERTERMINATE,
            ),
            (
                InsertionPositionState.UNKNOWN,
                InsertionActivity.UNKNOWN,
                STATE.INDERTERMINATE,
            ),
        ],
    )
    def test_device_state(self, position, activity, expected):
        state = EdInsertionState(
            activity=activity,
            state=position,
            can_drive_in=True,
            can_drive_out=True,
            can_stop=True,
        )
        assert oxford_adapter.device_state(state) == expected


class TestPreflight:
    def test_eds_must_be_cold(self, sim):
        sim.eds._cold_at = time.monotonic() + 3600

        with pytest.raises(DetectorError, match="not COLD"):
            oxford_adapter.preflight_eds(SETTINGS, [eds_settings()])

    def test_concurrent_eds_must_be_cold(self, sim):
        sim.eds._cold_at = time.monotonic() + 3600

        assert oxford_adapter.preflight_ebsd(SETTINGS, [ebsd_settings()])
        with pytest.raises(DetectorError, match="not COLD"):
            oxford_adapter.preflight_ebsd(SETTINGS, [ebsd_settings(enable_eds=True)])

    def test_preflight_does_not_need_the_detector_inserted(self, sim):
        """AZtec only reports ready once inserted, so preflight can't require it."""
        assert oxford_adapter.preflight_ebsd(SETTINGS, [ebsd_settings()])

    @pytest.mark.parametrize(
        "preflight, step",
        [
            (oxford_adapter.preflight_ebsd, lambda: ebsd_settings(profile=None)),
            (oxford_adapter.preflight_eds, lambda: eds_settings(profile=None)),
        ],
    )
    def test_every_step_must_name_a_profile(self, sim, preflight, step):
        with pytest.raises(ConfigurationError, match="oxford_settings"):
            preflight(SETTINGS, [step()])

    def test_unreachable_aztec(self, sim):
        sim.refuse_connections = True

        with pytest.raises(DetectorError):
            oxford_adapter.test_connection(SETTINGS, EBSD)

    def test_missing_detector(self, monkeypatch, chamber):
        simulator = Simulator(with_eds=False)
        monkeypatch.setattr(
            oxford_adapter,
            "session_factory",
            lambda general_settings: AztecSession.simulated(simulator),
        )

        assert oxford_adapter.test_connection(SETTINGS, EBSD)
        with pytest.raises(DetectorError):
            oxford_adapter.test_connection(SETTINGS, EDS)


class TestParameters:
    def test_unknown_profile_lists_the_available_ones(self, sim):
        with pytest.raises(ConfigurationError, match=EDS_PROFILE):
            oxford_adapter.set_ebsd_parameters(
                SETTINGS, ebsd_settings(profile="no such profile")
            )
        assert sim.loaded_profile is None

    def test_each_step_loads_its_own_profile(self, sim):
        """Steps can differ: two EBSD steps with different profiles."""
        oxford_adapter.set_ebsd_parameters(SETTINGS, ebsd_settings(profile=EDS_PROFILE))
        assert sim.loaded_profile == EDS_PROFILE

        oxford_adapter.set_ebsd_parameters(SETTINGS, ebsd_settings())
        assert sim.loaded_profile == EBSD_PROFILE


class TestMaps:
    def test_map_requires_aztec_readiness(self, sim):
        """With the camera retracted AZtec is not ready; the map says why."""
        with pytest.raises(DetectorError, match="not inserted"):
            oxford_adapter.map_ebsd(SETTINGS, ebsd_settings(), 1, print)

    def test_failed_acquisition_raises(self, sim):
        oxford_adapter.insert_eds_detector(MICROSCOPE, SETTINGS)
        sim.fail_next_acquisition = "beam blanked"

        with pytest.raises(DetectorError, match="beam blanked"):
            oxford_adapter.map_eds(SETTINGS, eds_settings(), 1, print)
        assert all_disconnected(sim)

    @pytest.mark.parametrize(
        "step, expected",
        [
            (ebsd_settings(), AcquisitionType.EBSD_MAP),
            (
                ebsd_settings(enable_eds=True),
                AcquisitionType.EBSD_MAP | AcquisitionType.EDS_MAP,
            ),
            (eds_settings(), AcquisitionType.EDS_MAP),
        ],
    )
    def test_acquisition_type(self, step, expected):
        assert oxford_adapter._acquisition_type(step) == expected

    def test_map_name(self):
        assert oxford_adapter.map_name(7) == "slice_0007"
