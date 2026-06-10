import json
from typing import Any, Dict

from pytribeam.mcp.state import MCPRuntime
from pytribeam.mcp.image_tools import get_image_tool_definitions


class PyTriBeamMCPServer:
    """
    Thin MCP server wrapper for pytribeam.

    This class stores tool metadata and dispatches tool calls.
    Adapt the transport/SDK glue in this file to your installed MCP SDK version.
    """

    def __init__(self):
        self.runtime = MCPRuntime()
        self._tools = {}

        for tool in get_image_tool_definitions(self.runtime):
            self._tools[tool["name"]] = tool

    def list_tools(self) -> list[Dict[str, Any]]:
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["inputSchema"],
            }
            for tool in self._tools.values()
        ]

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self._tools:
            raise KeyError(f"Unknown tool '{name}'")

        handler = self._tools[name]["handler"]
        return handler(arguments)
