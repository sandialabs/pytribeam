"""Fixtures for the external OEM adapter tests."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest


@pytest.fixture
def chamber(monkeypatch):
    """Intercept the chamber CCD view and the detector collision check.

    ``chamber.events`` records "ccd_on" / "ccd_off" around every guarded move,
    so tests can check motion happened inside the CCD view. Set
    ``chamber.collide = True`` to make the collision check refuse an insert.
    """
    import pytribeam.insertable_devices as devices

    state = SimpleNamespace(events=[], collide=False, checked=[])

    @contextmanager
    def ccd_live_view(microscope, **kwargs):
        state.events.append("ccd_on")
        try:
            yield
        finally:
            state.events.append("ccd_off")

    def detectors_will_collide(microscope, detector_to_insert):
        state.checked.append(detector_to_insert)
        return state.collide

    monkeypatch.setattr(devices, "ccd_live_view", ccd_live_view)
    monkeypatch.setattr(devices, "detectors_will_collide", detectors_will_collide)
    return state
