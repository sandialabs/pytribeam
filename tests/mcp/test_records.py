"""Image previews, statistics, image records, and the snapshot helpers.

Synthetic images written in the test; no AutoScript, no hardware.
"""

## python standard libraries
import base64
import io
import json
from pathlib import Path

# 3rd party libraries
import numpy as np
import pytest
import yaml
from PIL import Image

mcp = pytest.importorskip("mcp")  # the mcp extra needs Python >= 3.10
from mcp import Client  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

# local libraries
from pytribeam.mcp import connection as connection_module  # noqa: E402
from pytribeam.mcp import state  # noqa: E402
from pytribeam.mcp.capabilities import _helpers, _images, records  # noqa: E402
from pytribeam.mcp.config import ServerConfig  # noqa: E402
from pytribeam.mcp.connection import MicroscopeConnection  # noqa: E402
from pytribeam.mcp.server import build_server  # noqa: E402

pytestmark = pytest.mark.detached

STATE_DIR = Path(__file__).parent / "state_records"


def _checkerboard(size=256, cell=16, low=40, high=200, dtype=np.uint8):
    y, x = np.indices((size, size))
    board = ((x // cell + y // cell) % 2).astype(np.float64)
    return (low + board * (high - low)).astype(dtype)


def _blur(data, passes=6):
    out = data.astype(np.float64)
    for _ in range(passes):
        out = (out + np.roll(out, 1, 0) + np.roll(out, -1, 0) + np.roll(out, 1, 1) + np.roll(out, -1, 1)) / 5
    return out.astype(data.dtype)


# --- next_path -------------------------------------------------------------
def test_next_path_defaults_unchanged(tmp_path):
    (tmp_path / "s0007.yml").touch()
    (tmp_path / "i0099.tif").touch()
    assert state.next_path(tmp_path) == tmp_path / "s0008.yml"
    assert state.next_path(tmp_path, "i", ".tif") == tmp_path / "i0100.tif"
    assert state.next_path(tmp_path / "missing", "i", ".tif").name == "i0001.tif"


def test_next_path_ignores_other_suffixes(tmp_path):
    (tmp_path / "i0005.yml").touch()  # a sidecar without its image
    assert state.next_path(tmp_path, "i", ".tif").name == "i0001.tif"


# --- snapshot and acted ----------------------------------------------------
def test_snapshot_saves_and_acted_reports_changes(tmp_path, monkeypatch):
    queue = [state.load(STATE_DIR / "s0001.yml"), state.load(STATE_DIR / "s0002.yml")]
    monkeypatch.setattr(connection_module, "_connect", lambda config: object())
    monkeypatch.setattr(_helpers, "_capture", lambda m, d: {**queue.pop(0), "description": d})
    conn = MicroscopeConnection(ServerConfig(project_dir=tmp_path))

    before = _helpers.snapshot(conn, tmp_path, "before")
    after = _helpers.snapshot(conn, tmp_path, "after")
    record = _helpers.acted(before, after)

    assert (before[0], after[0]) == ("s0001", "s0002")
    assert state.load(tmp_path / "s0001.yml")["description"] == "before"
    assert record["before_state_id"] == "s0001" and record["after_state_id"] == "s0002"
    assert set(record["changes"]) == {
        "specimen.stage.current_position.r",
        "specimen.stage.current_position.x",
        "specimen.stage.current_position.y",
    }


def test_snapshot_refuses_an_empty_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(connection_module, "_connect", lambda config: object())
    monkeypatch.setattr(_helpers, "_capture", lambda m, d: {"values": {}, "read_errors": {}})
    conn = MicroscopeConnection(ServerConfig(project_dir=tmp_path))
    with conn.use():
        pass
    with pytest.raises(ToolError, match="connection"):
        _helpers.snapshot(conn, tmp_path, "")
    assert not conn.connected and not list(tmp_path.glob("s*.yml"))


# --- load --------------------------------------------------------------------
tifffile = pytest.importorskip("tifffile")  # a scikit-image dependency


@pytest.mark.parametrize(
    "layout",
    ["gray", "rgb", "big_endian"],
)
def test_load_keeps_16_bit_depth(tmp_path, layout):
    """Pillow opens a 16-bit RGB TIFF as 8-bit "RGB"; the loader must not."""
    gray = (np.arange(48 * 64, dtype=np.uint16).reshape(48, 64) * 20)
    data = {
        "gray": gray,
        "rgb": np.stack([gray, gray, gray], axis=-1),
        "big_endian": gray.astype(">u2"),
    }[layout]
    tifffile.imwrite(tmp_path / "i0001.tif", data)
    loaded, bits = _images.load(tmp_path / "i0001.tif")
    assert bits == 16 and loaded.shape == (48, 64)
    assert loaded.max() == gray.max()


def test_load_refuses_multi_page_files(tmp_path):
    gray = np.zeros((48, 64), np.uint16)
    tifffile.imwrite(tmp_path / "i0001.tif", np.stack([gray, gray]))
    with pytest.raises(_images.ImageTooLarge, match="2 pages"):
        _images.load(tmp_path / "i0001.tif")


def test_oversized_image_is_refused_before_decoding(tmp_path, monkeypatch):
    """The size comes from the header; no pixel data is read."""
    monkeypatch.setattr(_images, "MAX_IMAGE_PIXELS", 100 * 100)
    tifffile.imwrite(tmp_path / "i0001.tif", np.zeros((200, 200), np.uint8))

    decoded = []
    real = tifffile.TiffPage.asarray

    def record_decode(self, *args, **kwargs):
        decoded.append(self)  # recorded, not raised: a raise would be caught
        return real(self, *args, **kwargs)  # by the Pillow fallback and hidden

    monkeypatch.setattr(tifffile.TiffPage, "asarray", record_decode)
    with pytest.raises(_images.ImageTooLarge, match="200x200 px"):
        _images.load(tmp_path / "i0001.tif")
    assert decoded == []


def test_oversized_pillow_image_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(_images, "MAX_IMAGE_PIXELS", 100 * 100)
    Image.fromarray(np.zeros((200, 200), np.uint8)).save(tmp_path / "i0001.png")
    with pytest.raises(_images.ImageTooLarge, match="200x200 px"):
        _images.load(tmp_path / "i0001.png")


def test_oversized_file_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(_images, "MAX_FILE_BYTES", 1000)
    tifffile.imwrite(tmp_path / "i0001.tif", np.zeros((100, 100), np.uint8))
    with pytest.raises(_images.ImageTooLarge, match="MB"):
        _images.load(tmp_path / "i0001.tif")


def test_size_refusal_is_not_retried_with_pillow(tmp_path, monkeypatch):
    """The Pillow fallback must not catch a size refusal and decode anyway."""
    monkeypatch.setattr(_images, "MAX_IMAGE_PIXELS", 100 * 100)
    tifffile.imwrite(tmp_path / "i0001.tif", np.zeros((200, 200), np.uint8))
    opened = []
    monkeypatch.setattr(_images.PILImage, "open", lambda *a: opened.append(a) or 1 / 0)
    with pytest.raises(_images.ImageTooLarge):
        _images.load(tmp_path / "i0001.tif")
    assert opened == []


def test_large_image_stats_are_subsampled(monkeypatch):
    monkeypatch.setattr(_images, "STATS_SUBSAMPLE_PIXELS", 1000)
    small, large = np.full((20, 20), 50, np.uint8), np.full((100, 100), 50, np.uint8)
    assert _images.stats(small, 8)["subsampled"] is False
    assert _images.stats(large, 8)["subsampled"] is True
    assert _images.stats(large, 8)["mean"] == 50


def test_load_8_bit(tmp_path):
    gray = (np.arange(48 * 64) % 256).astype(np.uint8).reshape(48, 64)
    Image.fromarray(gray).save(tmp_path / "i0001.tif")
    loaded, bits = _images.load(tmp_path / "i0001.tif")
    assert bits == 8 and (loaded == gray).all()


def test_load_falls_back_to_pillow(tmp_path):
    gray = np.full((20, 30), 77, np.uint8)
    Image.fromarray(gray).save(tmp_path / "i0001.png")  # not a TIFF
    loaded, bits = _images.load(tmp_path / "i0001.png")
    assert bits == 8 and loaded.shape == (20, 30)


# --- statistics ------------------------------------------------------------
def test_stats_8bit_clipping():
    data = np.full((100, 100), 128, np.uint8)
    data[:10] = 255  # 10 % saturated
    data[10:15] = 0  # 5 % black
    s = _images.stats(data, 8)
    assert s["clipped_high_frac"] == pytest.approx(0.10)
    assert s["clipped_low_frac"] == pytest.approx(0.05)
    assert (s["min"], s["max"], s["p50"]) == (0, 255, 128.0)


def test_stats_16bit_uses_the_16bit_range():
    data = np.full((50, 50), 255, np.uint16)  # 255 is not clipped in 16 bits
    s = _images.stats(data, 16)
    assert s["clipped_high_frac"] == 0.0 and s["bit_depth"] == 16


def test_sharpness_is_higher_for_a_sharper_image():
    sharp = _checkerboard()
    blurred = _blur(sharp)
    assert _images.stats(sharp, 8)["sharpness"] > 2 * _images.stats(blurred, 8)["sharpness"]


def test_sharpness_does_not_depend_on_brightness():
    board = _checkerboard(low=20, high=60)
    brighter = (board.astype(np.float64) * 3).astype(np.uint8)
    a, b = _images.stats(board, 8)["sharpness"], _images.stats(brighter, 8)["sharpness"]
    assert a == pytest.approx(b, rel=0.05)


# --- preview ---------------------------------------------------------------
def _decode(png: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(png)))


def test_preview_downsamples_to_max_px():
    data = np.zeros((1024, 1536), np.uint8)
    png, info = _images.preview(data, 8, max_px=768)
    assert (info["width"], info["height"]) == (768, 512)
    assert _decode(png).shape == (512, 768)


def test_preview_never_upsamples_and_caps_max_px():
    small = np.zeros((100, 200), np.uint8)
    assert _images.preview(small, 8, max_px=1000)[1]["width"] == 200
    big = np.zeros((4096, 6144), np.uint8)
    assert _images.preview(big, 8, max_px=10_000)[1]["width"] == _images.MAX_PREVIEW_PX


def test_dark_16bit_image_stays_dark():
    """A fixed mapping: a dim 16-bit image must not be stretched to look fine."""
    data = np.linspace(0, 4000, 64 * 64).reshape(64, 64).astype(np.uint16)
    png, info = _images.preview(data, 16, max_px=64)
    pixels = _decode(png)
    assert pixels.max() <= 4000 >> 8  # 15, not 255
    assert "no contrast stretch" in info["mapping"]


def test_grid_cells_are_in_full_image_pixels():
    data = np.zeros((512, 1024), np.uint8)
    png, info = _images.preview(data, 8, max_px=256, grid=True, origin=(100, 50))
    grid = info["grid"]
    assert (grid["columns"], grid["rows"]) == (8, 4)
    assert grid["cells"]["A1"] == {"left": 100, "top": 50, "width": 128, "height": 128}
    assert grid["cells"]["H4"] == {"left": 100 + 896, "top": 50 + 384, "width": 128, "height": 128}
    assert _decode(png).ndim == 3  # drawn in colour on the preview


# --- crop ------------------------------------------------------------------
def test_crop_bounds():
    data = np.arange(100 * 200).reshape(100, 200)
    out, bounds = _images.crop(data, {"left": 0.5, "top": 0.25, "width": 0.25, "height": 0.5})
    assert bounds == {"left": 100, "top": 25, "width": 50, "height": 50}
    assert out[0, 0] == data[25, 100]


@pytest.mark.parametrize(
    "region, message",
    [
        ({"left": 0.9, "top": 0, "width": 0.2, "height": 0.5}, "past the image"),
        ({"left": -0.1, "top": 0, "width": 0.2, "height": 0.5}, "fractions"),
        ({"left": 0, "top": 0, "width": 0.01, "height": 0.5}, "at least"),
        ({"left": 0, "top": 0, "width": 0.5}, "missing height"),
    ],
)
def test_bad_regions_are_refused(region, message):
    with pytest.raises(ValueError, match=message):
        _images.crop(np.zeros((100, 200)), region)


# --- list_images and view_image -------------------------------------------
@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def project(tmp_path):
    """Three images: i0001 and i0002 with sidecars, i0003 without."""
    config = ServerConfig(project_dir=tmp_path)
    config.images_dir.mkdir(parents=True)
    for n in (1, 2, 3):
        data = _checkerboard(size=256, low=10 * n, high=100 + 10 * n)
        Image.fromarray(data).save(config.images_dir / f"i{n:04d}.tif")
        if n < 3:
            sidecar = {
                "recorded_at": f"2026-10-21T10:0{n}:00",
                "description": f"image {n}",
                "beam": "electron",
                "detector": "ETD",
                "resolution": "256x256",
                "hfw_mm": 0.1,
                "pixel_size_nm": 390.625,
                "stage_position": {"x_mm": float(n), "y_mm": 0.0},
                "before_state_id": f"s000{2 * n - 1}",
                "after_state_id": f"s000{2 * n}",
            }
            with open(config.images_dir / f"i{n:04d}.yml", "w") as f:
                yaml.safe_dump(sidecar, f)
    (config.images_dir / "notes.tif").touch()  # not an image id; ignored
    return config


@pytest.fixture
def server(project):
    return build_server(project, modules=(records,))


async def _call(client, tool, args=None):
    result = await client.call_tool(tool, args or {})
    assert not result.is_error, result.content[0].text
    return result


@pytest.mark.anyio
async def test_image_tools_are_read_only(server):
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"list_states", "list_images", "view_image"}
    assert all(t.annotations.read_only_hint for t in tools.values())


@pytest.mark.anyio
async def test_list_images(server):
    async with Client(server) as client:
        listing = json.loads((await _call(client, "list_images")).content[0].text)
        limited = json.loads((await _call(client, "list_images", {"limit": 2})).content[0].text)
    assert listing["total"] == 3
    assert [i["image_id"] for i in listing["images"]] == ["i0001", "i0002", "i0003"]
    first = listing["images"][0]
    assert first["description"] == "image 1" and first["stage_position"]["x_mm"] == 1.0
    assert first["before_state_id"] == "s0001"
    assert "no record" in listing["images"][2]["note"]
    assert [i["image_id"] for i in limited["images"]] == ["i0002", "i0003"]


@pytest.mark.anyio
async def test_view_image_returns_record_stats_and_picture(server):
    async with Client(server) as client:
        result = await _call(client, "view_image", {"image_id": "i0002", "max_px": 128})
    record = json.loads(result.content[0].text)
    picture = result.content[1]
    assert picture.type == "image" and picture.mime_type == "image/png"
    assert _decode(base64.b64decode(picture.data)).shape == (128, 128)
    assert record["image_id"] == "i0002" and record["description"] == "image 2"
    assert record["stats"]["bit_depth"] == 8
    assert record["preview"]["full_size"] == {"width": 256, "height": 256}


@pytest.mark.anyio
async def test_view_image_region_and_grid(server):
    region = {"left": 0.5, "top": 0.5, "width": 0.25, "height": 0.25}
    async with Client(server) as client:
        result = await _call(
            client, "view_image", {"image_id": "i0003", "region": region, "grid": True}
        )
    record = json.loads(result.content[0].text)
    assert record["preview"]["region_px"] == {"left": 128, "top": 128, "width": 64, "height": 64}
    assert record["preview"]["width"] == 64  # a small region is shown at full detail
    assert record["preview"]["grid"]["cells"]["A1"]["left"] == 128


@pytest.mark.anyio
@pytest.mark.parametrize("bad_id", ["i0009", "notes", "../states/s0001", "i0001.tif"])
async def test_unknown_or_malformed_image_id_is_refused(server, bad_id):
    async with Client(server) as client:
        result = await client.call_tool("view_image", {"image_id": bad_id})
    assert result.is_error and "No image with id" in result.content[0].text


@pytest.mark.anyio
async def test_bad_region_reaches_the_agent(server):
    async with Client(server) as client:
        result = await client.call_tool(
            "view_image",
            {"image_id": "i0001", "region": {"left": 0.9, "top": 0, "width": 0.5, "height": 0.5}},
        )
    assert result.is_error and "past the image" in result.content[0].text
