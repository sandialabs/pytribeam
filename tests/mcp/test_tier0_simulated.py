"""Tier 0 tools against the AutoScript simulator, through ``build_server``.

Runs only on machines listed in ``Constants.offline_machines``.
"""

## python standard libraries
import json

# 3rd party libraries
import pytest

mcp = pytest.importorskip("mcp")  # the mcp extra needs Python >= 3.10
from mcp import Client  # noqa: E402

# local libraries
from pytribeam.mcp.config import ServerConfig  # noqa: E402
from pytribeam.mcp.server import build_server  # noqa: E402

pytestmark = [pytest.mark.simulated, pytest.mark.anyio]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def server(tmp_path):
    config = ServerConfig(max_tier=0, microscope_host="localhost", project_dir=tmp_path)
    return build_server(config)


async def _call(client, tool, args=None):
    result = await client.call_tool(tool, args or {})
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


async def test_check_connection(server):
    async with Client(server) as client:
        info = await _call(client, "get_server_info")
        result = await _call(client, "check_connection")
        again = await _call(client, "reconnect")
    assert info["connected"] is False
    assert result["connected"] is True, result.get("error")
    assert result["simulator"] is True
    assert result["vacuum"] and result["active_device"]
    assert again["connected"] is True


@pytest.mark.parametrize("beam", ["electron", "ion"])
async def test_detector_queries_restore_the_view(server, beam):
    async with Client(server) as client:
        before = await _call(client, "check_connection")
        types = await _call(client, "get_available_detector_types", {"beam": beam})
        modes = await _call(
            client,
            "get_available_detector_modes",
            {"beam": beam, "detector": types["detector_types"][0]},
        )
        cached = await _call(client, "get_available_detector_types", {"beam": beam})
        after = await _call(client, "check_connection")

    assert types["detector_types"] and cached["cached"] is True
    assert modes["modes"]
    assert (after["active_view"], after["active_device"]) == (
        before["active_view"],
        before["active_device"],
    )


async def test_invalid_detector_mode_query_is_refused(server):
    async with Client(server) as client:
        result = await client.call_tool(
            "get_available_detector_modes", {"beam": "electron", "detector": "ICE"}
        )
    assert result.is_error and "Available detector types" in result.content[0].text


async def test_insertable_detectors(server):
    async with Client(server) as client:
        result = await _call(client, "get_available_insertable_detectors")
    for entry in result["detectors"]:
        assert set(entry) == {"detector", "state"}


@pytest.mark.parametrize("beam", ["electron", "ion"])
async def test_imaging_limits(server, beam):
    async with Client(server) as client:
        limits = await _call(client, "get_imaging_limits", {"beam": beam})
    for key in ("voltage_kv", "current_na", "hfw_mm", "working_dist_mm", "rotation_deg", "dwell_us"):
        assert limits[key]["min"] <= limits[key]["max"], key
    assert "1536x1024" in limits["preset_resolutions"]
    assert ("available_currents_na" in limits) == (beam == "ion")


async def test_stage_position_is_within_limits(server):
    async with Client(server) as client:
        position = await _call(client, "get_stage_position")
        limits = await _call(client, "get_stage_limits")
    assert position["coordinate_system"].lower() == "raw"
    for axis in ("x_mm", "y_mm", "z_mm", "t_deg"):
        assert limits[axis]["min"] <= position[axis] <= limits[axis]["max"], axis
