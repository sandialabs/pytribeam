"""EBSD / EDS detector motion and status.

Safety model
------------
* Before any command that moves a detector *toward the sample* (insert, move_to,
  tilt) an optional user ``interlock(detector, action)`` is called. Return False
  or raise to block the move. The wider microscope suite should use this to check
  stage position, tilt, etc. Retract and stop are never interlocked.
* AZtec's own permission flags (CanDriveIn, CanMoveTo...) are checked first.
* While waiting, a FAULT / auto-retract / touch-sensor trigger stops the detector
  (where possible) and raises. On timeout the detector is stopped, then
  DetectorTimeoutError is raised.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from ._events import translate
from .enums import (
    DeviceType,
    InsertionActivity,
    InsertionPositionState,
    OperatingMode,
    OperatingState,
    TiltActivity,
    TiltPositionState,
    VacuumState,
    coerce,
)
from .errors import (
    DetectorError,
    DetectorNotFoundError,
    DetectorTimeoutError,
    InterlockError,
)
from .models import (
    DetectorInfo,
    DetectorStatus,
    EbsdInsertionState,
    EbsdTiltState,
    EdInsertionState,
    EdThermalState,
)

log = logging.getLogger(__name__)

#: interlock(detector, action) -> bool. action is "insert" | "move_to" | "tilt".
Interlock = Callable[["_Detector", str], bool]

DEFAULT_MOTION_TIMEOUT_S = 120.0
DEFAULT_POLL_S = 0.25
#: After a command, how long a NOT_MOVING activity is tolerated before the
#: motion counts as stalled (the hardware may not report motion instantly).
STALL_GRACE_S = 3.0
_MOVING = (
    InsertionActivity.MOVING_IN,
    InsertionActivity.MOVING_OUT,
    InsertionActivity.AUTO_RETRACTING,
    InsertionActivity.HOMING,
)
_RETRACTED = (InsertionPositionState.OUT, InsertionPositionState.AUTO_RETRACTED)


class _Detector:
    """Common detector behaviour."""

    def __init__(
        self, manager: "DetectorManager", info: DetectorInfo, native_id, native_ctrl
    ):
        self._mgr = manager
        self.info = info
        self._native_id = native_id
        self._ctrl = native_ctrl
        self._move_lock = threading.Lock()

    @property
    def id(self) -> str:
        return self.info.id

    @property
    def name(self) -> str:
        return self.info.name

    @property
    def _api(self):
        return self._mgr._api

    def __repr__(self):
        return "<%s %r id=%s>" % (type(self).__name__, self.name, self.id)

    # -- helpers --------------------------------------------------------------

    def _sub(self, attr: str, what: str):
        sub = getattr(self._ctrl, attr, None)
        if sub is None:
            raise DetectorError("%s does not support %s" % (self.name, what))
        return sub

    def _check_interlock(self, action: str):
        lock = self._mgr.interlock
        if lock is None:
            return
        try:
            ok = lock(self, action)
        except InterlockError:
            raise
        except Exception as e:
            raise InterlockError(
                "Interlock blocked %s on %s: %s" % (action, self.name, e)
            ) from e
        if ok is False:
            raise InterlockError("Interlock blocked %s on %s" % (action, self.name))

    def _wait_motion(self, action, read, done, fault, timeout, poll, stop, stopped):
        """Poll ``read()`` until ``done``. Stops the detector and raises on ``fault`` or
        timeout. Counts as stalled only when the hardware *explicitly* reports
        NOT_MOVING (``stopped``) after the grace period - UNKNOWN activity is
        treated as possibly moving, so a detector that doesn't report activity
        isn't falsely aborted."""
        t0 = time.monotonic()
        while True:
            st = read()
            if done(st):
                log.info("%s: %s complete (%s)", self.name, action, st)
                return st
            reason = fault(st)
            if reason:
                self._try_stop(stop)
                raise DetectorError(
                    "%s: %s aborted - %s (%s)" % (self.name, action, reason, st)
                )
            elapsed = time.monotonic() - t0
            if elapsed > STALL_GRACE_S and stopped(st):
                raise DetectorError(
                    "%s: %s stopped before reaching target (%s)"
                    % (self.name, action, st)
                )
            if timeout is not None and elapsed > timeout:
                self._try_stop(stop)
                raise DetectorTimeoutError(
                    "%s: %s did not complete within %.0f s (%s)"
                    % (self.name, action, timeout, st)
                )
            time.sleep(poll)

    def _try_stop(self, stop):
        try:
            stop()
        except Exception:
            log.exception("%s: stop after fault/timeout failed", self.name)

    def _do(self, what, fn, *args):
        with translate(self._api, DetectorError, "%s %s" % (self.name, what)):
            return fn(*args)


class EbsdDetector(_Detector):
    """An EBSD camera: insertion (mm), optional tilt (mm), optional proximity sensor."""

    @property
    def has_insertion_control(self) -> bool:
        return getattr(self._ctrl, "InsertionControl", None) is not None

    @property
    def has_tilt_control(self) -> bool:
        return getattr(self._ctrl, "TiltControl", None) is not None

    @property
    def has_proximity_control(self) -> bool:
        return getattr(self._ctrl, "ProximityControl", None) is not None

    # -- state ------------------------------------------------------------------

    def insertion_state(self) -> EbsdInsertionState:
        ctl = self._sub("InsertionControl", "insertion control")
        s = self._do("read insertion state", lambda: ctl.State)
        return EbsdInsertionState(
            position_mm=float(s.Position),
            activity=coerce(InsertionActivity, s.Activity),
            state=coerce(InsertionPositionState, s.State),
            is_touching=bool(s.IsTouching),
            has_touch_sensor=bool(s.HasTouchSensor),
            can_drive_in=bool(s.CanDriveIn),
            can_drive_out=bool(s.CanDriveOut),
            can_stop=bool(s.CanStop),
            can_move_to=bool(s.CanMoveTo),
        )

    def tilt_state(self) -> EbsdTiltState:
        ctl = self._sub("TiltControl", "tilt control")
        s = self._do("read tilt state", lambda: ctl.State)
        return EbsdTiltState(
            position_mm=float(s.Position),
            activity=coerce(TiltActivity, s.Activity),
            state=coerce(TiltPositionState, s.State),
            can_drive_up=bool(s.CanDriveUp),
            can_drive_down=bool(s.CanDriveDown),
            can_stop=bool(s.CanStop),
            can_move_to=bool(s.CanMoveTo),
        )

    def proximity_sensor_enabled(self) -> bool:
        ctl = self._sub("ProximityControl", "proximity control")
        return bool(self._do("read proximity state", lambda: ctl.State.IsEnabled))

    @property
    def is_inserted(self) -> bool:
        return self.insertion_state().state == InsertionPositionState.IN

    @property
    def is_retracted(self) -> bool:
        return self.insertion_state().state in _RETRACTED

    @property
    def position_mm(self) -> float:
        return self.insertion_state().position_mm

    def status(self) -> DetectorStatus:
        st = DetectorStatus(info=self.info)
        try:
            if self.has_insertion_control:
                st.insertion = self.insertion_state()
            if self.has_tilt_control:
                st.tilt = self.tilt_state()
            if self.has_proximity_control:
                st.proximity_sensor_enabled = self.proximity_sensor_enabled()
        except Exception as e:
            st.error = str(e)
        return st

    # -- insertion -----------------------------------------------------------------

    def _ins_fault(self, s: EbsdInsertionState) -> Optional[str]:
        if s.state == InsertionPositionState.FAULT:
            return "detector reports FAULT"
        if (
            s.state == InsertionPositionState.AUTO_RETRACTED
            or s.activity == InsertionActivity.AUTO_RETRACTING
        ):
            return "detector auto-retracted"
        if s.is_touching:
            return "touch sensor triggered"
        return None

    def insert(
        self,
        wait: bool = True,
        timeout: Optional[float] = DEFAULT_MOTION_TIMEOUT_S,
        poll_interval: float = DEFAULT_POLL_S,
    ) -> EbsdInsertionState:
        """Drive the detector fully in. No-op if already inserted."""
        ctl = self._sub("InsertionControl", "insertion control")
        with self._move_lock:
            s = self.insertion_state()
            if s.state == InsertionPositionState.IN and s.activity not in _MOVING:
                return s
            if not s.can_drive_in:
                raise DetectorError("%s cannot drive in now (%s)" % (self.name, s))
            self._check_interlock("insert")
            log.info("%s: inserting", self.name)
            self._do("drive in", ctl.DriveIn)
            if not wait:
                return self.insertion_state()
            return self._wait_motion(
                "insert",
                self.insertion_state,
                done=lambda st: (
                    st.state == InsertionPositionState.IN and st.activity not in _MOVING
                ),
                fault=self._ins_fault,
                timeout=timeout,
                poll=poll_interval,
                stop=ctl.Stop,
                stopped=lambda st: st.activity == InsertionActivity.NOT_MOVING,
            )

    def retract(
        self,
        wait: bool = True,
        timeout: Optional[float] = DEFAULT_MOTION_TIMEOUT_S,
        poll_interval: float = DEFAULT_POLL_S,
    ) -> EbsdInsertionState:
        """Drive the detector fully out. No-op if already retracted. Never interlocked."""
        ctl = self._sub("InsertionControl", "insertion control")
        with self._move_lock:
            s = self.insertion_state()
            if s.state in _RETRACTED and s.activity not in _MOVING:
                return s
            if not s.can_drive_out:
                raise DetectorError("%s cannot drive out now (%s)" % (self.name, s))
            log.info("%s: retracting", self.name)
            self._do("drive out", ctl.DriveOut)
            if not wait:
                return self.insertion_state()
            return self._wait_motion(
                "retract",
                self.insertion_state,
                done=lambda st: st.state in _RETRACTED and st.activity not in _MOVING,
                fault=lambda st: (
                    "detector reports FAULT"
                    if st.state == InsertionPositionState.FAULT
                    else None
                ),
                timeout=timeout,
                poll=poll_interval,
                stop=ctl.Stop,
                stopped=lambda st: st.activity == InsertionActivity.NOT_MOVING,
            )

    def move_to(
        self,
        position_mm: float,
        wait: bool = True,
        tolerance_mm: float = 0.1,
        timeout: Optional[float] = DEFAULT_MOTION_TIMEOUT_S,
        poll_interval: float = DEFAULT_POLL_S,
    ) -> EbsdInsertionState:
        """Move to an intermediate insertion position (mm)."""
        ctl = self._sub("InsertionControl", "insertion control")
        with self._move_lock:
            s = self.insertion_state()
            if not s.can_move_to:
                raise DetectorError(
                    "%s cannot move to a position now (%s)" % (self.name, s)
                )
            self._check_interlock("move_to")
            log.info("%s: moving to %.2f mm", self.name, position_mm)

            def go():
                ctl.TargetPosition = float(position_mm)
                ctl.MoveTo()

            self._do("move to %.2f mm" % position_mm, go)
            if not wait:
                return self.insertion_state()
            return self._wait_motion(
                "move_to(%.2f)" % position_mm,
                self.insertion_state,
                done=lambda st: (
                    st.activity not in _MOVING
                    and abs(st.position_mm - position_mm) <= tolerance_mm
                ),
                fault=self._ins_fault,
                timeout=timeout,
                poll=poll_interval,
                stop=ctl.Stop,
                stopped=lambda st: st.activity == InsertionActivity.NOT_MOVING,
            )

    def stop(self):
        """Stop insertion motion (and tilt, if fitted)."""
        if self.has_insertion_control:
            self._do("stop", self._ctrl.InsertionControl.Stop)
        if self.has_tilt_control:
            self._do("stop tilt", self._ctrl.TiltControl.Stop)

    # -- tilt / proximity -------------------------------------------------------------

    def tilt_to(
        self,
        position_mm: float,
        wait: bool = True,
        tolerance_mm: float = 0.1,
        timeout: Optional[float] = DEFAULT_MOTION_TIMEOUT_S,
        poll_interval: float = DEFAULT_POLL_S,
    ) -> EbsdTiltState:
        """Move the detector tilt/elevation to ``position_mm``."""
        ctl = self._sub("TiltControl", "tilt control")
        with self._move_lock:
            s = self.tilt_state()
            if not s.can_move_to:
                raise DetectorError(
                    "%s cannot tilt to a position now (%s)" % (self.name, s)
                )
            self._check_interlock("tilt")

            def go():
                ctl.TargetPosition = float(position_mm)
                ctl.MoveTo()

            self._do("tilt to %.2f mm" % position_mm, go)
            if not wait:
                return self.tilt_state()
            return self._wait_motion(
                "tilt_to(%.2f)" % position_mm,
                self.tilt_state,
                done=lambda st: (
                    st.activity == TiltActivity.NOT_MOVING
                    and abs(st.position_mm - position_mm) <= tolerance_mm
                ),
                fault=lambda st: (
                    "tilt FAULT" if st.state == TiltPositionState.FAULT else None
                ),
                timeout=timeout,
                poll=poll_interval,
                stop=ctl.Stop,
                stopped=lambda st: st.activity == TiltActivity.NOT_MOVING,
            )

    def set_proximity_sensor(self, enabled: bool):
        ctl = self._sub("ProximityControl", "proximity control")
        self._do(
            "enable proximity sensor" if enabled else "disable proximity sensor",
            ctl.Enable,
            bool(enabled),
        )


class EdsDetector(_Detector):
    """An EDS (ED) detector: insertion (in/out only) and thermal mode."""

    @property
    def has_insertion_control(self) -> bool:
        return getattr(self._ctrl, "InsertionControl", None) is not None

    @property
    def has_thermal_control(self) -> bool:
        return getattr(self._ctrl, "ThermalControl", None) is not None

    def insertion_state(self) -> EdInsertionState:
        ctl = self._sub("InsertionControl", "insertion control")
        s = self._do("read insertion state", lambda: ctl.State)
        return EdInsertionState(
            activity=coerce(InsertionActivity, s.Activity),
            state=coerce(InsertionPositionState, s.State),
            can_drive_in=bool(s.CanDriveIn),
            can_drive_out=bool(s.CanDriveOut),
            can_stop=bool(s.CanStop),
        )

    def thermal_state(self) -> EdThermalState:
        ctl = self._sub("ThermalControl", "thermal control")
        s = self._do("read thermal state", lambda: ctl.State)
        return EdThermalState(
            operating_mode=coerce(OperatingMode, s.OperatingMode),
            operating_state=coerce(OperatingState, s.OperatingState),
            vacuum_state=coerce(VacuumState, s.VacuumState),
            has_vacuum_sensor=bool(s.HasVacuumSensor),
            can_operate=bool(s.CanOperate),
            can_standby=bool(s.CanStandby),
        )

    @property
    def is_inserted(self) -> bool:
        return self.insertion_state().state == InsertionPositionState.IN

    @property
    def is_retracted(self) -> bool:
        return self.insertion_state().state in _RETRACTED

    def status(self) -> DetectorStatus:
        st = DetectorStatus(info=self.info)
        try:
            if self.has_insertion_control:
                st.insertion = self.insertion_state()
            if self.has_thermal_control:
                st.thermal = self.thermal_state()
        except Exception as e:
            st.error = str(e)
        return st

    def _fault(self, s: EdInsertionState) -> Optional[str]:
        if s.state == InsertionPositionState.FAULT:
            return "detector reports FAULT"
        if (
            s.state == InsertionPositionState.AUTO_RETRACTED
            or s.activity == InsertionActivity.AUTO_RETRACTING
        ):
            return "detector auto-retracted"
        return None

    def insert(
        self,
        wait: bool = True,
        timeout: Optional[float] = DEFAULT_MOTION_TIMEOUT_S,
        poll_interval: float = DEFAULT_POLL_S,
    ) -> EdInsertionState:
        ctl = self._sub("InsertionControl", "insertion control")
        with self._move_lock:
            s = self.insertion_state()
            if s.state == InsertionPositionState.IN and s.activity not in _MOVING:
                return s
            if not s.can_drive_in:
                raise DetectorError("%s cannot drive in now (%s)" % (self.name, s))
            self._check_interlock("insert")
            log.info("%s: inserting", self.name)
            self._do("drive in", ctl.DriveIn)
            if not wait:
                return self.insertion_state()
            return self._wait_motion(
                "insert",
                self.insertion_state,
                done=lambda st: (
                    st.state == InsertionPositionState.IN and st.activity not in _MOVING
                ),
                fault=self._fault,
                timeout=timeout,
                poll=poll_interval,
                stop=ctl.Stop,
                stopped=lambda st: st.activity == InsertionActivity.NOT_MOVING,
            )

    def retract(
        self,
        wait: bool = True,
        timeout: Optional[float] = DEFAULT_MOTION_TIMEOUT_S,
        poll_interval: float = DEFAULT_POLL_S,
    ) -> EdInsertionState:
        ctl = self._sub("InsertionControl", "insertion control")
        with self._move_lock:
            s = self.insertion_state()
            if s.state in _RETRACTED and s.activity not in _MOVING:
                return s
            if not s.can_drive_out:
                raise DetectorError("%s cannot drive out now (%s)" % (self.name, s))
            log.info("%s: retracting", self.name)
            self._do("drive out", ctl.DriveOut)
            if not wait:
                return self.insertion_state()
            return self._wait_motion(
                "retract",
                self.insertion_state,
                done=lambda st: st.state in _RETRACTED and st.activity not in _MOVING,
                fault=lambda st: (
                    "detector reports FAULT"
                    if st.state == InsertionPositionState.FAULT
                    else None
                ),
                timeout=timeout,
                poll=poll_interval,
                stop=ctl.Stop,
                stopped=lambda st: st.activity == InsertionActivity.NOT_MOVING,
            )

    def stop(self):
        self._do("stop", self._sub("InsertionControl", "insertion control").Stop)

    def enter_standby(self):
        """Put the detector in standby (thermal) mode."""
        self._do(
            "enter standby",
            self._sub("ThermalControl", "thermal control").EnterStandbyMode,
        )

    def enter_automatic(self):
        """Put the detector in automatic (operating) mode."""
        self._do(
            "enter automatic mode",
            self._sub("ThermalControl", "thermal control").EnterAutomaticMode,
        )

    def wait_for_operating_state(
        self,
        states=(OperatingState.COLD,),
        timeout: float = 600.0,
        poll_interval: float = 1.0,
    ) -> EdThermalState:
        """Block until the thermal operating state is one of ``states`` (default COLD)."""
        t0 = time.monotonic()
        while True:
            s = self.thermal_state()
            if s.operating_state in states:
                return s
            if s.operating_state == OperatingState.FAULT:
                raise DetectorError("%s thermal FAULT (%s)" % (self.name, s))
            if time.monotonic() - t0 > timeout:
                raise DetectorTimeoutError(
                    "%s did not reach %s within %.0f s (%s)"
                    % (self.name, [x.name for x in states], timeout, s)
                )
            time.sleep(poll_interval)


class DetectorManager:
    """Discovers detectors and hands out cached EbsdDetector / EdsDetector objects."""

    def __init__(self, session, interlock: Optional[Interlock] = None):
        self._session = session
        self._api = session.api
        self.interlock = interlock
        self._client = None
        self._cache: Dict[str, _Detector] = {}
        self._lock = threading.Lock()

    def _native(self):
        if self._client is None:
            native = self._session._require()
            with translate(self._api, DetectorError, "Get detector control client"):
                self._client = native.GetDetectorControlClient()
        return self._client

    def _idents(self, device_type: Optional[DeviceType]):
        client = self._native()
        with translate(self._api, DetectorError, "List detectors"):
            raw = (
                client.GetDevices()
                if device_type is None
                else client.GetDevices(self._api.to_net(device_type))
            )
            return [
                (
                    DetectorInfo(
                        str(d.ID), str(d.DisplayName), coerce(DeviceType, d.DeviceType)
                    ),
                    d,
                )
                for d in list(raw)
            ]

    def list(self, device_type: Optional[DeviceType] = None) -> List[DetectorInfo]:
        """All available detectors, optionally filtered by type."""
        return [info for info, _ in self._idents(device_type)]

    def _get(self, device_type: DeviceType, name: Optional[str]):
        with self._lock:
            found = self._idents(device_type)
            if name is not None:
                found = [f for f in found if name in (f[0].name, f[0].id)]
            if not found:
                raise DetectorNotFoundError(
                    "No %s detector%s available"
                    % (device_type.name, "" if name is None else " named %r" % name)
                )
            info, native_id = found[0]
            if info.id not in self._cache:
                client = self._native()
                with translate(self._api, DetectorError, "Open %s" % info.name):
                    if device_type == DeviceType.EBSD:
                        self._cache[info.id] = EbsdDetector(
                            self, info, native_id, client.Ebsd(native_id)
                        )
                    else:
                        self._cache[info.id] = EdsDetector(
                            self, info, native_id, client.Ed(native_id)
                        )
            return self._cache[info.id]

    def ebsd(self, name: Optional[str] = None) -> EbsdDetector:
        """The EBSD detector (first found, or by display name / ID)."""
        return self._get(DeviceType.EBSD, name)

    def eds(self, name: Optional[str] = None) -> EdsDetector:
        """The EDS detector (first found, or by display name / ID)."""
        return self._get(DeviceType.ED, name)

    def statuses(self) -> List[DetectorStatus]:
        out = []
        for info in self.list():
            try:
                det = (
                    self.ebsd(info.id)
                    if info.device_type == DeviceType.EBSD
                    else self.eds(info.id)
                )
                out.append(det.status())
            except Exception as e:
                out.append(DetectorStatus(info=info, error=str(e)))
        return out

    def retract_all(
        self, timeout: Optional[float] = DEFAULT_MOTION_TIMEOUT_S
    ) -> List[str]:
        """Retract every detector with insertion control. Returns error strings (empty = all OK).

        Meant for shutdown / emergency paths, so it keeps going after a failure.
        """
        errors = []
        for info in self.list():
            try:
                det = (
                    self.ebsd(info.id)
                    if info.device_type == DeviceType.EBSD
                    else self.eds(info.id)
                )
                if det.has_insertion_control:
                    det.retract(timeout=timeout)
            except Exception as e:
                errors.append("%s: %s" % (info.name, e))
        return errors

    def close(self):
        for det in self._cache.values():
            self._api.dispose(det._ctrl)
        self._cache.clear()
        if self._client is not None:
            self._api.dispose(self._client)
            self._client = None
