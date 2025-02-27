## python standard libraries
from pathlib import Path

# 3rd party libraries
import pytest

# Local
# import pytribeam.image as img
import pytribeam.types as tbt
import pytribeam.utilities as ut


def test_resolution():
    """Tests construction of resolution object"""
    cust_res = tbt.Resolution(width=5, height=7)
    preset_res = tbt.PresetResolution.PRESET_1024X884

    assert type(cust_res).__name__ == "Resolution"
    assert type(preset_res).__name__ == "PresetResolution"
    assert isinstance(preset_res, tbt.Resolution) == True
    assert cust_res.width == 5
    assert cust_res.height == 7
    assert cust_res.value == "5x7"
    assert preset_res.width == 1024
    assert preset_res.height == 884
    assert preset_res.value == "1024x884"


def ion_image(microscope: tbt.Microscope) -> tbt.ImageSettings:
    """helper function for test image"""
    return tbt.ImageSettings(
        microscope=microscope,
        beam=tbt.IonBeam(
            settings=tbt.BeamSettings(
                voltage_kv=30.0,
                voltage_tol_kv=1.0,
                current_na=51.0,
                current_tol_na=1.0,
                hfw_mm=1.75,
                working_dist_mm=4.096,
            ),
        ),
        detector=tbt.Detector(
            type=tbt.DetectorType.TLD,
            mode=tbt.DetectorMode.BACKSCATTER_ELECTRONS,
            brightness=0.5,
            contrast=0.5,
        ),
        scan=tbt.Scan(
            rotation_deg=0.0,
            dwell_time_us=1.0,
            resolution=tbt.Resolution(
                width=4,
                height=3,
            ),
        ),
        bit_depth=tbt.ColorDepth.BITS_8,
    )


def electron_image(microscope: tbt.Microscope) -> tbt.ImageSettings:
    """helper function for test image"""
    return tbt.ImageSettings(
        microscope=microscope,
        beam=tbt.ElectronBeam(
            settings=tbt.BeamSettings(
                voltage_kv=30.0,
                voltage_tol_kv=1.0,
                current_na=51.0,
                current_tol_na=1.0,
                hfw_mm=1.75,
                working_dist_mm=4.096,
            ),
        ),
        detector=tbt.Detector(
            type=tbt.DetectorType.TLD,
            mode=tbt.DetectorMode.BACKSCATTER_ELECTRONS,
            brightness=0.5,
            contrast=0.5,
        ),
        scan=tbt.Scan(
            rotation_deg=0.0,
            dwell_time_us=1.0,
            resolution=tbt.PresetResolution.PRESET_1024X884,
        ),
        bit_depth=tbt.ColorDepth.BITS_8,
    )


def test_image():
    """Tests construction of image object"""
    microscope = tbt.Microscope()
    aa = electron_image(microscope=microscope)

    assert type(aa).__name__ == "ImageSettings"
    assert aa.beam.type.value == "electron"
    assert aa.beam.type == tbt.BeamType.ELECTRON
    assert aa.scan.resolution.value == "1024x884"

    bb = ion_image(microscope=microscope)

    cc = tbt.Resolution(width=4, height=3)

    assert bb.beam.type.value == "ion"
    assert bb.beam.type == tbt.BeamType.ION
    assert bb.scan.resolution == cc
    assert bb.bit_depth.value == 8
    assert bb.detector.mode.value == "BackscatterElectrons"
    assert bb.detector.type.value == "TLD"
    assert bb.beam.device.value == 2
    assert bb.scan.resolution.value == "4x3"


def test_beam_type():
    """Tests if beam type is assigned corrected and property returned"""
    microscope = tbt.Microscope()
    default_settings = tbt.BeamSettings()

    e_beam = tbt.ElectronBeam(
        settings=default_settings,
    )
    assert e_beam.type == tbt.BeamType.ELECTRON
    assert e_beam.type.value == "electron"

    assert ut.beam_type(e_beam, microscope) == microscope.beams.electron_beam

    i_beam = tbt.IonBeam(
        settings=default_settings,
    )
    assert i_beam.type == tbt.BeamType.ION
    assert i_beam.type.value == "ion"
    assert ut.beam_type(i_beam, microscope) == microscope.beams.ion_beam
