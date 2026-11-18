"""EDAX IPAPI adapter: EBSD camera motion over the IPAPI, state translation,
parameters, and forwarding to edax.workflow. Never touches LaserControl."""

from types import SimpleNamespace

import pytest

pytest.importorskip("autoscript_sdb_microscope_client")

import pytribeam.types as tbt  # noqa: E402
from pytribeam.external_oem.adapters import edax as edax_adapter  # noqa: E402
from pytribeam.external_oem.core.errors import DetectorError  # noqa: E402
from pytribeam.external_oem.edax.errors import EdaxStateError  # noqa: E402
from pytribeam.external_oem.edax.types import (  # noqa: E402
    EdaxCameraStatus,
    EdaxDetectorStatus,
    EdaxMappingStatus,
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

SETTINGS = general_settings(
    OEM.EDAX,
    OEM.EDAX,
    EDAX_settings=tbt.EDAXConfig(
        save_directory="D:/EDAX Data/exp1",
        project_name="exp1",
        connection=tbt.MicroscopeConnection(host="edax-pc", port=8301),
    ),
)


@pytest.fixture
def ipapi(monkeypatch, chamber):
    """Fake IPAPI client and controllers; record commands and client lifetimes."""
    state = SimpleNamespace(
        calls=[],
        camera=EdaxCameraStatus.SLIDE_OUT,
        map_status=EdaxMappingStatus.READY,
        eds_status=EdaxDetectorStatus.READY,
        open_clients=0,
        chamber=chamber,
    )

    class FakeClient:
        def __init__(self, settings, quiet=False):
            state.calls.append(("connect", settings.host, settings.port))

        def __enter__(self):
            state.open_clients += 1
            return self

        def __exit__(self, *exc):
            state.open_clients -= 1
            return False

    class FakeEbsd:
        def __init__(self, client):
            pass

        def camera_status(self):
            return state.camera

        def map_status(self):
            return state.map_status

        def insert_camera(self):
            state.calls.append(("insert_camera", list(chamber.events)))
            state.camera = EdaxCameraStatus.SLIDE_IN

        def retract_camera(self):
            state.calls.append(("retract_camera", list(chamber.events)))
            state.camera = EdaxCameraStatus.SLIDE_OUT

        def apply_map_parameters(self, params):
            state.calls.append(("apply_map_parameters", params))

    class FakeEds:
        def __init__(self, client):
            pass

        def detector_status(self):
            return state.eds_status

    monkeypatch.setattr(edax_adapter, "EdaxClient", FakeClient)
    monkeypatch.setattr(edax_adapter, "EdaxEbsdController", FakeEbsd)
    monkeypatch.setattr(edax_adapter, "EdaxEdsController", FakeEds)

    workflow = edax_adapter.edax_workflow

    def record(name, result=True):
        def call(*args, **kwargs):
            state.calls.append((name, args))
            if isinstance(result, BaseException):
                raise result
            return result

        monkeypatch.setattr(workflow, name, call)

    for name in (
        "check_connection",
        "preflight",
        "preflight_eds",
        "insert_eds_detector",
        "retract_eds_detector",
        "map_ebsd",
        "map_eds",
    ):
        record(name)
    record("eds_detector_state", STATE.RETRACTED)
    state.record = record
    return state


def commands(state):
    return [call[0] for call in state.calls]


class TestCameraState:
    def test_every_edax_camera_status_is_translated(self):
        assert set(edax_adapter.CAMERA_STATE) == set(EdaxCameraStatus)
        assert all(
            isinstance(value, tbt.RetractableDeviceState)
            for value in edax_adapter.CAMERA_STATE.values()
        )

    @pytest.mark.parametrize(
        "status, expected",
        [
            (EdaxCameraStatus.SLIDE_IN, STATE.INSERTED),
            (EdaxCameraStatus.SLIDE_OUT, STATE.RETRACTED),
            (EdaxCameraStatus.SLIDE_MOVING_IN, STATE.BUSY),
            (EdaxCameraStatus.SLIDE_TOUCH_SENSE, STATE.ERROR),
            (EdaxCameraStatus.UNKNOWN, STATE.INDERTERMINATE),
        ],
    )
    def test_reads_the_camera_over_the_ipapi(self, ipapi, status, expected):
        ipapi.camera = status

        assert edax_adapter.get_ebsd_camera_state(SETTINGS) == expected
        assert ipapi.calls == [("connect", "edax-pc", 8301)]
        assert ipapi.open_clients == 0

    def test_eds_state_comes_from_the_workflow(self, ipapi):
        assert edax_adapter.get_eds_detector_state(SETTINGS) == STATE.RETRACTED


class TestCameraMotion:
    def test_insert_runs_under_the_ccd_after_a_collision_check(self, ipapi):
        assert edax_adapter.insert_ebsd_camera(MICROSCOPE, SETTINGS)

        assert ipapi.chamber.checked == [tbt.DetectorType.EBSD]
        assert ("insert_camera", ["ccd_on"]) in ipapi.calls
        assert ipapi.chamber.events == ["ccd_on", "ccd_off"]
        assert ipapi.open_clients == 0

    def test_insert_is_a_no_op_when_already_in(self, ipapi):
        ipapi.camera = EdaxCameraStatus.SLIDE_IN

        assert edax_adapter.insert_ebsd_camera(MICROSCOPE, SETTINGS)
        assert "insert_camera" not in commands(ipapi)
        assert ipapi.chamber.events == []

    def test_insert_refuses_a_possible_collision(self, ipapi):
        ipapi.chamber.collide = True

        with pytest.raises(DetectorError, match="collide"):
            edax_adapter.insert_ebsd_camera(MICROSCOPE, SETTINGS)
        assert ipapi.calls == []

    @pytest.mark.parametrize(
        "status",
        [
            EdaxCameraStatus.UNKNOWN,
            EdaxCameraStatus.SLIDE_MID,
            EdaxCameraStatus.SLIDE_ERROR,
        ],
    )
    def test_insert_refuses_unless_the_slide_is_out(self, ipapi, status):
        ipapi.camera = status

        with pytest.raises(EdaxStateError, match=status.value):
            edax_adapter.insert_ebsd_camera(MICROSCOPE, SETTINGS)
        assert "insert_camera" not in commands(ipapi)

    def test_insert_refuses_during_a_map(self, ipapi):
        ipapi.map_status = EdaxMappingStatus.MAPPING_ACTIVE

        with pytest.raises(EdaxStateError, match="running"):
            edax_adapter.insert_ebsd_camera(MICROSCOPE, SETTINGS)
        assert "insert_camera" not in commands(ipapi)

    @pytest.mark.parametrize(
        "status", [EdaxCameraStatus.SLIDE_IN, EdaxCameraStatus.UNKNOWN]
    )
    def test_retract_proceeds_from_any_state(self, ipapi, status):
        ipapi.camera = status

        assert edax_adapter.retract_ebsd_camera(MICROSCOPE, SETTINGS)
        assert ("retract_camera", ["ccd_on"]) in ipapi.calls

    def test_retract_is_a_no_op_when_out(self, ipapi):
        assert edax_adapter.retract_ebsd_camera(MICROSCOPE, SETTINGS)
        assert "retract_camera" not in commands(ipapi)

    def test_eds_motion_goes_to_the_workflow(self, ipapi):
        assert edax_adapter.insert_eds_detector(MICROSCOPE, SETTINGS)
        assert edax_adapter.retract_eds_detector(MICROSCOPE, SETTINGS)
        assert ipapi.calls == [
            ("insert_eds_detector", (SETTINGS, MICROSCOPE)),
            ("retract_eds_detector", (SETTINGS, MICROSCOPE)),
        ]

    def test_eds_collision_refusal_is_a_detector_error(self, ipapi):
        ipapi.record("insert_eds_detector", SystemError("may collide"))

        with pytest.raises(DetectorError, match="may collide"):
            edax_adapter.insert_eds_detector(MICROSCOPE, SETTINGS)


class TestPreflight:
    def test_ebsd(self, ipapi):
        assert edax_adapter.preflight_ebsd(SETTINGS, [ebsd_settings()])
        assert commands(ipapi) == ["preflight"]

    def test_ebsd_with_concurrent_eds_checks_the_eds_detector(self, ipapi):
        ipapi.eds_status = EdaxDetectorStatus.NOT_READY

        with pytest.raises(EdaxStateError, match="notready"):
            edax_adapter.preflight_ebsd(SETTINGS, [ebsd_settings(enable_eds=True)])

    def test_eds(self, ipapi):
        assert edax_adapter.preflight_eds(SETTINGS, [eds_settings()])
        assert commands(ipapi) == ["preflight_eds", "connect"]

    def test_eds_detector_not_ready(self, ipapi):
        ipapi.eds_status = EdaxDetectorStatus.NOT_READY

        with pytest.raises(EdaxStateError, match="cooled"):
            edax_adapter.preflight_eds(SETTINGS, [])

    @pytest.mark.parametrize("technique", [EBSD, EDS])
    def test_connection(self, ipapi, technique):
        assert edax_adapter.test_connection(SETTINGS, technique)
        assert ipapi.calls == [("check_connection", ("edax-pc", 8301))]


class TestParametersAndMaps:
    def test_ebsd_parameters_are_applied_over_the_ipapi(self, ipapi):
        box = tbt.EBSDScanBox(
            x_start_um=1.0,
            y_start_um=2.0,
            x_size_um=30.0,
            y_size_um=20.0,
            step_size_um=0.5,
        )
        step = ebsd_settings(enable_eds=True, scan_box=box)

        assert edax_adapter.set_ebsd_parameters(SETTINGS, step)

        ((name, params),) = [c for c in ipapi.calls if c[0] == "apply_map_parameters"]
        assert params == edax_adapter.ebsd_map_params(step)
        assert params.step_size_um == 0.5
        assert params.save_spectra is True

    def test_eds_parameters_leave_apex_settings(self, ipapi):
        assert edax_adapter.set_eds_parameters(SETTINGS, eds_settings())
        assert ipapi.calls == []

    def test_ebsd_map_forwards_the_metric_callback(self, ipapi):
        step = ebsd_settings()

        assert edax_adapter.map_ebsd(SETTINGS, step, 4, print)
        assert ipapi.calls == [("map_ebsd", (SETTINGS, step, 4, print))]

    def test_eds_map(self, ipapi):
        step = eds_settings()

        assert edax_adapter.map_eds(SETTINGS, step, 4, print)
        assert ipapi.calls == [("map_eds", (SETTINGS, step, 4))]


def test_never_uses_laser_control():
    """Native EDAX is completely separate from LaserControl."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(edax_adapter))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "pytribeam.laser" not in imported
    source = inspect.getsource(edax_adapter)
    for laser_control in ("insert_EBSD", "retract_EBSD", "connect_EBSD", "insert_EDS"):
        assert laser_control not in source
