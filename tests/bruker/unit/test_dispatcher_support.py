"""Bruker wrapper additions used by the external OEM dispatcher: map timing
settings, the image configuration setter, and per-map HDF5 output."""

import json
from copy import deepcopy

import h5py
import numpy as np
import pytest

from pytribeam.external_oem.bruker.config import parse_bruker_eds_config
from pytribeam.external_oem.bruker.h5_output import (
    BrukerElementMap,
    settings_record,
    write_eds_map_h5,
)
from pytribeam.external_oem.bruker.image_config import BrukerImageConfigController
from pytribeam.external_oem.bruker.types import BrukerEDSElementMapSetting

CONFIG = {
    "session": {"dll_dir": "C:/Esprit API", "password": "secret"},
    "output": {"root_dir": "C:/data", "run_name": "run"},
    "detector": {},
    "map": {
        "mode": "profile",
        "width_px": 4,
        "height_px": 3,
        "pixel_time_us": 100,
        "profile": {"elements": [{"atomic_number": 26}]},
    },
}


def config(**map_values):
    cfg = deepcopy(CONFIG)
    cfg["map"].update(map_values)
    return cfg


class TestMapTiming:
    @pytest.mark.parametrize("mode", ["profile", "simple"])
    def test_defaults_match_the_previous_hard_coded_values(self, mode):
        settings = parse_bruker_eds_config(config(mode=mode))

        assert settings.map.poll_interval_s == 0.5
        assert settings.map.max_wait_s == 600.0

    @pytest.mark.parametrize("mode", ["profile", "simple"])
    def test_configured_values_are_used(self, mode):
        """These keys were validated before but silently ignored."""
        settings = parse_bruker_eds_config(
            config(mode=mode, poll_interval_s=2.0, max_wait_s=3600.0)
        )

        assert settings.map.poll_interval_s == 2.0
        assert settings.map.max_wait_s == 3600.0


class _Func:
    def __init__(self, side_effect=None):
        self.calls = []
        self.side_effect = side_effect
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        return self.side_effect(*args) if self.side_effect else 0


class _AnyDll:
    """Fake DLL: every function exists; the two under test are recorded."""

    def __init__(self):
        self.ImageSetConfiguration = _Func()
        self.ImageGetConfiguration = _Func(self._get)

    def __getattr__(self, name):
        func = _Func()
        setattr(self, name, func)
        return func

    @staticmethod
    def _get(cid, width, height, average, ch1, ch2):
        width._obj.value, height._obj.value, average._obj.value = 4, 3, 7
        return 0


class _Session:
    def __init__(self):
        self.dll = _AnyDll()
        self.cid = 11

    def _check(self, rc, name):
        if rc != 0:
            raise RuntimeError(name)


def test_set_image_configuration_sets_then_reads_back():
    session = _Session()

    accepted = BrukerImageConfigController(session).set_image_configuration(4, 3, 100)

    assert session.dll.ImageSetConfiguration.calls == [(11, 4, 3, 100, True, False)]
    assert (accepted.width_px, accepted.height_px, accepted.average) == (4, 3, 7)


class TestH5Output:
    def write(self, path, **kwargs):
        settings = parse_bruker_eds_config(deepcopy(CONFIG))
        element = BrukerEDSElementMapSetting(atomic_number=26, line="KA")
        defaults = dict(
            settings=settings,
            element_maps=[BrukerElementMap(0, element, data=np.ones((3, 4), "uint16"))],
            slice_number=2,
            timestamp="20261117_120000",
        )
        return write_eds_map_h5(path, **{**defaults, **kwargs})

    def test_refuses_to_overwrite(self, tmp_path):
        path = self.write(tmp_path / "map.h5")

        with pytest.raises(FileExistsError):
            self.write(path)

    def test_creates_parent_folders(self, tmp_path):
        path = self.write(tmp_path / "a" / "b" / "map.h5")

        with h5py.File(path, "r") as f:
            assert f.attrs["schema_version"] == "1.0"
            assert f["eds/maps/00"].shape == (3, 4)

    def test_settings_record_removes_the_password(self):
        record = settings_record(parse_bruker_eds_config(deepcopy(CONFIG)))

        assert "password" not in record["session"]
        assert record["session"]["dll_dir"] == "C:/Esprit API"
        assert "secret" not in json.dumps(record)
