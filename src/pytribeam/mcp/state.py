from dataclasses import dataclass, field
from threading import RLock
from typing import Optional

import pytribeam.types as tbt


@dataclass
class MCPRuntime:
    """
    Shared runtime state for the pytribeam MCP server.
    """

    microscope: Optional[tbt.Microscope] = None
    lock: RLock = field(default_factory=RLock)
    host: Optional[str] = None
    port: Optional[int] = None

    def connect(self, host: str, port: Optional[int] = None) -> str:
        """
        Connect to the microscope and retain the live connection.
        """
        microscope = tbt.Microscope()

        if port is None:
            microscope.connect(host)
            endpoint = host
        else:
            microscope.connect(f"{host}:{port}")
            endpoint = f"{host}:{port}"

        self.microscope = microscope
        self.host = host
        self.port = port
        return f"Connected to microscope at {endpoint}"

    def disconnect(self) -> str:
        """
        Disconnect from the microscope if possible.
        """
        if self.microscope is None:
            return "Microscope was not connected."

        try:
            if hasattr(self.microscope, "disconnect"):
                self.microscope.disconnect()
        finally:
            self.microscope = None
            self.host = None
            self.port = None

        return "Microscope disconnected."

    def require_microscope(self) -> tbt.Microscope:
        """
        Return the live microscope connection or raise.
        """
        if self.microscope is None:
            raise RuntimeError(
                "Microscope is not connected. Call microscope_connect first."
            )
        return self.microscope
