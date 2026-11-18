"""Tests for parsing the ``Bruker_settings`` block of an experiment YAML."""

from copy import deepcopy

import pytest
from schema import SchemaError

from pytribeam.external_oem.bruker.config import (
    parse_bruker_ebsd_config,
    parse_bruker_eds_config,
    parse_bruker_settings,
)
from pytribeam.external_oem.bruker.types import (
    BrukerEBSDWorkflowSettings,
    BrukerEDSProfileMapSettings,
    BrukerEDSWorkflowSettings,
    BrukerSettings,
)

SESSION = {
    "dll_dir": "C:/Program Files/Bruker/Esprit API",
    "mode": "local",
    "user": "operator",
    "password": "secret",
}

EDS = {
    "output": {"root_dir": "C:/data/eds", "run_name": "eds_run"},
    "detector": {"detector_index": 1},
    "map": {
        "mode": "profile",
        "width_px": 64,
        "height_px": 48,
        "pixel_time_us": 1024,
        "profile": {"elements": [{"atomic_number": 26, "line": "KA"}]},
    },
}

EBSD = {
    "output": {"root_dir": "C:/data/ebsd"},
    "detector": {"inserted_position_mm": 20.0, "retracted_position_mm": 0.0},
    "acquisition": {
        "profile_name": "default",
        "width_px": 50,
        "height_px": 24,
        "pixel_time_us": 512,
    },
}


def block(**sections):
    """Return a Bruker_settings block with a session and the given sections."""
    return deepcopy({"session": SESSION, **sections})


class TestParseBrukerSettings:
    def test_eds_only(self):
        settings = parse_bruker_settings(block(eds=EDS))

        assert isinstance(settings, BrukerSettings)
        assert isinstance(settings.eds, BrukerEDSWorkflowSettings)
        assert isinstance(settings.eds.map, BrukerEDSProfileMapSettings)
        assert settings.ebsd is None

    def test_ebsd_only(self):
        settings = parse_bruker_settings(block(ebsd=EBSD))

        assert settings.eds is None
        assert isinstance(settings.ebsd, BrukerEBSDWorkflowSettings)
        assert settings.ebsd.profile_name == "default"
        assert settings.ebsd.detector.inserted_position_mm == 20.0
        assert settings.ebsd.output.run_name == "bruker_ebsd"

    def test_both_techniques_share_the_session(self):
        settings = parse_bruker_settings(block(eds=EDS, ebsd=EBSD))

        assert settings.session == settings.eds.session == settings.ebsd.session

    def test_credentials_come_from_the_block(self):
        """The password lives in the experiment YAML, like other vendor settings."""
        settings = parse_bruker_settings(block(eds=EDS))

        assert settings.session.user == "operator"
        assert settings.session.password == "secret"

    def test_a_nested_session_cannot_override_the_shared_one(self):
        eds = {**deepcopy(EDS), "session": {"dll_dir": "C:/elsewhere"}}

        settings = parse_bruker_settings(block(eds=eds))

        assert settings.eds.session.dll_dir == SESSION["dll_dir"]

    def test_eds_section_matches_the_standalone_parser(self):
        """The eds section is the standalone EDS YAML without its session."""
        from_block = parse_bruker_settings(block(eds=EDS)).eds
        standalone = parse_bruker_eds_config({"session": SESSION, **deepcopy(EDS)})

        assert from_block == standalone

    @pytest.mark.parametrize(
        "cfg, match",
        [
            (None, "mapping"),
            ({"eds": EDS}, "Bruker_settings.session"),
            ({"session": SESSION}, "'eds' and/or an 'ebsd'"),
            ({"session": SESSION, "eds": "not a mapping"}, "Bruker_settings.eds"),
            ({"session": {"mode": "local"}, "eds": EDS}, "session.dll_dir"),
        ],
    )
    def test_invalid_blocks_are_rejected(self, cfg, match):
        with pytest.raises(SchemaError, match=match):
            parse_bruker_settings(deepcopy(cfg))


class TestParseBrukerEbsdConfig:
    def config(self, **overrides):
        cfg = {"session": deepcopy(SESSION), **deepcopy(EBSD)}
        for section, values in overrides.items():
            cfg[section] = {**cfg[section], **values}
        return cfg

    def test_defaults(self):
        settings = parse_bruker_ebsd_config(self.config())

        assert settings.detector.speed_mm_per_s == 2.0
        assert settings.detector.tolerance_mm == 0.10
        assert settings.detector.stable_polls == 2
        assert settings.scan_area.width_px == 50
        assert settings.with_patterns is False

    def test_motion_overrides(self):
        settings = parse_bruker_ebsd_config(
            self.config(detector={"move_timeout_s": 30.0, "stable_polls": 4})
        )

        assert settings.detector.timeout_s == 30.0
        assert settings.detector.stable_polls == 4

    @pytest.mark.parametrize("key", ["inserted_position_mm", "retracted_position_mm"])
    def test_camera_positions_have_no_default(self, key):
        """Both positions must be measured on the instrument, never assumed."""
        cfg = self.config()
        del cfg["detector"][key]

        with pytest.raises(SchemaError, match=f"detector.{key}"):
            parse_bruker_ebsd_config(cfg)

    def test_positions_closer_than_the_tolerance_are_rejected(self):
        """Inserted and retracted would be indistinguishable."""
        cfg = self.config(
            detector={"inserted_position_mm": 0.05, "retracted_position_mm": 0.0}
        )

        with pytest.raises(SchemaError, match="differ by more than tolerance_mm"):
            parse_bruker_ebsd_config(cfg)

    @pytest.mark.parametrize(
        "section, values, match",
        [
            ("acquisition", {"profile_name": ""}, "acquisition.profile_name"),
            ("acquisition", {"width_px": 0}, "acquisition.width_px"),
            ("acquisition", {"with_patterns": "yes"}, "acquisition.with_patterns"),
            ("detector", {"speed_mm_per_s": -1.0}, "detector.speed_mm_per_s"),
            ("detector", {"inserted_position_mm": -1.0}, "inserted_position_mm"),
            ("output", {"root_dir": ""}, "output.root_dir"),
        ],
    )
    def test_invalid_values_are_rejected(self, section, values, match):
        with pytest.raises(SchemaError, match=match):
            parse_bruker_ebsd_config(self.config(**{section: values}))

    def test_missing_section_is_rejected(self):
        cfg = self.config()
        del cfg["acquisition"]

        with pytest.raises(SchemaError, match="acquisition"):
            parse_bruker_ebsd_config(cfg)
