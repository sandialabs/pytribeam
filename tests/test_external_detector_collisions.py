"""Collision checks that involve the external EBSD/EDS detectors.

`insertable_devices.detectors_will_collide` reads the external detectors'
states from, in order: states passed by the caller, the source registered by
the external OEM dispatcher, then LaserControl. When none can report, the
detector is assumed to be in the way.
"""

from types import SimpleNamespace

import pytest

pytest.importorskip("autoscript_sdb_microscope_client")

import pytribeam.insertable_devices as devices  # noqa: E402
import pytribeam.types as tbt  # noqa: E402

CBS = tbt.DetectorType.CBS
EBSD = tbt.DetectorType.EBSD
EDS = tbt.DetectorType.EDS
STATE = tbt.RetractableDeviceState
MICROSCOPE = object()


@pytest.fixture
def sources(monkeypatch):
    """No registered source and no LaserControl, unless a test adds one."""
    monkeypatch.setattr(devices, "_external_state_source", None)
    monkeypatch.setattr(devices, "external", None)

    def laser_control(ebsd=STATE.RETRACTED, eds=STATE.RETRACTED):
        monkeypatch.setattr(
            devices,
            "external",
            SimpleNamespace(
                EBSD_CameraStatus=lambda: ebsd.value,
                EDS_CameraStatus=lambda: eds.value,
            ),
        )

    return SimpleNamespace(laser_control=laser_control)


def register(states):
    devices.set_external_detector_states(lambda: dict(states))


def system_detectors(monkeypatch, states):
    """Stand in for the microscope's insertable detectors and their states.

    Returns the list of microscopes it was asked about.
    """
    reads = []

    def available(microscope):
        reads.append(microscope)
        return list(states.items())

    monkeypatch.setattr(
        devices.img, "get_available_insertable_detector_states", available
    )
    return reads


class TestInsertingTheCbs:
    """The CBS collides with both external detectors."""

    def test_clear_when_both_report_retracted(self, sources):
        register({EBSD: STATE.RETRACTED, EDS: STATE.RETRACTED})

        assert devices.detectors_will_collide(MICROSCOPE, CBS) is False

    @pytest.mark.parametrize("detector", [EBSD, EDS])
    @pytest.mark.parametrize("state", [STATE.INSERTED, STATE.BUSY, STATE.ERROR])
    def test_blocked_by_an_external_detector(self, sources, detector, state):
        register({EBSD: STATE.RETRACTED, EDS: STATE.RETRACTED, detector: state})

        assert devices.detectors_will_collide(MICROSCOPE, CBS) is True

    def test_explicit_states_come_first(self, sources):
        register({EBSD: STATE.INSERTED, EDS: STATE.INSERTED})
        clear = {EBSD: STATE.RETRACTED, EDS: STATE.RETRACTED}

        assert (
            devices.detectors_will_collide(MICROSCOPE, CBS, external_states=clear)
            is False
        )

    def test_registered_source_comes_before_laser_control(self, sources):
        sources.laser_control(ebsd=STATE.INSERTED, eds=STATE.INSERTED)
        register({EBSD: STATE.RETRACTED, EDS: STATE.RETRACTED})

        assert devices.detectors_will_collide(MICROSCOPE, CBS) is False

    def test_laser_control_covers_detectors_the_source_lacks(self, sources):
        """A technique with no OEM is not in the dispatcher's states."""
        sources.laser_control(ebsd=STATE.RETRACTED, eds=STATE.INSERTED)
        register({EBSD: STATE.RETRACTED})

        assert devices.detectors_will_collide(MICROSCOPE, CBS) is True

    def test_laser_control_alone(self, sources):
        """Behaviour without any external OEM configured, as before."""
        sources.laser_control()

        assert devices.detectors_will_collide(MICROSCOPE, CBS) is False

    def test_unknown_state_is_assumed_in_the_way(self, sources):
        """Without LaserControl this used to raise AttributeError."""
        with pytest.warns(UserWarning, match="state is unknown"):
            assert devices.detectors_will_collide(MICROSCOPE, CBS) is True

    def test_a_failing_source_falls_back_and_warns(self, sources):
        def broken():
            raise RuntimeError("vendor offline")

        devices.set_external_detector_states(broken)
        sources.laser_control()

        with pytest.warns(UserWarning, match="vendor offline"):
            assert devices.detectors_will_collide(MICROSCOPE, CBS) is False


class TestInsertingAnExternalDetector:
    """EBSD and EDS collide with the CBS, read from the microscope."""

    @pytest.mark.parametrize(
        "cbs_state, expected", [(STATE.RETRACTED, False), (STATE.INSERTED, True)]
    )
    def test_checks_the_cbs(self, sources, monkeypatch, cbs_state, expected):
        system_detectors(monkeypatch, {CBS: cbs_state})

        assert devices.detectors_will_collide(MICROSCOPE, EBSD) is expected
        assert devices.detectors_will_collide(MICROSCOPE, EDS) is expected


class TestRetractAllDevices:
    @pytest.fixture
    def recorded(self, monkeypatch):
        import pytribeam.external_oem.dispatch as external_devices

        calls = []
        monkeypatch.setattr(
            devices,
            "retract_all_microscope_insertable_detectors",
            lambda microscope: calls.append("microscope") or True,
        )
        monkeypatch.setattr(
            external_devices,
            "retract_all_external_devices",
            lambda microscope, general_settings: (
                calls.append(("dispatcher", general_settings)) or True
            ),
        )
        for name in ("retract_EBSD", "retract_EDS"):
            monkeypatch.setattr(
                devices, name, lambda microscope, _n=name: calls.append(_n) or True
            )
        return calls

    def test_with_settings_external_detectors_go_through_the_dispatcher(
        self, sources, recorded
    ):
        settings = object()
        sources.laser_control()

        assert devices.retract_all_devices(
            MICROSCOPE, enable_EBSD=True, enable_EDS=True, general_settings=settings
        )
        assert recorded == ["microscope", ("dispatcher", settings)]

    def test_without_settings_laser_control_is_used(self, sources, recorded):
        sources.laser_control()

        assert devices.retract_all_devices(
            MICROSCOPE, enable_EBSD=True, enable_EDS=True
        )
        assert recorded == ["microscope", "retract_EBSD", "retract_EDS"]


class TestDeviceStatus:
    """The GUI's connection report uses the dispatcher when settings are known,
    and says which interface each EBSD/EDS status came from."""

    @staticmethod
    def settings(ebsd_oem, eds_oem, **blocks):
        from tests.external_oem.helpers import general_settings

        return general_settings(ebsd_oem, eds_oem, **blocks)

    def test_configured_detectors_come_from_the_dispatcher(self, monkeypatch):
        import pytribeam.external_oem.dispatch as external_devices
        import pytribeam.laser as laser

        settings = self.settings(
            tbt.ExternalDeviceOEM.NONE,
            tbt.ExternalDeviceOEM.OXFORD,
            Oxford_settings=tbt.OxfordConfig(
                connection=tbt.MicroscopeConnection(host="aztec-pc")
            ),
        )
        monkeypatch.setattr(laser, "laser_connected", lambda: False)
        monkeypatch.setattr(
            external_devices,
            "external_detector_states",
            lambda general_settings: {EDS: STATE.INSERTED},
        )

        status = laser._device_connections(general_settings=settings)

        assert status.eds == STATE.INSERTED
        assert status.ebsd == STATE.ERROR  # no OEM and LaserControl is down
        assert status.laser == STATE.ERROR
        assert status.sources == {"ebsd": "LaserControl", "eds": "Oxford AZtec"}
        assert 'EDS Detector (via Oxford AZtec): "' in str(status)
        assert 'EBSD Detector (via LaserControl): "' in str(status)

    @pytest.mark.parametrize(
        "oem, blocks, label",
        [
            (
                tbt.ExternalDeviceOEM.EDAX,
                {
                    "EDAX_settings": tbt.EDAXConfig(
                        save_directory="D:/x",
                        project_name="p",
                        connection=tbt.MicroscopeConnection(host="edax-pc"),
                    )
                },
                "EDAX IPAPI",
            ),
            (tbt.ExternalDeviceOEM.EDAX, {}, "LaserControl"),
            (
                tbt.ExternalDeviceOEM.BRUKER,
                {"Bruker_settings": tbt.BrukerConfig(dll_dir="C:/Esprit")},
                "Bruker ESPRIT",
            ),
        ],
    )
    def test_each_backend_is_named(self, monkeypatch, oem, blocks, label):
        import pytribeam.external_oem.dispatch as external_devices
        import pytribeam.laser as laser

        monkeypatch.setattr(laser, "laser_connected", lambda: False)
        monkeypatch.setattr(
            external_devices,
            "external_detector_states",
            lambda general_settings: {EBSD: STATE.RETRACTED, EDS: STATE.RETRACTED},
        )

        status = laser._device_connections(
            general_settings=self.settings(oem, oem, **blocks)
        )

        assert status.sources == {"ebsd": label, "eds": label}

    def test_without_settings_laser_control_is_used(self, monkeypatch):
        import pytribeam.laser as laser

        monkeypatch.setattr(laser, "laser_connected", lambda: True)
        monkeypatch.setattr(devices, "connect_EBSD", lambda: STATE.RETRACTED)
        monkeypatch.setattr(devices, "connect_EDS", lambda: STATE.INSERTED)

        status = laser._device_connections()

        assert (status.ebsd, status.eds) == (STATE.RETRACTED, STATE.INSERTED)
        assert status.sources == {"ebsd": "LaserControl", "eds": "LaserControl"}

    def test_text_without_sources_is_unchanged(self):
        status = tbt.DeviceStatus(
            laser=STATE.CONNECTED, ebsd=STATE.RETRACTED, eds=STATE.RETRACTED
        )

        assert "via" not in str(status)


def test_every_backend_has_a_label():
    assert {b.label for b in tbt.ExternalBackend} == {
        "LaserControl",
        "EDAX IPAPI",
        "Oxford AZtec",
        "Bruker ESPRIT",
    }


class TestStageGuard:
    def test_step_start_refuses_to_move_past_an_inserted_detector(self, monkeypatch):
        import pytribeam.external_oem.dispatch as external_devices
        import pytribeam.stage as stage
        from pytribeam.external_oem.core.errors import DetectorError

        moves = []
        monkeypatch.setattr(
            stage,
            "target_position",
            lambda *a, **k: SimpleNamespace(
                x_mm=0.0, y_mm=0.0, z_mm=0.0, r_deg=0.0, t_deg=0.0
            ),
        )
        monkeypatch.setattr(stage, "move_to_position", lambda **k: moves.append(k))

        def blocked(general_settings):
            raise DetectorError("EBSD is INSERTED")

        monkeypatch.setattr(external_devices, "check_safe_for_stage_motion", blocked)
        settings = SimpleNamespace(slice_thickness_um=1.0, stage_tolerance=None)
        operation = SimpleNamespace(stage=None)

        with pytest.raises(DetectorError, match="INSERTED"):
            stage.step_start_position(
                microscope=MICROSCOPE,
                slice_number=1,
                operation=operation,
                general_settings=settings,
            )
        assert moves == []

        monkeypatch.setattr(
            external_devices,
            "check_safe_for_stage_motion",
            lambda general_settings: True,
        )
        stage.step_start_position(
            microscope=MICROSCOPE,
            slice_number=1,
            operation=operation,
            general_settings=settings,
        )
        assert len(moves) == 1


class TestAbsentMicroscopeDetectors:
    """Microscope detectors come from the system's insertable detectors.

    Reported from a simulator with no CBS: EDS insertion was refused.
    """

    @pytest.mark.parametrize("insert", [EDS, EBSD])
    def test_no_insertable_detectors_means_nothing_to_check(
        self, sources, monkeypatch, insert
    ):
        system_detectors(monkeypatch, {})

        assert devices.detectors_will_collide(MICROSCOPE, insert) is False

    def test_other_insertable_detectors_do_not_matter(self, sources, monkeypatch):
        """Only the collision partners of the detector being inserted count."""
        system_detectors(monkeypatch, {tbt.DetectorType.ABS: STATE.INSERTED})

        assert devices.detectors_will_collide(MICROSCOPE, EDS) is False

    @pytest.mark.parametrize("state", [STATE.INSERTED, STATE.BUSY, STATE.ERROR])
    def test_a_present_cbs_must_be_retracted(self, sources, monkeypatch, state):
        system_detectors(monkeypatch, {CBS: state})

        assert devices.detectors_will_collide(MICROSCOPE, EDS) is True

    def test_the_system_is_read_once_and_only_when_needed(self, sources, monkeypatch):
        reads = system_detectors(monkeypatch, {CBS: STATE.RETRACTED})

        devices.detectors_will_collide(MICROSCOPE, EDS)
        assert reads == [MICROSCOPE]

        reads.clear()
        register({EBSD: STATE.RETRACTED, EDS: STATE.RETRACTED})
        devices.detectors_will_collide(MICROSCOPE, CBS)  # partners are external
        assert reads == []


class TestRetractionWithoutTheMicroscope:
    """After a step error the GUI stops the stage, which disconnects the
    microscope; the external detectors must still be retracted."""

    def test_external_detectors_are_retracted_when_the_microscope_part_fails(
        self, monkeypatch
    ):
        import pytribeam.external_oem.dispatch as external_devices

        retracted = []

        def broken(microscope):
            raise RuntimeError(
                "Cannot perform a call because the client is not running."
            )

        monkeypatch.setattr(
            devices, "retract_all_microscope_insertable_detectors", broken
        )
        monkeypatch.setattr(
            external_devices,
            "retract_all_external_devices",
            lambda microscope, general_settings: retracted.append(True) or True,
        )

        with pytest.raises(
            SystemError, match="microscope detectors.*client is not running"
        ):
            devices.retract_all_devices(
                MICROSCOPE, enable_EBSD=True, enable_EDS=True, general_settings=object()
            )
        assert retracted == [True]

    @pytest.fixture
    def broken_ccd(self, monkeypatch):
        def fail(microscope, quad=None):
            raise RuntimeError("client is not running")

        monkeypatch.setattr(devices, "CCD_view", fail)
        monkeypatch.setattr(devices, "CCD_pause", fail)

    def test_retraction_proceeds_without_the_ccd(self, broken_ccd):
        moved = []

        with pytest.warns(UserWarning, match="retracting without it"):
            with devices.ccd_live_view(MICROSCOPE, required=False):
                moved.append("retract")

        assert moved == ["retract"]

    def test_insertion_still_requires_the_ccd(self, broken_ccd):
        moved = []

        with pytest.raises(RuntimeError, match="client is not running"):
            with devices.ccd_live_view(MICROSCOPE):
                moved.append("insert")

        assert moved == []

    def test_the_ccd_is_paused_after_a_failed_move(self, monkeypatch):
        events = []
        monkeypatch.setattr(
            devices, "CCD_view", lambda microscope, quad=None: events.append("on")
        )
        monkeypatch.setattr(
            devices, "CCD_pause", lambda microscope, quad=None: events.append("off")
        )

        with pytest.raises(ValueError):
            with devices.ccd_live_view(MICROSCOPE, required=False):
                raise ValueError("slide stuck")

        assert events == ["on", "off"]
