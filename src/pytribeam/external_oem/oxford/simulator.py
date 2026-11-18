"""In-process simulator of the AZtec Plugin API surface.

It mimics the *shape* of the .NET objects the wrapper uses (PascalCase members,
``+=``/``-=`` events fired from background threads, exceptions carrying
``.Message``), so every controller runs unchanged against it.

It is a behavioural approximation for development and tests. It is NOT a
specification of how AZtec behaves; verify on hardware (see
``examples/smoke_test.py``) before relying on timing or state details.

    sim = Simulator(acquisition_seconds=0.5)
    with AztecSession.simulated(sim) as az:
        az.ebsd.insert()
        sim.ebsd.touch_at_mm = 50.0     # inject faults
        sim.fail_next_acquisition = "Please enter a valid value for the acquisition time."
"""

from __future__ import annotations

import math
import threading
import time
import uuid
from types import SimpleNamespace as NS
from typing import List, Optional

from . import enums as E
from ._dotnet import net_message
from .models import LineRegion, RectangleRegion

EMPTY = uuid.UUID(int=0)


class SimNetError(Exception):
    """Stands in for a .NET exception (has ``.Message``)."""

    def __init__(self, message):
        super().__init__(message)
        self.Message = message


class SimEvent:
    """A .NET-like event: ``obj.Evt += handler`` / ``obj.Evt -= handler``."""

    def __init__(self):
        self._handlers = []
        self._lock = threading.Lock()

    def __iadd__(self, h):
        with self._lock:
            self._handlers.append(h)
        return self

    def __isub__(self, h):
        with self._lock:
            if h in self._handlers:
                self._handlers.remove(h)
        return self

    @property
    def handler_count(self):
        return len(self._handlers)

    def fire(self, sender, args):
        with self._lock:
            hs = list(self._handlers)
        for h in hs:
            h(sender, args)


def _later(delay, fn, *args):
    t = threading.Timer(delay, fn, args)
    t.daemon = True
    t.start()
    return t


def _png(w=8, h=8, seed=0) -> bytes:
    """Tiny valid grayscale PNG (stand-in for AZtec's status images)."""
    import numpy as np
    from ._png import encode_gray8

    yy, xx = np.mgrid[0:h, 0:w]
    return encode_gray8(((xx * 31 + yy * 17 + seed) % 256).astype(np.uint8))


def write_fake_h5oina(
    path,
    techniques=("EBSD",),
    x_cells=16,
    y_cells=12,
    indexed=True,
    format_version="5.0",
    patterns=None,
    project_file=None,
):
    """Write a small file with the H5OINA layout (needs h5py). Not real Oxford data;
    for exercising export verification and the inspector."""
    import h5py
    import numpy as np

    n = x_cells * y_cells
    with h5py.File(path, "w") as f:
        f["Format Version"] = np.bytes_(format_version)
        f["Manufacturer"] = np.bytes_("Oxford Instruments")
        f["Software Version"] = np.bytes_("AZtec 6.1 (simulated)")
        sl = f.create_group("1")
        for tech in techniques:
            g = sl.create_group(tech)
            hdr, data = g.create_group("Header"), g.create_group("Data")
            hdr["X Cells"] = np.array([x_cells], dtype=np.int32)
            hdr["Y Cells"] = np.array([y_cells], dtype=np.int32)
            hdr["X Step"] = np.array([0.5], dtype=np.float32)
            if project_file:
                hdr["Project File"] = np.bytes_(project_file)
            hdr["Y Step"] = np.array([0.5], dtype=np.float32)
            if tech == "EBSD":
                ph = hdr.create_group("Phases")
                ph.create_group("1")["Phase Name"] = np.bytes_("Iron bcc")
                data["Phase"] = (
                    np.ones(n, dtype=np.uint8)
                    if indexed
                    else np.zeros(n, dtype=np.uint8)
                )
                data["Euler"] = np.zeros((n, 3), dtype=np.float32)
                data["Band Contrast"] = np.full(n, 120, dtype=np.uint8)
                data["X"] = np.tile(np.arange(x_cells, dtype=np.float32) * 0.5, y_cells)
                data["Y"] = np.repeat(
                    np.arange(y_cells, dtype=np.float32) * 0.5, x_cells
                )
                if (
                    patterns
                ):  # (height, width): synthetic Kikuchi-ish bands, unique per point
                    ph, pw = patterns
                    hdr["Pattern Height"] = np.array([ph], dtype=np.int32)
                    hdr["Pattern Width"] = np.array([pw], dtype=np.int32)
                    yy, xx = np.mgrid[0:ph, 0:pw]
                    pats = np.empty((n, ph, pw), dtype=np.uint8)
                    for i in range(n):
                        a = 0.3 + i * 0.05
                        pats[i] = (
                            127 + 100 * np.cos((xx * np.cos(a) + yy * np.sin(a)) / 4.0)
                        ).astype(np.uint8)
                    data.create_dataset(
                        "Processed Patterns",
                        data=pats,
                        chunks=(1, ph, pw),
                        compression="gzip",
                    )
            elif tech == "EDS":
                data.create_group("Window Integral")["Fe Ka"] = np.ones(
                    n, dtype=np.float32
                )


# --- hardware --------------------------------------------------------------------------


class _Axis:
    """1-D motion with constant speed, evaluated lazily from wall-clock time."""

    def __init__(self, pos, speed, lo, hi):
        self.pos, self.speed, self.lo, self.hi = (
            float(pos),
            float(speed),
            float(lo),
            float(hi),
        )
        self.target = None
        self._t0 = self._p0 = 0.0
        self.lock = threading.RLock()

    def position(self):
        with self.lock:
            if self.target is None:
                return self.pos
            travel = self.speed * (time.monotonic() - self._t0)
            d = self.target - self._p0
            if travel >= abs(d):
                self.pos, self.target = self.target, None
                return self.pos
            return self._p0 + math.copysign(travel, d)

    def command(self, target):
        with self.lock:
            self._p0 = self.position()
            self.pos = self._p0
            self._t0 = time.monotonic()
            self.target = min(max(float(target), self.lo), self.hi)

    def moving_direction(self):
        with self.lock:
            p = self.position()
            if self.target is None:
                return 0
            return 1 if self.target > p else -1

    def stop(self):
        with self.lock:
            self.pos = self.position()
            self.target = None


class SimEbsdHardware:
    def __init__(
        self,
        name="Symmetry S3 (sim)",
        in_mm=180.0,
        speed_mm_s=90.0,
        tilt_range_mm=(0.0, 10.0),
        tilt_speed_mm_s=5.0,
    ):
        self.id = "EBSD-SIM-1"
        self.name = name
        self.in_mm = in_mm
        self.insertion = _Axis(0.0, speed_mm_s, 0.0, in_mm)
        self.tilt = _Axis(tilt_range_mm[0], tilt_speed_mm_s, *tilt_range_mm)
        self.proximity_enabled = True
        self.has_tilt = True
        self.has_proximity = True
        #: Fault injection
        self.fault = False
        self.touch_at_mm: Optional[float] = None
        self.touching = False

    def command_insertion(self, target):
        """Inward motion stops at the touch point (if armed) as a hard barrier, so
        fast simulated moves can't skip past it between polls."""
        pos = self.insertion.position()
        self._touch_armed = False
        if self.touch_at_mm is not None and pos < self.touch_at_mm <= target:
            target, self._touch_armed = self.touch_at_mm, True
        self.insertion.command(target)

    def insertion_status(self):
        pos = self.insertion.position()
        d = self.insertion.moving_direction()
        if (
            getattr(self, "_touch_armed", False)
            and d == 0
            and abs(pos - self.touch_at_mm) < 1e-6
        ):
            self.touching, self._touch_armed = True, False
        if self.fault:
            state = E.InsertionPositionState.FAULT
        elif abs(pos - self.in_mm) < 1e-6:
            state = E.InsertionPositionState.IN
        elif abs(pos) < 1e-6:
            state = E.InsertionPositionState.OUT
        else:
            state = E.InsertionPositionState.INTERMEDIATE
        activity = (
            E.InsertionActivity.MOVING_IN
            if d > 0
            else E.InsertionActivity.MOVING_OUT
            if d < 0
            else E.InsertionActivity.NOT_MOVING
        )
        ok = not self.fault
        return NS(
            Position=pos,
            Activity=activity,
            State=state,
            IsTouching=self.touching,
            HasTouchSensor=True,
            CanDriveIn=ok and state != E.InsertionPositionState.IN,
            CanDriveOut=state != E.InsertionPositionState.OUT,
            CanStop=True,
            CanMoveTo=ok,
        )

    def tilt_status(self):
        pos = self.tilt.position()
        d = self.tilt.moving_direction()
        if abs(pos - self.tilt.lo) < 1e-6:
            state = E.TiltPositionState.BOTTOM
        elif abs(pos - self.tilt.hi) < 1e-6:
            state = E.TiltPositionState.TOP
        else:
            state = E.TiltPositionState.ABOVE_HOME_KNOWN
        act = (
            E.TiltActivity.TILTING_UP
            if d > 0
            else E.TiltActivity.TILTING_DOWN
            if d < 0
            else E.TiltActivity.NOT_MOVING
        )
        return NS(
            Position=pos,
            Activity=act,
            State=state,
            CanDriveUp=True,
            CanDriveDown=True,
            CanStop=True,
            CanMoveTo=True,
        )


class SimEdsHardware:
    def __init__(self, name="Ultim Max (sim)", move_s=1.0, cool_s=2.0):
        self.id = "ED-SIM-1"
        self.name = name
        self.insertion = _Axis(0.0, 1.0 / max(move_s, 1e-6), 0.0, 1.0)
        self.cool_s = cool_s
        self.mode = E.OperatingMode.AUTOMATIC
        self._cold_at = 0.0  # starts cold
        self.fault = False

    def insertion_status(self):
        pos = self.insertion.position()
        d = self.insertion.moving_direction()
        if self.fault:
            state = E.InsertionPositionState.FAULT
        elif pos >= 1.0 - 1e-9:
            state = E.InsertionPositionState.IN
        elif pos <= 1e-9:
            state = E.InsertionPositionState.OUT
        else:
            state = E.InsertionPositionState.INTERMEDIATE
        activity = (
            E.InsertionActivity.MOVING_IN
            if d > 0
            else E.InsertionActivity.MOVING_OUT
            if d < 0
            else E.InsertionActivity.NOT_MOVING
        )
        return NS(
            Activity=activity,
            State=state,
            CanDriveIn=not self.fault and state != E.InsertionPositionState.IN,
            CanDriveOut=state != E.InsertionPositionState.OUT,
            CanStop=True,
        )

    def thermal_status(self):
        if self.mode == E.OperatingMode.STANDBY:
            st = E.OperatingState.STANDBY
        else:
            st = (
                E.OperatingState.COLD
                if time.monotonic() >= self._cold_at
                else E.OperatingState.COOLING
            )
        return NS(
            OperatingMode=self.mode,
            OperatingState=st,
            VacuumState=E.VacuumState.UNDER_VACUUM,
            HasVacuumSensor=True,
            CanOperate=True,
            CanStandby=True,
        )

    @property
    def is_cold(self):
        return self.thermal_status().OperatingState == E.OperatingState.COLD


# --- .NET-shaped control objects -------------------------------------------------------------


class _InsertionControl:
    def __init__(self, hw, ebsd: bool):
        self._hw, self._ebsd = hw, ebsd
        self.TargetPosition = 0.0
        self.PropertyChanged = SimEvent()

    @property
    def State(self):
        return self._hw.insertion_status()

    def DriveIn(self):
        if self._hw.fault:
            raise SimNetError("Detector is in a fault state")
        if self._ebsd:
            self._hw.command_insertion(self._hw.insertion.hi)
        else:
            self._hw.insertion.command(self._hw.insertion.hi)

    def DriveOut(self):
        if self._ebsd:
            self._hw.touching = False
        self._hw.insertion.command(self._hw.insertion.lo)

    def Stop(self):
        self._hw.insertion.stop()

    def MoveTo(self):
        if not self._ebsd:
            raise SimNetError("ED detectors do not support MoveTo")
        self._hw.command_insertion(self.TargetPosition)


class _TiltControl:
    def __init__(self, hw):
        self._hw = hw
        self.TargetPosition = 0.0
        self.PropertyChanged = SimEvent()

    @property
    def State(self):
        return self._hw.tilt_status()

    def DriveUp(self):
        self._hw.tilt.command(self._hw.tilt.hi)

    def DriveDown(self):
        self._hw.tilt.command(self._hw.tilt.lo)

    def Stop(self):
        self._hw.tilt.stop()

    def MoveTo(self):
        self._hw.tilt.command(self.TargetPosition)


class _ProximityControl:
    def __init__(self, hw):
        self._hw = hw

    @property
    def State(self):
        return NS(IsEnabled=self._hw.proximity_enabled)

    def Enable(self, on):
        self._hw.proximity_enabled = bool(on)


class _ThermalControl:
    def __init__(self, hw):
        self._hw = hw

    @property
    def State(self):
        return self._hw.thermal_status()

    def EnterAutomaticMode(self):
        if self._hw.mode != E.OperatingMode.AUTOMATIC:
            self._hw.mode = E.OperatingMode.AUTOMATIC
            self._hw._cold_at = time.monotonic() + self._hw.cool_s

    def EnterStandbyMode(self):
        self._hw.mode = E.OperatingMode.STANDBY


class _DetectorControlClient:
    def __init__(self, sim):
        self._sim = sim
        self.DetectorsChanged = SimEvent()

    def IsConnected(self):
        return self._sim.session is not None

    def GetDevices(self, device_type=None):
        out = []
        if self._sim.ebsd is not None:
            out.append(
                NS(
                    ID=self._sim.ebsd.id,
                    DisplayName=self._sim.ebsd.name,
                    DeviceType=E.DeviceType.EBSD,
                )
            )
        if self._sim.eds is not None:
            out.append(
                NS(
                    ID=self._sim.eds.id,
                    DisplayName=self._sim.eds.name,
                    DeviceType=E.DeviceType.ED,
                )
            )
        if device_type is not None:
            out = [d for d in out if int(d.DeviceType) == int(device_type)]
        return out

    def Ebsd(self, ident):
        hw = self._sim.ebsd
        if hw is None or ident.ID != hw.id:
            raise SimNetError("Device type must be Ebsd")
        return NS(
            DetectorId=ident,
            InsertionControl=_InsertionControl(hw, True),
            TiltControl=_TiltControl(hw) if hw.has_tilt else None,
            ProximityControl=_ProximityControl(hw) if hw.has_proximity else None,
            Dispose=lambda: None,
        )

    def Ed(self, ident):
        hw = self._sim.eds
        if hw is None or ident.ID != hw.id:
            raise SimNetError("Device type must be Ed")
        return NS(
            DetectorId=ident,
            InsertionControl=_InsertionControl(hw, False),
            ThermalControl=_ThermalControl(hw),
            Dispose=lambda: None,
        )

    def Dispose(self):
        pass


# --- project data ---------------------------------------------------------------------------


class _Item:
    def __init__(self, label, data_type, parent=None, **extra):
        self.Id = uuid.uuid4()
        self.Label = label
        self.DataType = data_type
        self.parent = parent
        self.__dict__.update(extra)


class _ProjectDataController:
    def __init__(self, sim):
        self._sim = sim
        self.ExportFinished = SimEvent()

    def GetProjectData(self, *args):
        if len(args) == 1:
            parent, dtype = None, args[0]
        else:
            parent, dtype = args
        items = [i for i in self._sim.items if int(i.DataType) == int(dtype)]
        if parent is not None:
            items = [i for i in items if self._sim.is_descendant(i, parent.Id)]
        return items

    def FindParent(self, child, dtype):
        node = self._sim.item(child.Id).parent if self._sim.item(child.Id) else None
        while node is not None:
            if int(node.DataType) == int(dtype):
                return node
            node = node.parent
        return None

    def CreateSite(self, *args):
        if len(args) == 1:
            spec, name = self._sim.current_specimen, args[0]
        else:
            ref, name = args
            spec = self._sim.item(ref.Id if hasattr(ref, "Id") else ref)
            if spec is None:
                raise SimNetError("specimen not found")
        n = len([i for i in self._sim.items if i.DataType == E.DataType.SITE]) + 1
        site = self._sim.add(_Item(name or "Site %d" % n, E.DataType.SITE, spec))
        self._sim.current_site = site
        return site

    def ExportToH5OINA(self, guid, dtype, path):
        item = self._sim.item(guid)
        sim = self._sim
        if item is None:
            raise SimNetError("No data item with id %s" % guid)
        sim.exports.append((path, item.Id, int(dtype)))
        state = E.ExportState.ERROR if sim.fail_next_export else E.ExportState.COMPLETED
        msg, sim.fail_next_export = sim.fail_next_export, None
        if sim.write_export_files and state == E.ExportState.COMPLETED:
            sim.write_export(path, item)
        _later(
            sim.event_delay_s,
            self.ExportFinished.fire,
            self,
            NS(Data=[item], State=state, ExportType=1, ErrorMessage=msg),
        )


class _EdMapController:
    def __init__(self, sim):
        self._sim = sim
        self.ProcessingProgress = SimEvent()
        self.ProcessingFinished = SimEvent()

    def AvailableEdMappingModes(self):
        return [
            E.EdMappingMode.WINDOW_INTEGRAL,
            E.EdMappingMode.TRU_MAP,
            E.EdMappingMode.QUANT_MAP,
        ]

    def CreateElementMaps(self, item, mode):
        if int(mode) == 0:
            raise SimNetError("Ed mapping mode cannot be Unknown")
        _later(
            self._sim.event_delay_s,
            self.ProcessingProgress.fire,
            self,
            NS(ProgressPercentage=50.0),
        )
        _later(
            self._sim.event_delay_s * 2,
            self.ProcessingFinished.fire,
            self,
            NS(Mode=mode, Data=[item]),
        )

    def CancelProcessing(self, item):
        pass


class _EdSpectrumController:
    def __init__(self, sim):
        self._sim = sim
        self.ExperimentStarted = SimEvent()
        self.ExperimentFinished = SimEvent()

    def CreateEMSAOutput(self, item):
        return (
            "#FORMAT      : EMSA/MAS Spectral Data File\n#VERSION     : 1.0\n#TITLE       : %s\n"
            "#NPOINTS     : 4\n#SPECTRUM    :\n0.0, 1.0\n0.01, 4.0\n0.02, 9.0\n0.03, 2.0\n#ENDOFDATA   :\n"
            % item.Label
        )


# --- acquisition ----------------------------------------------------------------------------


class _AcquisitionClient:
    def __init__(self, sim):
        self._sim = sim
        self.AcquisitionType = E.AcquisitionType.EBSD_MAP
        self.AcquisitionRegion = None
        self.SiteName = None
        self.ProjectId = EMPTY
        self.SpecimenId = EMPTY
        self.StatusImageTypes = E.StatusImageTypes.NONE
        self.AutoLockMode = E.AutoLockMode.OFF
        self.MasterSiteNumber = None
        self.IsAutoIncrementSiteNumber = False
        self.IsResetAcquisitionNumberForEachSite = False
        self.SiteThickness = None
        self.IsAutoContrastBrightness = False
        self.IsAllEnglishInImageName = False
        self.AspectRatio = 4.0 / 3.0
        self.Starting = SimEvent()
        self.Acquired = SimEvent()
        self.Finished = SimEvent()
        self.ProgressChanged = SimEvent()
        self._running = False
        self._stops = 0
        self.released = False
        self.started_names: List[Optional[str]] = []

    @property
    def CurrentSite(self):
        return self._sim.current_site.Label if self._sim.current_site else ""

    def StartAcquisition(self, name=None):
        if self.released:
            raise SimNetError("Client has been released")
        if self._running:
            raise SimNetError("An acquisition is already in progress")
        self._running, self._stops = True, 0
        self.started_names.append(name)
        threading.Thread(
            target=self._run, args=(name, int(self.AcquisitionType)), daemon=True
        ).start()

    def StopAcquisition(self):
        if self._running:
            self._stops += 1

    def _finish(self, state, message=None, **ids):
        self._running = False
        self.Acquired.fire(self, NS(AcquisitionState=state))
        status = NS(
            State=state,
            AcquiredItemName=ids.pop("name", None),
            Message=message,
            Error=None,
            EdsMapId=ids.get("eds", EMPTY),
            EbsdMapId=ids.get("ebsd", EMPTY),
            EdsMap=ids.get("eds_img"),
            EbsdMap=ids.get("ebsd_img"),
            ElectronImage=ids.get("ei_img"),
            AcquiredRegion=self.AcquisitionRegion,
        )
        self.Finished.fire(self, NS(AcquisitionStatus=status))

    def _run(self, name, atype):
        sim = self._sim
        time.sleep(sim.event_delay_s)
        fail, sim.fail_next_acquisition = sim.fail_next_acquisition, None
        if fail:
            return self._finish(
                E.AcquisitionState.ERROR,
                "Data acquisition has invalid settings(s):\n" + fail,
            )
        problem = sim.readiness_problem(atype)
        if problem:
            return self._finish(E.AcquisitionState.ERROR, problem)
        self.Starting.fire(self, NS())
        steps = max(int(sim.progress_steps), 1)
        total = sim.acquisition_time(atype)
        for i in range(1, steps + 1):
            if self._stops >= 2:
                break
            time.sleep(total / steps)
            self.ProgressChanged.fire(
                self,
                NS(
                    AcquisitionProgress=NS(
                        ProgressPercentage=int(100 * i / steps),
                        EstimatedSecondsToCompletion=int(total * (steps - i) / steps),
                    )
                ),
            )
            if self._stops >= 1:
                break  # end-of-frame stop
        site = sim.site_named(self.SiteName) if self.SiteName else sim.current_site
        sim.acq_counter += 1
        label = name or "Map Data %d" % sim.acq_counter
        imgs = int(self.StatusImageTypes)
        ids = {"name": label}
        if atype & E.AcquisitionType.ELECTRON_IMAGE:
            sim.add(_Item(label + " (electron image)", E.DataType.UNKNOWN, site))
            if imgs & E.StatusImageTypes.ELECTRON_IMAGE:
                ids["ei_img"] = _png(seed=1)
        if atype & E.AcquisitionType.EDS_MAP:
            it = sim.add(
                _Item(
                    label + " EDS",
                    E.DataType.ED_MAP,
                    site,
                    region=self.AcquisitionRegion,
                )
            )
            ids["eds"] = it.Id
            if imgs & E.StatusImageTypes.EDS_MAP:
                ids["eds_img"] = _png(seed=2)
        if atype & E.AcquisitionType.EBSD_MAP:
            it = sim.add(_Item(label + " EBSD", sim.ebsd_result_item_type, site))
            ids["ebsd"] = it.Id
            if sim.save_patterns:
                sim.write_ebsp(it, site)
            it.includes_eds = sim.ebsd_includes_eds
            if sim.ebsd_includes_eds and not atype & E.AcquisitionType.EDS_MAP:
                ed = sim.add(_Item(label + " EDS (in EBSD)", E.DataType.ED_MAP, site))
                ids["eds"] = ed.Id
            if imgs & E.StatusImageTypes.EBSD_MAP:
                ids["ebsd_img"] = _png(seed=3)
        msg = "Stopped by user" if self._stops else None
        if sim.ids_only_with_status_images:
            if not imgs & E.StatusImageTypes.EBSD_MAP:
                ids.pop("ebsd", None)
            if not imgs & E.StatusImageTypes.EDS_MAP:
                ids.pop("eds", None)
        self._finish(E.AcquisitionState.COMPLETED, msg, **ids)

    def GetAcquiredEdData(self, guid, result_type):
        item = self._sim.item(guid)
        if item is None or item.DataType not in (E.DataType.ED_MAP, E.DataType.ED_LINE):
            raise SimNetError("No EDS map or line with id %s" % guid)
        import numpy as np

        w, h = self._sim.map_size
        yy, xx = np.mgrid[0:h, 0:w]
        elems = [
            NS(
                Name=el,
                Data=((np.sin(xx / (5.0 + k)) + np.cos(yy / (7.0 + k)) + 2) * 50)
                .astype(np.float32)
                .ravel(),
            )
            for k, el in enumerate(self._sim.elements)
        ]
        return NS(
            Id=item.Id,
            Name=item.Label,
            Width=w,
            Height=h,
            ResultType=result_type,
            ElementData=elems,
            AcquisitionRegion=getattr(item, "region", None),
        )

    def Release(self):
        self.released = True


class _TimeSpan:
    def __init__(self, s):
        self.TotalSeconds = float(s)


class _NativeSession:
    def __init__(self, sim):
        self._sim = sim
        self.ClientVersion = "6.1.0.0-sim"
        self.ServerVersion = "AZtec 6.1 (simulated)"
        self.ProjectStateChanged = SimEvent()
        self.ProfileStateChanged = SimEvent()
        self.BatchExportFinished = SimEvent()
        self._pdc = None

    @property
    def IsConnected(self):
        return self._sim.session is self and not self._sim.link_down

    @property
    def Projects(self):
        return [
            NS(Name=p.Label, Id=p.Id, FileName=p.file_name)
            for p in self._sim.of_type(E.DataType.PROJECT)
        ]

    @property
    def Specimens(self):
        return [
            NS(Name=s.Label, Id=s.Id, ProjectId=s.parent.Id)
            for s in self._sim.of_type(E.DataType.SPECIMEN)
        ]

    @property
    def Profiles(self):
        return [
            NS(Name=p.Name, Id=p.Id, Description=p.Description)
            for p in self._sim.profiles
        ]

    def _fire_project(self, state, item, message=None):
        info = (
            NS(Name=item.Label, Id=item.Id, FileName=getattr(item, "file_name", None))
            if item
            else None
        )
        _later(
            self._sim.event_delay_s,
            self.ProjectStateChanged.fire,
            self,
            NS(Status=state, Message=message, ProjectInfo=info),
        )

    def GetDetectorStatus(self, acq_type):
        problem = self._sim.readiness_problem(int(acq_type))
        if int(acq_type) not in (
            int(E.AcquisitionType.EDS_MAP),
            int(E.AcquisitionType.EBSD_MAP),
        ):
            raise SimNetError(
                "There is no detector associated with the specified acquisition type"
            )
        return NS(IsDetectorReady=problem is None, StatusDescription=problem or "Ready")

    def GetAcquisitionTime(self, acq_type=None):
        return _TimeSpan(
            self._sim.acquisition_time(int(acq_type) if acq_type is not None else 4)
        )

    def CreateProject(self, name, folder=None):
        # Layout observed on AZtec 6.1: <folder>\<name>\<name>.oipx
        folder = folder or r"C:\AZtec\Projects"
        sep = "\\" if ("\\" in folder or folder[1:2] == ":") else "/"
        file_name = sep.join([folder.rstrip("\\/"), name, name + ".oipx"])
        if sep == "/" and self._sim.write_export_files:
            import os

            os.makedirs(os.path.join(os.path.dirname(file_name), "data"), exist_ok=True)
        p = self._sim.add(_Item(name, E.DataType.PROJECT, None, file_name=file_name))
        s = self._sim.add(_Item("Specimen 1", E.DataType.SPECIMEN, p))
        self._sim.current_specimen = s  # the new project is opened and becomes current
        self._sim.current_site = self._sim.add(_Item("Site 1", E.DataType.SITE, s))
        self._fire_project(E.ProjectChangeState.OPENED, p)

    def LoadProject(self, file_name, guid):
        for p in self._sim.of_type(E.DataType.PROJECT):
            if p.file_name == file_name and (guid == EMPTY or guid == p.Id):
                return self._fire_project(E.ProjectChangeState.OPENED, p)
        self._fire_project(E.ProjectChangeState.FAILED, None, "Project file not found")

    def CloseProject(self, guid):
        p = self._sim.item(guid)
        if p is None:
            return self._fire_project(
                E.ProjectChangeState.ERROR, None, "No such project"
            )
        self._sim.remove_tree(p)
        self._fire_project(E.ProjectChangeState.CLOSED, p)

    def CreateSpecimen(self, project_guid, name):
        p = self._sim.item(project_guid)
        if p is None:
            return self._fire_project(
                E.ProjectChangeState.ERROR, None, "No such project"
            )
        self._sim.current_specimen = self._sim.add(_Item(name, E.DataType.SPECIMEN, p))
        self._fire_project(E.ProjectChangeState.SPECIMEN_ADDED, p)

    def CreateProfile(self, name):
        self._sim.profiles.append(
            NS(Name=name, Id=uuid.uuid4(), Description="Created via plugin")
        )

    def LoadProfile(self, guid):
        prof = next((p for p in self._sim.profiles if p.Id == guid), None)
        state = E.ProfileChangeState.LOADED if prof else E.ProfileChangeState.FAILED
        if prof:
            self._sim.loaded_profile = prof.Name
        _later(
            self._sim.event_delay_s,
            self.ProfileStateChanged.fire,
            self,
            NS(
                Status=state,
                Message=None if prof else "Profile not found",
                ProfileInfo=prof,
            ),
        )

    def DeleteProfile(self, guid):
        self._sim.profiles = [p for p in self._sim.profiles if p.Id != guid]

    def BatchExport(self, guid, folder):
        self._sim.exports.append((folder, guid, -1))
        if self._sim.write_export_files:
            import os

            for m in self._sim.of_type(E.DataType.EBSD_MAP):
                write_fake_h5oina(
                    os.path.join(folder, "%s.h5oina" % m.Label.replace(" ", "_")),
                    ("EBSD",),
                    patterns=self._sim.batch_export_patterns,
                )
        _later(
            self._sim.event_delay_s,
            self.BatchExportFinished.fire,
            self,
            NS(Message="Batch export complete: %s" % folder),
        )

    def GetAcquisitionClient(self):
        if self._sim.acquisition_client is not None:
            raise SimNetError("Could not take exclusive acquisition lock")
        self._sim.acquisition_client = _AcquisitionClient(self._sim)
        return self._sim.acquisition_client

    def ReleaseAcquisitionClient(self, client):
        client.Release()
        if self._sim.acquisition_client is client:
            self._sim.acquisition_client = None

    def GetDetectorControlClient(self):
        return _DetectorControlClient(self._sim)

    def ProjectDataController(self):
        if self._pdc is None:
            self._pdc = _ProjectDataController(self._sim)
        return self._pdc

    def EdMapController(self):
        return _EdMapController(self._sim)

    def EdSpectrumController(self):
        return _EdSpectrumController(self._sim)


class Simulator:
    """The simulated AZtec instance. Tweak attributes to shape behaviour / inject faults."""

    def __init__(
        self,
        acquisition_seconds=2.0,
        progress_steps=5,
        event_delay_s=0.02,
        ebsd_speed_mm_s=90.0,
        eds_move_s=1.0,
        eds_cool_s=2.0,
        map_size=(64, 48),
        elements=("Fe Ka", "Cr Ka", "Ni Ka"),
        with_ebsd=True,
        with_eds=True,
        require_inserted=True,
    ):
        self.acquisition_seconds = acquisition_seconds
        self.progress_steps = progress_steps
        self.event_delay_s = event_delay_s
        self.map_size = map_size
        self.elements = list(elements)
        #: If True, acquisitions fail unless the needed detector is inserted (and EDS cold).
        self.require_inserted = require_inserted
        self.ebsd = SimEbsdHardware(speed_mm_s=ebsd_speed_mm_s) if with_ebsd else None
        self.eds = (
            SimEdsHardware(move_s=eds_move_s, cool_s=eds_cool_s) if with_eds else None
        )
        self.session: Optional[_NativeSession] = None
        self.acquisition_client: Optional[_AcquisitionClient] = None
        self.refuse_connections = False
        self.link_down = False
        self.fail_next_acquisition: Optional[str] = None
        self.fail_next_export: Optional[str] = None
        self.exports = []
        #: If True, ExportToH5OINA writes a synthetic .h5oina file at the given path (needs h5py).
        self.write_export_files = False
        #: Whether EBSD points in written files are indexed (False mimics unsolved data).
        self.export_indexed = True
        #: (height, width) to include saved EBSD patterns in written files; None = no patterns.
        self.export_patterns = None
        #: Write <project>/data/<map id>.ebsp on EBSD acquisition (AZtec "save patterns"),
        #: only for projects whose folder is a local path (tests).
        self.save_patterns = False
        #: AZtec "Include EDS" on EBSD maps: an EBSD acquisition also creates an EDS map.
        self.ebsd_includes_eds = False
        #: (height, width) of patterns written by BatchExport files (mimics UI batch settings).
        self.batch_export_patterns = None
        #: DataType of the node an acquisition's EbsdMapId refers to (to test type lookup).
        self.ebsd_result_item_type = E.DataType.EBSD_MAP
        #: Mimic AZtec leaving EbsdMapId/EdsMapId empty unless that status image was requested.
        self.ids_only_with_status_images = False
        self.acq_counter = 0
        self.loaded_profile = None
        self.profiles = [
            NS(Name="EBSD 1um step", Id=uuid.uuid4(), Description="sim"),
            NS(Name="EDS 512px 50us", Id=uuid.uuid4(), Description="sim"),
        ]
        self.items: List[_Item] = []
        self._lock = threading.RLock()
        proj = self.add(
            _Item(
                "Sim Project",
                E.DataType.PROJECT,
                None,
                file_name=r"C:\AZtec\Projects\Sim Project.oip",
            )
        )
        self.current_specimen = self.add(_Item("Specimen 1", E.DataType.SPECIMEN, proj))
        self.current_site = self.add(
            _Item("Site 1", E.DataType.SITE, self.current_specimen)
        )
        self.add(_Item("Spectrum 1", E.DataType.ED_SPECTRUM, self.current_site))

    # tree helpers
    def add(self, item):
        with self._lock:
            self.items.append(item)
        return item

    def item(self, guid):
        return next((i for i in self.items if i.Id == guid), None)

    def of_type(self, dtype):
        return [i for i in self.items if int(i.DataType) == int(dtype)]

    def is_descendant(self, item, ancestor_id):
        node = item.parent
        while node is not None:
            if node.Id == ancestor_id:
                return True
            node = node.parent
        return False

    def remove_tree(self, root):
        with self._lock:
            self.items = [
                i
                for i in self.items
                if i is not root and not self.is_descendant(i, root.Id)
            ]

    def site_named(self, name):
        for s in self.of_type(E.DataType.SITE):
            if s.Label == name and s.parent is self.current_specimen:
                return s
        site = self.add(_Item(name, E.DataType.SITE, self.current_specimen))
        self.current_site = site
        return site

    def write_ebsp(self, map_item, site):
        import os

        node = site
        while node is not None and node.DataType != E.DataType.PROJECT:
            node = node.parent
        fn = getattr(node, "file_name", None) if node else None
        if not fn or "\\" in fn:
            return  # Windows-style path: not writable from the test machine
        data_dir = os.path.join(os.path.dirname(fn), "data")
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "%s.ebsp" % map_item.Id), "wb") as f:
            f.write(b"\x00" * 4096)  # placeholder bytes, not the real .ebsp format

    def write_export(self, path, item):
        dtype = int(item.DataType)
        if dtype in (
            int(E.DataType.ED_MAP),
            int(E.DataType.ED_LINE),
            int(E.DataType.ED_SPECTRUM),
        ):
            techs = ("EDS",)
        elif dtype in (int(E.DataType.EBSD_MAP), int(E.DataType.MAP_ACQUIRE)):
            techs = (
                ("EBSD", "EDS") if getattr(item, "includes_eds", False) else ("EBSD",)
            )
        elif dtype == int(E.DataType.SITE):
            techs = ("EBSD", "EDS")
        else:
            techs = ()
        write_fake_h5oina(
            path, techs, indexed=self.export_indexed, patterns=self.export_patterns
        )

    # behaviour helpers
    def acquisition_time(self, atype: int) -> float:
        n = bin(int(atype) & 7).count("1") or 1
        return self.acquisition_seconds * n

    def readiness_problem(self, atype: int) -> Optional[str]:
        if not self.require_inserted:
            return None
        if atype & E.AcquisitionType.EBSD_MAP:
            if self.ebsd is None:
                return "No EBSD detector"
            if self.ebsd.insertion_status().State != E.InsertionPositionState.IN:
                return "EBSD detector is not inserted"
        if atype & E.AcquisitionType.EDS_MAP:
            if self.eds is None:
                return "No EDS detector"
            if self.eds.insertion_status().State != E.InsertionPositionState.IN:
                return "EDS detector is not inserted"
            if not self.eds.is_cold:
                return "EDS detector is not at operating temperature"
        return None


class _SessionStatics:
    """Stands in for the static ``Session.Connect`` / ``Session.Disconnect``."""

    def __init__(self, sim):
        self._sim = sim

    def Connect(self, address):
        sim = self._sim
        if sim.refuse_connections or sim.session is not None:
            raise SimNetError(
                "Could not connect to AZtec Plugin. Verify the machine running AZtec is "
                "accessible at the given IP address and port and does not have an active "
                "Plugin connection."
            )
        sim.session = _NativeSession(sim)
        return sim.session

    def Disconnect(self, session):
        if self._sim.session is not session:
            raise SimNetError("Session is not connected.")
        if self._sim.acquisition_client is not None:
            self._sim.acquisition_client.Release()
            self._sim.acquisition_client = None
        self._sim.session = None


class SimulatedApi:
    """Drop-in replacement for ``DotNetApi`` backed by :class:`Simulator`."""

    name = "simulator"
    uses_network = False

    def __init__(self, simulator: Optional[Simulator] = None):
        self.sim = simulator or Simulator()
        self.Session = _SessionStatics(self.sim)

    @staticmethod
    def to_net(member):
        return member

    @staticmethod
    def guid(value):
        return EMPTY if value is None else uuid.UUID(str(value))

    @staticmethod
    def uuid(g):
        if g is None:
            return None
        g = uuid.UUID(str(g))
        return None if g.int == 0 else g

    @staticmethod
    def impl(obj):
        return obj

    @staticmethod
    def region(r):
        return r

    @staticmethod
    def from_region(r):
        return r if isinstance(r, (RectangleRegion, LineRegion)) else None

    @staticmethod
    def floats(x):
        import numpy as np

        return np.asarray(x if x is not None else [], dtype=np.float32).ravel()

    @staticmethod
    def to_bytes(b):
        return bytes(b) if b else None

    @staticmethod
    def seconds(ts):
        return float(ts.TotalSeconds)

    @staticmethod
    def dispose(obj):
        fn = getattr(obj, "Dispose", None)
        if fn:
            fn()

    message = staticmethod(net_message)

    def enable_native_logging(self, file_name, level="Info"):
        pass
