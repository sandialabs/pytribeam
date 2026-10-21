"""Imaging tools against the AutoScript simulator, through ``build_server``.

Runs only on machines listed in ``Constants.offline_machines``.
"""

## python standard libraries
import base64
import io
import json

# 3rd party libraries
import pytest
from PIL import Image

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
def config(tmp_path):
    return ServerConfig(max_tier=1, microscope_host="localhost", project_dir=tmp_path)


@pytest.fixture
def server(config):
    return build_server(config)


async def _call(client, tool, args=None):
    result = await client.call_tool(tool, args or {})
    assert not result.is_error, result.content[0].text
    return result, json.loads(result.content[0].text)


async def test_set_view_round_trip(server):
    async with Client(server) as client:
        _, ion = await _call(client, "set_view", {"quad": 2})
        _, electron = await _call(client, "set_view", {"quad": 1})
    assert ion["active_view"] == 2 and electron["active_view"] == 1
    assert electron["active_device"] == "ELECTRON_BEAM"


async def test_prepare_imaging_changes_only_hfw_and_dwell(server):
    async with Client(server) as client:
        # Settle on the electron beam first, so the second call changes only
        # what it is asked to.
        _, start = await _call(client, "prepare_imaging", {"beam": "electron"})
        hfw = start["settings"]["hfw_mm"] * 0.5
        dwell = 3.0 if start["settings"]["dwell_us"] != 3.0 else 1.0
        _, result = await _call(
            client, "prepare_imaging", {"beam": "electron", "hfw_mm": hfw, "dwell_us": dwell}
        )
    changed = set(result["changes"])
    assert changed == {
        "beams.electron_beam.horizontal_field_width.value",
        "beams.electron_beam.scanning.dwell_time.value",
    }, changed
    assert result["settings"]["hfw_mm"] == pytest.approx(hfw, rel=1e-3)


async def test_collect_two_images(server, config):
    async with Client(server) as client:
        first, a = await _call(
            client,
            "collect_single_image",
            {"beam": "electron", "resolution": "768x512", "dwell_us": 0.5, "description": "a"},
        )
        _, b = await _call(
            client,
            "collect_single_image",
            {"beam": "electron", "resolution": "768x512", "dwell_us": 0.5, "bit_depth": 16},
        )
        _, listing = await _call(client, "list_images")
        viewed, record = await _call(client, "view_image", {"image_id": "i0002", "grid": True})

    assert (a["image_id"], b["image_id"]) == ("i0001", "i0002")
    for name in ("i0001", "i0002"):
        with Image.open(config.images_dir / f"{name}.tif") as img:
            assert img.size == (768, 512)
        assert (config.images_dir / f"{name}.yml").is_file()
    assert (a["bit_depth"], b["bit_depth"]) == (8, 16)
    assert a["acquisition_s"] > 0 and a["stats"]["max"] > a["stats"]["min"]
    assert a["stats"]["sharpness"] > 0
    preview = Image.open(io.BytesIO(base64.b64decode(first.content[1].data)))
    assert max(preview.size) == 768
    assert listing["total"] == 2 and listing["images"][0]["description"] == "a"
    assert "A1" in record["preview"]["grid"]["cells"] and viewed.content[1].type == "image"


async def test_custom_resolution_is_8_bit(server, config):
    async with Client(server) as client:
        _, result = await _call(
            client,
            "collect_single_image",
            {"beam": "electron", "resolution": "640x480", "dwell_us": 0.5, "bit_depth": 16},
        )
    assert result["bit_depth"] == 8
    assert any("8 bits" in w or "8-bit" in w for w in result["warnings"])


async def test_auto_cb_reports_chosen_values(server):
    async with Client(server) as client:
        _, result = await _call(client, "prepare_imaging", {"beam": "electron", "auto_cb": True})
    assert 0 < result["settings"]["brightness"] <= 1
    assert 0 < result["settings"]["contrast"] <= 1


async def test_retractable_detector_refused_at_tier_1(server):
    async with Client(server) as client:
        _, insertable = await _call(client, "get_available_insertable_detectors")
        if not insertable["detectors"]:
            pytest.skip("simulator has no retractable detectors")
        detector = insertable["detectors"][0]["detector"]
        result = await client.call_tool(
            "prepare_imaging", {"beam": "electron", "detector": detector}
        )
    assert result.is_error and "needs tier 2" in result.content[0].text


async def test_long_frame_is_refused_without_confirmation(server):
    async with Client(server) as client:
        result = await client.call_tool(
            "collect_single_image",
            {"beam": "electron", "resolution": "6144x4096", "dwell_us": 20},
        )
    assert result.is_error and "confirm_long" in result.content[0].text
