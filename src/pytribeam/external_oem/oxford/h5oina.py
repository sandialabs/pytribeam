"""Inspect and compare .h5oina files (Oxford's HDF5-based export format).

Used to check exports and to diagnose files that AZtecCrystal refuses to open:

    python -m oxford_aztec.h5oina ours.h5oina --reference manual_export.h5oina

Requires ``h5py`` (``pip install h5py``) for anything beyond the HDF5 signature check.

The checks are deliberately generic (walk the whole tree). Known H5OINA layout:
root datasets ``Format Version`` / ``Manufacturer`` / ``Software Version``, numbered
slice groups (``1``, ``2``...) containing technique groups (``EBSD``, ``EDS``,
``Electron Image``...), each with ``Data`` and ``Header`` subgroups.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"
#: HDF5 allows the superblock at 0, 512, 1024, 2048, ... (user block before it).
_SIG_OFFSETS = (0, 512, 1024, 2048, 4096, 8192)
ROOT_KEYS = ("Format Version", "Manufacturer", "Software Version")


def is_hdf5(path: str) -> bool:
    """True if the file carries an HDF5 superblock signature (no h5py needed)."""
    try:
        with open(path, "rb") as f:
            for off in _SIG_OFFSETS:
                f.seek(off)
                if f.read(8) == HDF5_SIGNATURE:
                    return True
    except OSError:
        pass
    return False


def wait_for_stable_file(
    path: str, timeout: float = 60.0, settle_s: float = 1.0, poll_s: float = 0.25
) -> bool:
    """Wait until ``path`` exists and its size stops changing for ``settle_s``.
    Returns False on timeout. Exports can report "finished" slightly before the
    writer has closed the file."""
    deadline = time.monotonic() + timeout
    last, since = None, None
    while time.monotonic() < deadline:
        try:
            size = os.path.getsize(path)
        except OSError:
            size = None
        if size is not None and size == last and size > 0:
            if since is not None and time.monotonic() - since >= settle_s:
                return True
        else:
            last, since = size, time.monotonic()
        time.sleep(poll_s)
    return False


@dataclass
class DatasetInfo:
    shape: Tuple[int, ...]
    dtype: str


@dataclass
class H5oinaSummary:
    path: str
    size_bytes: int = 0
    is_hdf5: bool = False
    format_version: Optional[str] = None
    manufacturer: Optional[str] = None
    software_version: Optional[str] = None
    #: slice name -> technique group names, e.g. {"1": ["EBSD", "EDS", "Electron Image"]}
    slices: Dict[str, List[str]] = field(default_factory=dict)
    #: Every dataset in the file: "/1/EBSD/Data/Phase" -> DatasetInfo
    datasets: Dict[str, DatasetInfo] = field(default_factory=dict)
    #: Selected small header values, e.g. "/1/EBSD/Header/X Cells" -> 256
    header_values: Dict[str, object] = field(default_factory=dict)
    #: Fraction of EBSD points with a non-zero phase (None if no Phase dataset)
    ebsd_indexed_fraction: Optional[float] = None
    #: EBSD pattern datasets: "/1/EBSD/Data/Processed Patterns" -> DatasetInfo (N, height, width)
    patterns: Dict[str, DatasetInfo] = field(default_factory=dict)
    problems: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def has_ebsd(self) -> bool:
        return any("EBSD" in t for t in self.slices.values())

    @property
    def has_patterns(self) -> bool:
        return bool(self.patterns)

    @property
    def looks_loadable(self) -> bool:
        return self.is_hdf5 and not self.problems

    def report(self) -> str:
        lines = [
            "%s (%d bytes)" % (self.path, self.size_bytes),
            "  HDF5: %s | format %s | %s | software %s"
            % (
                self.is_hdf5,
                self.format_version,
                self.manufacturer,
                self.software_version,
            ),
            "  slices: %s" % (self.slices or "none"),
        ]
        for k in sorted(self.header_values):
            lines.append("  %-45s %s" % (k, self.header_values[k]))
        if self.ebsd_indexed_fraction is not None:
            lines.append(
                "  EBSD indexed fraction: %.1f%%" % (100 * self.ebsd_indexed_fraction)
            )
        if self.has_ebsd:
            if self.patterns:
                for k, v in self.patterns.items():
                    lines.append("  patterns: %s %s %s" % (k, v.shape, v.dtype))
            else:
                lines.append("  patterns: none saved")
        lines += ["  PROBLEM: " + p for p in self.problems]
        lines += ["  warning: " + w for w in self.warnings]
        return "\n".join(lines)


def _text(v):
    """Decode HDF5 scalar/array string values to str."""
    try:
        import numpy as np

        if isinstance(v, np.ndarray):
            if v.size == 0:
                return ""
            v = v.ravel()[0]
    except ImportError:  # pragma: no cover
        pass
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return str(v)


def _root_value(f, key):
    if key in f:
        try:
            return _text(f[key][()])
        except Exception:
            return None
    if key in f.attrs:
        return _text(f.attrs[key])
    return None


_HEADER_KEYS = (
    "X Cells",
    "Y Cells",
    "X Step",
    "Y Step",
    "Beam Voltage",
    "Magnification",
    "Project File",
    "Site Name",
    "Specimen Orientation Euler",
    "Acquisition Speed",
    "Pattern Height",
    "Pattern Width",
)
#: Preferred pattern dataset; others matching ``_is_pattern_path`` are also reported.
PROCESSED_PATTERNS = "Processed Patterns"


def _is_pattern_path(path: str, info: "DatasetInfo") -> bool:
    return (
        "/EBSD/Data/" in path
        and "pattern" in path.rsplit("/", 1)[-1].lower()
        and len(info.shape) == 3
    )


def inspect_h5oina(path: str) -> H5oinaSummary:
    """Summarise an .h5oina file and flag things that would stop AZtecCrystal loading it."""
    s = H5oinaSummary(path=path)
    if not os.path.isfile(path):
        s.problems.append("file does not exist")
        return s
    s.size_bytes = os.path.getsize(path)
    s.is_hdf5 = is_hdf5(path)
    if not s.is_hdf5:
        s.problems.append(
            "not an HDF5 file (no HDF5 signature) - empty, truncated, or a different format"
        )
        return s
    try:
        import h5py
        import numpy as np
    except ImportError:
        s.warnings.append(
            "h5py not installed: only the HDF5 signature was checked (pip install h5py)"
        )
        return s

    try:
        f = h5py.File(path, "r")
    except Exception as e:
        s.problems.append(
            "HDF5 file cannot be opened: %s (truncated, or still being written/locked?)"
            % e
        )
        return s
    with f:
        s.format_version = _root_value(f, "Format Version")
        s.manufacturer = _root_value(f, "Manufacturer")
        s.software_version = _root_value(f, "Software Version")
        for k in ROOT_KEYS:
            if _root_value(f, k) is None:
                s.problems.append("missing root entry %r" % k)

        for name, obj in f.items():
            if isinstance(obj, h5py.Group) and name.isdigit():
                s.slices[name] = sorted(obj.keys())
        if not s.slices:
            s.problems.append("no numbered slice groups (expected '/1/...')")

        def visit(name, obj):
            if isinstance(obj, h5py.Dataset):
                p = "/" + name
                s.datasets[p] = DatasetInfo(tuple(obj.shape), str(obj.dtype))
                leaf = name.rsplit("/", 1)[-1]
                if "/Header/" in p and leaf in _HEADER_KEYS and obj.size <= 16:
                    try:
                        v = obj[()]
                        s.header_values[p] = (
                            _text(v)
                            if obj.dtype.kind in "SOU"
                            else (v.tolist() if hasattr(v, "tolist") else v)
                        )
                    except Exception:
                        pass

        f.visititems(visit)

        if not s.has_ebsd:
            s.warnings.append(
                "no EBSD group in any slice - AZtecCrystal needs EBSD data "
                "(is this the EDS-only export?)"
            )
        for sl, techs in s.slices.items():
            if "EBSD" not in techs:
                continue
            base = "/%s/EBSD" % sl
            for sub in ("Data", "Header"):
                if base + "/" + sub not in f:
                    s.problems.append("%s/%s group missing" % (base, sub))
            data = base + "/Data"
            if data in f:
                lengths = {
                    k: v.shape[0]
                    for k, v in s.datasets.items()
                    if k.startswith(data + "/")
                    and v.shape
                    and not _is_pattern_path(k, v)
                }
                if not lengths:
                    s.problems.append("%s has no datasets (empty map)" % data)
                elif len(set(lengths.values())) > 1:
                    s.warnings.append(
                        "EBSD datasets have differing lengths: %s" % lengths
                    )
                xc = s.header_values.get(base + "/Header/X Cells")
                yc = s.header_values.get(base + "/Header/Y Cells")
                try:
                    n_expected = int(_scalar(xc)) * int(_scalar(yc))
                    n = max(lengths.values()) if lengths else 0
                    if lengths and n != n_expected:
                        s.problems.append(
                            "EBSD has %d points but header says %s x %s = %d"
                            % (n, xc, yc, n_expected)
                        )
                except (TypeError, ValueError):
                    pass
                if data + "/Phase" in f:
                    ph = np.asarray(f[data + "/Phase"][()])
                    if ph.size:
                        s.ebsd_indexed_fraction = float(np.count_nonzero(ph)) / ph.size
                        if s.ebsd_indexed_fraction == 0:
                            s.warnings.append(
                                "no EBSD point is indexed (all Phase == 0) - typical of "
                                "simulated or unsolved data; AZtecCrystal may reject it"
                            )
            for p, info in s.datasets.items():
                if p.startswith(data + "/") and _is_pattern_path(p, info):
                    s.patterns[p] = info
                    n_pts = max(
                        (
                            v.shape[0]
                            for k, v in s.datasets.items()
                            if k.startswith(data + "/")
                            and v.shape
                            and k not in s.patterns
                        ),
                        default=None,
                    )
                    if n_pts is not None and info.shape[0] != n_pts:
                        s.warnings.append(
                            "%s holds %d patterns but the map has %d points"
                            % (p, info.shape[0], n_pts)
                        )
                    ph = s.header_values.get(base + "/Header/Pattern Height")
                    pw = s.header_values.get(base + "/Header/Pattern Width")
                    try:
                        if (
                            ph is not None
                            and pw is not None
                            and (int(_scalar(ph)), int(_scalar(pw)))
                            != tuple(info.shape[1:])
                        ):
                            s.warnings.append(
                                "%s is %sx%s but header says %sx%s"
                                % (
                                    p,
                                    info.shape[1],
                                    info.shape[2],
                                    _scalar(ph),
                                    _scalar(pw),
                                )
                            )
                    except (TypeError, ValueError):
                        pass
            if base + "/Header/Phases" in f and len(f[base + "/Header/Phases"]) == 0:
                s.warnings.append(
                    "%s/Header/Phases is empty (no phases defined)" % base
                )
    return s


def find_ebsp_files(
    project_file_or_dir: str, since: Optional[float] = None
) -> List[Tuple[str, int, float]]:
    """Oxford binary pattern files (*.ebsp) saved under an AZtec project folder.

    AZtec writes these when pattern saving is on, independently of any export.
    Returns [(path, size_bytes, mtime)] newest first; ``since`` (epoch seconds)
    keeps only files modified after it.
    """
    root = project_file_or_dir
    if os.path.isfile(root) or root.lower().endswith((".oip", ".oipx")):
        root = os.path.dirname(root)
    out = []
    for dirpath, _, files in os.walk(root):
        for name in files:
            if name.lower().endswith(".ebsp"):
                p = os.path.join(dirpath, name)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if since is None or st.st_mtime >= since:
                    out.append((p, st.st_size, st.st_mtime))
    return sorted(out, key=lambda t: -t[2])


class PatternReader:
    """Read EBSD patterns from an .h5oina file without loading them all.

        with PatternReader("map.h5oina") as pr:
            print(pr.count, pr.pattern_shape, pr.dtype)
            p = pr[0]                      # one pattern (height, width)
            p = pr.at(col=10, row=3)       # by map position
            for start, block in pr.batches(512):
                ...

    ``dataset`` defaults to "Processed Patterns", else the first pattern dataset found.
    """

    def __init__(self, path: str, slice_name: str = "1", dataset: Optional[str] = None):
        import h5py

        self.path = path
        self._f = h5py.File(path, "r")
        base = "/%s/EBSD" % slice_name
        if base not in self._f:
            self._f.close()
            raise KeyError("%s has no %s group" % (path, base))
        data = self._f[base + "/Data"]
        candidates = [
            k
            for k, v in data.items()
            if isinstance(v, h5py.Dataset) and v.ndim == 3 and "pattern" in k.lower()
        ]
        name = dataset or (
            PROCESSED_PATTERNS
            if PROCESSED_PATTERNS in candidates
            else (candidates[0] if candidates else None)
        )
        if name is None or name not in data:
            self._f.close()
            raise KeyError(
                "%s has no EBSD pattern dataset (found: %s). Was pattern saving enabled "
                "in AZtec for this map?" % (path, candidates or "none")
            )
        self.dataset_name = name
        self.available = candidates
        self._ds = data[name]
        self._data = data
        hdr = self._f[base + "/Header"] if base + "/Header" in self._f else {}
        self.x_cells = int(_scalar(_val(hdr, "X Cells"))) if "X Cells" in hdr else None
        self.y_cells = int(_scalar(_val(hdr, "Y Cells"))) if "Y Cells" in hdr else None

    @property
    def count(self) -> int:
        return int(self._ds.shape[0])

    @property
    def pattern_shape(self) -> Tuple[int, int]:
        return tuple(int(x) for x in self._ds.shape[1:])

    @property
    def dtype(self):
        return self._ds.dtype

    @property
    def nbytes(self) -> int:
        return int(self._ds.size * self._ds.dtype.itemsize)

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        return self._ds[index]

    def index_of(self, col: int, row: int) -> int:
        """Point index for map column/row. Assumes raster order (X fastest), which is
        cross-checked against the X/Y datasets when they exist."""
        if self.x_cells is None:
            raise ValueError("header has no X Cells; cannot map col/row to an index")
        if not (
            0 <= col < self.x_cells
            and (self.y_cells is None or 0 <= row < self.y_cells)
        ):
            raise IndexError(
                "col/row (%d, %d) outside the %sx%s map"
                % (col, row, self.x_cells, self.y_cells)
            )
        # Raster order with X fastest is assumed; refuse if the X/Y datasets say otherwise.
        if (
            "X" in self._data
            and "Y" in self._data
            and self.x_cells > 1
            and self._data["X"].shape[0] > 1
        ):
            x, y = self._data["X"][:2], self._data["Y"][:2]
            if float(x[1]) == float(x[0]) and float(y[1]) != float(y[0]):
                raise ValueError(
                    "points are stored Y-fastest, not raster X-fastest; "
                    "locate patterns via the X/Y datasets instead"
                )
        return row * self.x_cells + col

    def at(self, col: int, row: int):
        return self[self.index_of(col, row)]

    def batches(self, size: int = 1024):
        """Yield (start_index, array[n, h, w]) blocks."""
        for start in range(0, self.count, size):
            yield start, self._ds[start : start + size]

    def save_png(self, index: int, path: str) -> str:
        from ._png import save_gray8

        return save_gray8(self[index], path)

    def close(self):
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _val(group, key):
    v = group[key][()]
    return v.tolist() if hasattr(v, "tolist") else v


def _scalar(v):
    if isinstance(v, (list, tuple)):
        return v[0]
    return v


def compare_h5oina(path: str, reference: str) -> List[str]:
    """Structural differences between ``path`` and a known-good ``reference`` file
    (e.g. exported manually from the AZtec UI). Empty list = same structure."""
    a, b = inspect_h5oina(path), inspect_h5oina(reference)
    diffs = []
    for key in ("format_version", "manufacturer", "software_version"):
        va, vb = getattr(a, key), getattr(b, key)
        if va != vb:
            diffs.append("%s: %r vs reference %r" % (key, va, vb))
    if a.slices != b.slices:
        diffs.append("slices/techniques: %s vs reference %s" % (a.slices, b.slices))
    only_ref = sorted(set(b.datasets) - set(a.datasets))
    only_ours = sorted(set(a.datasets) - set(b.datasets))
    if only_ref:
        diffs.append("missing (present in reference): %s" % _clip(only_ref))
    if only_ours:
        diffs.append("extra (not in reference): %s" % _clip(only_ours))
    for p in sorted(set(a.datasets) & set(b.datasets)):
        da, db = a.datasets[p], b.datasets[p]
        if da.dtype != db.dtype or len(da.shape) != len(db.shape):
            diffs.append(
                "%s: %s %s vs reference %s %s"
                % (p, da.shape, da.dtype, db.shape, db.dtype)
            )
    return diffs


def _clip(items, n=25):
    return (
        items if len(items) <= n else items[:n] + ["... (%d more)" % (len(items) - n)]
    )


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Inspect .h5oina files; optionally compare to a reference."
    )
    ap.add_argument("files", nargs="+")
    ap.add_argument(
        "--reference", help="known-good .h5oina (e.g. exported manually from AZtec)"
    )
    args = ap.parse_args(argv)
    bad = 0
    for p in args.files:
        s = inspect_h5oina(p)
        print(s.report())
        bad += not s.looks_loadable
        if args.reference:
            diffs = compare_h5oina(p, args.reference)
            print(
                "  vs reference %s: %s"
                % (args.reference, "same structure" if not diffs else "")
            )
            for d in diffs:
                print("    - " + d)
        print()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
