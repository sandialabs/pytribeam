"""TFS LaserControl adapter: forwards to the existing LaserControl functions."""

from types import SimpleNamespace

import pytest

pytest.importorskip("autoscript_sdb_microscope_client")

import pytribeam.insertable_devices as devices  # noqa: E402
import pytribeam.laser as fs_laser  # noqa: E402
import pytribeam.types as tbt  # noqa: E402
from pytribeam.external_oem.adapters import tfs_laser  # noqa: E402
from pytribeam.external_oem.core.errors import DetectorError  # noqa: E402
from tests.external_oem.helpers import (  # noqa: E402
    EBSD,
    EDS,
    MICROSCOPE,
    OEM,
    STATE,
    ebsd_settings,
    eds_settings,
    general_settings,
)

SETTINGS = general_settings(OEM.OXFORD, OEM.OXFORD)


@pytest.fixture
def laser_control(monkeypatch):
    """Replace LaserControl and the functions wrapping it with recorders."""
    calls = []
    status = {"ebsd": "Idle", "eds": "Idle"}
    external = SimpleNamespace(
        EBSD_MappingStatus=lambda: status["ebsd"],
        EDS_MappingStatus=lambda: status["eds"],
    )
    monkeypatch.setattr(devices, "external", external)

    def recorder(name, result=True):
        def record(*args, **kwargs):
            calls.append((name, kwargs))
            if isinstance(result, BaseException):
                raise result
            return result

        return record

    def install(module, name, result=True):
        monkeypatch.setattr(module, name, recorder(name, result))

    install(fs_laser, "laser_connected")
    install(fs_laser, "map_ebsd")
    install(fs_laser, "map_eds")
    install(devices, "connect_EBSD", STATE.RETRACTED)
    install(devices, "connect_EDS", STATE.INSERTED)
    for name in ("insert_EBSD", "insert_EDS", "retract_EBSD", "retract_EDS"):
        install(devices, name)
    return SimpleNamespace(
        calls=calls, status=status, install=lambda *a: install(*a), external=external
    )


def names(calls):
    return [name for name, _ in calls]


class TestForwarding:
    def test_state(self, laser_control):
        assert tfs_laser.get_ebsd_camera_state(SETTINGS) == STATE.RETRACTED
        assert tfs_laser.get_eds_detector_state(SETTINGS) == STATE.INSERTED

    def test_motion_passes_the_microscope(self, laser_control):
        assert tfs_laser.insert_ebsd_camera(MICROSCOPE, SETTINGS)
        assert tfs_laser.insert_eds_detector(MICROSCOPE, SETTINGS)
        assert tfs_laser.retract_ebsd_camera(MICROSCOPE, SETTINGS)
        assert tfs_laser.retract_eds_detector(MICROSCOPE, SETTINGS)

        assert laser_control.calls == [
            (name, {"microscope": MICROSCOPE})
            for name in ("insert_EBSD", "insert_EDS", "retract_EBSD", "retract_EDS")
        ]

    def test_maps(self, laser_control):
        assert tfs_laser.map_ebsd(SETTINGS, ebsd_settings(), 1, print)
        assert tfs_laser.map_eds(SETTINGS, eds_settings(), 1, print)
        assert names(laser_control.calls) == ["map_ebsd", "map_eds"]

    def test_parameters_cannot_be_set_and_are_accepted(self, laser_control):
        assert tfs_laser.set_ebsd_parameters(SETTINGS, ebsd_settings())
        assert tfs_laser.set_eds_parameters(SETTINGS, eds_settings())
        assert laser_control.calls == []


class TestConnection:
    @pytest.mark.parametrize(
        "technique, probe", [(EBSD, "connect_EBSD"), (EDS, "connect_EDS")]
    )
    def test_checks_laser_control_then_the_technique(
        self, laser_control, technique, probe
    ):
        assert tfs_laser.test_connection(SETTINGS, technique)
        assert names(laser_control.calls) == ["laser_connected", probe]

    def test_laser_control_down(self, laser_control):
        laser_control.install(fs_laser, "laser_connected", False)

        assert tfs_laser.test_connection(SETTINGS, EBSD) is False

    def test_technique_unreachable_is_a_detector_error(self, laser_control):
        laser_control.install(devices, "connect_EDS", ConnectionError("not open"))

        with pytest.raises(DetectorError, match="not open"):
            tfs_laser.test_connection(SETTINGS, EDS)


class TestPreflight:
    def test_idle_mapping_passes_and_notes_parameters(self, laser_control, capsys):
        assert tfs_laser.preflight_ebsd(SETTINGS, [ebsd_settings()])
        assert "cannot set EBSD parameters" in capsys.readouterr().out

    def test_busy_mapping_is_refused(self, laser_control):
        laser_control.status["eds"] = "Active"

        with pytest.raises(DetectorError, match="EDS mapping is 'Active'"):
            tfs_laser.preflight_eds(SETTINGS, [eds_settings()])

    def test_missing_laser_api(self, laser_control, monkeypatch):
        monkeypatch.setattr(devices, "external", None)

        with pytest.raises(DetectorError, match="LaserControl is not available"):
            tfs_laser.preflight_ebsd(SETTINGS, [])
        with pytest.raises(DetectorError, match="LaserControl is not available"):
            tfs_laser.map_ebsd(SETTINGS, ebsd_settings(), 1, print)


class TestErrorTranslation:
    @pytest.mark.parametrize(
        "name, call",
        [
            ("insert_EBSD", lambda: tfs_laser.insert_ebsd_camera(MICROSCOPE, SETTINGS)),
            (
                "retract_EDS",
                lambda: tfs_laser.retract_eds_detector(MICROSCOPE, SETTINGS),
            ),
            ("connect_EBSD", lambda: tfs_laser.get_ebsd_camera_state(SETTINGS)),
        ],
    )
    def test_system_errors_become_detector_errors(self, laser_control, name, call):
        laser_control.install(devices, name, SystemError("camera in error state"))

        with pytest.raises(DetectorError, match="camera in error state"):
            call()

    def test_a_too_fast_map_is_a_detector_error(self, laser_control):
        laser_control.install(fs_laser, "map_eds", ValueError("minimum expected time"))

        with pytest.raises(DetectorError, match="minimum expected time"):
            tfs_laser.map_eds(SETTINGS, eds_settings(), 1, print)

    def test_unrelated_errors_are_not_masked(self, laser_control):
        laser_control.install(devices, "insert_EDS", KeyError("bug"))

        with pytest.raises(KeyError):
            tfs_laser.insert_eds_detector(MICROSCOPE, SETTINGS)


# ---------------------------------------------------------------
# Hardware: read-only checks through a live LaserControl install
# ---------------------------------------------------------------


class _LaserControlHardware:
    """Read-only: connection and detector state. Nothing moves."""

    OEM = None

    @pytest.mark.parametrize("technique", [EBSD, EDS], ids=["ebsd", "eds"])
    def test_connection(self, technique):
        assert tfs_laser.test_connection(
            general_settings(self.OEM, self.OEM), technique
        )

    def test_states_are_readable(self):
        settings = general_settings(self.OEM, self.OEM)
        for state in (
            tfs_laser.get_ebsd_camera_state(settings),
            tfs_laser.get_eds_detector_state(settings),
        ):
            assert isinstance(state, tbt.RetractableDeviceState)
            assert state != STATE.ERROR


# Markers are applied per class so conftest's per-vendor gating sees them.
@pytest.mark.hardware
@pytest.mark.laser_hardware
@pytest.mark.edax_hardware
class TestLaserControlHardwareEdax(_LaserControlHardware):
    OEM = OEM.EDAX


@pytest.mark.hardware
@pytest.mark.laser_hardware
@pytest.mark.oxford_hardware
class TestLaserControlHardwareOxford(_LaserControlHardware):
    OEM = OEM.OXFORD
