"""
Bruker EDS HDF5 Output
======================

Writes one Bruker EDS map, with its settings and provenance, to its own HDF5
file. A serial-sectioning experiment therefore produces one file per slice.

Layout::

    /                         attrs: schema_version, vendor, technique,
                                     run_name, slice_number, timestamp,
                                     bcf_path, image_path, elapsed_s,
                                     errors (JSON list of problems noted
                                     during collection; empty when none)
    /settings                 attrs: json (workflow settings, password removed)
    /esprit                   attrs: query_info
    /eds/maps/<NN>            dataset (height x width) per element, attrs:
                              element_index, atomic_number, line,
                              energy_keV, width
                              (an element whose readback failed is a group
                              with an ``error`` attr and no data)

The native ``.bcf`` HyperMap file is still saved by ESPRIT; its path is
recorded here.
"""

import json
from pathlib import Path
from typing import Any, NamedTuple, Optional, Sequence, Union

import h5py
import numpy as np

from pytribeam.external_oem.bruker.types import (
    BrukerEDSElementMapSetting,
    BrukerEDSWorkflowSettings,
)

#: Version of the layout above. Bump on any incompatible change.
SCHEMA_VERSION = "1.0"

#: Session fields never written to disk.
_REDACTED_SESSION_FIELDS = ("password",)


class BrukerElementMap(NamedTuple):
    """One element's readback: data on success, the error otherwise."""

    element_index: int
    element: BrukerEDSElementMapSetting
    data: Optional[np.ndarray] = None
    error: Optional[str] = None


def _plain(value: Any) -> Any:
    """Convert named tuples and sequences to JSON-serializable values."""
    if hasattr(value, "_asdict"):
        return {key: _plain(item) for key, item in value._asdict().items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def settings_record(settings: BrukerEDSWorkflowSettings) -> dict:
    """Return the workflow settings as a dictionary, with credentials removed."""
    record = _plain(settings)
    for key in _REDACTED_SESSION_FIELDS:
        record["session"].pop(key, None)
    return record


def write_eds_map_h5(
    path: Union[str, Path],
    *,
    settings: BrukerEDSWorkflowSettings,
    element_maps: Sequence[BrukerElementMap],
    slice_number: Optional[int],
    timestamp: str,
    query_info: str = "",
    bcf_path: Optional[str] = None,
    image_path: Optional[str] = None,
    elapsed_s: Optional[float] = None,
    errors: Sequence[str] = (),
) -> Path:
    """
    Write one EDS map to a new HDF5 file.

    Parameters
    ----------
    path : str or Path
        Output file. Parent folders are created. An existing file is refused,
        so a map is never silently overwritten.
    settings : BrukerEDSWorkflowSettings
        Settings the map was collected with.
    element_maps : sequence of BrukerElementMap
        Readback for each requested element, in profile order.
    slice_number : int, optional
        Slice the map belongs to.
    timestamp : str
        Collection timestamp.
    query_info : str, optional
        ESPRIT ``QueryInfo`` text, for provenance.
    bcf_path, image_path : str, optional
        Native files ESPRIT saved for this map.
    elapsed_s : float, optional
        Collection time.
    errors : sequence of str, optional
        Problems noted during collection, such as a missing ``.bcf`` file.

    Returns
    -------
    Path
        The file written.

    Raises
    ------
    FileExistsError
        If ``path`` already exists.
    """
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing map file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)

    with h5py.File(path, "w") as file:
        root = file.attrs
        root["schema_version"] = SCHEMA_VERSION
        root["vendor"] = "Bruker"
        root["technique"] = "EDS"
        root["run_name"] = settings.output.run_name
        root["slice_number"] = -1 if slice_number is None else int(slice_number)
        root["timestamp"] = timestamp
        root["bcf_path"] = bcf_path or ""
        root["image_path"] = image_path or ""
        root["elapsed_s"] = float("nan") if elapsed_s is None else float(elapsed_s)
        root["errors"] = json.dumps(list(errors))

        file.create_group("settings").attrs["json"] = json.dumps(
            settings_record(settings)
        )
        file.create_group("esprit").attrs["query_info"] = query_info or ""

        maps = file.create_group("eds").create_group("maps")
        for element_map in element_maps:
            name = f"{element_map.element_index:02d}"
            if element_map.data is None:
                node = maps.create_group(name)
                node.attrs["error"] = element_map.error or "no data"
            else:
                node = maps.create_dataset(
                    name, data=np.asarray(element_map.data), compression="gzip"
                )
            element = element_map.element
            node.attrs["element_index"] = int(element_map.element_index)
            node.attrs["atomic_number"] = int(element.atomic_number)
            node.attrs["line"] = element.line
            node.attrs["energy_keV"] = float(element.energy_keV)
            node.attrs["width"] = float(element.width)

    return path
