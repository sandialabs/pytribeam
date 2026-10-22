"""Imaging tools, driven through an in-process MCP client with a fake
microscope. No AutoScript, no hardware.

The pytribeam calls in ``imaging`` (``_validate``, ``_prepare``, ``_grab`` and
so on) are replaced by fakes that act on a small model of the microscope, and
state captures are built from that model, so ``changes`` in each result is a
real diff of what the tool did.
"""

## python standard libraries
import base64
import copy
import io
import json
import threading
import time

# 3rd party libraries
import anyio
import numpy as np
import pytest
import yaml
from PIL import Image

mcp = pytest.importorskip("mcp")  # the mcp extra needs Python >= 3.10
from mcp import Client  # noqa: E402

# local libraries
from pytribeam.mcp import connection  # noqa: E402
from pytribeam.mcp.capabilities import _helpers, imaging, records, views  # noqa: E402
from pytribeam.mcp.config import ServerConfig  # noqa: E402
from pytribeam.mcp.server import build_server  # noqa: E402

pytestmark = [pytest.mark.detached, pytest.mark.anyio]

ELECTRON = {
    "voltage_kv": 5.0,
    "current_na": 0.4,
    "hfw_mm": 0.9,
    "working_dist_mm": 4.0,
    "dynamic_focus": True,
    "tilt_correction": False,
    "detector": "ETD",
    "detector_mode": "SecondaryElectrons",
    "brightness": 0.5,
    "contrast": 0.4,
    "rotation_deg": 0.0,
    "dwell_us": 1.0,
    "resolution": "768x512",
}
ION = {
    **ELECTRON,
    "voltage_kv": 30.0,
    "current_na": 0.1,
    "dynamic_focus": None,
    "tilt_correction": None,
    "detector": "ICE",
    "detector_mode": "SecondaryIons",
}
PRESETS = {"512x442", "768x512", "1024x884", "1536x1024", "2048x1768", "3072x2048"}
DETECTORS = {"electron": {"ETD", "TLD", "CBS"}, "ion": {"ETD", "ICE"}}
MODES = {
    "ETD": ["SecondaryElectrons", "BackscatterElectrons"],
    "TLD": ["SecondaryElectrons"],
    "CBS": ["All", "ABCD"],
    "ICE": ["SecondaryIons", "SecondaryElectrons"],
}
DEVICE = {"electron": "ELECTRON_BEAM", "ion": "ION_BEAM"}
QUAD = {"electron": 1, "ion": 2}


def _stub_factory(monkeypatch):
    """A stand-in pytribeam.factory with string_to_res, which raises
    ValueError on bad input as the real one does."""
    import sys
    import types

    import pytribeam

    res = types.SimpleNamespace
    factory = types.ModuleType("pytribeam.factory")

    def string_to_res(text):
        try:
            width, height = (int(v) for v in text.lower().split("x"))
        except Exception:
            raise ValueError(f'Invalid string format: "{text}"') from None
        return res(width=width, height=height)

    factory.string_to_res = string_to_res
    monkeypatch.setitem(sys.modules, "pytribeam.factory", factory)
    monkeypatch.setattr(pytribeam, "factory", factory, raising=False)


class SchemaError(Exception):
    """Same name and base as schema.SchemaError, which pytribeam's range
    checks raise; it is not a ValueError."""


class FakeScope:
    """Just enough microscope for the imaging tools."""

    def __init__(self):
        self.settings = {"electron": dict(ELECTRON), "ion": dict(ION)}
        self.view = 1
        self.devices = {1: "ELECTRON_BEAM", 2: "ION_BEAM", 3: "NAV_CAM", 4: "CCD_CAMERA"}
        self.beam_on = {"electron": True, "ion": True}
        self.detector_states = {"CBS": "Retracted"}  # others are Stationary
        self.calls = []
        self.grab_s = 0.0
        self.grab_error = None
        self.validate_error = None
        self.bit_depth = 8

    @property
    def active_beam(self):
        device = self.devices[self.view]
        return {"ELECTRON_BEAM": "electron", "ION_BEAM": "ion"}.get(device)

    def values(self):
        flat = {"imaging.active_view": self.view, "imaging.active_device": self.devices[self.view]}
        for beam, settings in self.settings.items():
            for key, value in settings.items():
                flat[f"beams.{beam}.{key}"] = value
        for detector, value in self.detector_states.items():
            flat[f"detectors.{detector}.state"] = value
        return flat


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def scope(monkeypatch):
    fake = FakeScope()
    captures = {"n": 0}

    def capture(microscope, description):
        captures["n"] += 1
        return {
            "recorded_at": f"t{captures['n']}",
            "description": description,
            "values": copy.deepcopy(fake.values()),
            "read_errors": {},
        }

    def select_beam(microscope, beam):
        fake.calls.append(("select", beam))
        fake.view = QUAD[beam]
        fake.devices[fake.view] = DEVICE[beam]

    def current(microscope):
        beam = fake.active_beam
        if beam is None:
            raise ValueError("Currently selected device is a camera")
        return dict(fake.settings[beam])

    def detector_modes(microscope, detector):
        beam = fake.active_beam
        return list(MODES[detector]) if beam and detector in DETECTORS[beam] else None

    def detector_state(microscope, detector):
        return fake.detector_states.get(detector, "Stationary")

    def validate(microscope, step):
        fake.calls.append(("validate", step))
        # factory.image selects quad 1 and the electron beam while checking
        # the detector (device_access); imaging._validate leaves it there.
        fake.view = 1
        fake.devices[1] = "ELECTRON_BEAM"
        if fake.validate_error:
            raise fake.validate_error
        beam = step["beam"]["type"]
        detector = step["detector"]["type"]
        if detector not in DETECTORS[beam]:
            raise ValueError(
                f"Requested detector of {detector} is unavailable on this tool. "
                f"Available detectors are: {sorted(DETECTORS[beam])}"
            )
        det, bm = step["detector"], step["beam"]
        if det["auto_cb"]["left"] is not None and (
            det["brightness"] is not None or det["contrast"] is not None
        ):
            raise KeyError(  # as factory.validate_detector_settings
                "Users may use either fixed brightness/contrast values or auto "
                "contrast/brightness settings, but not both."
            )
        if bm["type"] == "ion" and (bm["dynamic_focus"] or bm["tilt_correction"]):
            raise SchemaError(  # as factory.validate_beam_settings
                "In step 'mcp' with 'ion' beam imaging, 'dynamic_focus' must be "
                "'False' or 'None'"
            )
        for key in ("brightness", "contrast"):
            level = step["detector"][key]
            if level is not None and not 0 < level <= 1:
                raise SchemaError(
                    f"In step 'mcp', requested fixed {key} of '{level}'. This is "
                    "not within limits of '>0.0' and '<=1.0'."
                )
        mode = step["detector"]["mode"]
        if mode not in MODES[detector]:
            raise ValueError(
                f"Requested mode of {mode} for {detector} detector is invalid. "
                f"Valid mode types are: {MODES[detector]}"
            )
        if not isinstance(step["scan"]["dwell_time_us"], float):
            raise KeyError("dwell_time_us must be a float")
        if not 0.025 <= step["scan"]["dwell_time_us"] <= 100:
            raise ValueError("requested fixed dwell_time is not within limits")
        if (step["beam"]["dynamic_focus"] or step["beam"]["tilt_correction"]) and step[
            "scan"
        ]["rotation_deg"]:
            raise ValueError("Cannot use dynamic focus or tilt correction for non-zero scan rotation.")
        return {"beam": beam, "step": step}

    def prepare(microscope, settings):
        fake.calls.append(("prepare", settings["beam"]))
        beam, step = settings["beam"], settings["step"]
        fake.view = QUAD[beam]
        s = fake.settings[beam]
        b, d, sc = step["beam"], step["detector"], step["scan"]
        s.update(
            voltage_kv=b["voltage_kv"],
            current_na=b["current_na"],
            hfw_mm=b["hfw_mm"],
            working_dist_mm=b["working_dist_mm"],
            detector=d["type"],
            detector_mode=d["mode"],
            rotation_deg=sc["rotation_deg"],
            dwell_us=sc["dwell_time_us"],
        )
        if beam == "electron":
            s.update(dynamic_focus=b["dynamic_focus"], tilt_correction=b["tilt_correction"])
        if d["auto_cb"]["left"] is not None:
            s.update(brightness=0.61, contrast=0.37)  # what auto CB chose
        else:
            s.update(brightness=d["brightness"], contrast=d["contrast"])
        if sc["resolution"] in PRESETS:
            s["resolution"] = sc["resolution"]
        if d["type"] in fake.detector_states:
            fake.detector_states[d["type"]] = "Inserted"

    def collect(settings, path):
        """As image.collect_single_image: apply the settings, then grab."""
        prepare(fake, settings)
        fake.calls.append(("grab", str(path)))
        time.sleep(fake.grab_s)
        if fake.grab_error:
            path.write_bytes(b"partial")
            raise fake.grab_error
        width, height = (int(v) for v in settings["step"]["scan"]["resolution"].split("x"))
        dtype = np.uint16 if fake.bit_depth == 16 else np.uint8
        data = (np.indices((height, width)).sum(axis=0) % 200 + 20).astype(dtype)
        Image.fromarray(data).save(path)
        if settings["step"]["scan"]["resolution"] not in PRESETS:
            import warnings

            warnings.warn("Non-preset resolution: written at 8-bit depth.")

    monkeypatch.setattr(connection, "_connect", lambda config: fake)
    monkeypatch.setattr(_helpers, "_capture", capture)
    monkeypatch.setattr(imaging, "_select_beam", select_beam)
    monkeypatch.setattr(imaging, "_current", current)
    monkeypatch.setattr(imaging, "_beam_is_on", lambda m, beam: fake.beam_on[beam])
    monkeypatch.setattr(imaging, "_detector_state", detector_state)
    monkeypatch.setattr(imaging, "_detector_modes", detector_modes)
    monkeypatch.setattr(imaging, "_validate", validate)
    monkeypatch.setattr(imaging, "_prepare", prepare)
    monkeypatch.setattr(imaging, "_collect", collect)
    # parse_resolution uses pytribeam's factory.string_to_res; stand in for it
    # so the plain-Python checks run without pytribeam's dependencies.
    _stub_factory(monkeypatch)
    monkeypatch.setattr(imaging, "_stage_position", lambda m: {"x_mm": 1.5, "y_mm": -2.0})
    monkeypatch.setattr(
        views,
        "_read_view",
        lambda m: {"active_view": fake.view, "active_device": fake.devices[fake.view]},
    )
    monkeypatch.setattr(views, "_set_view", lambda m, quad: setattr(fake, "view", quad))
    return fake


def _server(tmp_path, max_tier=5, **config):
    """Tier 5 by default, so ion-beam behavior can be tested; the tier gates
    have their own tests below."""
    config = ServerConfig(max_tier=max_tier, project_dir=tmp_path, **config)
    return config, build_server(config, modules=(imaging, records, views))


@pytest.fixture
def server(tmp_path):
    return _server(tmp_path)[1]


async def _call(client, tool, args=None, **kwargs):
    result = await client.call_tool(tool, args or {}, **kwargs)
    assert not result.is_error, result.content[0].text
    return result, json.loads(result.content[0].text)


async def _refused(client, tool, args=None):
    result = await client.call_tool(tool, args or {})
    assert result.is_error, result.content[0].text
    return result.content[0].text


def _validated_step(scope):
    return [c[1] for c in scope.calls if c[0] == "validate"][-1]


# --- registration ----------------------------------------------------------
async def test_registration_and_annotations(server):
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert {"set_view", "prepare_imaging", "collect_single_image"} <= set(tools)
    # Both scan the sample (auto_cb or the image), so both are destructive.
    assert tools["collect_single_image"].annotations.destructive_hint is True
    assert tools["prepare_imaging"].annotations.destructive_hint is True
    assert not tools["set_view"].annotations.read_only_hint
    assert not tools["set_view"].annotations.destructive_hint
    assert "ctx" not in tools["collect_single_image"].input_schema["properties"]


@pytest.mark.parametrize("max_tier", [0, 1])
async def test_imaging_needs_tier_2(tmp_path, max_tier):
    config = ServerConfig(max_tier=max_tier, project_dir=tmp_path)
    async with Client(build_server(config, modules=(imaging,))) as client:
        assert (await client.list_tools()).tools == []


# --- set_view (views module, tier 1) ----------------------------------------
async def test_set_view(server, scope):
    async with Client(server) as client:
        _, result = await _call(client, "set_view", {"quad": 2})
        bad = await client.call_tool("set_view", {"quad": 5})
    assert (result["active_view"], result["active_device"]) == (2, "ION_BEAM")
    assert result["changes"] == {"imaging.active_view": [1, 2], "imaging.active_device": ["ELECTRON_BEAM", "ION_BEAM"]}
    assert result["before_state_id"] == "s0001" and result["after_state_id"] == "s0002"
    assert bad.is_error


# --- ion beam needs tier 5 (security review P0) ------------------------------
@pytest.mark.parametrize("max_tier", [2, 3, 4])
@pytest.mark.parametrize(
    "tool, args",
    [
        ("prepare_imaging", {"beam": "ion"}),
        ("prepare_imaging", {"beam": "ion", "auto_cb": True}),
        ("collect_single_image", {"beam": "ion"}),
        ("collect_single_image", {"beam": "ion", "resolution": "768x512", "dwell_us": 1}),
    ],
)
async def test_ion_beam_needs_tier_5(tmp_path, scope, max_tier, tool, args):
    _, server = _server(tmp_path, max_tier=max_tier)
    before = scope.values()
    async with Client(server) as client:
        message = await _refused(client, tool, args)
    assert "removes material" in message and "needs tier 5" in message
    assert scope.calls == []  # no select, validate, prepare, or grab
    assert scope.values() == before
    assert not list(tmp_path.glob("states/*.yml"))  # refused before any snapshot


async def test_ion_beam_works_at_tier_5(tmp_path, scope):
    _, server = _server(tmp_path, max_tier=5)
    async with Client(server) as client:
        _, result = await _call(client, "collect_single_image", {"beam": "ion"})
    assert result["beam"] == "ion"


async def test_electron_beam_works_at_tier_2(tmp_path, scope):
    _, server = _server(tmp_path, max_tier=2)
    async with Client(server) as client:
        _, result = await _call(client, "collect_single_image", {"beam": "electron"})
    assert result["image_id"] == "i0001"


# --- prepare_imaging -------------------------------------------------------
async def test_only_overrides_change(server, scope):
    async with Client(server) as client:
        _, result = await _call(
            client, "prepare_imaging", {"beam": "electron", "hfw_mm": 0.2, "dwell_us": 3}
        )
    assert set(result["changes"]) == {"beams.electron.hfw_mm", "beams.electron.dwell_us"}
    assert result["changes"]["beams.electron.dwell_us"] == [1.0, 3.0]
    assert result["settings"]["hfw_mm"] == 0.2
    assert result["estimated_frame_s"] == pytest.approx(768 * 512 * 3e-6 + 1, abs=0.1)


async def test_angular_correction_is_preserved_when_not_passed(server, scope):
    async with Client(server) as client:
        await _call(client, "prepare_imaging", {"beam": "electron", "hfw_mm": 0.3})
    step = _validated_step(scope)
    assert step["beam"]["dynamic_focus"] is True  # current value, not None (= off)
    assert step["beam"]["tilt_correction"] is False
    assert scope.settings["electron"]["dynamic_focus"] is True


async def test_step_uses_floats_and_full_settings(server, scope):
    async with Client(server) as client:
        await _call(client, "prepare_imaging", {"beam": "electron", "brightness": 1, "dwell_us": 2})
    step = _validated_step(scope)
    assert step["step_general"]["step_type"] == "image"
    assert isinstance(step["detector"]["brightness"], float)
    assert isinstance(step["scan"]["dwell_time_us"], float)
    assert step["detector"]["auto_cb"] == {"left": None, "top": None, "width": None, "height": None}
    assert step["beam"]["voltage_tol_kv"] == pytest.approx(0.25)


async def test_ion_beam_leaves_angular_correction_unset(server, scope):
    async with Client(server) as client:
        _, result = await _call(client, "prepare_imaging", {"beam": "ion", "hfw_mm": 0.05})
        step = _validated_step(scope)  # carried over: angular correction left out
        refused = await _refused(client, "prepare_imaging", {"beam": "ion", "dynamic_focus": True})
    assert step["beam"]["dynamic_focus"] is None and step["beam"]["type"] == "ion"
    assert _validated_step(scope)["beam"]["dynamic_focus"] is True  # explicit: passed on
    assert set(result["changes"]) >= {"beams.ion.hfw_mm"}
    assert "must be 'False' or 'None'" in refused  # pytribeam's message


async def test_auto_cb(server, scope):
    async with Client(server) as client:
        _, result = await _call(client, "prepare_imaging", {"beam": "electron", "auto_cb": True})
        step = _validated_step(scope)  # carried-over levels left out for auto_cb
        refused = await _refused(
            client, "prepare_imaging", {"beam": "electron", "auto_cb": True, "contrast": 0.5}
        )
    assert _validated_step(scope)["detector"]["contrast"] == 0.5  # explicit: passed on
    assert step["detector"]["auto_cb"] == {"left": 0.0, "top": 0.0, "width": 1.0, "height": 1.0}
    assert step["detector"]["brightness"] is None and step["detector"]["contrast"] is None
    assert (result["settings"]["brightness"], result["settings"]["contrast"]) == (0.61, 0.37)
    assert "either fixed brightness/contrast values or auto" in refused  # pytribeam's


async def test_invalid_current_mode_is_replaced(server, scope):
    """The simulator reports TLD2's mode as "None", which TLD2 rejects."""
    scope.settings["electron"].update(detector="TLD", detector_mode="None")
    async with Client(server) as client:
        _, result = await _call(client, "prepare_imaging", {"beam": "electron", "hfw_mm": 0.5})
    assert _validated_step(scope)["detector"]["mode"] == "SecondaryElectrons"
    assert any("'None' is not available on TLD" in w for w in result["warnings"])


async def test_new_detector_does_not_inherit_the_old_mode(server, scope):
    scope.settings["electron"]["detector_mode"] = "BackscatterElectrons"  # ETD only
    async with Client(server) as client:
        _, result = await _call(client, "prepare_imaging", {"beam": "electron", "detector": "TLD"})
    assert result["settings"]["detector_mode"] == "SecondaryElectrons"
    assert result["warnings"]


async def test_valid_current_mode_is_kept_without_warning(server, scope):
    scope.settings["electron"]["detector_mode"] = "BackscatterElectrons"
    async with Client(server) as client:
        _, result = await _call(client, "prepare_imaging", {"beam": "electron", "hfw_mm": 0.5})
    assert _validated_step(scope)["detector"]["mode"] == "BackscatterElectrons"
    assert result["warnings"] == []


async def test_explicit_invalid_mode_is_refused_not_replaced(server, scope):
    async with Client(server) as client:
        message = await _refused(
            client, "prepare_imaging", {"beam": "electron", "detector": "TLD", "detector_mode": "None"}
        )
    assert "Requested mode of None for TLD detector is invalid" in message
    assert "SecondaryElectrons" in message


@pytest.mark.parametrize("key", ["brightness", "contrast"])
async def test_invalid_current_level_is_moved_into_range(server, scope, key):
    """The simulator reports brightness 0.0, which pytribeam rejects."""
    scope.settings["electron"][key] = 0.0
    async with Client(server) as client:
        _, result = await _call(client, "prepare_imaging", {"beam": "electron", "hfw_mm": 0.5})
    assert _validated_step(scope)["detector"][key] == imaging.LEVEL_MIN
    assert any(f"Current {key} of 0.0 is outside" in w for w in result["warnings"])


async def test_small_valid_level_is_kept(server, scope):
    scope.settings["electron"]["brightness"] = 0.0005
    async with Client(server) as client:
        _, result = await _call(client, "prepare_imaging", {"beam": "electron"})
    assert _validated_step(scope)["detector"]["brightness"] == 0.0005
    assert result["warnings"] == []


async def test_auto_cb_does_not_clamp(server, scope):
    scope.settings["electron"]["brightness"] = 0.0
    async with Client(server) as client:
        _, result = await _call(client, "prepare_imaging", {"beam": "electron", "auto_cb": True})
    assert _validated_step(scope)["detector"]["brightness"] is None
    assert result["warnings"] == []


async def test_schema_errors_reach_the_agent(server, scope, monkeypatch):
    """pytribeam's SchemaError is not a ValueError; its message must still
    reach the agent rather than a bare "Error executing tool"."""
    original = imaging._validate

    def strict(microscope, step):
        step["detector"]["brightness"] = 0.0  # as if the check below were missed
        return original(microscope, step)

    monkeypatch.setattr(imaging, "_validate", strict)
    async with Client(server) as client:
        message = await _refused(client, "prepare_imaging", {"beam": "electron"})
    assert "Invalid imaging settings" in message
    assert "requested fixed brightness of '0.0'" in message


@pytest.mark.parametrize("value", [0, 1.5, -0.2])
async def test_brightness_out_of_range(server, scope, value):
    async with Client(server) as client:
        message = await _refused(client, "prepare_imaging", {"beam": "electron", "brightness": value})
    assert "not within limits of '>0.0' and '<=1.0'" in message  # pytribeam's
    assert not any(c[0] == "prepare" for c in scope.calls)


async def test_invalid_detector_message(server, scope):
    async with Client(server) as client:
        message = await _refused(client, "prepare_imaging", {"beam": "ion", "detector": "TLD"})
    assert "Invalid imaging settings" in message and "TLD is unavailable" in message
    assert "Available detectors are" in message
    assert not any(c[0] == "prepare" for c in scope.calls)


@pytest.mark.parametrize("resolution", ["1536", "big", "1536x"])
async def test_invalid_resolution_message(server, scope, resolution):
    async with Client(server) as client:
        message = await _refused(
            client, "prepare_imaging", {"beam": "electron", "resolution": resolution}
        )
    assert "WIDTHxHEIGHT" in message and "get_imaging_limits" in message
    assert not any(c[0] in ("validate", "prepare") for c in scope.calls)


async def test_validation_errors_reach_the_agent(server, scope):
    async with Client(server) as client:
        rotation = await _refused(
            client, "prepare_imaging", {"beam": "electron", "rotation_deg": 10}
        )
        dwell = await _refused(client, "prepare_imaging", {"beam": "electron", "dwell_us": 500})
    assert "non-zero scan rotation" in rotation
    assert "dwell_time is not within limits" in dwell


async def test_vacuum_message_reaches_the_agent(server, scope, monkeypatch):
    def not_pumped(microscope, settings):
        raise ValueError('Vacuum is not pumped, current state is "Vented"')

    monkeypatch.setattr(imaging, "_prepare", not_pumped)
    async with Client(server) as client:
        message = await _refused(client, "prepare_imaging", {"beam": "electron"})
    assert "Vacuum is not pumped" in message


@pytest.mark.parametrize("beam", ["electron", "ion"])
async def test_beam_off_is_refused(server, scope, beam):
    scope.beam_on[beam] = False
    async with Client(server) as client:
        message = await _refused(client, "prepare_imaging", {"beam": beam})
    assert f"The {beam} beam is off; ask the operator" in message
    assert not any(c[0] == "prepare" for c in scope.calls)


async def test_tier2_refuses_retractable_detectors(tmp_path, scope):
    _, server = _server(tmp_path, max_tier=2)
    scope.detector_states["CBS"] = "Inserted"  # even when already inserted
    async with Client(server) as client:
        message = await _refused(client, "prepare_imaging", {"beam": "electron", "detector": "CBS"})
    assert "CBS is a retractable detector (currently Inserted)" in message
    assert "needs tier 3" in message
    assert not any(c[0] == "prepare" for c in scope.calls)


async def test_tier3_inserts_retractable_detectors(tmp_path, scope):
    _, server = _server(tmp_path, max_tier=3)
    async with Client(server) as client:
        _, first = await _call(client, "prepare_imaging", {"beam": "electron", "detector": "CBS"})
        _, second = await _call(client, "prepare_imaging", {"beam": "electron", "detector": "CBS"})
    assert first["detector_inserted"] is True
    assert first["changes"]["detectors.CBS.state"] == ["Retracted", "Inserted"]
    assert second["detector_inserted"] is False  # already in


async def test_guardrails_check_the_beams_own_device(server, scope, monkeypatch):
    """Validation leaves quad 1 on the electron beam; the guardrails must not
    run there for an ion request."""
    seen = []
    original = imaging._detector_state

    def record(microscope, detector):
        seen.append(scope.devices[scope.view])
        return original(microscope, detector)

    monkeypatch.setattr(imaging, "_detector_state", record)
    async with Client(server) as client:
        await _call(client, "prepare_imaging", {"beam": "ion"})
    assert seen == ["ION_BEAM"]


# --- acquisition time ------------------------------------------------------
async def test_long_frame_needs_confirmation(tmp_path, scope):
    _, server = _server(tmp_path, max_frame_s=10, hard_max_frame_s=100)
    long_frame = {"beam": "electron", "resolution": "1536x1024", "dwell_us": 20}  # ~32 s
    async with Client(server) as client:
        refused = await _refused(client, "collect_single_image", long_frame)
        _, ok = await _call(client, "collect_single_image", {**long_frame, "confirm_long": True})
    assert "about 32 s" in refused and "confirm_long=true" in refused
    assert ok["image_id"] == "i0001"
    assert [c[0] for c in scope.calls].count("grab") == 1


async def test_hard_limit_cannot_be_overridden(tmp_path, scope):
    _, server = _server(tmp_path, max_frame_s=10, hard_max_frame_s=20)
    async with Client(server) as client:
        message = await _refused(
            client,
            "collect_single_image",
            {"beam": "electron", "resolution": "1536x1024", "dwell_us": 20, "confirm_long": True},
        )
    assert "more than this server's limit of 20 s" in message
    assert "only the operator" in message


async def test_time_check_uses_current_settings_without_changing_anything(tmp_path, scope):
    """The beam is selected so its own current settings are read
    (factory.active_image_settings reads the active device); nothing is
    validated, applied, or scanned before the refusal."""
    scope.settings["electron"].update(resolution="3072x2048", dwell_us=10.0)  # ~64 s
    before = dict(scope.settings["electron"])
    _, server = _server(tmp_path, max_frame_s=30)
    async with Client(server) as client:
        message = await _refused(client, "collect_single_image", {"beam": "electron"})
    assert "about 64 s" in message
    assert scope.calls == [("select", "electron")]
    assert scope.settings["electron"] == before
    assert not list(tmp_path.glob("images/*"))


def test_frame_seconds(monkeypatch):
    _stub_factory(monkeypatch)
    assert imaging.frame_seconds("1000x1000", 2.0) == pytest.approx(2.0 + imaging.FRAME_OVERHEAD_S)


async def test_progress_is_reported_during_acquisition(server, scope, monkeypatch):
    monkeypatch.setattr(imaging, "PROGRESS_INTERVAL_S", 0.05)
    scope.grab_s = 0.3
    seen = []

    async def on_progress(progress, total, message):
        seen.append((progress, total, message))

    async with Client(server) as client:
        await _call(client, "collect_single_image", {"beam": "electron"}, progress_callback=on_progress)
    assert len(seen) >= 3
    expected = 768 * 512 * 1e-6 + 1 + imaging.SETTINGS_ALLOWANCE_S  # frame + settings
    assert all(total == pytest.approx(expected, abs=0.1) for _, total, _ in seen)
    assert "acquiring frame" in seen[0][2]
    assert [p for p, _, _ in seen] == sorted(p for p, _, _ in seen)


async def test_busy_refusal_names_the_running_acquisition(tmp_path, scope):
    """While one image acquires, a second hardware call is refused at once
    with the expected remaining time, and file-only tools still answer."""
    config = ServerConfig(max_tier=2, project_dir=tmp_path, max_frame_s=1000)
    server = build_server(config, modules=(imaging, records))
    scope.grab_s = 1.0
    long_frame = {"beam": "electron", "resolution": "6144x4096", "dwell_us": 2}  # ~51 s estimate
    out = {}

    async with Client(server) as client:

        async def collect():
            out["image"] = await client.call_tool("collect_single_image", long_frame)

        async with anyio.create_task_group() as tg:
            tg.start_soon(collect)
            for _ in range(100):  # wait until the grab has started
                if any(c[0] == "grab" for c in scope.calls):
                    break
                await anyio.sleep(0.01)
            t0 = time.monotonic()
            listing = await client.call_tool("list_images", {})
            busy = await client.call_tool("prepare_imaging", {"beam": "electron"})
            out["elapsed"] = time.monotonic() - t0

    assert not listing.is_error
    assert busy.is_error and "collect_single_image has been running" in busy.content[0].text
    assert "s left" in busy.content[0].text
    assert out["elapsed"] < 0.9  # neither waited for the 1 s grab
    assert not out["image"].is_error


# --- collect_single_image --------------------------------------------------
async def test_collect_result_shape_and_files(server, scope, tmp_path):
    async with Client(server) as client:
        first, result = await _call(
            client, "collect_single_image", {"beam": "electron", "hfw_mm": 0.1, "description": "grain A"}
        )
        _, second = await _call(client, "collect_single_image", {"beam": "electron"})

    assert (result["image_id"], second["image_id"]) == ("i0001", "i0002")
    images_dir = tmp_path / "images"
    assert {p.name for p in images_dir.iterdir()} == {"i0001.tif", "i0001.yml", "i0002.tif", "i0002.yml"}
    assert result["path"] == str(images_dir / "i0001.tif")
    assert result["pixel_size_nm"] == pytest.approx(0.1 * 1e6 / 768)
    assert (result["detector"], result["resolution"], result["bit_depth"]) == ("ETD", "768x512", 8)
    assert result["dynamic_focus"] is True  # left on after imaging
    assert result["estimated_frame_s"] > 0 and result["acquisition_s"] >= 0
    assert set(result["stats"]) >= {"mean", "p1", "p99", "clipped_high_frac", "sharpness"}
    assert result["before_state_id"] == "s0001" and result["after_state_id"] == "s0002"
    assert "beams.electron.hfw_mm" in result["changes"]
    assert result["preview"]["width"] == 768 and result["warnings"] == []

    picture = first.content[1]
    assert picture.type == "image" and picture.mime_type == "image/png"
    shown = np.asarray(Image.open(io.BytesIO(base64.b64decode(picture.data))))
    assert shown.shape == (512, 768)

    sidecar = yaml.safe_load((images_dir / "i0001.yml").read_text())
    assert sidecar["description"] == "grain A"
    # The image and both states trace back to the same audited call.
    before = yaml.safe_load((tmp_path / "states" / "s0001.yml").read_text())
    after = yaml.safe_load((tmp_path / "states" / "s0002.yml").read_text())
    assert sidecar["op_id"] and sidecar["op_id"] == before["op_id"] == after["op_id"]
    assert sidecar["stage_position"] == {"x_mm": 1.5, "y_mm": -2.0}
    assert sidecar["before_state_id"] == "s0001"
    assert "changes" not in sidecar and "path" not in sidecar


async def test_collect_without_preview(server, scope):
    async with Client(server) as client:
        result, data = await _call(
            client, "collect_single_image", {"beam": "electron", "preview": False}
        )
    assert len(result.content) == 1 and data["preview"] is None
    assert data["stats"]["mean"] > 0  # stats still computed on the full image


async def test_preview_px_is_respected(server, scope):
    async with Client(server) as client:
        _, data = await _call(
            client, "collect_single_image", {"beam": "electron", "preview_px": 256}
        )
    assert (data["preview"]["width"], data["preview"]["height"]) == (256, 171)


async def test_failed_acquisition_leaves_no_image(server, scope, tmp_path):
    scope.grab_error = RuntimeError("scan aborted")
    async with Client(server) as client:
        failed = await client.call_tool("collect_single_image", {"beam": "electron"})
        scope.grab_error = None
        _, retry = await _call(client, "collect_single_image", {"beam": "electron"})
    assert failed.is_error
    assert retry["image_id"] == "i0001"  # the failed id is reused, no gap
    assert {p.name for p in (tmp_path / "images").iterdir()} == {"i0001.tif", "i0001.yml"}


async def test_failed_validation_takes_no_image(server, scope, tmp_path):
    async with Client(server) as client:
        message = await _refused(client, "collect_single_image", {"beam": "ion", "detector": "TLD"})
    assert "TLD is unavailable" in message
    assert not any(c[0] == "grab" for c in scope.calls)
    assert not list(tmp_path.glob("images/*"))


async def test_custom_resolution_warning(server, scope):
    async with Client(server) as client:
        _, data = await _call(
            client, "collect_single_image", {"beam": "electron", "resolution": "640x480"}
        )
    assert any("Non-preset resolution" in w for w in data["warnings"])  # from the grab thread
    assert data["pixel_size_nm"] == pytest.approx(0.9 * 1e6 / 640)


async def test_16bit_stats(server, scope):
    scope.bit_depth = 16
    async with Client(server) as client:
        _, data = await _call(client, "collect_single_image", {"beam": "electron", "bit_depth": 16})
    assert data["bit_depth"] == 16 and data["stats"]["bit_depth"] == 16
    assert data["requested_bit_depth"] == 16 and data["warnings"] == []


async def test_saved_depth_differs_from_requested(server, scope):
    """If the microscope saves 8 bits when 16 were asked for, say so."""
    scope.bit_depth = 8
    async with Client(server) as client:
        _, data = await _call(client, "collect_single_image", {"beam": "electron", "bit_depth": 16})
    assert (data["bit_depth"], data["requested_bit_depth"]) == (8, 16)
    assert any("Requested 16-bit, but the saved image is 8-bit" in w for w in data["warnings"])


async def test_collected_images_are_listed(server, scope):
    async with Client(server) as client:
        await _call(client, "collect_single_image", {"beam": "electron", "description": "one"})
        await _call(client, "collect_single_image", {"beam": "ion", "description": "two"})
        _, listing = await _call(client, "list_images")
        viewed, record = await _call(client, "view_image", {"image_id": "i0002", "max_px": 100})
    assert [i["description"] for i in listing["images"]] == ["one", "two"]
    assert listing["images"][1]["beam"] == "ion"
    assert record["detector"] == "ICE" and viewed.content[1].type == "image"


# --- fail closed: abandoned acquisitions and failed restores (3.5.4) ---------
async def test_hung_grab_is_abandoned_and_fails_closed(tmp_path, scope, monkeypatch):
    from pytribeam.mcp.capabilities import diagnostics

    monkeypatch.setattr(imaging, "GRAB_GRACE_MIN_S", 0.2)  # give up after estimate + 0.2 s
    monkeypatch.setattr(imaging, "FRAME_OVERHEAD_S", 0.0)
    monkeypatch.setattr(imaging, "SETTINGS_ALLOWANCE_S", 0.0)
    release = threading.Event()
    original = imaging._collect

    def hung(settings, path):
        original(settings, path)  # writes the file, then hangs
        release.wait(10)

    monkeypatch.setattr(imaging, "_collect", hung)
    config = ServerConfig(max_tier=2, project_dir=tmp_path)
    server = build_server(config, modules=(diagnostics, imaging, records, views))
    frame = {"beam": "electron", "resolution": "768x512", "dwell_us": 0.1}

    async with Client(server) as client:
        t0 = time.monotonic()
        stuck = await client.call_tool("collect_single_image", frame)
        elapsed = time.monotonic() - t0
        busy_check = await client.call_tool("check_connection", {})  # uses the microscope
        early_clear = await client.call_tool("clear_fault", {})
        listing = await client.call_tool("list_images", {})  # files only
        info = json.loads((await client.call_tool("get_server_info", {})).content[0].text)
        files_while_hung = list(tmp_path.glob("images/*.tif"))

        release.set()  # the orphaned grab finally returns
        for _ in range(100):
            if json.loads((await client.call_tool("get_server_info", {})).content[0].text)["busy"] is None:
                break
            await anyio.sleep(0.02)
        files_after_late_finish = list(tmp_path.glob("images/*.tif"))
        blocked = await client.call_tool("prepare_imaging", {"beam": "electron"})
        cleared = await client.call_tool("clear_fault", {})
        retry = await client.call_tool("collect_single_image", frame)

    assert stuck.is_error and elapsed < 3
    assert "Stopped waiting" in stuck.content[0].text and "No image was saved" in stuck.content[0].text
    assert busy_check.is_error and "abandoned image acquisition" in busy_check.content[0].text
    assert early_clear.is_error and "Cannot clear the fault while" in early_clear.content[0].text
    assert not listing.is_error
    assert "abandoned" in info["busy"]
    assert files_while_hung == []  # deleted when the tool gave up
    assert files_after_late_finish == []  # nothing kept from the late finish
    assert blocked.is_error and "did not finish" in blocked.content[0].text
    assert not cleared.is_error
    assert not retry.is_error and json.loads(retry.content[0].text)["image_id"] == "i0001"


def test_grab_limit():
    assert imaging.grab_limit_s(10) == 70  # at least 60 s of grace
    assert imaging.grab_limit_s(1000) == 1500  # or half the estimate


async def test_failed_validation_restore_sets_the_fault(tmp_path, scope, monkeypatch):
    def broken_restore(microscope, step):
        raise imaging.RestoreFailed(
            "after validating settings, could not put the electron beam back in quad 1 (busy)"
        )

    monkeypatch.setattr(imaging, "_validate", broken_restore)
    config, server = _server(tmp_path, max_tier=2)
    async with Client(server) as client:
        first = await _refused(client, "prepare_imaging", {"beam": "electron"})
        second = await _refused(client, "set_view", {"quad": 1})
    assert "could not put the electron beam back" in first and "clear_fault" in first
    assert "may not be in the state" in second
    assert not any(c[0] == "prepare" for c in scope.calls)


# --- every scan is time-limited (3.5.3) ---------------------------------------
async def test_auto_cb_is_time_limited(tmp_path, scope):
    scope.settings["electron"].update(resolution="3072x2048", dwell_us=10.0)  # ~64 s
    _, server = _server(tmp_path, max_tier=2, max_frame_s=30)
    async with Client(server) as client:
        refused = await _refused(client, "prepare_imaging", {"beam": "electron", "auto_cb": True})
        assert scope.calls == [("select", "electron")]  # read, not changed
        _, confirmed = await _call(
            client, "prepare_imaging", {"beam": "electron", "auto_cb": True, "confirm_long": True}
        )
        _, no_scan = await _call(client, "prepare_imaging", {"beam": "electron", "hfw_mm": 0.5})
    assert "about 64 s" in refused and "confirm_long=true" in refused
    assert confirmed["auto_cb"] is True
    assert no_scan["auto_cb"] is False  # no scan, so no time check


async def test_auto_cb_hard_limit(tmp_path, scope):
    _, server = _server(tmp_path, max_tier=2, max_frame_s=10, hard_max_frame_s=20)
    async with Client(server) as client:
        message = await _refused(
            client,
            "prepare_imaging",
            {"beam": "electron", "auto_cb": True, "resolution": "1536x1024", "dwell_us": 20, "confirm_long": True},
        )
    assert "more than this server's limit of 20 s" in message
