# python standard libraries
from types import SimpleNamespace

# 3rd party libraries
import pytest

# The dispatcher is built on pytribeam.types, which needs AutoScript. Skip,
# rather than error at collection, on machines without it.
pytest.importorskip("autoscript_sdb_microscope_client")

# Local
import pytribeam.external_oem.dispatch as external_devices
import pytribeam.types as tbt

# ----------------
# Helper functions
# ----------------


def edax_config() -> tbt.EDAXConfig:
    """Return an EDAX_settings block naming an IPAPI host."""
    return tbt.EDAXConfig(
        save_directory="D:/EDAX Data/exp1",
        project_name="exp1",
        connection=tbt.MicroscopeConnection(host="edax-pc", port=8301),
    )


def general_settings(
    ebsd_oem: tbt.ExternalDeviceOEM,
    eds_oem: tbt.ExternalDeviceOEM,
    edax_settings: tbt.EDAXConfig = None,
) -> tbt.GeneralSettings:
    """Build minimal GeneralSettings for external OEM dispatcher tests."""
    return tbt.GeneralSettings(
        yml_version=1.0,
        slice_thickness_um=1.0,
        max_slice_number=1,
        pre_tilt_deg=0.0,
        sectioning_axis=tbt.SectioningAxis.Z,
        stage_tolerance=tbt.StageTolerance(
            translational_um=1.0,
            angular_deg=1.0,
        ),
        connection=tbt.MicroscopeConnection(host="localhost"),
        EBSD_OEM=ebsd_oem,
        EDS_OEM=eds_oem,
        exp_dir=".",
        h5_log_name="log",
        step_count=1,
        EDAX_settings=edax_settings,
    )


# -----
# Tests
# -----


@pytest.mark.simulated
class TestBrukerDeviceControlPlaceholders:
    """Phase 1 Bruker dispatcher tests for no-op placeholder behavior."""

    def test_bruker_connect_ebsd_no_tfs_placeholder(self, capsys):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.BRUKER,
            eds_oem=tbt.ExternalDeviceOEM.NONE,
        )

        status = external_devices.connect_ebsd(general_settings=settings)
        captured = capsys.readouterr()

        assert status == tbt.RetractableDeviceState.CONNECTED
        assert (
            "Bruker EBSD device control is not implemented in Phase 1" in captured.out
        )

    def test_bruker_connect_eds_no_tfs_placeholder(self, capsys):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.NONE,
            eds_oem=tbt.ExternalDeviceOEM.BRUKER,
        )

        status = external_devices.connect_eds(general_settings=settings)
        captured = capsys.readouterr()

        assert status == tbt.RetractableDeviceState.CONNECTED
        assert (
            "Bruker EDS device control is handled by the Bruker workflow configuration"
            in captured.out
        )

    def test_bruker_insert_ebsd_no_tfs_placeholder(self, capsys):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.BRUKER,
            eds_oem=tbt.ExternalDeviceOEM.NONE,
        )

        assert external_devices.insert_ebsd(
            microscope=None,
            general_settings=settings,
        )
        captured = capsys.readouterr()
        assert (
            "Bruker EBSD device control is not implemented in Phase 1" in captured.out
        )

    def test_bruker_retract_ebsd_no_tfs_placeholder(self, capsys):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.BRUKER,
            eds_oem=tbt.ExternalDeviceOEM.NONE,
        )

        assert external_devices.retract_ebsd(
            microscope=None,
            general_settings=settings,
        )
        captured = capsys.readouterr()
        assert (
            "Bruker EBSD device control is not implemented in Phase 1" in captured.out
        )

    def test_bruker_insert_eds_no_tfs_placeholder(self, capsys):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.NONE,
            eds_oem=tbt.ExternalDeviceOEM.BRUKER,
        )

        assert external_devices.insert_eds(
            microscope=None,
            general_settings=settings,
        )
        captured = capsys.readouterr()
        assert (
            "Bruker EDS device control is handled by the Bruker workflow configuration"
            in captured.out
        )

    def test_bruker_retract_eds_no_tfs_placeholder(self, capsys):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.NONE,
            eds_oem=tbt.ExternalDeviceOEM.BRUKER,
        )

        assert external_devices.retract_eds(
            microscope=None,
            general_settings=settings,
        )
        captured = capsys.readouterr()
        assert (
            "Bruker EDS device control is handled by the Bruker workflow configuration"
            in captured.out
        )


@pytest.mark.laser_hardware
@pytest.mark.oxford_hardware
class TestOxfordDeviceControlDispatcher:
    """Oxford hardware tests for dispatcher routes that use TFS Laser API."""

    def test_connect_ebsd_routes_to_tfs_laser_style_control(self):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.OXFORD,
            eds_oem=tbt.ExternalDeviceOEM.NONE,
        )

        status = external_devices.connect_ebsd(general_settings=settings)

        assert isinstance(status, tbt.RetractableDeviceState)
        assert status != tbt.RetractableDeviceState.ERROR

    def test_connect_eds_routes_to_tfs_laser_style_control(self):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.NONE,
            eds_oem=tbt.ExternalDeviceOEM.OXFORD,
        )

        status = external_devices.connect_eds(general_settings=settings)

        assert isinstance(status, tbt.RetractableDeviceState)
        assert status != tbt.RetractableDeviceState.ERROR

    def test_retract_ebsd_routes_to_tfs_laser_style_control(self, microscope):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.OXFORD,
            eds_oem=tbt.ExternalDeviceOEM.NONE,
        )

        assert external_devices.retract_ebsd(
            microscope=microscope,
            general_settings=settings,
        )

    def test_retract_eds_routes_to_tfs_laser_style_control(self, microscope):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.NONE,
            eds_oem=tbt.ExternalDeviceOEM.OXFORD,
        )

        assert external_devices.retract_eds(
            microscope=microscope,
            general_settings=settings,
        )


@pytest.mark.laser_hardware
@pytest.mark.edax_hardware
class TestEdaxDeviceControlDispatcher:
    """EDAX hardware tests for dispatcher routes that use TFS Laser API."""

    def test_connect_ebsd_routes_to_tfs_laser_style_control(self):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.EDAX,
            eds_oem=tbt.ExternalDeviceOEM.NONE,
        )

        status = external_devices.connect_ebsd(general_settings=settings)

        assert isinstance(status, tbt.RetractableDeviceState)
        assert status != tbt.RetractableDeviceState.ERROR

    def test_connect_eds_routes_to_tfs_laser_style_control(self):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.NONE,
            eds_oem=tbt.ExternalDeviceOEM.EDAX,
        )

        status = external_devices.connect_eds(general_settings=settings)

        assert isinstance(status, tbt.RetractableDeviceState)
        assert status != tbt.RetractableDeviceState.ERROR

    def test_retract_ebsd_routes_to_tfs_laser_style_control(self, microscope):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.EDAX,
            eds_oem=tbt.ExternalDeviceOEM.NONE,
        )

        assert external_devices.retract_ebsd(
            microscope=microscope,
            general_settings=settings,
        )

    def test_retract_eds_routes_to_tfs_laser_style_control(self, microscope):
        settings = general_settings(
            ebsd_oem=tbt.ExternalDeviceOEM.NONE,
            eds_oem=tbt.ExternalDeviceOEM.EDAX,
        )

        assert external_devices.retract_eds(
            microscope=microscope,
            general_settings=settings,
        )


# -----------------------
# Routing, without devices
# -----------------------


@pytest.fixture
def routes(monkeypatch):
    """Replace every backend the dispatcher can reach with a recorder.

    Returns the list of backend calls in order and the list of log writes, so
    tests can assert which backend handled an operation without touching a
    microscope, a LaserControl install, or an IPAPI service.
    """
    calls = []
    logged = []

    fake_laser = SimpleNamespace(
        map_ebsd=lambda: calls.append("laser.map_ebsd") or True,
        map_eds=lambda: calls.append("laser.map_eds") or True,
    )

    def edax_map_ebsd(general_settings, step_settings, slice_number, on_metric=None):
        calls.append("edax.map_ebsd")
        if on_metric is not None:
            on_metric("camera_saturation", 0.6)
            on_metric("average_ci", 0.85)

    fake_edax = SimpleNamespace(
        map_ebsd=edax_map_ebsd,
        preflight=lambda general_settings: calls.append("edax.preflight") or True,
        check_connection=lambda host, port: (
            calls.append(("edax.check", host, port)) or True
        ),
        preflight_eds=lambda general_settings: (
            calls.append("edax.preflight_eds") or True
        ),
        eds_detector_state=lambda general_settings: (
            calls.append("edax.eds_detector_state")
            or tbt.RetractableDeviceState.RETRACTED
        ),
        insert_eds_detector=lambda general_settings, microscope: (
            calls.append("edax.insert_eds_detector") or True
        ),
        retract_eds_detector=lambda general_settings, microscope: (
            calls.append("edax.retract_eds_detector") or True
        ),
        map_eds=lambda general_settings, step_settings, slice_number: calls.append(
            "edax.map_eds"
        ),
    )

    # LaserControl's EDS detector calls, so a test can show they were not used.
    for name in ("connect_EDS", "insert_EDS", "retract_EDS"):
        monkeypatch.setattr(
            external_devices.devices,
            name,
            lambda *args, _name=name, **kwargs: (
                calls.append(f"laser_control.{_name}")
                or tbt.RetractableDeviceState.RETRACTED
            ),
        )

    monkeypatch.setattr(external_devices, "_laser", lambda: fake_laser)
    monkeypatch.setattr(external_devices, "_edax_workflow", lambda: fake_edax)
    monkeypatch.setattr(
        external_devices.log,
        "ebsd_camera_saturation",
        lambda **kwargs: logged.append(("camera_saturation", kwargs)),
    )
    monkeypatch.setattr(
        external_devices.log,
        "ebsd_average_ci",
        lambda **kwargs: logged.append(("average_ci", kwargs)),
    )
    return SimpleNamespace(calls=calls, logged=logged)


STEP = SimpleNamespace(number=3, name="ebsd_map")


def _map_ebsd(settings):
    return external_devices.map_ebsd(
        general_settings=settings, step_settings=None, slice_number=7, step=STEP
    )


class TestEbsdRouting:
    """EBSD mapping and preflight reach the right backend for each OEM."""

    def test_edax_with_ipapi_settings_uses_the_native_wrapper(self, routes):
        settings = general_settings(
            tbt.ExternalDeviceOEM.EDAX, tbt.ExternalDeviceOEM.NONE, edax_config()
        )

        assert _map_ebsd(settings) is True
        assert routes.calls == ["edax.map_ebsd"]

    def test_edax_without_ipapi_settings_falls_back_to_laser_control(self, routes):
        """A v1.0 configuration names no IPAPI host, so LaserControl drives it."""
        settings = general_settings(
            tbt.ExternalDeviceOEM.EDAX, tbt.ExternalDeviceOEM.NONE
        )

        _map_ebsd(settings)

        assert routes.calls == ["laser.map_ebsd"]

    def test_oxford_ignores_an_edax_block(self, routes):
        """v1.1 configurations carry EDAX_settings whatever the OEM."""
        settings = general_settings(
            tbt.ExternalDeviceOEM.OXFORD, tbt.ExternalDeviceOEM.NONE, edax_config()
        )

        _map_ebsd(settings)

        assert routes.calls == ["laser.map_ebsd"]

    def test_bruker_ebsd_is_refused_with_the_reason(self, routes):
        settings = general_settings(
            tbt.ExternalDeviceOEM.BRUKER, tbt.ExternalDeviceOEM.NONE
        )

        with pytest.raises(NotImplementedError, match="Bruker EBSD wrapper"):
            _map_ebsd(settings)
        assert routes.calls == []

    def test_no_ebsd_oem_is_refused(self, routes):
        settings = general_settings(
            tbt.ExternalDeviceOEM.NONE, tbt.ExternalDeviceOEM.NONE
        )

        with pytest.raises(NotImplementedError, match="EBSD step was requested"):
            _map_ebsd(settings)

    def test_native_preflight_runs_over_the_ipapi(self, routes):
        settings = general_settings(
            tbt.ExternalDeviceOEM.EDAX, tbt.ExternalDeviceOEM.NONE, edax_config()
        )

        assert external_devices.preflight_ebsd(general_settings=settings) is True
        assert routes.calls == ["edax.preflight"]

    @pytest.mark.parametrize(
        "oem, edax",
        [
            (tbt.ExternalDeviceOEM.EDAX, False),
            (tbt.ExternalDeviceOEM.OXFORD, True),
            (tbt.ExternalDeviceOEM.BRUKER, False),
        ],
    )
    def test_preflight_is_a_no_op_off_the_native_path(self, routes, oem, edax):
        settings = general_settings(
            oem, tbt.ExternalDeviceOEM.NONE, edax_config() if edax else None
        )

        assert external_devices.preflight_ebsd(general_settings=settings) is True
        assert routes.calls == []

    @pytest.mark.parametrize(
        "oem, edax, expected",
        [
            (tbt.ExternalDeviceOEM.EDAX, True, True),
            (tbt.ExternalDeviceOEM.EDAX, False, False),
            (tbt.ExternalDeviceOEM.OXFORD, True, False),
            (tbt.ExternalDeviceOEM.BRUKER, True, False),
            (tbt.ExternalDeviceOEM.NONE, True, False),
        ],
    )
    def test_native_edax_selection(self, oem, edax, expected):
        settings = general_settings(
            oem, tbt.ExternalDeviceOEM.NONE, edax_config() if edax else None
        )
        assert external_devices.uses_native_edax_ebsd(settings) is expected


class TestEdsRouting:
    """EDAX EDS runs over the IPAPI whenever an IPAPI host is configured."""

    def _eds(self, oem, edax=True):
        return general_settings(
            tbt.ExternalDeviceOEM.NONE, oem, edax_config() if edax else None
        )

    def test_native_edax_eds_never_touches_laser_control(self, routes):
        """Connect, preflight, insert, map, and retract all go over the IPAPI."""
        settings = self._eds(tbt.ExternalDeviceOEM.EDAX)

        external_devices.connect_eds(general_settings=settings)
        external_devices.preflight_eds(general_settings=settings)
        external_devices.insert_eds(microscope=None, general_settings=settings)
        external_devices.map_eds(general_settings=settings, slice_number=4)
        external_devices.retract_eds(microscope=None, general_settings=settings)

        assert routes.calls == [
            "edax.eds_detector_state",
            "edax.preflight_eds",
            "edax.insert_eds_detector",
            "edax.map_eds",
            "edax.retract_eds_detector",
        ]

    def test_edax_without_ipapi_settings_falls_back_to_laser_control(self, routes):
        """A v1.0 configuration names no IPAPI host."""
        settings = self._eds(tbt.ExternalDeviceOEM.EDAX, edax=False)

        external_devices.insert_eds(microscope=None, general_settings=settings)
        external_devices.map_eds(general_settings=settings)
        external_devices.retract_eds(microscope=None, general_settings=settings)

        assert routes.calls == [
            "laser_control.insert_EDS",
            "laser.map_eds",
            "laser_control.retract_EDS",
        ]
        assert external_devices.preflight_eds(general_settings=settings) is True

    def test_oxford_ignores_an_edax_block(self, routes):
        """v1.1 configurations carry EDAX_settings whatever the OEM."""
        settings = self._eds(tbt.ExternalDeviceOEM.OXFORD)

        external_devices.map_eds(general_settings=settings)
        external_devices.preflight_eds(general_settings=settings)

        assert routes.calls == ["laser.map_eds"]

    def test_concurrent_eds_moves_the_detector_over_the_ipapi(self, routes):
        """An EBSD step with concurrent EDS inserts the EDS detector natively."""
        settings = general_settings(
            tbt.ExternalDeviceOEM.EDAX, tbt.ExternalDeviceOEM.EDAX, edax_config()
        )

        external_devices.insert_eds(microscope=None, general_settings=settings)

        assert routes.calls == ["edax.insert_eds_detector"]

    @pytest.mark.parametrize(
        "oem, edax, expected",
        [
            (tbt.ExternalDeviceOEM.EDAX, True, True),
            (tbt.ExternalDeviceOEM.EDAX, False, False),
            (tbt.ExternalDeviceOEM.OXFORD, True, False),
            (tbt.ExternalDeviceOEM.BRUKER, True, False),
            (tbt.ExternalDeviceOEM.NONE, True, False),
        ],
    )
    def test_native_edax_eds_selection(self, oem, edax, expected):
        assert external_devices.uses_native_edax_eds(self._eds(oem, edax)) is expected

    def test_bruker_eds_points_to_the_custom_step(self, routes):
        settings = self._eds(tbt.ExternalDeviceOEM.BRUKER, edax=False)

        with pytest.raises(NotImplementedError, match="custom"):
            external_devices.map_eds(general_settings=settings)
        assert routes.calls == []


class TestMetricLogging:
    """Native EDAX metrics land in the experiment log as they are measured."""

    def test_native_map_logs_saturation_and_ci(self, routes):
        settings = general_settings(
            tbt.ExternalDeviceOEM.EDAX, tbt.ExternalDeviceOEM.NONE, edax_config()
        )

        _map_ebsd(settings)

        names = [name for name, _ in routes.logged]
        assert names == ["camera_saturation", "average_ci"]
        saturation = routes.logged[0][1]
        assert saturation["cam_sat_p"] == 0.6
        assert saturation["step_number"] == 3
        assert saturation["step_name"] == "ebsd_map"
        assert saturation["slice_number"] == 7
        assert routes.logged[1][1]["avg_ci_p"] == 0.85

    def test_unknown_metric_is_reported_not_raised(self, routes, capsys):
        """A vendor reporting something new must not abort an experiment."""
        settings = general_settings(
            tbt.ExternalDeviceOEM.EDAX, tbt.ExternalDeviceOEM.NONE, edax_config()
        )

        logged = external_devices.log_ebsd_metric(
            settings, STEP, 7, "pattern_quality", 0.4
        )

        assert logged is False
        assert routes.logged == []
        assert "pattern_quality" in capsys.readouterr().out


class TestConnectionCheck:
    """Configuration validation reaches the IPAPI through the dispatcher."""

    def test_check_delegates_to_the_edax_wrapper(self, routes):
        assert external_devices.check_edax_connection(host="edax-pc", port=8301)
        assert routes.calls == [("edax.check", "edax-pc", 8301)]
