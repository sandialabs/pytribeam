#!/usr/bin/python3
"""
Collection tests on an EDAX TriBeam: an EBSD map, an EBSD + EDS map, and an
EDS map.

Each test makes the same dispatcher calls as the workflow's EBSD or EDS step,
so what passes here is what an experiment runs:

========================  ================================================
Map                       Path
========================  ================================================
EBSD                      native IPAPI, camera inserted by LaserControl
EBSD + concurrent EDS     as EBSD, spectra saved, EDS detector over IPAPI
EDS                       native IPAPI throughout, headless
========================  ================================================

Unlike the read-only sweep in ``test_edax_ipapi_hardware.py``, these need the
microscope PC: AutoScript for the camera-saturation measurement, LaserControl
for detector motion and EDS, and the IPAPI for EBSD. They insert detectors,
scan the beam, and write maps, so they have their own opt-in::

    $env:PYTRIBEAM_RUN_HARDWARE = "1"
    $env:PYTRIBEAM_EDAX_HOST = "localhost"
    $env:PYTRIBEAM_EDAX_ALLOW_MAPPING = "1"
    $env:PYTRIBEAM_EDAX_MAP_FOLDER = "D:\\EDAX Data\\pytribeam_hardware_test"
    python -m pytest tests/edax/hardware/test_edax_collection_hardware.py -v

Before running:

- Put the sample at the EBSD position (tilted, at working distance) with the
  electron beam on. Nothing here moves the stage.
- Leave the EDAX software open with no map running.
- The EDS map uses APEX's current EDS map settings (resolution, frames,
  dwell); only where it saves is set by the test.
- Point ``PYTRIBEAM_EDAX_MAP_FOLDER`` at an existing scratch folder on the EDAX
  PC, and clear it between runs. Each run writes ``Slice_0001`` (EBSD),
  ``Slice_0002`` (EBSD + EDS), and ``Slice_0003_EDS`` there, and EDAX requires
  tags to be unique within a folder.

When the IPAPI host is this machine, as it is with ``localhost``, the tests
also look in that folder and fail if a map wrote nothing to it.

``PYTRIBEAM_EDAX_MAP_SIZE_UM`` (default 5) and ``PYTRIBEAM_EDAX_MAP_STEP_UM``
(default 0.5) set the square scan area, centered in the field of view.

Every test also watches detector motion: each insertion and retraction, over
LaserControl or the IPAPI, must happen while the chamber CCD is live in the
lower-right quadrant, so the operator can stop a collision. A move made with
the CCD off fails the test.
"""

# Default python modules
import os
import platform
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

# Third-party modules
import pytest

# These tests drive the microscope, so they need AutoScript. Skip, rather than
# error at collection, on machines without it, such as the EDAX PC.
pytest.importorskip("autoscript_sdb_microscope_client")

import h5py  # noqa: E402

# Local scripts
import pytribeam.external_oem.dispatch as external_devices  # noqa: E402
import pytribeam.image as img  # noqa: E402
import pytribeam.insertable_devices as devices  # noqa: E402
import pytribeam.log as log  # noqa: E402
import pytribeam.types as tbt  # noqa: E402
from pytribeam.constants import Constants  # noqa: E402
from pytribeam.external_oem.edax.client import EdaxClient  # noqa: E402
from pytribeam.external_oem.edax.ebsd import EdaxEbsdController  # noqa: E402
from pytribeam.external_oem.edax.eds import EdaxEdsController  # noqa: E402
from pytribeam.external_oem.edax.errors import EdaxUnsupportedCommandError  # noqa: E402
from pytribeam.external_oem.edax.types import (  # noqa: E402
    EdaxCameraStatus,
    EdaxCommand,
    EdaxConnectionSettings,
    EdaxDetectorSlideStatus,
    EdaxEbsdMapParams,
    EdaxEbsdResolution,
    EdaxMappingStatus,
)

EDAX_HOST_ENV_VAR = "PYTRIBEAM_EDAX_HOST"
EDAX_PORT_ENV_VAR = "PYTRIBEAM_EDAX_PORT"
ALLOW_MAPPING_ENV_VAR = "PYTRIBEAM_EDAX_ALLOW_MAPPING"
MAP_FOLDER_ENV_VAR = "PYTRIBEAM_EDAX_MAP_FOLDER"
MAP_SIZE_ENV_VAR = "PYTRIBEAM_EDAX_MAP_SIZE_UM"
MAP_STEP_ENV_VAR = "PYTRIBEAM_EDAX_MAP_STEP_UM"

#: EDAX project the test maps are filed under, kept apart from real experiments.
PROJECT_NAME = "pytribeam_hardware_test"

# Statuses meaning EDAX is busy and a test map must not be started.
_BUSY = frozenset(
    {
        EdaxMappingStatus.SETUP_ACTIVE,
        EdaxMappingStatus.SETUP_PAUSED,
        EdaxMappingStatus.MAPPING_ACTIVE,
        EdaxMappingStatus.MAPPING_PAUSED,
        EdaxMappingStatus.MAPPING_RESUMED,
    }
)


def _flag(name: str) -> bool:
    """Return True when an environment variable is an explicit opt-in."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


pytestmark = [
    pytest.mark.hardware,
    pytest.mark.laser_hardware,
    pytest.mark.edax_hardware,
    pytest.mark.skipif(
        not _flag(ALLOW_MAPPING_ENV_VAR),
        reason=(
            f"{ALLOW_MAPPING_ENV_VAR} is not set; these tests insert detectors, "
            "scan the beam, and write maps"
        ),
    ),
]


# ----------------------------------------------------------------------
# Fixtures and helpers
# ----------------------------------------------------------------------
def _scan_geometry():
    """Return the (size, step) of the square test scan, in micrometers."""
    size_um = float(os.environ.get(MAP_SIZE_ENV_VAR, "5.0"))
    step_um = float(os.environ.get(MAP_STEP_ENV_VAR, "0.5"))
    return size_um, step_um


@pytest.fixture(scope="module")
def edax_config() -> tbt.EDAXConfig:
    """Return the EDAX_settings block for the test experiment."""
    host = os.environ.get(EDAX_HOST_ENV_VAR, "").strip()
    folder = os.environ.get(MAP_FOLDER_ENV_VAR, "").strip()
    if not host:
        pytest.skip(f"{EDAX_HOST_ENV_VAR} is not set")
    if not folder:
        pytest.skip(f"{MAP_FOLDER_ENV_VAR} is not set; maps need a scratch folder")
    return tbt.EDAXConfig(
        save_directory=folder,
        project_name=PROJECT_NAME,
        connection=tbt.MicroscopeConnection(
            host=host, port=int(os.environ.get(EDAX_PORT_ENV_VAR, "8301"))
        ),
    )


@pytest.fixture
def experiment(tmp_path, edax_config) -> tbt.GeneralSettings:
    """Return experiment settings with a fresh log file for this test."""
    settings = tbt.GeneralSettings(
        yml_version=1.1,
        slice_thickness_um=1.0,
        max_slice_number=2,
        pre_tilt_deg=0.0,
        sectioning_axis=tbt.SectioningAxis.Z,
        stage_tolerance=tbt.StageTolerance(translational_um=1.0, angular_deg=1.0),
        connection=tbt.MicroscopeConnection(host="localhost"),
        EBSD_OEM=tbt.ExternalDeviceOEM.EDAX,
        EDS_OEM=tbt.ExternalDeviceOEM.EDAX,
        exp_dir=str(tmp_path),
        h5_log_name="edax_hardware",
        step_count=3,
        EDAX_settings=edax_config,
    )
    log.create_file(settings.log_filepath)
    return settings


@contextmanager
def _ipapi(config: tbt.EDAXConfig):
    """Open a client of our own, for checks around the dispatcher's calls."""
    settings = EdaxConnectionSettings(
        host=config.connection.host, port=config.connection.port
    )
    with EdaxClient(settings, quiet=True) as client:
        yield client


def _require_idle(config: tbt.EDAXConfig) -> None:
    """Skip, rather than interfere, if EDAX is not free to collect."""
    with _ipapi(config) as client:
        ebsd = EdaxEbsdController(client)
        if not ebsd.app_started():
            pytest.skip("The EDAX application is not running.")
        if ebsd.map_status() in _BUSY:
            pytest.skip("An EBSD map or setup is already running in EDAX.")
        try:
            if EdaxEdsController(client).map_status() in _BUSY:
                pytest.skip("An EDS map or setup is already running in EDAX.")
        except EdaxUnsupportedCommandError:
            pass  # this build cannot report EDS status; EBSD status sufficed


def _ebsd_step_settings(microscope, enable_eds: bool) -> tbt.EBSDSettings:
    """Return EBSD step settings for a small square scan at the FOV center."""
    size_um, step_um = _scan_geometry()
    return tbt.EBSDSettings(
        # Only the microscope handle is read from the image settings here.
        image=SimpleNamespace(microscope=microscope),
        enable_eds=enable_eds,
        scan_box=tbt.EBSDScanBox(
            x_start_um=-size_um / 2.0,
            y_start_um=-size_um / 2.0,
            x_size_um=size_um,
            y_size_um=size_um,
            step_size_um=step_um,
        ),
        grid_type=tbt.EBSDGridType.SQUARE,
        # Pattern files are large and not what these tests check.
        save_patterns=False,
    )


def _imaging_state(microscope):
    """Return the electron-beam field width and active detector."""
    img.set_beam_device(microscope=microscope, device=tbt.Device.ELECTRON_BEAM)
    return (
        microscope.beams.electron_beam.horizontal_field_width.value,
        microscope.detector.type.value,
    )


def _logged(settings: tbt.GeneralSettings, step, dataset_name: str):
    """Return the (slice, value) rows logged for one step and dataset."""
    location = f"{step.number:02d}_{step.name}/{dataset_name}"
    with h5py.File(settings.log_filepath, "r") as log_file:
        if location not in log_file:
            return []
        return [(int(row[0]), float(row[1])) for row in log_file[location][()]]


def _collect_ebsd(microscope, experiment, *, slice_number, name, enable_eds):
    """Run the external-device half of the workflow's EBSD step.

    Returns the step and the imaging state from before the map, so the caller
    can confirm the camera-saturation measurement restored it.
    """
    step = SimpleNamespace(number=slice_number, name=name)
    step_settings = _ebsd_step_settings(microscope, enable_eds)

    _require_idle(experiment.EDAX_settings)
    devices.retract_all_microscope_insertable_detectors(microscope=microscope)

    folder = _local_map_folder(experiment.EDAX_settings)
    files_before = _folder_snapshot(folder)

    external_devices.preflight_ebsd(general_settings=experiment)
    try:
        external_devices.insert_ebsd(microscope=microscope, general_settings=experiment)
        if enable_eds:
            external_devices.insert_eds(
                microscope=microscope, general_settings=experiment
            )
        # The saturation measurement must hand back exactly the imaging state
        # it found. Capture that state here, after insertion: the collision
        # check in insert_EBSD selects the CBS as the active detector as a side
        # effect, so an earlier baseline would expect the wrong detector back.
        before = _imaging_state(microscope)
        assert external_devices.map_ebsd(
            general_settings=experiment,
            step_settings=step_settings,
            slice_number=slice_number,
            step=step,
        )
    finally:
        external_devices.retract_all_external_devices(
            microscope=microscope, general_settings=experiment
        )
    _assert_data_written(folder, files_before, name)
    return step, before


def _assert_ebsd_map_recorded(microscope, experiment, step, slice_number, before):
    """Check the log, the restored imaging state, and what EDAX was sent."""
    saturation = _logged(
        experiment, step, Constants.ebsd_camera_saturation_dataset_name
    )
    average_ci = _logged(experiment, step, Constants.ebsd_average_ci_dataset_name)
    assert [number for number, _ in saturation] == [slice_number]
    assert [number for number, _ in average_ci] == [slice_number]
    assert 0.0 <= saturation[0][1] <= 1.0
    # EDAX reports a CI of -1 for points it could not index.
    assert -1.0 <= average_ci[0][1] <= 1.0

    hfw_m, detector = _imaging_state(microscope)
    assert hfw_m == pytest.approx(before[0], rel=1e-3), "field width not restored"
    assert detector == before[1], "detector not restored after saturation"

    size_um, step_um = _scan_geometry()
    with _ipapi(experiment.EDAX_settings) as client:
        ebsd = EdaxEbsdController(client)
        params = ebsd.map_parameters()
        camera = ebsd.camera_status()
    assert params.resolution is EdaxEbsdResolution.CUSTOM
    assert params.x_size_um == pytest.approx(size_um, abs=step_um)
    assert params.y_size_um == pytest.approx(size_um, abs=step_um)
    assert params.custom_step_size_um == pytest.approx(step_um)
    assert camera is EdaxCameraStatus.SLIDE_OUT
    return params


#: Hosts that mean APEX runs on this machine, so its save folder is local.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", platform.node().lower()}


def _local_map_folder(config: tbt.EDAXConfig):
    """Return the map folder when this test can see it, otherwise None."""
    if config.connection.host.strip().lower() not in _LOCAL_HOSTS:
        return None
    folder = Path(config.save_directory)
    return folder if folder.is_dir() else None


def _folder_snapshot(folder):
    """Return every file under a folder with its modification time."""
    if folder is None:
        return None
    return {path: path.stat().st_mtime for path in folder.rglob("*") if path.is_file()}


def _assert_data_written(folder, before, label: str, grace_s: float = 30.0):
    """Fail unless a map created or updated a file in its folder.

    APEX reports completion after finalization, but writes can trail slightly,
    so the folder is polled for a short grace period.
    """
    if folder is None:
        print(f"\t{label}: map folder is not on this machine; data not checked")
        return
    deadline = time.time() + grace_s
    while True:
        after = _folder_snapshot(folder)
        written = [path for path, mtime in after.items() if before.get(path) != mtime]
        if written or time.time() >= deadline:
            break
        time.sleep(1.0)
    assert written, (
        f"The {label} map completed but wrote nothing to {folder}. Check where "
        "APEX saved it, and that the folder was set before the map started."
    )


def _same_path(first: str, second: str) -> bool:
    """Compare paths the way Windows does: case and separators aside."""
    normalize = lambda path: os.path.normcase(os.path.normpath(str(path).strip()))
    return normalize(first) == normalize(second)


class MotionWatch:
    """Tracks whether the chamber CCD is live, and every detector move."""

    #: LaserControl calls that physically move an EBSD or EDS detector.
    LASER_CONTROL_MOVES = (
        "EBSD_InsertCamera",
        "EBSD_RetractCamera",
        "EDS_InsertCamera",
        "EDS_RetractCamera",
    )

    def __init__(self):
        self.live = False
        self.moves = []  # every move, in order
        self.blind = []  # moves made while the CCD was off
        self.laser_control_observed = True

    def moved(self, name: str) -> None:
        self.moves.append(name)
        if not self.live:
            self.blind.append(name)

    def assert_all_moves_observed(self, expect=()):
        """Fail on any blind move, and on any expected move that never came."""
        assert not self.blind, (
            f"Detector moved with the chamber CCD off: {self.blind}. Every "
            "insertion and retraction must run under the live CCD view."
        )
        for name in expect:
            assert name in self.moves, f"expected {name} among moves {self.moves}"


@pytest.fixture
def motion_watch(monkeypatch) -> MotionWatch:
    """Spy on the CCD and on detector motion, calling through to the real ones.

    The CCD counts as live only once CCD_view has returned, and stops counting
    as soon as CCD_pause is called, so a move racing either edge is blind.
    """
    watch = MotionWatch()
    real_view, real_pause = devices.CCD_view, devices.CCD_pause

    def view(*args, **kwargs):
        result = real_view(*args, **kwargs)
        watch.live = True
        return result

    def pause(*args, **kwargs):
        watch.live = False
        return real_pause(*args, **kwargs)

    monkeypatch.setattr(devices, "CCD_view", view)
    monkeypatch.setattr(devices, "CCD_pause", pause)

    for controller, method, label in (
        (EdaxEbsdController, "insert_camera", "IPAPI insert_camera"),
        (EdaxEbsdController, "retract_camera", "IPAPI retract_camera"),
        (EdaxEdsController, "insert_detector", "IPAPI EDS insert_detector"),
        (EdaxEdsController, "retract_detector", "IPAPI EDS retract_detector"),
    ):
        real = getattr(controller, method)

        def spy(self, *args, _real=real, _label=label, **kwargs):
            watch.moved(_label)
            return _real(self, *args, **kwargs)

        monkeypatch.setattr(controller, method, spy)

    # LaserControl may be an extension module whose attributes cannot be
    # replaced; the IPAPI moves are still watched if so.
    laser_control = getattr(devices, "external", None)
    for name in MotionWatch.LASER_CONTROL_MOVES:
        try:
            real = getattr(laser_control, name)

            def spy(*args, _real=real, _name=name, **kwargs):
                watch.moved(f"LaserControl {_name}")
                return _real(*args, **kwargs)

            monkeypatch.setattr(laser_control, name, spy)
        except (AttributeError, TypeError):
            watch.laser_control_observed = False
    return watch


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------
def test_ebsd_map(microscope, experiment, motion_watch):
    """Collect an EBSD map over the native IPAPI.

    Spectra are switched on first, as an earlier EBSD + EDS step would leave
    them, to confirm an EBSD-only step clears the setting rather than inheriting
    it with the EDS detector retracted.
    """
    with _ipapi(experiment.EDAX_settings) as client:
        EdaxEbsdController(client).apply_map_parameters(
            EdaxEbsdMapParams(save_spectra=True)
        )

    step, before = _collect_ebsd(
        microscope, experiment, slice_number=1, name="edax_hw_ebsd", enable_eds=False
    )

    params = _assert_ebsd_map_recorded(microscope, experiment, step, 1, before)
    assert params.save_spectra is False
    motion_watch.assert_all_moves_observed(expect=["IPAPI retract_camera"])


def test_ebsd_map_with_concurrent_eds(microscope, experiment, motion_watch):
    """Collect an EBSD map with spectra saved at every point.

    This is still an EBSD scan, routed with the EBSD OEM; the EDS detector is
    inserted alongside the camera and spectra are enabled on the EBSD map.
    """
    step, before = _collect_ebsd(
        microscope,
        experiment,
        slice_number=2,
        name="edax_hw_ebsd_eds",
        enable_eds=True,
    )

    params = _assert_ebsd_map_recorded(microscope, experiment, step, 2, before)
    assert params.save_spectra is True
    motion_watch.assert_all_moves_observed(
        expect=[
            "IPAPI retract_camera",
            "IPAPI EDS insert_detector",
            "IPAPI EDS retract_detector",
        ]
    )


def test_eds_map(microscope, experiment, motion_watch):
    """Collect an EDS map entirely over the IPAPI, headless.

    Checks the two things LaserControl collection could not guarantee: that
    APEX was told where to save before the map started, and, when the folder is
    on this machine, that the map actually wrote data there. The detector moves
    over the IPAPI, under the live chamber CCD.
    """
    config = experiment.EDAX_settings
    step = SimpleNamespace(number=3, name="edax_hw_eds")

    _require_idle(config)
    devices.retract_all_microscope_insertable_detectors(microscope=microscope)
    folder = _local_map_folder(config)
    files_before = _folder_snapshot(folder)

    external_devices.preflight_eds(general_settings=experiment)
    try:
        external_devices.insert_eds(microscope=microscope, general_settings=experiment)
        assert external_devices.map_eds(
            general_settings=experiment,
            step_settings=None,
            slice_number=3,
            step=step,
        )
    finally:
        external_devices.retract_all_external_devices(
            microscope=microscope, general_settings=experiment
        )

    with _ipapi(config) as client:
        eds = EdaxEdsController(client)
        eds_folder = client.query(EdaxCommand.EDS_GET_FOLDERPATH)
        position = eds.slide_status()
        status = eds.map_status()
    assert _same_path(eds_folder, config.save_directory), (
        f"APEX's EDS folder is {eds_folder!r}, not {config.save_directory!r}"
    )
    assert position is EdaxDetectorSlideStatus.SLIDE_OUT
    assert status not in _BUSY, f"APEX still reports the EDS side as {status.value}"

    _assert_data_written(folder, files_before, "EDS")
    motion_watch.assert_all_moves_observed(
        expect=["IPAPI EDS insert_detector", "IPAPI EDS retract_detector"]
    )
