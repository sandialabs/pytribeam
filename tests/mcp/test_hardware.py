"""Hardware query tools, driven through an in-process MCP client with a fake
microscope. No AutoScript, no hardware.

The pytribeam calls (``hardware._detector_types`` and so on) are replaced by
fakes that change the fake microscope the way the real functions do, so the
tests can check what the tools put back afterwards.
"""

## python standard libraries
import json
import types

# 3rd party libraries
import pytest

mcp = pytest.importorskip("mcp")  # the mcp extra needs Python >= 3.10
from mcp import Client  # noqa: E402

# local libraries
from pytribeam.mcp import connection  # noqa: E402
from pytribeam.mcp.capabilities import hardware  # noqa: E402
from pytribeam.mcp.config import ServerConfig  # noqa: E402
from pytribeam.mcp.server import build_server  # noqa: E402

pytestmark = [pytest.mark.detached, pytest.mark.anyio]

DEVICES = {"electron": "ELECTRON_BEAM", "ion": "ION_BEAM"}
DETECTORS = {"ELECTRON_BEAM": ["ETD", "TLD", "CBS"], "ION_BEAM": ["ETD", "ICE"]}
MODES = {"ETD": ["SecondaryElectrons", "BackscatterElectrons"], "TLD": ["None"]}


class FakeImaging:
    def __init__(self):
        self.view, self.device = 1, "ELECTRON_BEAM"
        self.fail_set_view = False

    def get_active_view(self):
        return self.view

    def set_active_view(self, view):
        if self.fail_set_view:
            raise RuntimeError("view locked")
        self.view = view

    def get_active_device(self):
        return self.device

    def set_active_device(self, device):
        self.device = device


class FakeSetting:
    """``detector.type`` or ``detector.mode``, held per device like xT does."""

    def __init__(self, scope, name):
        self._scope, self._name = scope, name

    @property
    def value(self):
        return self._scope.detectors[self._scope.imaging.device][self._name]

    @value.setter
    def value(self, value):
        self._scope.detectors[self._scope.imaging.device][self._name] = value


class FakeMicroscope:
    def __init__(self):
        self.imaging = FakeImaging()
        self.detectors = {
            "ELECTRON_BEAM": {"type": "TLD", "mode": "None"},
            "ION_BEAM": {"type": "ICE", "mode": "SecondaryIons"},
        }
        self.detector = types.SimpleNamespace(
            type=FakeSetting(self, "type"), mode=FakeSetting(self, "mode")
        )

    def snapshot(self):
        return (
            self.imaging.view,
            self.imaging.device,
            json.dumps(self.detectors, sort_keys=True),
        )


class ApplicationServerException(Exception):
    """Same name as the AutoScript exception, which is what the tools match."""


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def scope(monkeypatch):
    """A fake microscope behind the shared connection.

    ``scope.calls`` counts calls to each pytribeam function; set
    ``scope.fail`` to an exception to make the next probe raise partway
    through, after it has already changed the device and detector.
    """
    microscope = FakeMicroscope()
    microscope.calls = {}
    microscope.fail = None

    def probing(name):
        """Count a call, then disturb the microscope as pytribeam does."""
        microscope.calls[name] = microscope.calls.get(name, 0) + 1

        def disturb(device):
            microscope.imaging.set_active_device(device)
            microscope.detector.type.value = "ETD"
            microscope.detector.mode.value = "BackscatterElectrons"
            if microscope.fail:
                raise microscope.fail

        return disturb

    def detector_types(scope_, beam):
        probing("types")(DEVICES[beam])
        return list(DETECTORS[DEVICES[beam]])

    def detector_modes(scope_, beam, detector):
        if detector not in {"ETD", "TLD", "CBS", "ICE", "EBSD"}:
            raise ValueError(f"'{detector}' is not a valid DetectorType")
        probing("modes")(DEVICES[beam])
        if detector not in DETECTORS[DEVICES[beam]]:
            return None
        return MODES.get(detector, [])

    def insertable(scope_):
        probing("insertable")("ELECTRON_BEAM")
        return [("CBS", "Retracted")]

    monkeypatch.setattr(connection, "_connect", lambda config: microscope)
    monkeypatch.setattr(hardware, "_device", DEVICES.__getitem__)
    monkeypatch.setattr(hardware, "_detector_types", detector_types)
    monkeypatch.setattr(hardware, "_detector_modes", detector_modes)
    monkeypatch.setattr(hardware, "_insertable_detectors", insertable)
    return microscope


@pytest.fixture
def server(tmp_path):
    from pytribeam.mcp.capabilities import diagnostics

    config = ServerConfig(max_tier=5, project_dir=tmp_path)  # ion probes need 5
    return build_server(config, modules=(diagnostics, hardware))


async def _call(client, tool, args=None):
    result = await client.call_tool(tool, args or {})
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


async def _refused(client, tool, args=None):
    result = await client.call_tool(tool, args or {})
    assert result.is_error
    return result.content[0].text


async def test_annotations_are_honest(server):
    """Probes change the UI and stage tools the coordinate system, so they are
    not read-only; nothing here moves hardware, so nothing is destructive."""
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    changes_ui = {
        "get_available_detector_types",
        "get_available_detector_modes",
        "get_available_insertable_detectors",
        "get_stage_position",
        "get_stage_limits",
    }
    assert changes_ui | {"get_imaging_limits"} <= set(tools)
    assert not any(tools[name].annotations.read_only_hint for name in changes_ui)
    assert tools["get_imaging_limits"].annotations.read_only_hint is True
    assert not any(tools[name].annotations.destructive_hint for name in changes_ui)


@pytest.mark.parametrize(
    "tool, args",
    [
        ("get_available_detector_types", {"beam": "ion"}),
        ("get_available_detector_modes", {"beam": "ion", "detector": "ICE"}),
    ],
)
async def test_ion_probes_need_tier_5(tmp_path, scope, monkeypatch, tool, args):
    monkeypatch.setattr(hardware, "_imaging_limits", lambda m, beam: {"hfw_mm": {"min": 0, "max": 1}})
    config = ServerConfig(max_tier=4, project_dir=tmp_path)
    before = scope.snapshot()
    async with Client(build_server(config, modules=(hardware,))) as client:
        message = await _refused(client, tool, args)
        limits = await _call(client, "get_imaging_limits", {"beam": "ion"})
    assert "needs tier 5" in message
    assert scope.calls == {} and scope.snapshot() == before  # nothing touched
    assert limits["beam"] == "ion"  # reading ion limits is not gated


async def test_hardware_tools_need_tier_1(tmp_path):
    config = ServerConfig(max_tier=0, project_dir=tmp_path)
    async with Client(build_server(config, modules=(hardware,))) as client:
        assert (await client.list_tools()).tools == []


async def test_beam_must_be_electron_or_ion(server, scope):
    async with Client(server) as client:
        await _refused(client, "get_available_detector_types", {"beam": "laser"})
    assert scope.calls == {}


# --- get_available_detector_types ---------------------------------------
@pytest.mark.parametrize("beam", ["electron", "ion"])
async def test_detector_types_restores_and_caches(server, scope, beam):
    before = scope.snapshot()
    async with Client(server) as client:
        first = await _call(client, "get_available_detector_types", {"beam": beam})
        second = await _call(client, "get_available_detector_types", {"beam": beam})

    assert first["beam"] == beam
    assert first["detector_types"] == DETECTORS[DEVICES[beam]]
    assert (first["cached"], second["cached"]) == (False, True)
    assert second["detector_types"] == first["detector_types"]
    assert scope.calls == {"types": 1}
    assert scope.snapshot() == before  # both devices' detectors put back


async def test_detector_types_cached_per_beam_until_reconnect(server, scope):
    async with Client(server) as client:
        await _call(client, "get_available_detector_types", {"beam": "electron"})
        await _call(client, "get_available_detector_types", {"beam": "ion"})
        await _call(client, "get_available_detector_types", {"beam": "electron"})
        await _call(client, "reconnect")
        again = await _call(client, "get_available_detector_types")
    assert again["cached"] is False
    assert scope.calls == {"types": 3}


async def test_detector_types_restores_on_failure(server, scope):
    scope.fail = RuntimeError("detector server crashed")
    scope.imaging.view = 3
    before = scope.snapshot()
    async with Client(server) as client:
        message = await _refused(client, "get_available_detector_types", {"beam": "ion"})
        assert "detector server crashed" not in message  # unexpected: not leaked
        scope.fail = None
        retry = await _call(client, "get_available_detector_types", {"beam": "ion"})
    assert scope.snapshot() == before
    assert retry["cached"] is False  # a failure is not cached


async def test_value_errors_reach_the_agent(server, scope):
    scope.fail = ValueError("Could not correctly set detector type")
    before = scope.snapshot()
    async with Client(server) as client:
        message = await _refused(client, "get_available_detector_types")
    assert "Could not correctly set detector type" in message
    assert scope.snapshot() == before


async def test_restore_failure_is_reported_as_a_warning(server, scope):
    scope.imaging.view = 2
    scope.imaging.fail_set_view = True
    async with Client(server) as client:
        result = await _call(client, "get_available_detector_types", {"beam": "ion"})
    assert any("Could not restore the view" in w for w in result["warnings"])
    # the device and detectors are still put back
    assert scope.imaging.device == "ELECTRON_BEAM"
    assert scope.detectors["ION_BEAM"] == {"type": "ICE", "mode": "SecondaryIons"}


# --- get_available_detector_modes ---------------------------------------
async def test_detector_modes(server, scope):
    before = scope.snapshot()
    async with Client(server) as client:
        first = await _call(client, "get_available_detector_modes", {"detector": "ETD"})
        second = await _call(client, "get_available_detector_modes", {"detector": "ETD"})
    assert first == {
        "beam": "electron",
        "detector": "ETD",
        "modes": MODES["ETD"],
        "cached": False,
        "restored": True,
        "warnings": [],
    }
    assert second["cached"] is True
    assert scope.calls == {"modes": 1}
    assert scope.snapshot() == before


async def test_detector_modes_defaults_to_the_beams_current_detector(server, scope):
    async with Client(server) as client:
        electron = await _call(client, "get_available_detector_modes")
        ion = await _call(client, "get_available_detector_modes", {"beam": "ion"})
    assert electron["detector"] == "TLD"
    assert ion["detector"] == "ICE"  # read from the ion device, not the active one


async def test_detector_modes_wrong_beam_lists_valid_types(server, scope):
    before = scope.snapshot()
    async with Client(server) as client:
        message = await _refused(
            client, "get_available_detector_modes", {"beam": "ion", "detector": "TLD"}
        )
    assert "'TLD' does not work with the ion beam" in message
    assert "ETD, ICE" in message
    assert scope.snapshot() == before


async def test_detector_modes_unknown_type_is_refused(server, scope):
    async with Client(server) as client:
        message = await _refused(
            client, "get_available_detector_modes", {"detector": "NotADetector"}
        )
    assert "'NotADetector' is not a detector type" in message
    assert "ETD, TLD, CBS" in message
    assert "modes" not in scope.calls


# --- get_available_insertable_detectors ---------------------------------
async def test_insertable_detectors_from_the_ion_view(server, scope):
    scope.imaging.view, scope.imaging.device = 2, "ION_BEAM"
    before = scope.snapshot()
    async with Client(server) as client:
        first = await _call(client, "get_available_insertable_detectors")
        second = await _call(client, "get_available_insertable_detectors")
    assert first["detectors"] == [{"detector": "CBS", "state": "Retracted"}]
    assert (first["cached"], second["cached"]) == (False, True)
    assert scope.calls == {"insertable": 1}
    assert scope.snapshot() == before


async def test_insertable_detectors_restores_on_failure(server, scope):
    scope.fail = RuntimeError("insert server timeout")
    scope.imaging.device = "ION_BEAM"
    before = scope.snapshot()
    async with Client(server) as client:
        await _refused(client, "get_available_insertable_detectors")
    assert scope.snapshot() == before


# --- limits and stage ---------------------------------------------------
async def test_imaging_limits(server, scope, monkeypatch):
    seen = []

    def limits(microscope, beam):
        seen.append(beam)
        return {"hfw_mm": {"min": 0.0001, "max": 2.5}}

    monkeypatch.setattr(hardware, "_imaging_limits", limits)
    async with Client(server) as client:
        ion = await _call(client, "get_imaging_limits", {"beam": "ion"})
        await _call(client, "get_imaging_limits", {"beam": "ion"})
    assert ion == {"beam": "ion", "hfw_mm": {"min": 0.0001, "max": 2.5}}
    assert seen == ["ion", "ion"]  # not cached: limits depend on current settings


async def test_stage_position_and_limits(server, scope, monkeypatch):
    position = {
        "x_mm": 1.0,
        "y_mm": -2.0,
        "z_mm": 4.0,
        "r_deg": 0.0,
        "t_deg": 0.0,
        "coordinate_system": "Raw",
    }
    limits = {"x_mm": {"min": -55.0, "max": 55.0}}
    monkeypatch.setattr(hardware, "_stage_position", lambda m: position)
    monkeypatch.setattr(hardware, "_stage_limits", lambda m: limits)
    async with Client(server) as client:
        assert await _call(client, "get_stage_position") == position
        assert await _call(client, "get_stage_limits") == limits


@pytest.mark.parametrize("tool", ["get_stage_position", "get_stage_limits"])
async def test_inactive_bulk_stage_is_reported(server, scope, monkeypatch, tool):
    def refuse(microscope):
        raise ApplicationServerException("Bulk stage is not an active stage.")

    monkeypatch.setattr(hardware, "_stage_position", refuse)
    monkeypatch.setattr(hardware, "_stage_limits", refuse)
    async with Client(server) as client:
        message = await _refused(client, tool)
    assert "Bulk stage is not an active stage" in message


def test_round_strips_conversion_noise():
    assert hardware._round(0.8999999999999999) == 0.9
    assert hardware._limit(types.SimpleNamespace(min=1e-3 * 3, max=30.000000000000004)) == {
        "min": 0.003,
        "max": 30.0,
    }


# --- fail closed (security review P2) ----------------------------------------
async def test_failed_restore_sets_the_fault_and_blocks(tmp_path, scope, monkeypatch):
    from pytribeam.mcp.capabilities import diagnostics, records, views

    monkeypatch.setattr(hardware, "_imaging_limits", lambda m, beam: {})
    config = ServerConfig(max_tier=5, project_dir=tmp_path)
    server = build_server(config, modules=(diagnostics, records, hardware, views))
    scope.imaging.view = 2
    scope.imaging.fail_set_view = True
    async with Client(server) as client:
        probe = await _call(client, "get_available_detector_types", {"beam": "ion"})
        scope.imaging.fail_set_view = False
        blocked = await _refused(client, "get_available_detector_types")
        blocked_read = await _refused(client, "get_imaging_limits")
        info = await _call(client, "get_server_info")  # tier 0 still works
        listing = await _call(client, "list_images")
        cleared = await _call(client, "clear_fault")
        again = await _call(client, "get_available_detector_types")

    assert probe["restored"] is False and probe["cached"] is False
    assert "could not restore the view" in blocked
    assert "clear_fault" in blocked and "Tier 0 tools still work" in blocked
    assert "could not restore" in blocked_read  # even read-only tier 1 tools
    assert info["pytribeam_version"] and listing["total"] == 0
    assert cleared == {"cleared": True, "fault": probe_fault(cleared)}
    assert again["restored"] is True


def probe_fault(cleared):
    assert "after probing detectors, could not restore the view" in cleared["fault"]
    return cleared["fault"]


async def test_reconnect_does_not_clear_the_fault(tmp_path, scope):
    from pytribeam.mcp.capabilities import diagnostics, views

    config = ServerConfig(max_tier=5, project_dir=tmp_path)
    server = build_server(config, modules=(diagnostics, hardware, views))
    scope.imaging.fail_set_view = True
    scope.imaging.view = 2
    async with Client(server) as client:
        await _call(client, "get_available_detector_types", {"beam": "ion"})
        scope.imaging.fail_set_view = False
        await client.call_tool("reconnect", {})
        message = await _refused(client, "get_available_detector_types")
    assert "could not restore" in message


async def test_clear_fault_is_audited(tmp_path, scope, caplog):
    from pytribeam.mcp.capabilities import views

    caplog.set_level("INFO", logger="pytribeam.mcp.audit")
    config = ServerConfig(max_tier=1, project_dir=tmp_path)
    server = build_server(config, modules=(hardware, views))
    scope.imaging.fail_set_view = True
    scope.imaging.view = 2
    async with Client(server) as client:
        await _call(client, "get_available_detector_types")
        await _call(client, "clear_fault")
        nothing = await _call(client, "clear_fault")
    audit = [
        json.loads(r.getMessage()) for r in caplog.records if r.name == "pytribeam.mcp.audit"
    ]
    cleared = [r for r in audit if r["tool"] == "clear_fault" and r["event"] == "ended"]
    assert len(cleared) == 2 and all(r["ok"] for r in cleared)
    assert "could not restore the view" in cleared[0]["cleared_fault"]  # which fault
    assert cleared[1]["cleared_fault"] is None
    assert nothing == {"cleared": False, "fault": None}
