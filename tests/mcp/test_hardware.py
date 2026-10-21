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

    config = ServerConfig(project_dir=tmp_path)
    return build_server(config, modules=(diagnostics, hardware))


async def _call(client, tool, args=None):
    result = await client.call_tool(tool, args or {})
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


async def _refused(client, tool, args=None):
    result = await client.call_tool(tool, args or {})
    assert result.is_error
    return result.content[0].text


async def test_tools_are_read_only(server):
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    hardware_tools = {
        "get_available_detector_types",
        "get_available_detector_modes",
        "get_available_insertable_detectors",
        "get_imaging_limits",
        "get_stage_position",
        "get_stage_limits",
    }
    assert hardware_tools <= set(tools)
    assert all(tools[name].annotations.read_only_hint for name in hardware_tools)


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
