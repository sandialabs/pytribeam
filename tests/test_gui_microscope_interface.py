# tests/test_gui_microscope_interface.py
"""Tests for :class:`pytribeam.GUI.config_ui.microscope_interface.MicroscopeInterface`
and related helper functions.
"""

from unittest.mock import MagicMock, patch, call
import pytest

from pytribeam.GUI.config_ui.microscope_interface import (
    MicroscopeInterface,
    format_stage_info,
    check_device_connections,
)
from pytribeam.GUI.common.errors import MicroscopeConnectionError


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def iface():
    """Return a disconnected MicroscopeInterface."""
    return MicroscopeInterface(host="localhost", port="")


@pytest.fixture
def connected_iface(monkeypatch):
    """Return a MicroscopeInterface that appears connected (microscope mocked)."""
    iface = MicroscopeInterface(host="localhost", port="7520")
    fake_microscope = MagicMock()
    iface._microscope = fake_microscope
    return iface


# ----------------------------------------------------------------------
# Initialization
# ----------------------------------------------------------------------
class TestInit:

    def test_default_host_port(self, iface):
        assert iface.host == "localhost"
        assert iface.port == ""

    def test_custom_host_port(self):
        mi = MicroscopeInterface(host="192.168.1.10", port="7520")
        assert mi.host == "192.168.1.10"
        assert mi.port == "7520"

    def test_initially_disconnected(self, iface):
        assert iface.is_connected is False
        assert iface.microscope is None


# ----------------------------------------------------------------------
# is_connected property
# ----------------------------------------------------------------------
class TestIsConnected:

    def test_false_when_no_microscope(self, iface):
        assert iface.is_connected is False

    def test_true_when_microscope_set(self, connected_iface):
        assert connected_iface.is_connected is True

    def test_false_after_disconnect(self, connected_iface, monkeypatch):
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.ut.disconnect_microscope",
            lambda m: None,
        )
        connected_iface.disconnect()
        assert connected_iface.is_connected is False


# ----------------------------------------------------------------------
# connect
# ----------------------------------------------------------------------
class TestConnect:

    def test_connect_success(self, iface, monkeypatch):
        fake_microscope = MagicMock()
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.tbt.Microscope",
            lambda: fake_microscope,
        )
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.ut.connect_microscope",
            lambda m, **kw: None,
        )
        iface.connect()
        assert iface.is_connected is True
        assert iface._microscope is fake_microscope

    def test_connect_when_already_connected_is_no_op(self, connected_iface, monkeypatch):
        original_microscope = connected_iface._microscope
        call_count = {"n": 0}

        def fake_connect(m, **kw):
            call_count["n"] += 1

        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.ut.connect_microscope",
            fake_connect,
        )
        connected_iface.connect()
        assert call_count["n"] == 0
        assert connected_iface._microscope is original_microscope

    def test_connect_failure_raises_connection_error(self, iface, monkeypatch):
        fake_microscope = MagicMock()
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.tbt.Microscope",
            lambda: fake_microscope,
        )
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.ut.connect_microscope",
            lambda m, **kw: (_ for _ in ()).throw(ConnectionError("refused")),
        )
        with pytest.raises(MicroscopeConnectionError) as exc_info:
            iface.connect()
        assert "Failed to connect" in str(exc_info.value)

    def test_connect_failure_clears_microscope(self, iface, monkeypatch):
        fake_microscope = MagicMock()
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.tbt.Microscope",
            lambda: fake_microscope,
        )
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.ut.connect_microscope",
            lambda m, **kw: (_ for _ in ()).throw(ConnectionError("refused")),
        )
        try:
            iface.connect()
        except MicroscopeConnectionError:
            pass
        assert iface._microscope is None


# ----------------------------------------------------------------------
# disconnect
# ----------------------------------------------------------------------
class TestDisconnect:

    def test_disconnect_clears_microscope(self, connected_iface, monkeypatch):
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.ut.disconnect_microscope",
            lambda m: None,
        )
        connected_iface.disconnect()
        assert connected_iface._microscope is None

    def test_disconnect_when_not_connected_does_nothing(self, iface):
        iface.disconnect()  # should not raise

    def test_disconnect_exception_does_not_propagate(self, connected_iface, monkeypatch):
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.ut.disconnect_microscope",
            lambda m: (_ for _ in ()).throw(RuntimeError("hardware error")),
        )
        connected_iface.disconnect()  # should not raise
        assert connected_iface._microscope is None


# ----------------------------------------------------------------------
# ensure_connected
# ----------------------------------------------------------------------
class TestEnsureConnected:

    def test_raises_when_not_connected(self, iface):
        with pytest.raises(MicroscopeConnectionError, match="Not connected"):
            iface.ensure_connected()

    def test_does_not_raise_when_connected(self, connected_iface):
        connected_iface.ensure_connected()  # should not raise


# ----------------------------------------------------------------------
# Context manager
# ----------------------------------------------------------------------
class TestContextManager:

    def test_enter_calls_connect(self, iface, monkeypatch):
        calls = []
        monkeypatch.setattr(iface, "connect", lambda: calls.append("connect"))
        monkeypatch.setattr(iface, "disconnect", lambda: calls.append("disconnect"))

        with iface:
            pass

        assert "connect" in calls
        assert "disconnect" in calls

    def test_exit_calls_disconnect_on_exception(self, iface, monkeypatch):
        calls = []
        monkeypatch.setattr(iface, "connect", lambda: None)
        monkeypatch.setattr(iface, "disconnect", lambda: calls.append("disconnect"))

        try:
            with iface:
                raise ValueError("inside context")
        except ValueError:
            pass

        assert "disconnect" in calls

    def test_exit_returns_false(self, iface, monkeypatch):
        monkeypatch.setattr(iface, "connect", lambda: None)
        monkeypatch.setattr(iface, "disconnect", lambda: None)

        result = iface.__exit__(None, None, None)
        assert result is False


# ----------------------------------------------------------------------
# get_stage_position
# ----------------------------------------------------------------------
class TestGetStagePosition:

    def test_raises_when_not_connected(self, iface):
        with pytest.raises(MicroscopeConnectionError):
            iface.get_stage_position()

    def test_returns_stage_position(self, connected_iface, monkeypatch):
        fake_pos = MagicMock()
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.factory.active_stage_position_settings",
            lambda m: fake_pos,
        )
        pos = connected_iface.get_stage_position()
        assert pos is fake_pos

    def test_wraps_exception_in_connection_error(self, connected_iface, monkeypatch):
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.factory.active_stage_position_settings",
            lambda m: (_ for _ in ()).throw(RuntimeError("hardware error")),
        )
        with pytest.raises(MicroscopeConnectionError, match="Failed to get stage position"):
            connected_iface.get_stage_position()


# ----------------------------------------------------------------------
# test_connection
# ----------------------------------------------------------------------
class TestTestConnection:

    def test_success(self, iface, monkeypatch):
        monkeypatch.setattr(iface, "connect", lambda: None)
        monkeypatch.setattr(iface, "disconnect", lambda: None)

        ok, msg = iface.test_connection()
        assert ok is True
        assert "successful" in msg.lower()

    def test_connection_error(self, iface, monkeypatch):
        monkeypatch.setattr(
            iface,
            "connect",
            lambda: (_ for _ in ()).throw(MicroscopeConnectionError("refused")),
        )
        ok, msg = iface.test_connection()
        assert ok is False
        assert "refused" in msg

    def test_unexpected_error(self, iface, monkeypatch):
        monkeypatch.setattr(
            iface,
            "connect",
            lambda: (_ for _ in ()).throw(RuntimeError("unexpected")),
        )
        ok, msg = iface.test_connection()
        assert ok is False
        assert "Unexpected error" in msg


# ----------------------------------------------------------------------
# get_working_distances
# ----------------------------------------------------------------------
class TestGetWorkingDistances:

    def test_raises_when_not_connected(self, iface):
        with pytest.raises(MicroscopeConnectionError):
            iface.get_working_distances()

    def test_wraps_exception(self, connected_iface, monkeypatch):
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.ut.beam_type",
            lambda beam, m: (_ for _ in ()).throw(RuntimeError("beam error")),
        )
        with pytest.raises(MicroscopeConnectionError, match="Failed to get working distances"):
            connected_iface.get_working_distances()


# ----------------------------------------------------------------------
# get_stage_info
# ----------------------------------------------------------------------
class TestGetStageInfo:

    def test_raises_when_not_connected(self, iface):
        with pytest.raises(MicroscopeConnectionError):
            iface.get_stage_info()

    def test_returns_combined_dict(self, connected_iface, monkeypatch):
        fake_pos = MagicMock(x_mm=1.0, y_mm=2.0, z_mm=3.0, r_deg=4.0, t_deg=5.0)
        fake_wds = {"electron_wd_mm": 6.0, "ion_wd_mm": 7.0}

        monkeypatch.setattr(connected_iface, "get_stage_position", lambda: fake_pos)
        monkeypatch.setattr(connected_iface, "get_working_distances", lambda: fake_wds)

        info = connected_iface.get_stage_info()
        assert info["x_mm"] == 1.0
        assert info["electron_wd_mm"] == 6.0

    def test_re_raises_connection_error(self, connected_iface, monkeypatch):
        monkeypatch.setattr(
            connected_iface,
            "get_stage_position",
            lambda: (_ for _ in ()).throw(MicroscopeConnectionError("pos error")),
        )
        monkeypatch.setattr(connected_iface, "get_working_distances", lambda: {})

        with pytest.raises(MicroscopeConnectionError):
            connected_iface.get_stage_info()


# ----------------------------------------------------------------------
# get_imaging_settings
# ----------------------------------------------------------------------
class TestGetImagingSettings:

    def test_raises_when_not_connected(self, iface):
        with pytest.raises(MicroscopeConnectionError):
            iface.get_imaging_settings()

    def test_returns_settings(self, connected_iface, monkeypatch):
        fake_settings = MagicMock()
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.factory.active_image_settings",
            lambda m: fake_settings,
        )
        result = connected_iface.get_imaging_settings()
        assert result is fake_settings

    def test_wraps_exception(self, connected_iface, monkeypatch):
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.factory.active_image_settings",
            lambda m: (_ for _ in ()).throw(RuntimeError("image error")),
        )
        with pytest.raises(MicroscopeConnectionError, match="Failed to get imaging settings"):
            connected_iface.get_imaging_settings()


# ----------------------------------------------------------------------
# get_laser_state
# ----------------------------------------------------------------------
class TestGetLaserState:

    def test_returns_state(self, iface, monkeypatch):
        fake_state = MagicMock()
        fake_db = {"power": 10}
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.factory.active_laser_state",
            lambda: fake_state,
        )
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.laser.laser_state_to_db",
            lambda state: fake_db,
        )
        result = iface.get_laser_state()
        assert result == fake_db

    def test_wraps_exception(self, iface, monkeypatch):
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.factory.active_laser_state",
            lambda: (_ for _ in ()).throw(RuntimeError("laser error")),
        )
        with pytest.raises(MicroscopeConnectionError, match="Failed to get laser state"):
            iface.get_laser_state()


# ----------------------------------------------------------------------
# check_device_connections
# ----------------------------------------------------------------------
class TestCheckDeviceConnections:

    def test_returns_status_dict(self, monkeypatch):
        fake_status = {"EDS": True, "EBSD": False}
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.laser._device_connections",
            lambda: fake_status,
        )
        result = check_device_connections()
        assert result == fake_status

    def test_returns_error_dict_on_exception(self, monkeypatch):
        monkeypatch.setattr(
            "pytribeam.GUI.config_ui.microscope_interface.laser._device_connections",
            lambda: (_ for _ in ()).throw(RuntimeError("device error")),
        )
        result = check_device_connections()
        assert "error" in result
        assert "device error" in result["error"]


# ----------------------------------------------------------------------
# format_stage_info
# ----------------------------------------------------------------------
class TestFormatStageInfo:

    @pytest.fixture
    def stage_info(self):
        return {
            "electron_wd_mm": 10.12345,
            "ion_wd_mm": 5.54321,
            "x_mm": 1.11111,
            "y_mm": 2.22222,
            "z_mm": 3.33333,
            "r_deg": 4.44444,
            "t_deg": 5.55555,
        }

    def test_contains_ebeam_wd(self, stage_info):
        text = format_stage_info(stage_info)
        assert "EBeam WD" in text
        assert "10.12345" in text

    def test_contains_ibeam_wd(self, stage_info):
        text = format_stage_info(stage_info)
        assert "IBeam WD" in text
        assert "5.54321" in text

    def test_contains_xyz(self, stage_info):
        text = format_stage_info(stage_info)
        assert "1.11111" in text
        assert "2.22222" in text
        assert "3.33333" in text

    def test_contains_rotation_tilt(self, stage_info):
        text = format_stage_info(stage_info)
        assert "4.44444" in text
        assert "5.55555" in text

    def test_output_is_multiline(self, stage_info):
        text = format_stage_info(stage_info)
        assert "\n" in text

    def test_five_decimal_precision(self, stage_info):
        text = format_stage_info(stage_info)
        # Values formatted to 5 decimal places
        assert "10.12345" in text
