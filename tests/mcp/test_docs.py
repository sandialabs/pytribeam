"""Userguide pages served as MCP resources. In-process: no AutoScript, no LLM."""

## python standard libraries
import tomllib
from pathlib import Path

# 3rd party libraries
import pytest
from mcp import Client

# local libraries
from pytribeam.mcp import docs
from pytribeam.mcp.config import ServerConfig
from pytribeam.mcp.server import INSTRUCTIONS, build_server

pytestmark = [pytest.mark.detached]

REPO = Path(__file__).resolve().parents[2]
REFERENCE_FRAME = docs.PAGES[0]


def test_every_page_exists_in_the_userguide():
    for page in docs.PAGES:
        assert (docs.REPO_DIR / page.source).is_file(), page.source


def test_every_page_is_packaged_in_the_wheel():
    """force-include in pyproject.toml must map each source to its packaged name,
    or an installed server has no copy of the page."""
    with open(REPO / "pyproject.toml", "rb") as f:
        included = tomllib.load(f)["tool"]["hatch"]["build"]["targets"]["wheel"][
            "force-include"
        ]
    for page in docs.PAGES:
        source = f"docs/userguide/src/{page.source}"
        assert included.get(source) == f"pytribeam/mcp/docs/{page.packaged}"


def test_figures_become_their_alt_text():
    text = docs.for_agent("Before\n![Stage Axes Side View](stage_side_view.png)\nAfter")
    assert text == "Before\n[Figure: Stage Axes Side View]\nAfter"


def test_relative_links_keep_only_their_text():
    text = docs.for_agent(
        "See **[General Settings](../config_file/general/index.html)** and "
        "[above](#stage-axes), or [AutoScript](https://example.com/a)."
    )
    assert text == (
        "See **General Settings** and above, or [AutoScript](https://example.com/a)."
    )


def test_reference_frame_page_reads_from_the_repository():
    text = docs.read(REFERENCE_FRAME)
    assert "RAW" in text and "Imaging quadrants" in text
    assert ".png)" not in text and "index.html" not in text


def test_missing_page_explains_instead_of_raising(monkeypatch, tmp_path):
    monkeypatch.setattr(docs, "PACKAGED_DIR", tmp_path / "none")
    monkeypatch.setattr(docs, "REPO_DIR", tmp_path / "none")
    assert "not installed" in docs.read(REFERENCE_FRAME)


def test_packaged_copy_is_preferred(monkeypatch, tmp_path):
    (tmp_path / REFERENCE_FRAME.packaged).write_text("packaged copy", encoding="utf-8")
    monkeypatch.setattr(docs, "PACKAGED_DIR", tmp_path)
    assert docs.read(REFERENCE_FRAME).endswith("packaged copy")


def test_instructions_point_at_the_resource():
    assert REFERENCE_FRAME.uri in INSTRUCTIONS


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_resource_is_served_at_tier_0(tmp_path):
    config = ServerConfig(max_tier=0, microscope_host="scope-pc", project_dir=tmp_path)
    async with Client(build_server(config)) as client:
        listed = {str(r.uri): r for r in (await client.list_resources()).resources}
        assert REFERENCE_FRAME.uri in listed
        assert listed[REFERENCE_FRAME.uri].mime_type == "text/markdown"
        result = await client.read_resource(REFERENCE_FRAME.uri)
    assert "Stage Axes" in result.contents[0].text


@pytest.mark.anyio
async def test_read_userguide_tool_returns_the_same_text(tmp_path):
    """The fallback for clients that cannot read resources."""
    import json

    config = ServerConfig(max_tier=0, microscope_host="scope-pc", project_dir=tmp_path)
    async with Client(build_server(config)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        result = await client.call_tool("read_userguide", {})
        resource = await client.read_resource(REFERENCE_FRAME.uri)
    assert tools["read_userguide"].annotations.read_only_hint is True
    payload = json.loads(result.content[0].text)
    assert payload["uri"] == REFERENCE_FRAME.uri
    assert payload["text"] == resource.contents[0].text


@pytest.mark.anyio
async def test_read_userguide_refuses_unknown_pages(tmp_path):
    config = ServerConfig(max_tier=0, microscope_host="scope-pc", project_dir=tmp_path)
    async with Client(build_server(config)) as client:
        result = await client.call_tool("read_userguide", {"page": "../../secrets"})
    assert result.is_error
    assert "Pages: reference_frame" in result.content[0].text
