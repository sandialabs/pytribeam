"""Bruker ESPRIT adapter, against fake ESPRIT controllers.

The fakes stand in for the ctypes-backed controllers, so these run anywhere.
Real ESPRIT runs are covered by tests/bruker (simulator and hardware tiers).
"""

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("autoscript_sdb_microscope_client")

import h5py  # noqa: E402
import numpy as np  # noqa: E402

import pytribeam.types as tbt  # noqa: E402
from pytribeam.external_oem.adapters import bruker as bruker_adapter  # noqa: E402
from pytribeam.external_oem.bruker.config import parse_bruker_settings  # noqa: E402
from pytribeam.external_oem.bruker.types import (  # noqa: E402
    BrukerDetectorPositionState,
    BrukerEBSDDetectorMotionResult,
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
    ebsd_settings,
    eds_settings,
    general_settings,
)

ELEMENTS = [
    {"atomic_number": 26, "line": "KA"},
    {"atomic_number": 14, "line": "KA"},
]


def bruker_block(root, close_on_exit=False, map_mode="profile", **detector):
    return {
        "session": {
            "dll_dir": "C:/Program Files/Bruker/Esprit API",
            "password": "secret",
            "close_on_exit": close_on_exit,
        },
        "eds": {
            "output": {"root_dir": str(root / "esprit_eds"), "run_name": "eds"},
            "detector": {"detector_index": 1, "move_timeout_s": 5.0, **detector},
            "map": {
                "mode": map_mode,
                "width_px": 8,
                "height_px": 6,
                "pixel_time_us": 100,
                "max_wait_s": 1800.0,
                "profile": {"elements": ELEMENTS},
            },
        },
        "ebsd": {
            "output": {"root_dir": str(root / "esprit_ebsd"), "run_name": "ebsd"},
            "detector": {"inserted_position_mm": 20.0, "retracted_position_mm": 0.0},
            "acquisition": {
                "profile_name": "default",
                "width_px": 50,
                "height_px": 24,
                "pixel_time_us": 512,
            },
        },
    }


def settings_for(tmp_path, **block_options):
    return general_settings(
        OEM.BRUKER,
        OEM.BRUKER,
        exp_dir=str(tmp_path / "exp"),
        Bruker_settings=parse_bruker_settings(bruker_block(tmp_path, **block_options)),
    )


@pytest.fixture
def esprit(monkeypatch, chamber):
    """Fake ESPRIT: sessions, detector positions, maps and readback."""
    state = SimpleNamespace(
        calls=[],
        sessions=[],
        eds_position="park",
        ebsd_mm=0.0,
        spectrometer_ready=True,
        image_size=None,  # None: accept the request
        profiles="default;fast",
        readback_fails=set(),
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

        def query_info(self):
            return "ESPRIT 2.5 (fake)"

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
            record("create_profile", len(settings.elements))
            return "<profile/>"

        def _acquire(self, kind, settings, poll_interval_s, max_wait_s):
            record(kind, settings.output_bcf_path, max_wait_s)
            if state.save_bcf:
                with open(settings.output_bcf_path, "wb") as f:
                    f.write(b"bcf")
            return BrukerMapOutputs(settings.output_bcf_path, None)

        def acquire_map_with_profile(self, settings, poll_interval_s, max_wait_s):
            return self._acquire(
                "acquire_profile", settings, poll_interval_s, max_wait_s
            )

        def acquire_map(self, settings, poll_interval_s, max_wait_s):
            return self._acquire(
                "acquire_simple", settings, poll_interval_s, max_wait_s
            )

    class Readback:
        def __init__(self, session):
            pass

        @staticmethod
        def _effective_readback_dimensions(settings):
            return settings.width_px, settings.height_px

        def get_element_data_array(self, element_index, width_px, height_px):
            if element_index in state.readback_fails:
                raise ValueError("size mismatch")
            return np.full((height_px, width_px), element_index + 1, dtype="uint16")

    class Ebsd:
        def __init__(self, session):
            pass

        def get_detector_position_mm(self):
            return state.ebsd_mm

        def move_detector_position_tolerant(self, settings):
            record("move_ebsd", settings.target_position_mm, list(chamber.events))
            state.ebsd_mm = settings.target_position_mm
            return BrukerEBSDDetectorMotionResult(
                settings.target_position_mm, state.ebsd_mm, 0.0, True, 0
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
            record("ebsd_acquisition", settings.output_path, settings.with_edx)

    for name, fake in {
        "session_factory": FakeSession,
        "BrukerDetectorMotionController": Motion,
        "BrukerSpectrometerController": Spectrometer,
        "BrukerImageConfigController": ImageConfig,
        "BrukerEDSController": Eds,
        "BrukerEDSReadbackController": Readback,
        "BrukerEBSDController": Ebsd,
    }.items():
        monkeypatch.setattr(bruker_adapter, name, fake)
    bruker_adapter._SESSIONS.clear()
    yield state
    bruker_adapter._SESSIONS.clear()


def calls(state, name):
    return [call for call in state.calls if call[0] == name]


class TestSessions:
    def test_one_session_is_reused(self, esprit, tmp_path):
        settings = settings_for(tmp_path)

        bruker_adapter.test_connection(settings, EDS)
        bruker_adapter.get_eds_detector_state(settings)
        bruker_adapter.get_ebsd_camera_state(settings)

        assert len(esprit.sessions) == 1
        assert not esprit.sessions[0].closed

    def test_a_dropped_session_is_replaced(self, esprit, tmp_path):
        settings = settings_for(tmp_path)
        bruker_adapter.test_connection(settings, EDS)
        esprit.sessions[0].alive = False

        assert bruker_adapter.test_connection(settings, EDS)
        assert len(esprit.sessions) == 2

    def test_close_on_exit_closes_after_every_call(self, esprit, tmp_path):
        settings = settings_for(tmp_path, close_on_exit=True)

        bruker_adapter.test_connection(settings, EDS)
        bruker_adapter.test_connection(settings, EDS)

        assert [s.closed for s in esprit.sessions] == [True, True]
        assert bruker_adapter._SESSIONS == {}

    def test_close_sessions(self, esprit, tmp_path):
        bruker_adapter.test_connection(settings_for(tmp_path), EBSD)

        bruker_adapter.close_sessions()

        assert esprit.sessions[0].closed
        assert bruker_adapter._SESSIONS == {}

    def test_wrapper_errors_become_detector_errors(self, esprit, tmp_path, monkeypatch):
        def no_dll(settings):
            raise FileNotFoundError("Bruker.API.Esprit64.dll")

        monkeypatch.setattr(bruker_adapter, "session_factory", no_dll)

        with pytest.raises(DetectorError, match="Esprit64.dll"):
            bruker_adapter.test_connection(settings_for(tmp_path), EDS)


def test_esprit_load_failure_is_a_detector_error(monkeypatch, tmp_path):
    """Off Windows, or with a wrong dll_dir, loading the DLL fails variously."""

    def no_dll(settings):
        raise AttributeError("module 'os' has no attribute 'add_dll_directory'")

    monkeypatch.setattr(bruker_adapter, "BrukerSession", no_dll)
    settings = settings_for(tmp_path).Bruker_settings.session

    with pytest.raises(DetectorError, match="Could not load the Bruker ESPRIT API"):
        bruker_adapter._new_session(settings)


class TestEdsDetector:
    @pytest.mark.parametrize(
        "position, expected",
        [
            ("park", STATE.RETRACTED),
            ("acquire", STATE.INSERTED),
            ("unknown", STATE.INDERTERMINATE),
        ],
    )
    def test_state(self, esprit, tmp_path, position, expected):
        esprit.eds_position = position

        assert bruker_adapter.get_eds_detector_state(settings_for(tmp_path)) == expected

    def test_insert_and_retract_under_the_ccd(self, esprit, tmp_path):
        settings = settings_for(tmp_path)

        assert bruker_adapter.insert_eds_detector(MICROSCOPE, settings)
        assert bruker_adapter.retract_eds_detector(MICROSCOPE, settings)

        assert calls(esprit, "move_eds") == [
            ("move_eds", "acquire", ["ccd_on"]),
            ("move_eds", "park", ["ccd_on", "ccd_off", "ccd_on"]),
        ]
        assert esprit.chamber.checked == [tbt.DetectorType.EDS]

    def test_insert_refuses_unless_parked(self, esprit, tmp_path):
        esprit.eds_position = "unknown"

        with pytest.raises(DetectorError, match="not parked"):
            bruker_adapter.insert_eds_detector(MICROSCOPE, settings_for(tmp_path))
        assert calls(esprit, "move_eds") == []

    def test_insert_refuses_a_possible_collision(self, esprit, tmp_path):
        esprit.chamber.collide = True

        with pytest.raises(DetectorError, match="collide"):
            bruker_adapter.insert_eds_detector(MICROSCOPE, settings_for(tmp_path))
        assert calls(esprit, "move_eds") == []

    def test_motion_disabled_for_simulator_configs(self, esprit, tmp_path):
        settings = settings_for(tmp_path, move_detector=False)

        assert bruker_adapter.insert_eds_detector(MICROSCOPE, settings)
        assert bruker_adapter.retract_eds_detector(MICROSCOPE, settings)
        assert calls(esprit, "move_eds") == []


class TestEbsdCamera:
    @pytest.mark.parametrize(
        "position_mm, expected",
        [
            (20.0, STATE.INSERTED),
            (19.95, STATE.INSERTED),
            (0.05, STATE.RETRACTED),
            (10.0, STATE.INDERTERMINATE),
        ],
    )
    def test_state_from_position(self, esprit, tmp_path, position_mm, expected):
        esprit.ebsd_mm = position_mm

        assert bruker_adapter.get_ebsd_camera_state(settings_for(tmp_path)) == expected

    def test_insert_and_retract(self, esprit, tmp_path):
        settings = settings_for(tmp_path)

        assert bruker_adapter.insert_ebsd_camera(MICROSCOPE, settings)
        assert bruker_adapter.retract_ebsd_camera(MICROSCOPE, settings)

        assert [call[1] for call in calls(esprit, "move_ebsd")] == [20.0, 0.0]

    def test_insert_refuses_from_an_intermediate_position(self, esprit, tmp_path):
        esprit.ebsd_mm = 10.0

        with pytest.raises(DetectorError, match="neither inserted nor retracted"):
            bruker_adapter.insert_ebsd_camera(MICROSCOPE, settings_for(tmp_path))
        assert calls(esprit, "move_ebsd") == []

    def test_retract_from_an_intermediate_position(self, esprit, tmp_path):
        esprit.ebsd_mm = 10.0

        assert bruker_adapter.retract_ebsd_camera(MICROSCOPE, settings_for(tmp_path))
        assert [call[1] for call in calls(esprit, "move_ebsd")] == [0.0]


class TestPreflightAndParameters:
    def test_eds_preflight(self, esprit, tmp_path):
        settings = settings_for(tmp_path)

        assert bruker_adapter.preflight_eds(settings, [eds_settings()])
        assert (tmp_path / "esprit_eds").is_dir()
        assert (tmp_path / "exp" / bruker_adapter.EDS_H5_FOLDER).is_dir()

    def test_spectrometer_not_ready(self, esprit, tmp_path):
        esprit.spectrometer_ready = False

        with pytest.raises(DetectorError, match="not ready"):
            bruker_adapter.preflight_eds(settings_for(tmp_path), [])

    def test_ebsd_preflight_needs_the_exports(self, esprit, tmp_path, monkeypatch):
        missing = SimpleNamespace(
            **{name: True for name in bruker_adapter._EBSD_REQUIRED_EXPORTS}
        )
        missing.has_save_to_file = False
        monkeypatch.setattr(
            bruker_adapter.BrukerEBSDController, "export_status", lambda self: missing
        )

        with pytest.raises(DetectorError, match="has_save_to_file"):
            bruker_adapter.preflight_ebsd(settings_for(tmp_path), [])

    def test_eds_parameters(self, esprit, tmp_path):
        assert bruker_adapter.set_eds_parameters(settings_for(tmp_path), eds_settings())
        assert calls(esprit, "set_image") == [("set_image", 8, 6, 100)]
        assert calls(esprit, "create_profile") == [("create_profile", 2)]

    def test_eds_size_adjusted_by_esprit_is_refused(self, esprit, tmp_path):
        esprit.image_size = (16, 6)

        with pytest.raises(ConfigurationError, match="16x6"):
            bruker_adapter.set_eds_parameters(settings_for(tmp_path), eds_settings())

    def test_simple_map_builds_no_profile(self, esprit, tmp_path):
        settings = settings_for(tmp_path, map_mode="simple")

        bruker_adapter.set_eds_parameters(settings, eds_settings())

        assert calls(esprit, "create_profile") == []

    def test_ebsd_parameters(self, esprit, tmp_path):
        assert bruker_adapter.set_ebsd_parameters(
            settings_for(tmp_path), ebsd_settings()
        )
        assert [call[0] for call in esprit.calls] == [
            "configure_scan_area",
            "select_profile",
        ]

    def test_unknown_ebsd_profile(self, esprit, tmp_path):
        esprit.profiles = "fast;slow"

        with pytest.raises(ConfigurationError, match="'default'"):
            bruker_adapter.set_ebsd_parameters(settings_for(tmp_path), ebsd_settings())


class TestEdsMap:
    def h5_files(self, tmp_path):
        return sorted((tmp_path / "exp" / bruker_adapter.EDS_H5_FOLDER).glob("*.h5"))

    def test_each_map_writes_its_own_hdf5_file(self, esprit, tmp_path):
        settings = settings_for(tmp_path)

        assert bruker_adapter.map_eds(settings, eds_settings(), 3, print)
        assert bruker_adapter.map_eds(settings, eds_settings(), 4, print)

        files = self.h5_files(tmp_path)
        assert len(files) == 2
        assert [h5py.File(f, "r").attrs["slice_number"] for f in files] == [3, 4]

    def test_hdf5_contents(self, esprit, tmp_path):
        bruker_adapter.map_eds(settings_for(tmp_path), eds_settings(), 3, print)

        (path,) = self.h5_files(tmp_path)
        with h5py.File(path, "r") as f:
            assert f.attrs["vendor"] == "Bruker"
            assert f.attrs["technique"] == "EDS"
            assert f.attrs["bcf_path"].endswith(".bcf")
            assert json.loads(f.attrs["errors"]) == []
            assert f["esprit"].attrs["query_info"] == "ESPRIT 2.5 (fake)"
            maps = f["eds/maps"]
            assert sorted(maps) == ["00", "01"]
            assert maps["00"].shape == (6, 8)
            assert int(maps["01"][0, 0]) == 2
            assert maps["00"].attrs["atomic_number"] == 26
            assert maps["01"].attrs["atomic_number"] == 14
            recorded = json.loads(f["settings"].attrs["json"])
            assert recorded["output"]["slice_number"] == 3
            assert recorded["map"]["output_bcf_path"] == f.attrs["bcf_path"]

    def test_password_is_never_written(self, esprit, tmp_path):
        bruker_adapter.map_eds(settings_for(tmp_path), eds_settings(), 3, print)

        (path,) = self.h5_files(tmp_path)
        assert b"secret" not in path.read_bytes()
        with h5py.File(path, "r") as f:
            assert "password" not in json.loads(f["settings"].attrs["json"])["session"]

    def test_uses_the_configured_time_limit(self, esprit, tmp_path):
        bruker_adapter.map_eds(settings_for(tmp_path), eds_settings(), 3, print)

        ((_, bcf_path, max_wait_s),) = calls(esprit, "acquire_profile")
        assert max_wait_s == 1800.0
        assert "Slice_0003" in bcf_path

    def test_problems_are_recorded_not_raised(self, esprit, tmp_path, capsys):
        esprit.readback_fails = {1}
        esprit.save_bcf = False

        assert bruker_adapter.map_eds(settings_for(tmp_path), eds_settings(), 3, print)

        (path,) = self.h5_files(tmp_path)
        with h5py.File(path, "r") as f:
            errors = json.loads(f.attrs["errors"])
            assert "BCF file missing after acquisition" in errors
            assert any("Element 1" in error for error in errors)
            assert f["eds/maps/01"].attrs["error"] == "ValueError: size mismatch"
            assert "00" in f["eds/maps"]
        assert "WARNING" in capsys.readouterr().out

    def test_simple_map_has_no_element_data(self, esprit, tmp_path):
        bruker_adapter.map_eds(
            settings_for(tmp_path, map_mode="simple"), eds_settings(), 3, print
        )

        assert calls(esprit, "acquire_simple")
        (path,) = self.h5_files(tmp_path)
        with h5py.File(path, "r") as f:
            assert len(f["eds/maps"]) == 0


class TestEbsdMap:
    @pytest.mark.parametrize("concurrent_eds", [False, True])
    def test_map(self, esprit, tmp_path, concurrent_eds):
        step = ebsd_settings(enable_eds=concurrent_eds)

        assert bruker_adapter.map_ebsd(settings_for(tmp_path), step, 5, print)

        ((_, output_path, with_edx),) = calls(esprit, "ebsd_acquisition")
        assert "Slice_0005" in output_path
        assert with_edx is concurrent_eds
