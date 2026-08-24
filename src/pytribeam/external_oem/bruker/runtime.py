"""Runtime preflight helpers for Bruker ESPRIT API usage."""

from pathlib import Path
from typing import Dict

from pytribeam.external_oem.bruker.types import BrukerSessionSettings


REQUIRED_ESPRIT_DLL = "Bruker.API.Esprit64.dll"
OPTIONAL_LOGGING_DLL = "Bruker.API.Logging64.dll"


def validate_bruker_runtime_environment(
    session_settings: BrukerSessionSettings,
    require_logging_dll: bool = False,
) -> Dict[str, str]:
    """Validate local Bruker DLL availability before loading with ctypes.

    This is intentionally separate from YAML schema parsing because documentation,
    CI, and unit-test environments may parse Bruker configs without local Bruker
    DLLs installed. Call this from operator-facing scripts/tools before creating a
    ``BrukerSession``.

    Parameters
    ----------
    session_settings : BrukerSessionSettings
        Bruker session settings containing the user-configurable DLL directory.
    require_logging_dll : bool
        If True, require ``Bruker.API.Logging64.dll`` in addition to the main
        ESPRIT API DLL. By default this DLL is treated as optional.

    Returns
    -------
    dict
        Paths to discovered DLL files.

    Raises
    ------
    FileNotFoundError
        If the DLL directory or required DLLs are missing.
    """
    dll_dir = Path(session_settings.dll_dir)
    if not dll_dir.is_dir():
        raise FileNotFoundError(
            "Bruker DLL directory does not exist or is not a directory: "
            f"{dll_dir}. Python must have local Bruker API DLLs because ctypes "
            "loads them in-process."
        )

    esprit_dll = dll_dir / REQUIRED_ESPRIT_DLL
    if not esprit_dll.is_file():
        raise FileNotFoundError(
            f"Required Bruker API DLL not found: {esprit_dll}. "
            "Check session.dll_dir in the Bruker YAML/config."
        )

    logging_dll = dll_dir / OPTIONAL_LOGGING_DLL
    if require_logging_dll and not logging_dll.is_file():
        raise FileNotFoundError(
            f"Required Bruker logging DLL not found: {logging_dll}."
        )

    result = {
        "dll_dir": str(dll_dir),
        "esprit_dll": str(esprit_dll),
    }
    if logging_dll.is_file():
        result["logging_dll"] = str(logging_dll)
    return result
