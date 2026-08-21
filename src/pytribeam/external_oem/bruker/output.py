"""
Bruker EDS Output Directory Management
=======================================

Handles output directory creation and file naming conventions for
Bruker EDS mapping workflows.

Directory naming convention:
    Standalone:     {run_name}_{timestamp}/
    With slice:     {run_name}_Slice_{NNNN}_{timestamp}/
    With repeat:    {run_name}_Slice_{NNNN}_{R}_{timestamp}/

Where:
    NNNN = zero-padded slice number (4 digits)
    R    = repeat index (only appended when > 0)
    timestamp = YYYYMMDD_HHMMSS

File naming within a run directory:
    {run_name}_{timestamp}.bcf          - HyperMap data file
    {run_name}_{timestamp}.bmp          - Overview map image
    {run_name}_{timestamp}_config.yml   - Copy of input config
    {run_name}_{timestamp}.log          - Text log
    {run_name}_{timestamp}_summary.json - Structured result summary
    readback/                           - Element map readback directory
        {prefix}_element_{N}_Z{Z}_{line}.npy
        {prefix}_readback_summary.json
"""

from datetime import datetime
from pathlib import Path
from typing import Dict

from pytribeam.external_oem.bruker.types import BrukerEDSOutputSettings


def make_run_dir_name(output: BrukerEDSOutputSettings, stamp: str) -> str:
    """Construct the run directory name from output settings.

    Parameters
    ----------
    output : BrukerEDSOutputSettings
        Output configuration including run_name, slice_number, repeat_index.
    stamp : str
        Timestamp string (typically YYYYMMDD_HHMMSS).

    Returns
    -------
    str
        The directory name (not full path).

    Examples
    --------
    >>> # Standalone (no slice)
    "eds_map_20260821_131304"

    >>> # Slice 1, first attempt
    "eds_map_Slice_0001_20260821_131304"

    >>> # Slice 1, second attempt (repeat_index=1)
    "eds_map_Slice_0001_1_20260821_131304"
    """
    parts = [output.run_name]

    if output.slice_number is not None:
        parts.append(f"Slice_{output.slice_number:04d}")
        if output.repeat_index is not None and output.repeat_index > 0:
            parts.append(str(output.repeat_index))

    parts.append(stamp)

    return "_".join(parts)


def make_run_paths(output: BrukerEDSOutputSettings, stamp: str) -> Dict[str, Path]:
    """Create the full run directory structure and return path dictionary.

    Parameters
    ----------
    output : BrukerEDSOutputSettings
        Output configuration.
    stamp : str
        Timestamp string.

    Returns
    -------
    dict
        Dictionary with keys: run_dir, bcf_path, bmp_path, log_path,
        config_copy_path, readback_dir, summary_json_path.
    """
    dir_name = make_run_dir_name(output, stamp)
    run_dir = Path(output.output_dir) / dir_name
    run_dir.mkdir(parents=True, exist_ok=True)

    # File prefix uses run_name + slice info (without timestamp for readability)
    file_prefix = make_file_prefix(output)

    return {
        "run_dir": run_dir,
        "bcf_path": run_dir / f"{file_prefix}.bcf",
        "bmp_path": run_dir / f"{file_prefix}.{output.image_format}",
        "log_path": run_dir / f"{file_prefix}.log",
        "config_copy_path": run_dir / f"{file_prefix}_config.yml",
        "readback_dir": run_dir / "readback",
        "summary_json_path": run_dir / f"{file_prefix}_summary.json",
    }


def make_file_prefix(output: BrukerEDSOutputSettings) -> str:
    """Construct the file prefix for output files within a run directory.

    This is the base name used for .bcf, .bmp, .log, etc. It includes
    slice/repeat info but NOT the timestamp (since the directory already
    contains the timestamp for uniqueness).

    Parameters
    ----------
    output : BrukerEDSOutputSettings
        Output configuration.

    Returns
    -------
    str
        File prefix string.

    Examples
    --------
    >>> # Standalone
    "eds_map"

    >>> # Slice 5, first attempt
    "eds_map_Slice_0005"

    >>> # Slice 5, repeat 2
    "eds_map_Slice_0005_2"
    """
    parts = [output.run_name]

    if output.slice_number is not None:
        parts.append(f"Slice_{output.slice_number:04d}")
        if output.repeat_index is not None and output.repeat_index > 0:
            parts.append(str(output.repeat_index))

    return "_".join(parts)


def now_stamp() -> str:
    """Return current timestamp string in YYYYMMDD_HHMMSS format."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")
