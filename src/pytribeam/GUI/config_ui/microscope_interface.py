"""Microscope communication interface.

This module provides an abstraction layer for microscope communication,
separating hardware interaction from UI code.
"""

from typing import Optional, Dict, Tuple

import pytribeam.factory as factory
import pytribeam.laser as laser
import pytribeam.types as tbt
import pytribeam.utilities as ut
from pytribeam.GUI.common.errors import MicroscopeConnectionError
from pytribeam.constants import Conversions


class MicroscopeInterface:
    """Interface for microscope communication.

    This class abstracts microscope operations and provides a clean API
    for the GUI to interact with hardware. It handles connection management
    and provides context manager support for automatic cleanup.

    Attributes:
        host: Connection host address
        port: Connection port
        is_connected: Whether microscope is currently connected
    """

    def __init__(self, host: str = "localhost", port: str = ""):
        """Initialize microscope interface.

        Args:
            host: Microscope connection host (default: 'localhost')
            port: Microscope connection port (default: '')
        """
        self.host = host
        self.port = port
        self._microscope: Optional[tbt.Microscope] = None

    @property
    def is_connected(self) -> bool:
        """Check if microscope is connected."""
        return self._microscope is not None

    @property
    def microscope(self) -> Optional[tbt.Microscope]:
        """Get microscope object (read-only access)."""
        return self._microscope

    def __enter__(self):
        """Context manager entry - connect to microscope."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - disconnect from microscope."""
        self.disconnect()
        return False

    def connect(self):
        """Establish connection to microscope.

        Raises:
            MicroscopeConnectionError: If connection fails
        """
        if self.is_connected:
            return  # Already connected

        try:
            self._microscope = tbt.Microscope()
            ut.connect_microscope(
                self._microscope,
                quiet_output=True,
                connection_host=self.host,
                connection_port=self.port,
            )
        except ConnectionError as e:
            self._microscope = None
            raise MicroscopeConnectionError(
                f"Failed to connect to microscope at {self.host}:{self.port}"
            ) from e

    def disconnect(self):
        """Close microscope connection."""
        if self._microscope is not None:
            try:
                ut.disconnect_microscope(self._microscope)
            except Exception:
                pass  # Ignore errors during disconnect
            finally:
                self._microscope = None

    def ensure_connected(self):
        """Ensure microscope is connected, raise if not.

        Raises:
            MicroscopeConnectionError: If not connected
        """
        if not self.is_connected:
            raise MicroscopeConnectionError(
                "Not connected to microscope. Call connect() first."
            )

    def get_stage_position(self) -> tbt.StagePositionUser:
        """Get current stage position.

        Returns:
            Current stage position with x, y, z, r, t

        Raises:
            MicroscopeConnectionError: If not connected or operation fails
        """
        self.ensure_connected()

        try:
            return factory.active_stage_position_settings(self._microscope)
        except Exception as e:
            raise MicroscopeConnectionError("Failed to get stage position") from e

    def get_working_distances(self) -> Dict[str, float]:
        """Get current electron and ion beam working distances.

        Returns:
            Dictionary with 'electron_wd_mm' and 'ion_wd_mm' keys

        Raises:
            MicroscopeConnectionError: If not connected or operation fails
        """
        self.ensure_connected()

        try:
            electron_wd = (
                ut.beam_type(
                    tbt.ElectronBeam(tbt.BeamSettings()), self._microscope
                ).working_distance.value
                * Conversions.M_TO_MM
            )

            ion_wd = (
                ut.beam_type(
                    tbt.IonBeam(tbt.BeamSettings()), self._microscope
                ).working_distance.value
                * Conversions.M_TO_MM
            )

            return {
                "electron_wd_mm": electron_wd,
                "ion_wd_mm": ion_wd,
            }
        except Exception as e:
            raise MicroscopeConnectionError("Failed to get working distances") from e

    def get_stage_info(self) -> Dict[str, any]:
        """Get comprehensive stage information.

        Returns:
            Dictionary with position and working distance info

        Raises:
            MicroscopeConnectionError: If not connected or operation fails
        """
        self.ensure_connected()

        try:
            position = self.get_stage_position()
            wds = self.get_working_distances()

            return {
                "x_mm": position.x_mm,
                "y_mm": position.y_mm,
                "z_mm": position.z_mm,
                "r_deg": position.r_deg,
                "t_deg": position.t_deg,
                "electron_wd_mm": wds["electron_wd_mm"],
                "ion_wd_mm": wds["ion_wd_mm"],
            }
        except MicroscopeConnectionError:
            raise
        except Exception as e:
            raise MicroscopeConnectionError("Failed to get stage info") from e

    def get_imaging_settings(self) -> tbt.ImageSettings:
        """Get current imaging settings.

        Returns:
            Current image settings including beam, detector, scan parameters

        Raises:
            MicroscopeConnectionError: If not connected or operation fails
        """
        self.ensure_connected()

        try:
            return factory.active_image_settings(self._microscope)
        except Exception as e:
            raise MicroscopeConnectionError("Failed to get imaging settings") from e

    def get_laser_state(self) -> Dict:
        """Get current laser settings.

        Returns:
            Dictionary of laser state parameters

        Raises:
            MicroscopeConnectionError: If operation fails
        """
        try:
            laser_state = factory.active_laser_state()
            return laser.laser_state_to_db(laser_state)
        except Exception as e:
            raise MicroscopeConnectionError("Failed to get laser state") from e

    def test_connection(self) -> Tuple[bool, str]:
        """Test microscope connection.

        Returns:
            Tuple of (success, message)
        """
        try:
            self.connect()
            self.disconnect()
            return True, "Connection successful"
        except MicroscopeConnectionError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Unexpected error: {e}"


def check_device_connections() -> Dict[str, bool]:
    """Check connections to peripheral devices (EDS, EBSD, laser).

    Returns:
        Dictionary mapping device names to connection status

    Note:
        This doesn't require a MicroscopeInterface instance as it
        checks device connections directly.
    """
    try:
        status = laser._device_connections()
        return status
    except Exception as e:
        return {"error": str(e)}


def format_stage_info(stage_info: Dict[str, float]) -> str:
    """Format stage information for display.

    Args:
        stage_info: Dictionary from get_stage_info()

    Returns:
        Formatted multi-line string
    """
    return (
        f"EBeam WD = {stage_info['electron_wd_mm']:.5f} mm\n"
        f"IBeam WD = {stage_info['ion_wd_mm']:.5f} mm\n"
        f"\tX = {stage_info['x_mm']:.5f} mm\n"
        f"\tY = {stage_info['y_mm']:.5f} mm\n"
        f"\tZ = {stage_info['z_mm']:.5f} mm\n"
        f"\tR = {stage_info['r_deg']:.5f} °\n"
        f"\tT = {stage_info['t_deg']:.5f} °"
    )
