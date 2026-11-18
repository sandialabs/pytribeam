"""Bruker ESPRIT adapter, against fake ESPRIT controllers.

The fakes stand in for the ctypes-backed controllers, so these run anywhere.
Real ESPRIT runs are covered by tests/bruker (simulator and hardware tiers).
"""

from types import SimpleNamespace

import pytest

pytest.importorskip("autoscript_sdb_microscope_client")

import pytribeam.external_oem.dispatch as external_devices  # noqa: E402
import pytribeam.types as tbt  # noqa: E402
from pytribeam.external_oem.adapters import bruker as bruker_adapter  # noqa: E402
from pytribeam.external_oem.bruker.types import (  # noqa: E402
    BrukerDetectorPositionState,
    BrukerEDSProfileMapSettings,
    BrukerImageConfiguration,
    BrukerMapOutputs,
    BrukerSpectrometerStatus,
)
from pytribeam.external_oem.core.errors import (  # noqa: E402
    APICallError,
    ConfigurationError,
    DetectorError,
)
from tests.external_oem.helpers import (  # noqa: E402
    EBSD,
    EDS,
    MICROSCOPE,
    OEM,
    STATE,
    general_settings,
)

MAP = tbt.BrukerMapSettings(width_px=8, height_px=6, dwell_us=100)


INSERTED_MM, RETRACTED_MM = 20.0, 0.0


def settings_for(**config):
    """General settings for a Bruker system with the given instrument config.

    Detector motion is on and the EBSD camera positions are set, unless a test
    overrides them.
    """
    values = {
        "move_detector": True,
        "ebsd_inserted_position_mm": INSERTED_MM,
        "ebsd_retracted_position_mm": RETRACTED_MM,
        **config,
    }
    return general_settings(
        OEM.BRUKER,
        OEM.BRUKER,
        Bruker_settings=tbt.BrukerConfig(
            dll_dir="C:/Program Files/Bruker/Esprit API", **values
        ),
    )


def eds_step(tmp_path, bruker=True):
    return tbt.EDSSettings(
        image=None,
        bruker=tbt.BrukerEDSStepSettings(
            output_path=tmp_path / "esprit_eds", map=MAP, run_name="eds_step"
        )
        if bruker
        else None,
    )


def ebsd_step(tmp_path, enable_eds=False, bruker=True):
    return tbt.EBSDSettings(
        image=None,
        enable_eds=enable_eds,
        bruker=tbt.BrukerEBSDStepSettings(
            output_path=tmp_path / "esprit_ebsd",
            profile_name="default",
            map=MAP,
            save_patterns=True,
            run_name="ebsd_step",
        )
        if bruker
        else None,
    )


@pytest.fixture
def esprit(monkeypatch, chamber):
    """Fake ESPRIT: sessions, detector positions, maps."""
    state = SimpleNamespace(
        calls=[],
        sessions=[],
        eds_position="park",
        ebsd_mm=RETRACTED_MM,
        spectrometer_ready=True,
        image_size=None,  # None: accept the request
        profiles="default;fast",
        save_bcf=True,
        chamber=chamber,
    )

    class FakeSession:
        def __init__(self, settings):
            self.settings = settings
            self.alive = True
            self.closed = False
            state.sessions.append(self)

        def check_connection(self):
            if not self.alive:
                raise APICallError("CheckConnection", -1)

        def close(self):
            self.closed = True

    def record(name, *args):
        state.calls.append((name,) + args)

    class Motion:
        def __init__(self, session):
            pass

        def get_eds_detector_position(self, index):
            code = {"park": 1, "acquire": 2}.get(state.eds_position, 9)
            return BrukerDetectorPositionState(index, code, state.eds_position)

        def move_eds_detector(self, settings):
            record("move_eds", settings.target_position, list(chamber.events))
            state.eds_position = settings.target_position

    class Spectrometer:
        def __init__(self, session):
            pass

        def get_spectrometer_status(self, spu=1):
            record("spectrometer", spu)
            return BrukerSpectrometerStatus(1, (), 0, state.spectrometer_ready)

    class ImageConfig:
        def __init__(self, session):
            pass

        def set_image_configuration(self, width, height, pixel_time):
            record("set_image", width, height, pixel_time)
            w, h = state.image_size or (width, height)
            return BrukerImageConfiguration(w, h, 1, True, False)

    class Eds:
        def __init__(self, session):
            pass

        def create_hymap_profile(self, settings):
            record("create_profile", [e.atomic_number for e in settings.elements])
            return "<profile/>"

        def acquire_map_with_profile(self, settings, poll_interval_s, max_wait_s):
            record("acquire", settings, max_wait_s)
            if state.save_bcf:
                with open(settings.output_bcf_path, "wb") as f:
                    f.write(b"bcf")
            return BrukerMapOutputs(
                settings.output_bcf_path, settings.output_image_path
            )

    class Ebsd:
        def __init__(self, session):
            pass

        def get_detector_position_mm(self):
            return state.ebsd_mm

        def move_detector_position_tolerant(self, settings):
            record("move_ebsd", settings.target_position_mm, list(chamber.events))
            state.ebsd_mm = settings.target_position_mm
            return SimpleNamespace(
                within_tolerance=True, final_position_mm=state.ebsd_mm
            )

        def export_status(self):
            fields = bruker_adapter._EBSD_REQUIRED_EXPORTS
            return SimpleNamespace(**{name: True for name in fields})

        def get_profiles_raw(self):
            return state.profiles

        def configure_scan_area(self, scan_area):
            record("configure_scan_area", scan_area)

        def select_profile(self, name):
            record("select_profile", name)

        def run_profile_acquisition(self, settings):
            record("ebsd_acquisition", settings)

    for name, fake in {
        "session_factory": FakeSession,
        "BrukerDetectorMotionController": Motion,
        "BrukerSpectrometerController": Spectrometer,
        "BrukerImageConfigController": ImageConfig,
        "BrukerEDSController": Eds,
        "BrukerEBSDController": Ebsd,
    }.items():
        monkeypatch.setattr(bruker_adapter, name, fake)
    bruker_adapter._SESSIONS.clear()
    yield state
    bruker_adapter._SESSIONS.clear()


def calls(state, name):
    return [call for call in state.calls if call[0] == name]


class TestFixedDefaults:
    """Only what varies is configured; the rest matches the custom-step version."""

    def test_session(self):
        session = bruker_adapter.session_settings(
            tbt.BrukerConfig(
                dll_dir="C:/Esprit",
                mode=tbt.BrukerConnectionMode.TCP,
                host="esprit-pc",
                port=5328,
            )
        )

        assert (session.mode, session.host, session.port) == ("tcp", "esprit-pc", 5328)
        assert (session.server, session.user, session.password) == (
            "Lokaler Server",
            "edx",
            "edx",
        )
        assert session.close_on_exit is False

    def test_eds_settings(self, tmp_path):
        config = tbt.BrukerConfig(dll_dir="C:/Esprit", detector_index=2)

        settings = bruker_adapter.eds_workflow_settings(
            config, eds_step(tmp_path).bruker, slice_number=7
        )

        assert isinstance(settings.map, BrukerEDSProfileMapSettings)
        assert (settings.map.width_px, settings.map.height_px) == (8, 6)
        assert settings.map.pixel_time_us == 100
        assert settings.map.spu_device == 2
        assert settings.map.name == "0007"
        assert [e.atomic_number for e in settings.map.elements] == [6]
        assert settings.output.run_name == "eds_step"
        assert settings.output.slice_number == 7
        assert settings.readback.enabled is False

    @pytest.mark.parametrize("move", [True, False])
    def test_move_detector_drives_every_motion_flag(self, tmp_path, move):
        config = tbt.BrukerConfig(dll_dir="C:/Esprit", move_detector=move)

        detector = bruker_adapter.eds_workflow_settings(
            config, eds_step(tmp_path).bruker
        ).detector

        assert (
            detector.verify_park_before,
            detector.move_to_acquire_before,
            detector.park_after,
        ) == (move, move, move)

    def test_map_time_limit_grows_with_the_map(self):
        small = tbt.BrukerMapSettings(64, 48, 100)
        large = tbt.BrukerMapSettings(2048, 1536, 1000)

        assert bruker_adapter.map_wait_s(small, 600.0) == 600.0
        assert bruker_adapter.map_wait_s(large, 600.0) == pytest.approx(
            3 * 2048 * 1536 * 1000e-6
        )


class TestSessions:
    def test_one_session_is_reused(self, esprit):
        settings = settings_for()

        bruker_adapter.test_connection(settings, EDS)
        bruker_adapter.get_eds_detector_state(settings)
        bruker_adapter.test_connection(settings, EBSD)

        assert len(esprit.sessions) == 1
        assert not esprit.sessions[0].closed

    def test_a_dropped_session_is_replaced(self, esprit):
        settings = settings_for()
        bruker_adapter.test_connection(settings, EDS)
        esprit.sessions[0].alive = False

        assert bruker_adapter.test_connection(settings, EDS)
        assert len(esprit.sessions) == 2

    def test_close_sessions(self, esprit):
        bruker_adapter.test_connection(settings_for(), EBSD)

        bruker_adapter.close_sessions()

        assert esprit.sessions[0].closed
        assert bruker_adapter._SESSIONS == {}

    def test_wrapper_errors_become_detector_errors(self, esprit, monkeypatch):
        def no_dll(settings):
            raise FileNotFoundError("Bruker.API.Esprit64.dll")

        monkeypatch.setattr(bruker_adapter, "session_factory", no_dll)

        with pytest.raises(DetectorError, match="Esprit64.dll"):
            bruker_adapter.test_connection(settings_for(), EDS)


def test_esprit_load_failure_is_a_detector_error(monkeypatch):
    """Off Windows, or with a wrong dll_dir, loading the DLL fails variously."""

    def no_dll(settings):
        raise AttributeError("module 'os' has no attribute 'add_dll_directory'")

    monkeypatch.setattr(bruker_adapter, "BrukerSession", no_dll)
    session = bruker_adapter.session_settings(settings_for().Bruker_settings)

    with pytest.raises(DetectorError, match="Could not load the Bruker ESPRIT API"):
        bruker_adapter._new_session(session)


class TestEdsDetector:
    @pytest.mark.parametrize(
        "position, expected",
        [
            ("park", STATE.RETRACTED),
            ("acquire", STATE.INSERTED),
            ("unknown", STATE.INDERTERMINATE),
        ],
    )
    def test_state(self, esprit, position, expected):
        esprit.eds_position = position

        assert bruker_adapter.get_eds_detector_state(settings_for()) == expected

    def test_insert_and_retract(self, esprit):
        settings = settings_for()

        assert bruker_adapter.insert_eds_detector(MICROSCOPE, settings)
        assert bruker_adapter.retract_eds_detector(MICROSCOPE, settings)

        # The adapter only moves; the dispatcher guards (see below).
        assert calls(esprit, "move_eds") == [
            ("move_eds", "acquire", []),
            ("move_eds", "park", []),
        ]

    def test_through_the_dispatcher_moves_are_guarded(self, esprit):
        settings = settings_for()

        assert external_devices.insert_eds_detector(MICROSCOPE, settings)
        assert external_devices.retract_eds_detector(MICROSCOPE, settings)

        assert calls(esprit, "move_eds") == [
            ("move_eds", "acquire", ["ccd_on"]),
            ("move_eds", "park", ["ccd_on", "ccd_off", "ccd_on"]),
        ]
        assert [d for d, _ in esprit.chamber.checked] == [tbt.DetectorType.EDS]

    def test_insert_refuses_unless_parked(self, esprit):
        esprit.eds_position = "unknown"

        with pytest.raises(DetectorError, match="not parked"):
            bruker_adapter.insert_eds_detector(MICROSCOPE, settings_for())
        assert calls(esprit, "move_eds") == []

    def test_dispatcher_refuses_a_possible_collision(self, esprit):
        esprit.chamber.collide = True

        with pytest.raises(DetectorError, match="collide"):
            external_devices.insert_eds_detector(MICROSCOPE, settings_for())
        assert calls(esprit, "move_eds") == []

    def test_motion_is_off_unless_set(self, esprit):
        """A missing or unticked move_detector means the detector is not moved."""
        config = tbt.BrukerConfig(dll_dir="C:/Esprit")
        settings = general_settings(OEM.NONE, OEM.BRUKER, Bruker_settings=config)

        assert config.move_detector is False
        assert bruker_adapter.insert_eds_detector(MICROSCOPE, settings)
        assert calls(esprit, "move_eds") == []

    def test_motion_disabled_for_the_simulator(self, esprit):
        settings = settings_for(move_detector=False)

        assert bruker_adapter.insert_eds_detector(MICROSCOPE, settings)
        assert bruker_adapter.retract_eds_detector(MICROSCOPE, settings)
        assert calls(esprit, "move_eds") == []


class TestEbsdCamera:
    """The camera is driven to its configured positions (not hardware-validated)."""

    @pytest.mark.parametrize(
        "position_mm, expected",
        [
            (INSERTED_MM, STATE.INSERTED),
            (INSERTED_MM - 0.05, STATE.INSERTED),
            (RETRACTED_MM + 0.05, STATE.RETRACTED),
            (10.0, STATE.INDERTERMINATE),
        ],
    )
    def test_state_from_position(self, esprit, position_mm, expected):
        esprit.ebsd_mm = position_mm

        assert bruker_adapter.get_ebsd_camera_state(settings_for()) == expected

    def test_insert_and_retract(self, esprit):
        settings = settings_for()

        assert bruker_adapter.insert_ebsd_camera(MICROSCOPE, settings)
        assert bruker_adapter.retract_ebsd_camera(MICROSCOPE, settings)

        assert [call[1] for call in calls(esprit, "move_ebsd")] == [
            INSERTED_MM,
            RETRACTED_MM,
        ]

    def test_through_the_dispatcher_moves_are_guarded(self, esprit):
        settings = settings_for()

        external_devices.insert_ebsd_camera(MICROSCOPE, settings)

        assert calls(esprit, "move_ebsd") == [("move_ebsd", INSERTED_MM, ["ccd_on"])]
        assert [d for d, _ in esprit.chamber.checked] == [tbt.DetectorType.EBSD]

    def test_insert_refuses_from_an_intermediate_position(self, esprit):
        esprit.ebsd_mm = 10.0

        with pytest.raises(DetectorError, match="neither inserted nor retracted"):
            bruker_adapter.insert_ebsd_camera(MICROSCOPE, settings_for())
        assert calls(esprit, "move_ebsd") == []

    def test_retract_from_an_intermediate_position(self, esprit):
        esprit.ebsd_mm = 10.0

        assert bruker_adapter.retract_ebsd_camera(MICROSCOPE, settings_for())
        assert [call[1] for call in calls(esprit, "move_ebsd")] == [RETRACTED_MM]

    @pytest.mark.parametrize(
        "call",
        [
            lambda s: bruker_adapter.get_ebsd_camera_state(s),
            lambda s: bruker_adapter.insert_ebsd_camera(MICROSCOPE, s),
            lambda s: bruker_adapter.retract_ebsd_camera(MICROSCOPE, s),
            lambda s: bruker_adapter.preflight_ebsd(s, []),
        ],
    )
    def test_positions_are_required(self, esprit, call):
        settings = settings_for(ebsd_inserted_position_mm=None)

        with pytest.raises(ConfigurationError, match="ebsd_inserted_position_mm"):
            call(settings)
        assert calls(esprit, "move_ebsd") == []

    def test_stage_guard_sees_an_inserted_camera(self, esprit):
        settings = general_settings(
            OEM.BRUKER, OEM.NONE, Bruker_settings=settings_for().Bruker_settings
        )
        esprit.ebsd_mm = INSERTED_MM

        with pytest.raises(DetectorError, match="EBSD is INSERTED"):
            external_devices.check_safe_for_stage_motion(settings)


class TestPreflightAndParameters:
    def test_eds_preflight(self, esprit, tmp_path):
        settings = settings_for(detector_index=2)

        assert bruker_adapter.preflight_eds(settings, [eds_step(tmp_path)])
        assert calls(esprit, "spectrometer") == [("spectrometer", 2)]
        assert (tmp_path / "esprit_eds").is_dir()

    def test_spectrometer_not_ready(self, esprit, tmp_path):
        esprit.spectrometer_ready = False

        with pytest.raises(DetectorError, match="not ready"):
            bruker_adapter.preflight_eds(settings_for(), [eds_step(tmp_path)])

    @pytest.mark.parametrize(
        "call",
        [
            lambda s, p: bruker_adapter.preflight_eds(s, [eds_step(p, bruker=False)]),
            lambda s, p: bruker_adapter.preflight_ebsd(s, [ebsd_step(p, bruker=False)]),
            lambda s, p: bruker_adapter.set_eds_parameters(
                s, eds_step(p, bruker=False)
            ),
            lambda s, p: bruker_adapter.map_eds(s, eds_step(p, bruker=False), 1, print),
        ],
    )
    def test_a_step_without_bruker_settings_is_refused(self, esprit, tmp_path, call):
        with pytest.raises(ConfigurationError, match="bruker_settings"):
            call(settings_for(), tmp_path)

    def test_ebsd_preflight_needs_the_exports(self, esprit, tmp_path, monkeypatch):
        missing = SimpleNamespace(
            **{name: True for name in bruker_adapter._EBSD_REQUIRED_EXPORTS}
        )
        missing.has_save_to_file = False
        monkeypatch.setattr(
            bruker_adapter.BrukerEBSDController, "export_status", lambda self: missing
        )

        with pytest.raises(DetectorError, match="has_save_to_file"):
            bruker_adapter.preflight_ebsd(settings_for(), [ebsd_step(tmp_path)])

    def test_eds_parameters(self, esprit, tmp_path):
        assert bruker_adapter.set_eds_parameters(settings_for(), eds_step(tmp_path))
        assert calls(esprit, "set_image") == [("set_image", 8, 6, 100)]
        assert calls(esprit, "create_profile") == [("create_profile", [6])]

    def test_eds_size_adjusted_by_esprit_is_refused(self, esprit, tmp_path):
        esprit.image_size = (16, 6)

        with pytest.raises(ConfigurationError, match="16x6"):
            bruker_adapter.set_eds_parameters(settings_for(), eds_step(tmp_path))

    def test_ebsd_parameters(self, esprit, tmp_path):
        assert bruker_adapter.set_ebsd_parameters(settings_for(), ebsd_step(tmp_path))
        ((_, area),) = calls(esprit, "configure_scan_area")
        assert (area.width_px, area.height_px, area.pixel_time_us) == (8, 6, 100)
        assert calls(esprit, "select_profile") == [("select_profile", "default")]

    def test_unknown_ebsd_profile(self, esprit, tmp_path):
        esprit.profiles = "fast;slow"

        with pytest.raises(ConfigurationError, match="'default'"):
            bruker_adapter.set_ebsd_parameters(settings_for(), ebsd_step(tmp_path))


class TestMaps:
    def test_eds_map_saves_bcf_and_overview(self, esprit, tmp_path):
        assert bruker_adapter.map_eds(settings_for(), eds_step(tmp_path), 3, print)

        ((_, map_settings, max_wait_s),) = calls(esprit, "acquire")
        assert map_settings.output_bcf_path.endswith(".bcf")
        assert "Slice_0003" in map_settings.output_bcf_path
        assert map_settings.output_image_path.endswith(".bmp")
        assert max_wait_s == 600.0
        assert (tmp_path / "esprit_eds").exists()

    def test_a_missing_bcf_is_reported_not_raised(self, esprit, tmp_path, capsys):
        esprit.save_bcf = False

        assert bruker_adapter.map_eds(settings_for(), eds_step(tmp_path), 3, print)
        assert "no .bcf file found" in capsys.readouterr().out

    @pytest.mark.parametrize("concurrent_eds", [False, True])
    def test_ebsd_map(self, esprit, tmp_path, concurrent_eds):
        step = ebsd_step(tmp_path, enable_eds=concurrent_eds)

        assert bruker_adapter.map_ebsd(settings_for(), step, 5, print)

        ((_, acquisition),) = calls(esprit, "ebsd_acquisition")
        assert "Slice_0005" in acquisition.output_path
        assert acquisition.with_edx is concurrent_eds
        assert acquisition.with_patterns is True
        assert acquisition.profile_name == "default"
        assert acquisition.timeout_s == 3600.0
