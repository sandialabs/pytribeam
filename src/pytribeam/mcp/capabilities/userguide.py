#!/usr/bin/python3
"""
Userguide Capabilities
======================

A tier 0 tool that returns a pytribeam userguide page as text. The same pages
are also served as MCP resources (``pytribeam.mcp.docs``), but not every
client lets the model read resources; this tool is the fallback that works in
any client. Both read through ``pytribeam.mcp.docs``, so they always agree.

Reads only files that ship with pytribeam; never touches the microscope.
"""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError

from pytribeam.mcp import docs

TIER = 0


def register(add, config, connection) -> None:
    """Register this module's tools."""
    pages = {page.name: page for page in docs.PAGES}

    def read_userguide(page: str = "reference_frame") -> dict:
        """Return a page of the pytribeam userguide as markdown text.

        Pages: "reference_frame", the reference frame conventions: the RAW
        stage axes and their directions, pre-tilt and rotation_side, imaging
        quadrants, and the image and patterning coordinate systems. Read it
        before moving the stage or giving positions in an image, if you have
        not already read the resource of the same content (its ``uri``).

        Figures are omitted; their captions are kept. Reads files only;
        touches no hardware.
        """
        if page not in pages:
            raise ToolError(
                f"No userguide page {page!r}. Pages: {', '.join(sorted(pages))}."
            )
        chosen = pages[page]
        return {
            "page": chosen.name,
            "title": chosen.title,
            "uri": chosen.uri,
            "text": docs.read(chosen),
        }

    add(read_userguide, read_only=True, uses_microscope=False)
