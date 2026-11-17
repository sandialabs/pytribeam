"""The only module that touches pythonnet / .NET.

``DotNetApi`` loads the AZtec Plugin assemblies and provides the small set of
conversion helpers the rest of the package relies on. ``simulator.SimulatedApi``
implements the same surface in pure Python, so every controller works unchanged
against either.

Interop rules this module encodes (verified against the shipped v6.1 DLLs):

* Return values typed as an interface (IAcquiredData, IAcquisitionRegion...) are
  wrapped by pythonnet 3 as that interface, hiding concrete members. Use
  ``impl(obj)`` (``__implementation__``) to reach the concrete object.
* .NET enums are constructed from ints with ``EnumType(int)``; ``int(e)`` reads them.
* ``Nullable<T>`` properties accept/return ``None``.
* Python lists do not convert to ``IEnumerable<T>``; build a ``List[T]``.
* ``float[]`` -> numpy is ~10x faster via ``Marshal.Copy`` than iterating.
"""
from __future__ import annotations

import logging
import os
import sys
import uuid
from typing import Iterable, Optional

from . import enums as py_enums
from .errors import DotNetUnavailableError
from .models import LineRegion, RectangleRegion

log = logging.getLogger(__name__)

MAIN_ASSEMBLY = "OINA.Plugin.AcquisitionClient"
NS = "OINA.Plugin.AcquisitionClient"

#: Searched in order when no dll_dir is given.
DEFAULT_DLL_DIRS = [
    r"C:\Program Files (x86)\Oxford Instruments NanoAnalysis\Plugin",
    r"C:\Program Files\Oxford Instruments NanoAnalysis\Plugin",
]
ENV_DLL_DIR = "AZTEC_PLUGIN_DIR"


def find_dll_dir(dll_dir=None) -> str:
    """Locate the folder containing OINA.Plugin.AcquisitionClient.dll.

    Order: explicit argument, $AZTEC_PLUGIN_DIR, the SDK default install folders.
    """
    candidates = []
    if dll_dir:
        candidates.append(dll_dir)
    if os.environ.get(ENV_DLL_DIR):
        candidates.append(os.environ[ENV_DLL_DIR])
    candidates.extend(DEFAULT_DLL_DIRS)
    for c in candidates:
        if os.path.isfile(os.path.join(c, MAIN_ASSEMBLY + ".dll")):
            return os.path.abspath(c)
    raise DotNetUnavailableError(
        "Could not find %s.dll. Looked in: %s. Pass dll_dir=... or set $%s."
        % (MAIN_ASSEMBLY, "; ".join(candidates), ENV_DLL_DIR)
    )


def net_message(exc: BaseException) -> str:
    """Best human-readable message for a .NET (or Python) exception, including
    inner exceptions (WCF faults and type-initializer errors hide the cause there)."""
    parts = []
    e = exc
    for _ in range(5):  # bounded walk of the InnerException chain
        if e is None:
            break
        msg = getattr(e, "Message", None) or str(e)
        msg = msg.strip().splitlines()[0] if msg.strip() else type(e).__name__
        if msg not in parts:
            parts.append(msg)
        e = getattr(e, "InnerException", None)
    return " -> ".join(parts) if parts else repr(exc)


class DotNetApi:
    """Gateway to the real AZtec Plugin assemblies via pythonnet."""

    name = "dotnet"
    #: The real API talks TCP; the session does a fast port pre-check first.
    uses_network = True

    def __init__(self, dll_dir=None, runtime=None):
        self.dll_dir = find_dll_dir(dll_dir)
        self._load_runtime(runtime)
        try:
            import clr  # noqa: F401  (pythonnet)
            if self.dll_dir not in sys.path:
                sys.path.append(self.dll_dir)  # pythonnet resolves dependencies (log4net) from sys.path
            clr.AddReference(MAIN_ASSEMBLY)
            import System
            from System.Runtime.InteropServices import Marshal
            import OINA.Plugin.AcquisitionClient as root
        except DotNetUnavailableError:
            raise
        except Exception as e:  # ImportError, FileNotFoundException, BadImageFormat...
            raise DotNetUnavailableError(
                "Failed to load %s from %s: %s" % (MAIN_ASSEMBLY, self.dll_dir, net_message(e))
            ) from e

        self._clr = clr
        self.System = System
        self._Marshal = Marshal
        self._root = root
        self.Session = root.Session
        self._RectangleRegion = root.RectangleRegion
        self._LineRegion = root.LineRegion
        self._Logger = root.Logger
        self._LoggingLevel = root.LoggingLevel
        self._enum_types = {py: self._resolve(net) for py, net in py_enums.NET_ENUM_TYPES.items()}
        self._float_array_type = System.Array[System.Single]
        log.info("Loaded %s from %s", MAIN_ASSEMBLY, self.dll_dir)

    # -- loading --------------------------------------------------------------

    @staticmethod
    def _load_runtime(runtime):
        """Select the CLR before ``import clr``. The plugin is WCF on .NET Framework
        4.5.2, so on Windows the default ("netfx") is the right choice. If the
        host application already loaded pythonnet, that runtime is reused."""
        if "clr" in sys.modules:
            return
        try:
            import pythonnet
        except ImportError as e:
            raise DotNetUnavailableError(
                "pythonnet is not installed (pip install 'pythonnet>=3,<4')."
            ) from e
        if runtime:
            try:
                if isinstance(runtime, str):
                    pythonnet.load(runtime)
                else:  # (name, kwargs)
                    pythonnet.load(runtime[0], **runtime[1])
            except RuntimeError:
                # Already loaded with some runtime; keep it.
                log.debug("pythonnet runtime already loaded; ignoring runtime=%r", runtime)

    def _resolve(self, dotted):
        obj = self._root
        for part in dotted.split("."):
            obj = getattr(obj, part) if hasattr(obj, part) else __import__(
                "%s.%s" % (obj.__name__, part), fromlist=["*"])
        return obj

    # -- conversions ----------------------------------------------------------

    def to_net(self, member):
        """Python enum member -> .NET enum value."""
        return self._enum_types[type(member).__name__](int(member))

    def guid(self, value: Optional[uuid.UUID]):
        if value is None:
            return self.System.Guid.Empty
        return self.System.Guid(str(value))

    def uuid(self, net_guid) -> Optional[uuid.UUID]:
        if net_guid is None:
            return None
        u = uuid.UUID(str(net_guid))
        return None if u.int == 0 else u

    @staticmethod
    def impl(obj):
        """Concrete object behind an interface-typed return value."""
        return getattr(obj, "__implementation__", obj)

    def region(self, region):
        if region is None:
            return None
        if isinstance(region, RectangleRegion):
            return self._RectangleRegion(float(region.x), float(region.y),
                                         float(region.width), float(region.height))
        if isinstance(region, LineRegion):
            return self._LineRegion(
                float(region.x), float(region.y), float(region.x2), float(region.y2),
                int(region.max_points or 0), float(region.point_separation_um or 0.0),
                self.to_net(region.definition))
        raise TypeError("Unsupported region type: %r" % (region,))

    def from_region(self, net_region):
        if net_region is None:
            return None
        r = self.impl(net_region)
        try:
            if hasattr(r, "Width"):
                return RectangleRegion(r.X, r.Y, r.Width, r.Height)
            if hasattr(r, "X2"):
                return LineRegion(r.X, r.Y, r.X2, r.Y2, int(r.MaximumNumberOfPoints) or None,
                                  float(r.PointSeparation) or None,
                                  py_enums.coerce(py_enums.LineDefinitionMode, r.LineDefinition, 2))
        except ValueError:
            log.debug("Region reported by AZtec failed validation: %s", r)
        return None

    def floats(self, net_list):
        """IReadOnlyList<float> / float[] -> 1-D numpy float32 array."""
        import numpy as np
        if net_list is None:
            return np.empty(0, dtype=np.float32)
        arr = self.impl(net_list)
        if isinstance(arr, self._float_array_type):
            out = np.empty(arr.Length, dtype=np.float32)
            if arr.Length:
                self._Marshal.Copy(arr, 0, self.System.IntPtr(out.ctypes.data), arr.Length)
            return out
        return np.fromiter(net_list, dtype=np.float32, count=int(net_list.Count))

    @staticmethod
    def to_bytes(net_bytes) -> Optional[bytes]:
        if net_bytes is None:
            return None
        b = bytes(net_bytes)
        return b or None

    @staticmethod
    def seconds(timespan) -> float:
        return float(timespan.TotalSeconds)

    def list_of(self, net_type, items: Iterable):
        lst = self.System.Collections.Generic.List[net_type]()
        for i in items:
            lst.Add(i)
        return lst

    def dispose(self, obj):
        """Dispose a .NET object even when it's wrapped as an interface that doesn't
        itself extend IDisposable (e.g. IDetectorControlClient). Never raises."""
        if obj is None:
            return
        try:
            self.System.IDisposable(self.impl(obj)).Dispose()
        except Exception as e:
            log.debug("Dispose of %r skipped: %s", obj, net_message(e))

    def enum_type(self, py_enum_cls):
        return self._enum_types[py_enum_cls.__name__]

    message = staticmethod(net_message)

    # -- native logging ---------------------------------------------------------

    def enable_native_logging(self, file_name: str, level: str = "Info"):
        """Turn on the plugin client's own log4net log (useful for Oxford support)."""
        self._Logger.Initialize(file_name)
        self._Logger.SetLoggingLevel(getattr(self._LoggingLevel, level.capitalize()))


_cached = {}


def load_dotnet_api(dll_dir=None, runtime=None) -> DotNetApi:
    """Load (once per dll_dir) and return the real .NET API gateway."""
    key = find_dll_dir(dll_dir)
    if key not in _cached:
        _cached[key] = DotNetApi(key, runtime=runtime)
    return _cached[key]
