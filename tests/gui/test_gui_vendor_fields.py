"""Configurator rules for the external-detector (vendor) fields."""

import pytest

import pytribeam.GUI.CustomTkinterWidgets as ctk
from pytribeam.GUI.config_ui.lookup import get_lut

VERSION = 1.2


def vendor_fields():
    """(step type, key, field) for every vendor block field, general and per-step."""
    found = []
    for step_type in ("general", "ebsd", "eds"):
        lut = get_lut(step_type, VERSION)
        lut.flatten()
        for key in lut.keys():
            if key.split("/")[0] in {
                "EDAX_settings",
                "Oxford_settings",
                "Bruker_settings",
                "edax_settings",
                "bruker_settings",
            }:
                found.append((step_type, key, lut[key]))
    return found


def test_vendor_fields_exist():
    keys = {key for _, key, _ in vendor_fields()}
    assert "Bruker_settings/detector_index" in keys
    assert "bruker_settings/map/dwell_us" in keys


@pytest.mark.parametrize(
    "step_type, key, field",
    [f for f in vendor_fields() if f[2].widget is ctk.Checkbutton],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_checkboxes_start_unticked(step_type, key, field):
    """A checkbox the user never clicks must mean False."""
    assert field.default is False


@pytest.mark.parametrize(
    "step_type, key",
    [
        ("general", "Bruker_settings/mode"),
        ("general", "Bruker_settings/detector_index"),
        ("general", "EBSD_OEM"),
        ("general", "EDS_OEM"),
        ("ebsd", "edax_settings/grid_type"),
    ],
)
def test_fixed_choice_fields_are_dropdowns(step_type, key):
    lut = get_lut(step_type, VERSION)
    lut.flatten()
    field = lut[key]

    assert field.widget is ctk.MenuButton
    assert field.widget_kwargs["options"]


def test_bruker_is_offered_as_an_oem():
    lut = get_lut("general", VERSION)
    lut.flatten()
    for key in ("EBSD_OEM", "EDS_OEM"):
        assert "Bruker" in lut[key].widget_kwargs["options"]


def test_no_vendor_entry_holds_an_enumeration():
    """Entries are for free values; enumerations belong in dropdowns."""
    from enum import Enum

    for _, key, field in vendor_fields():
        if field.widget is ctk.Entry:
            assert not (
                isinstance(field.dtype, type) and issubclass(field.dtype, Enum)
            ), key
