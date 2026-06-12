import time
import ctypes as ct

from .bindings import bind_eds
from .ctypes_types import c_i32
from .session import BrukerSession
from .types import BrukerDetectorMotionSettings, BrukerDetectorPositionState

_POSITION_NAME_TO_CODE = {
    "park": 1,
    "acquire": 2,
}

_POSITION_CODE_TO_NAME = {
    1: "park",
    2: "acquire",
}


class BrukerDetectorMotionController:
    def __init__(self, session: BrukerSession):
        self._session = session
        bind_eds(self._session.dll)

    def get_eds_detector_position(
        self, detector_index: int
    ) -> BrukerDetectorPositionState:
        pos = c_i32(0)
        rc = self._session.dll.EDSGetDetectorPosition(
            self._session.cid, int(detector_index), ct.byref(pos)
        )
        self._session._check(rc, "EDSGetDetectorPosition")

        position_code = int(pos.value)
        position_name = _POSITION_CODE_TO_NAME.get(position_code, "unknown")

        return BrukerDetectorPositionState(
            detector_index=detector_index,
            position_code=position_code,
            position_name=position_name,
        )

    def move_eds_detector(
        self, settings: BrukerDetectorMotionSettings
    ) -> BrukerDetectorPositionState:
        target_code = _POSITION_NAME_TO_CODE[settings.target_position]

        rc = self._session.dll.EDSSetDetectorPosition(
            self._session.cid,
            int(settings.detector_index),
            int(target_code),
        )
        self._session._check(rc, "EDSSetDetectorPosition")

        t0 = time.time()
        while True:
            state = self.get_eds_detector_position(settings.detector_index)
            if state.position_code == target_code:
                return state

            if (time.time() - t0) > settings.timeout_s:
                raise TimeoutError(
                    f"EDS detector {settings.detector_index} did not reach {settings.target_position}"
                )

            time.sleep(settings.poll_interval_s)
