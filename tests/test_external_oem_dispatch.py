"""Routing tests for the external OEM dispatcher.

Every backend is replaced by a recording fake adapter, so these tests check
which backend handles each call, with which arguments, and in what order,
without a microscope, LaserControl, or any vendor software. Each adapter is
tested on its own in phase 3.
"""

# python standard libraries
import os
import subprocess
import sys
from types import SimpleNamespace

# 3rd party libraries
import pytest

# The dispatcher is built on pytribeam.types, which needs AutoScript. Skip,
# rather than error at collection, on machines without it.
pytest.importorskip("autoscript_sdb_microscope_client")

# Local
import pytribeam.external_oem.dispatch as external_devices
import pytribeam.types as tbt
from pytribeam.external_oem.core.errors import ConfigurationError, DetectorError

OEM = tbt.ExternalDeviceOEM
BACKEND = tbt.ExternalBackend
STATE = tbt.RetractableDeviceState
EBSD = tbt.ExternalTechnique.EBSD
EDS = tbt.ExternalTechnique.EDS

MICROSCOPE = object()
STEP = SimpleNamespace(number=3, name="ebsd_map")

# ----------------
# Helper functions
# ----------------


def edax_config() -> tbt.EDAXConfig:
    return tbt.EDAXConfig(
        save_directory="D:/EDAX Data/exp1",
        project_name="exp1",
        connection=tbt.MicroscopeConnection(host="edax-pc", port=8301),
    )


def oxford_config() -> tbt.OxfordConfig:
    return tbt.OxfordConfig(
        connection=tbt.MicroscopeConnection(host="aztec-pc", port=22201),
    )


def bruker_config() -> tbt.BrukerConfig:
    return tbt.BrukerConfig(dll_dir="C:/Program Files/Bruker/Esprit API")


def general_settings(ebsd_oem=OEM.NONE, eds_oem=OEM.NONE, **blocks):
    """Build minimal GeneralSettings for dispatcher tests."""
    return tbt.GeneralSettings(
        yml_version=1.2,
        slice_thickness_um=1.0,
        max_slice_number=1,
        pre_tilt_deg=0.0,
        sectioning_axis=tbt.SectioningAxis.Z,
        stage_tolerance=tbt.StageTolerance(translational_um=1.0, angular_deg=1.0),
        connection=tbt.MicroscopeConnection(host="localhost"),
        EBSD_OEM=ebsd_oem,
        EDS_OEM=eds_oem,
        exp_dir=".",
        h5_log_name="log",
        step_count=1,
        **blocks,
    )


def ebsd_settings(enable_eds=False) -> tbt.EBSDSettings:
    return tbt.EBSDSettings(image=None, enable_eds=enable_eds)


def eds_settings() -> tbt.EDSSettings:
    return tbt.EDSSettings(image=None)


def step(operation_settings, number=1):
    return tbt.Step(
        type=None,
        name=f"step_{number}",
        number=number,
        frequency=1,
        stage=None,
        operation_settings=operation_settings,
    )


class FakeAdapter:
    """Stand-in adapter that records every call into a shared list."""

    FUNCTIONS = (
        "test_connection",
        "preflight_ebsd",
        "preflight_eds",
        "get_ebsd_camera_state",
        "get_eds_detector_state",
        "insert_ebsd_camera",
        "insert_eds_detector",
        "retract_ebsd_camera",
        "retract_eds_detector",
        "set_ebsd_parameters",
        "set_eds_parameters",
        "map_ebsd",
        "map_eds",
    )

    def __init__(self, backend, calls):
        self.__name__ = f"fake.{backend.value}"
        self.backend = backend
        self.calls = calls
        self.returns = {name: True for name in self.FUNCTIONS}
        self.returns["get_ebsd_camera_state"] = STATE.RETRACTED
        self.returns["get_eds_detector_state"] = STATE.RETRACTED
        self.raises = {}
        self.metrics = []  # (name, value) reported by map_* through on_metric

    def __getattr__(self, name):
        if name not in self.FUNCTIONS:
            raise AttributeError(name)

        def record(*args):
            self.calls.append((self.backend, name, args))
            if name in self.raises:
                raise self.raises[name]
            if name.startswith("map_"):
                on_metric = args[-1]
                for metric in self.metrics:
                    on_metric(*metric)
            return self.returns[name]

        return record


@pytest.fixture
def adapters(monkeypatch, chamber):
    """Replace every adapter with a FakeAdapter; record calls and metric logs.

    The chamber CCD and collision check are intercepted too (``chamber``).
    """
    calls = []
    logged = []
    fakes = {backend: FakeAdapter(backend, calls) for backend in BACKEND}
    monkeypatch.setattr(external_devices, "adapter", lambda backend: fakes[backend])
    monkeypatch.setattr(
        external_devices.log,
        "ebsd_camera_saturation",
        lambda **kwargs: logged.append((external_devices.CAMERA_SATURATION, kwargs)),
    )
    monkeypatch.setattr(
        external_devices.log,
        "ebsd_average_ci",
        lambda **kwargs: logged.append((external_devices.AVERAGE_CI, kwargs)),
    )
    return SimpleNamespace(fakes=fakes, calls=calls, logged=logged, chamber=chamber)


def names(calls):
    """Return just (backend, function) from recorded calls."""
    return [(backend, name) for backend, name, _ in calls]


# Settings for each backend, both techniques on the same OEM.
EVERY_BACKEND = {
    BACKEND.TFS_LASER: lambda: general_settings(OEM.EDAX, OEM.EDAX),
    BACKEND.EDAX_IPAPI: lambda: general_settings(
        OEM.EDAX, OEM.EDAX, EDAX_settings=edax_config()
    ),
    BACKEND.OXFORD_AZTEC: lambda: general_settings(
        OEM.OXFORD, OEM.OXFORD, Oxford_settings=oxford_config()
    ),
    BACKEND.BRUKER_ESPRIT: lambda: general_settings(
        OEM.BRUKER, OEM.BRUKER, Bruker_settings=bruker_config()
    ),
}

# -----------------
# Backend selection
# -----------------


class TestBackendSelection:
    @pytest.mark.parametrize(
        "settings, expected",
        [
            (general_settings(OEM.EDAX), BACKEND.TFS_LASER),
            (
                general_settings(OEM.EDAX, EDAX_settings=edax_config()),
                BACKEND.EDAX_IPAPI,
            ),
            (general_settings(OEM.OXFORD), BACKEND.TFS_LASER),
            (
                general_settings(OEM.OXFORD, Oxford_settings=oxford_config()),
                BACKEND.OXFORD_AZTEC,
            ),
            (
                general_settings(OEM.OXFORD, EDAX_settings=edax_config()),
                BACKEND.TFS_LASER,
            ),
            (
                general_settings(OEM.BRUKER, Bruker_settings=bruker_config()),
                BACKEND.BRUKER_ESPRIT,
            ),
            (general_settings(), None),
        ],
    )
    def test_ebsd_backend(self, settings, expected):
        assert external_devices.backend(settings, EBSD) is expected

    def test_each_technique_follows_its_own_oem(self):
        settings = general_settings(OEM.NONE, OEM.EDAX, EDAX_settings=edax_config())

        assert external_devices.backend(settings, EBSD) is None
        assert external_devices.backend(settings, EDS) is BACKEND.EDAX_IPAPI

    def test_bruker_without_its_block_is_a_configuration_error(self):
        with pytest.raises(ConfigurationError, match="Bruker_settings"):
            external_devices.backend(general_settings(OEM.BRUKER), EBSD)

    def test_every_backend_has_an_adapter_module(self):
        assert set(external_devices.ADAPTER_MODULES) == set(BACKEND)
        for module in external_devices.ADAPTER_MODULES.values():
            assert module.startswith("pytribeam.external_oem.adapters.")

    def test_adapter_imports_the_backend_module(self, monkeypatch):
        imported = []
        monkeypatch.setattr(
            external_devices.importlib,
            "import_module",
            lambda name: imported.append(name) or name,
        )

        found = external_devices.adapter(BACKEND.OXFORD_AZTEC)

        assert imported == ["pytribeam.external_oem.adapters.oxford"]
        assert found == "pytribeam.external_oem.adapters.oxford"

    def test_importing_the_dispatcher_loads_no_vendor_package(self):
        """Vendor code is imported lazily, so one OEM never loads another."""
        code = (
            "import sys, pytribeam.external_oem.dispatch\n"
            "vendors = ('edax', 'oxford', 'adapters')\n"
            "loaded = [m for m in sys.modules\n"
            "          if m.split('.')[2:3] and m.split('.')[2] in vendors\n"
            "          and m.startswith('pytribeam.external_oem.')]\n"
            "print(loaded)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)},
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().splitlines()[-1] == "[]"


# -------------------------
# Forwarding, every backend
# -------------------------


@pytest.mark.parametrize("backend", list(BACKEND))
class TestForwarding:
    """Each public call reaches the selected backend with the same arguments."""

    def test_detector_motion_and_state(self, adapters, backend):
        settings = EVERY_BACKEND[backend]()

        assert external_devices.insert_ebsd_camera(MICROSCOPE, settings)
        assert external_devices.insert_eds_detector(MICROSCOPE, settings)
        assert external_devices.get_ebsd_camera_state(settings) == STATE.RETRACTED
        assert external_devices.get_eds_detector_state(settings) == STATE.RETRACTED
        assert external_devices.retract_ebsd_camera(MICROSCOPE, settings)
        assert external_devices.retract_eds_detector(MICROSCOPE, settings)

        assert adapters.calls == [
            (backend, "insert_ebsd_camera", (MICROSCOPE, settings)),
            (backend, "insert_eds_detector", (MICROSCOPE, settings)),
            (backend, "get_ebsd_camera_state", (settings,)),
            (backend, "get_eds_detector_state", (settings,)),
            (backend, "retract_ebsd_camera", (MICROSCOPE, settings)),
            (backend, "retract_eds_detector", (MICROSCOPE, settings)),
        ]

    def test_connection(self, adapters, backend):
        settings = EVERY_BACKEND[backend]()

        assert external_devices.test_connection(settings, EBSD)
        assert external_devices.test_connection(settings, EDS)

        assert adapters.calls == [
            (backend, "test_connection", (settings, EBSD)),
            (backend, "test_connection", (settings, EDS)),
        ]

    def test_parameters(self, adapters, backend):
        settings = EVERY_BACKEND[backend]()
        ebsd, eds = ebsd_settings(), eds_settings()

        assert external_devices.set_ebsd_parameters(settings, ebsd)
        assert external_devices.set_eds_parameters(settings, eds)

        assert adapters.calls == [
            (backend, "set_ebsd_parameters", (settings, ebsd)),
            (backend, "set_eds_parameters", (settings, eds)),
        ]

    def test_maps_apply_the_step_parameters_first(self, adapters, backend):
        settings = EVERY_BACKEND[backend]()
        ebsd, eds = ebsd_settings(), eds_settings()

        assert external_devices.map_ebsd(settings, ebsd, 7, STEP)
        assert external_devices.map_eds(settings, eds, 8, STEP)

        assert names(adapters.calls) == [
            (backend, "set_ebsd_parameters"),
            (backend, "map_ebsd"),
            (backend, "set_eds_parameters"),
            (backend, "map_eds"),
        ]
        assert adapters.calls[1][2][:3] == (settings, ebsd, 7)
        assert adapters.calls[3][2][:3] == (settings, eds, 8)
        assert callable(adapters.calls[1][2][3])

    def test_adapter_results_are_passed_back(self, adapters, backend):
        settings = EVERY_BACKEND[backend]()
        adapters.fakes[backend].returns["insert_ebsd_camera"] = False
        adapters.fakes[backend].returns["get_eds_detector_state"] = STATE.INSERTED

        assert external_devices.insert_ebsd_camera(MICROSCOPE, settings) is False
        assert external_devices.get_eds_detector_state(settings) == STATE.INSERTED


# ------------------
# No OEM configured
# ------------------


class TestNoOemConfigured:
    @pytest.mark.parametrize(
        "call",
        [
            lambda s: external_devices.test_connection(s, EBSD),
            lambda s: external_devices.get_ebsd_camera_state(s),
            lambda s: external_devices.get_eds_detector_state(s),
            lambda s: external_devices.insert_ebsd_camera(MICROSCOPE, s),
            lambda s: external_devices.insert_eds_detector(MICROSCOPE, s),
            lambda s: external_devices.set_ebsd_parameters(s, ebsd_settings()),
            lambda s: external_devices.set_eds_parameters(s, eds_settings()),
            lambda s: external_devices.map_ebsd(s, ebsd_settings(), 1, STEP),
            lambda s: external_devices.map_eds(s, eds_settings(), 1, STEP),
        ],
    )
    def test_device_operations_are_refused(self, adapters, call):
        with pytest.raises(ConfigurationError, match="OEM is configured"):
            call(general_settings())
        assert adapters.calls == []

    def test_retraction_is_a_no_op(self, adapters):
        settings = general_settings()

        assert external_devices.retract_ebsd_camera(MICROSCOPE, settings)
        assert external_devices.retract_eds_detector(MICROSCOPE, settings)
        assert external_devices.retract_all_external_devices(MICROSCOPE, settings)
        assert adapters.calls == []

    def test_concurrent_eds_needs_an_eds_oem(self, adapters):
        """Detector motion follows the detector's OEM, not the EBSD step's."""
        settings = general_settings(OEM.EDAX, OEM.NONE, EDAX_settings=edax_config())

        with pytest.raises(ConfigurationError, match="EDS OEM"):
            external_devices.insert_eds_detector(MICROSCOPE, settings)


# ---------------
# Input checking
# ---------------


class TestInputChecking:
    def test_vendor_states_are_rejected(self, adapters):
        """Adapters must translate vendor states; a raw value is a bug."""
        settings = EVERY_BACKEND[BACKEND.OXFORD_AZTEC]()
        adapters.fakes[BACKEND.OXFORD_AZTEC].returns["get_ebsd_camera_state"] = "IN"

        with pytest.raises(TypeError, match="RetractableDeviceState"):
            external_devices.get_ebsd_camera_state(settings)

    @pytest.mark.parametrize(
        "call",
        [
            lambda s: external_devices.set_ebsd_parameters(s, eds_settings()),
            lambda s: external_devices.set_eds_parameters(s, ebsd_settings()),
            lambda s: external_devices.map_ebsd(s, eds_settings(), 1, STEP),
            lambda s: external_devices.map_eds(s, ebsd_settings(), 1, STEP),
        ],
    )
    def test_step_settings_must_match_the_technique(self, adapters, call):
        with pytest.raises(TypeError):
            call(EVERY_BACKEND[BACKEND.EDAX_IPAPI]())
        assert adapters.calls == []

    def test_unknown_technique(self):
        with pytest.raises(TypeError):
            external_devices.oem(general_settings(), "EBSD")


# ---------
# Preflight
# ---------


class TestPreflight:
    def steps(self):
        return [
            step(ebsd_settings(), number=1),
            step(eds_settings(), number=2),
            step(ebsd_settings(enable_eds=True), number=3),
            step(object(), number=4),  # e.g. an image step
        ]

    def test_ebsd_sequence(self, adapters):
        settings = EVERY_BACKEND[BACKEND.OXFORD_AZTEC]()
        steps = self.steps()
        ebsd_steps = [steps[0].operation_settings, steps[2].operation_settings]
        backend = BACKEND.OXFORD_AZTEC

        assert external_devices.preflight_ebsd(settings, steps)

        assert adapters.calls == [
            (backend, "test_connection", (settings, EBSD)),
            (backend, "get_ebsd_camera_state", (settings,)),
            (backend, "preflight_ebsd", (settings, ebsd_steps)),
            (backend, "set_ebsd_parameters", (settings, ebsd_steps[0])),
            (backend, "set_ebsd_parameters", (settings, ebsd_steps[1])),
        ]

    def test_eds_sequence(self, adapters):
        settings = EVERY_BACKEND[BACKEND.BRUKER_ESPRIT]()
        steps = self.steps()
        eds_steps = [steps[1].operation_settings]
        backend = BACKEND.BRUKER_ESPRIT

        assert external_devices.preflight_eds(settings, steps)

        assert adapters.calls == [
            (backend, "test_connection", (settings, EDS)),
            (backend, "get_eds_detector_state", (settings,)),
            (backend, "preflight_eds", (settings, eds_steps)),
            (backend, "set_eds_parameters", (settings, eds_steps[0])),
        ]

    def test_without_steps_still_checks_the_detector(self, adapters):
        settings = EVERY_BACKEND[BACKEND.EDAX_IPAPI]()

        assert external_devices.preflight_eds(settings, [])

        assert names(adapters.calls) == [
            (BACKEND.EDAX_IPAPI, "test_connection"),
            (BACKEND.EDAX_IPAPI, "get_eds_detector_state"),
            (BACKEND.EDAX_IPAPI, "preflight_eds"),
        ]

    def test_failed_connection_stops_preflight(self, adapters):
        settings = EVERY_BACKEND[BACKEND.EDAX_IPAPI]()
        adapters.fakes[BACKEND.EDAX_IPAPI].returns["test_connection"] = False

        with pytest.raises(DetectorError, match="connection test failed"):
            external_devices.preflight_ebsd(settings, self.steps())
        assert names(adapters.calls) == [(BACKEND.EDAX_IPAPI, "test_connection")]

    def test_detector_in_error_stops_preflight(self, adapters):
        settings = EVERY_BACKEND[BACKEND.EDAX_IPAPI]()
        adapters.fakes[BACKEND.EDAX_IPAPI].returns["get_ebsd_camera_state"] = (
            STATE.ERROR
        )

        with pytest.raises(DetectorError, match="error state"):
            external_devices.preflight_ebsd(settings, self.steps())
        assert (BACKEND.EDAX_IPAPI, "preflight_ebsd") not in names(adapters.calls)

    def test_parameter_failure_is_raised_before_the_experiment(self, adapters):
        settings = EVERY_BACKEND[BACKEND.OXFORD_AZTEC]()
        adapters.fakes[BACKEND.OXFORD_AZTEC].raises["set_ebsd_parameters"] = (
            ConfigurationError("profile 'ebsd' not found")
        )

        with pytest.raises(ConfigurationError, match="profile"):
            external_devices.preflight_ebsd(settings, self.steps())

    def test_no_oem_and_no_steps_has_nothing_to_check(self, adapters):
        assert external_devices.preflight_ebsd(general_settings(), [step(object())])
        assert adapters.calls == []

    def test_steps_without_an_oem_are_refused(self, adapters):
        with pytest.raises(ConfigurationError, match="EBSD steps"):
            external_devices.preflight_ebsd(general_settings(), self.steps())

    def test_concurrent_eds_without_an_eds_oem_is_refused(self, adapters):
        """Caught before the experiment, not at the first slice's insert."""
        settings = general_settings(
            OEM.OXFORD, OEM.NONE, Oxford_settings=oxford_config()
        )

        with pytest.raises(ConfigurationError, match="concurrent EDS"):
            external_devices.preflight_ebsd(
                settings, [step(ebsd_settings(enable_eds=True))]
            )
        assert adapters.calls == []

    def test_ebsd_only_steps_need_no_eds_oem(self, adapters):
        settings = general_settings(
            OEM.OXFORD, OEM.NONE, Oxford_settings=oxford_config()
        )

        assert external_devices.preflight_ebsd(settings, [step(ebsd_settings())])


# ----------------
# Retract all
# ----------------


class TestMotionSafety:
    """Collision checks and the chamber CCD are enforced here for every backend."""

    @pytest.mark.parametrize("backend", list(BACKEND))
    def test_insert_is_checked_then_runs_under_the_ccd(self, adapters, backend):
        settings = EVERY_BACKEND[backend]()
        fake = adapters.fakes[backend]
        seen = []
        fake.returns["insert_ebsd_camera"] = True
        original = fake.__getattr__("insert_ebsd_camera")

        def insert(*args):
            seen.append(list(adapters.chamber.events))
            return original(*args)

        fake.__dict__["insert_ebsd_camera"] = insert

        assert external_devices.insert_ebsd_camera(MICROSCOPE, settings)

        assert [d for d, _ in adapters.chamber.checked] == [tbt.DetectorType.EBSD]
        assert seen == [["ccd_on"]]  # the move ran with the CCD live
        assert adapters.chamber.events == ["ccd_on", "ccd_off"]

    @pytest.mark.parametrize(
        "insert, detector",
        [
            (external_devices.insert_ebsd_camera, tbt.DetectorType.EBSD),
            (external_devices.insert_eds_detector, tbt.DetectorType.EDS),
        ],
    )
    def test_a_possible_collision_is_refused(self, adapters, insert, detector):
        adapters.chamber.collide = True

        with pytest.raises(DetectorError, match=f"insert the {detector.value}"):
            insert(MICROSCOPE, EVERY_BACKEND[BACKEND.OXFORD_AZTEC]())
        assert adapters.calls == []
        assert adapters.chamber.events == []

    def test_retract_runs_under_the_ccd(self, adapters):
        settings = EVERY_BACKEND[BACKEND.BRUKER_ESPRIT]()

        external_devices.retract_ebsd_camera(MICROSCOPE, settings)
        external_devices.retract_eds_detector(MICROSCOPE, settings)

        assert adapters.chamber.events == ["ccd_on", "ccd_off"] * 2
        assert adapters.chamber.checked == []  # retracting is the safe direction

    def test_the_ccd_closes_when_a_move_fails(self, adapters):
        settings = EVERY_BACKEND[BACKEND.EDAX_IPAPI]()
        adapters.fakes[BACKEND.EDAX_IPAPI].raises["retract_eds_detector"] = (
            DetectorError("slide stuck")
        )

        with pytest.raises(DetectorError, match="slide stuck"):
            external_devices.retract_eds_detector(MICROSCOPE, settings)
        assert adapters.chamber.events == ["ccd_on", "ccd_off"]

    def test_no_oem_retract_shows_no_ccd(self, adapters):
        assert external_devices.retract_ebsd_camera(MICROSCOPE, general_settings())
        assert adapters.chamber.events == []

    def test_external_states_only_when_a_collision_partner_is_external(
        self, adapters, monkeypatch
    ):
        """Today EBSD and EDS collide only with the CBS, so no vendor query."""
        settings = EVERY_BACKEND[BACKEND.OXFORD_AZTEC]()

        external_devices.insert_eds_detector(MICROSCOPE, settings)
        assert adapters.chamber.checked == [(tbt.DetectorType.EDS, None)]

        monkeypatch.setattr(
            external_devices.Constants,
            "detector_collisions",
            [[tbt.DetectorType.EBSD, tbt.DetectorType.EDS]],
        )
        adapters.chamber.checked.clear()
        external_devices.insert_eds_detector(MICROSCOPE, settings)

        ((detector, states),) = adapters.chamber.checked
        assert states == {
            tbt.DetectorType.EBSD: STATE.RETRACTED,
            tbt.DetectorType.EDS: STATE.RETRACTED,
        }


class TestExternalStates:
    def test_only_configured_detectors(self, adapters):
        settings = general_settings(
            OEM.NONE, OEM.OXFORD, Oxford_settings=oxford_config()
        )
        adapters.fakes[BACKEND.OXFORD_AZTEC].returns["get_eds_detector_state"] = (
            STATE.INSERTED
        )

        assert external_devices.external_detector_states(settings) == {
            tbt.DetectorType.EDS: STATE.INSERTED
        }

    def test_an_unreadable_state_counts_as_error(self, adapters, capsys):
        settings = EVERY_BACKEND[BACKEND.EDAX_IPAPI]()
        adapters.fakes[BACKEND.EDAX_IPAPI].raises["get_ebsd_camera_state"] = (
            DetectorError("IPAPI down")
        )

        states = external_devices.external_detector_states(settings)

        assert states[tbt.DetectorType.EBSD] == STATE.ERROR
        assert states[tbt.DetectorType.EDS] == STATE.RETRACTED
        assert "IPAPI down" in capsys.readouterr().out

    def test_registered_for_collision_checks(self, adapters, monkeypatch):
        import pytribeam.insertable_devices as devices

        monkeypatch.setattr(devices, "_external_state_source", None)
        monkeypatch.setattr(devices, "external", None)  # no LaserControl
        settings = EVERY_BACKEND[BACKEND.BRUKER_ESPRIT]()
        adapters.fakes[BACKEND.BRUKER_ESPRIT].returns["get_eds_detector_state"] = (
            STATE.INSERTED
        )

        assert devices.external_detector_state(tbt.DetectorType.EDS) is None
        external_devices.use_for_collision_checks(settings)

        assert devices.external_detector_state(tbt.DetectorType.EDS) == STATE.INSERTED
        assert devices.external_detector_state(tbt.DetectorType.EBSD) == STATE.RETRACTED


class TestStageGuard:
    def test_all_retracted(self, adapters):
        assert external_devices.check_safe_for_stage_motion(
            EVERY_BACKEND[BACKEND.TFS_LASER]()
        )

    def test_no_oem_has_nothing_to_check(self, adapters):
        assert external_devices.check_safe_for_stage_motion(general_settings())
        assert adapters.calls == []

    @pytest.mark.parametrize("state", [STATE.INSERTED, STATE.BUSY, STATE.ERROR])
    def test_blocking_states_refuse_the_move(self, adapters, state):
        settings = EVERY_BACKEND[BACKEND.OXFORD_AZTEC]()
        adapters.fakes[BACKEND.OXFORD_AZTEC].returns["get_eds_detector_state"] = state

        with pytest.raises(DetectorError, match=f"EDS is {state.name}"):
            external_devices.check_safe_for_stage_motion(settings)

    def test_indeterminate_warns_but_allows(self, adapters, capsys):
        settings = EVERY_BACKEND[BACKEND.EDAX_IPAPI]()
        adapters.fakes[BACKEND.EDAX_IPAPI].returns["get_eds_detector_state"] = (
            STATE.INDERTERMINATE
        )

        assert external_devices.check_safe_for_stage_motion(settings)
        assert "INDERTERMINATE" in capsys.readouterr().out


class TestRetractAll:
    def test_retracts_both_detectors(self, adapters):
        settings = EVERY_BACKEND[BACKEND.EDAX_IPAPI]()

        assert external_devices.retract_all_external_devices(MICROSCOPE, settings)

        assert names(adapters.calls) == [
            (BACKEND.EDAX_IPAPI, "retract_ebsd_camera"),
            (BACKEND.EDAX_IPAPI, "retract_eds_detector"),
        ]

    def test_skips_a_technique_with_no_oem(self, adapters):
        settings = general_settings(
            OEM.NONE, OEM.OXFORD, Oxford_settings=oxford_config()
        )

        assert external_devices.retract_all_external_devices(MICROSCOPE, settings)
        assert names(adapters.calls) == [(BACKEND.OXFORD_AZTEC, "retract_eds_detector")]

    def test_attempts_every_retraction_before_raising(self, adapters):
        """An abort must still retract the EDS detector if the camera fails."""
        settings = EVERY_BACKEND[BACKEND.OXFORD_AZTEC]()
        adapters.fakes[BACKEND.OXFORD_AZTEC].raises["retract_ebsd_camera"] = (
            DetectorError("camera touched")
        )

        with pytest.raises(DetectorError, match="EBSD camera.*camera touched"):
            external_devices.retract_all_external_devices(MICROSCOPE, settings)
        assert names(adapters.calls) == [
            (BACKEND.OXFORD_AZTEC, "retract_ebsd_camera"),
            (BACKEND.OXFORD_AZTEC, "retract_eds_detector"),
        ]

    def test_a_reported_failure_is_raised(self, adapters):
        settings = EVERY_BACKEND[BACKEND.TFS_LASER]()
        adapters.fakes[BACKEND.TFS_LASER].returns["retract_eds_detector"] = False

        with pytest.raises(DetectorError, match="EDS detector"):
            external_devices.retract_all_external_devices(MICROSCOPE, settings)


# --------------
# Metric logging
# --------------


class TestMetricLogging:
    def test_map_logs_each_metric_as_reported(self, adapters):
        settings = EVERY_BACKEND[BACKEND.EDAX_IPAPI]()
        adapters.fakes[BACKEND.EDAX_IPAPI].metrics = [
            (external_devices.CAMERA_SATURATION, 0.6),
            (external_devices.AVERAGE_CI, 0.85),
        ]

        external_devices.map_ebsd(settings, ebsd_settings(), 7, STEP)

        assert [name for name, _ in adapters.logged] == [
            external_devices.CAMERA_SATURATION,
            external_devices.AVERAGE_CI,
        ]
        saturation = adapters.logged[0][1]
        assert saturation["cam_sat_p"] == 0.6
        assert saturation["step_number"] == 3
        assert saturation["step_name"] == "ebsd_map"
        assert saturation["slice_number"] == 7
        assert saturation["log_filepath"] == settings.log_filepath
        assert adapters.logged[1][1]["avg_ci_p"] == 0.85

    def test_unknown_metric_is_reported_not_raised(self, adapters, capsys):
        """A vendor reporting something new must not abort an experiment."""
        settings = EVERY_BACKEND[BACKEND.OXFORD_AZTEC]()
        adapters.fakes[BACKEND.OXFORD_AZTEC].metrics = [("pattern_quality", 0.4)]

        assert external_devices.map_ebsd(settings, ebsd_settings(), 7, STEP)

        assert adapters.logged == []
        assert "pattern_quality" in capsys.readouterr().out
