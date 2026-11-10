#!/usr/bin/python3
"""
Documentation Resources
=======================

Serves pages of the pytribeam userguide (``docs/userguide/src``) to the agent
as MCP resources, so the conventions an agent needs (stage axes, quadrants,
image and patterning coordinates) come from the same text the users read.
Nothing is copied into this package's source: the userguide is the one place
to edit.

The pages reach an installed package through ``force-include`` in
``pyproject.toml``, which puts them in the wheel under ``pytribeam/mcp/docs/``.
An editable install or a source checkout has no copy there, so the page is
read from the repository's ``docs/`` folder instead.

Pages are adapted for an agent that reads text, not a browser: figures become
``[Figure: alt text]`` (their captions, the italic line after each figure, are
kept), and links to other userguide pages keep only their text.

Uses only the standard library, so the server starts without AutoScript.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple, Optional

# Wheel location (force-include) and repository location of the userguide.
PACKAGED_DIR = Path(__file__).parent / "docs"
REPO_DIR = Path(__file__).resolve().parents[3] / "docs" / "userguide" / "src"


class Page(NamedTuple):
    uri: str
    name: str
    title: str
    description: str
    packaged: str  # file name under PACKAGED_DIR
    source: str  # path under REPO_DIR


PAGES = (
    Page(
        uri="pytribeam://docs/reference-frame",
        name="reference_frame",
        title="Reference frame conventions",
        description=(
            "pytribeam userguide: RAW stage axes and their directions, pre-tilt "
            "and rotation_side conventions, imaging quadrants, and the image and "
            "patterning coordinate systems. Read before moving the stage or "
            "giving positions in an image."
        ),
        packaged="reference_frame.md",
        source="reference_frame/README.md",
    ),
)

_FIGURE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
# A markdown link whose target is not an absolute URL: another userguide page
# or an anchor on this one. Absolute links are left alone.
_RELATIVE_LINK = re.compile(r"\[([^\]]+)\]\((?!https?://)[^)]*\)")


def page_path(page: Page) -> Optional[Path]:
    """Where *page* is on this install, or None if it is missing."""
    for path in (PACKAGED_DIR / page.packaged, REPO_DIR / page.source):
        if path.is_file():
            return path
    return None


def for_agent(markdown: str) -> str:
    """Adapt a userguide page for a text-only reader (see module docstring)."""
    text = _FIGURE.sub(lambda m: f"[Figure: {m.group(1)}]", markdown)
    return _RELATIVE_LINK.sub(lambda m: m.group(1), text)


def read(page: Page) -> str:
    """The text of *page* for the agent. Never raises: a missing page says so,
    so a broken install shows up as an explanation rather than an error."""
    path = page_path(page)
    if path is None:
        return (
            f"The userguide page {page.source!r} is not installed with this copy "
            "of pytribeam. Ask the operator to reinstall pytribeam, or see the "
            "Reference Frame Conventions page of the pytribeam userguide."
        )
    body = for_agent(path.read_text(encoding="utf-8"))
    return (
        f"<!-- From the pytribeam userguide ({page.source}). Figures are "
        "omitted; their captions are kept. -->\n\n" + body
    )


def register(server) -> None:
    """Add every page to *server* as a text resource.

    Resources only read files that ship with pytribeam, so they are available
    at every tier, including 0.
    """
    for page in PAGES:
        server.resource(
            page.uri,
            name=page.name,
            title=page.title,
            description=page.description,
            mime_type="text/markdown",
        )(_reader(page))


def _reader(page: Page):
    """A no-argument function returning *page*'s text: static resources may
    not take parameters, so the page is bound here rather than as a default."""

    def content() -> str:
        return read(page)

    content.__name__ = f"read_{page.name}"
    return content
