## python standard libraries
from pathlib import Path
import platform
import time
import warnings
from enum import Enum

# 3rd party libraries
import pytest
from PIL import Image as pil_img
import numpy as np
from skimage import filters, measure
import cv2

# Local
import pytribeam.constants as cs
from pytribeam.constants import Conversions, Constants
import pytribeam.insertable_devices as devices
import pytribeam.image as img
import pytribeam.factory as factory
import pytribeam.stage as stage
import pytribeam.types as tbt
import pytribeam.utilities as ut
import pytribeam.fib as fib


@pytest.fixture
def test_dir() -> str:
    """The relative path and file string locating the default yml test file."""

    return Path(__file__).parent.joinpath("files")


# @ut.run_on_standalone_machine
def test_shutter_mode():
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    shutter = microscope.beams.electron_beam.protective_shutter
    shutter.mode.value = tbt.ProtectiveShutterMode.OFF
    status = shutter.mode.value
    assert status == tbt.ProtectiveShutterMode.OFF == "Off"

    fib.shutter_control(microscope=microscope)
    new_status = shutter.mode.value
    assert new_status == tbt.ProtectiveShutterMode.AUTOMATIC == "Automatic"

    microscope.disconnect()


def ion_image(microscope: tbt.Microscope) -> tbt.ImageSettings:
    """helper function for test image"""
    return tbt.ImageSettings(
        microscope=microscope,
        beam=tbt.IonBeam(
            settings=tbt.BeamSettings(
                voltage_kv=5.0,
                voltage_tol_kv=0.5,
                current_na=5.0,
                current_tol_na=0.5,
                hfw_mm=0.75,
                working_dist_mm=10.021,
            ),
        ),
        detector=tbt.Detector(
            type=tbt.DetectorType.ETD,
            mode=tbt.DetectorMode.SECONDARY_ELECTRONS,
            brightness=0.2,
            contrast=0.3,
        ),
        scan=tbt.Scan(
            rotation_deg=0.0,
            dwell_time_us=1.0,
            resolution=tbt.PresetResolution.PRESET_768X512,
        ),
        bit_depth=tbt.ColorDepth.BITS_8,
    )


def mill_beam() -> tbt.Beam:
    return tbt.IonBeam(
        settings=tbt.BeamSettings(
            voltage_kv=30.0,
            voltage_tol_kv=1.5,
            current_na=51.0,
            current_tol_na=1.0,
            hfw_mm=0.75,
            working_dist_mm=15.001,
        ),
    )


def rectangle_pattern(microscope: tbt.Microscope):
    return tbt.FIBSettings(
        microscope=microscope,
        image=ion_image(microscope=microscope),
        mill_beam=mill_beam(),
        pattern=tbt.FIBPattern(
            application=tbt.FIBApplication.SI,
            type=tbt.FIBPatternType.RECTANGLE,
            geometry=tbt.FIBRectanglePattern(
                center_um=tbt.Point(
                    x=5.11,
                    y=0.0,
                ),
                width_um=500.0,
                height_um=40.0,
                depth_um=5.0,
                scan_direction=tbt.FIBPatternScanDirection.TOP_TO_BOTTOM,
                scan_type=tbt.FIBPatternScanType.RASTER,
            ),
        ),
    )


def regular_cross_section_pattern(microscope: tbt.Microscope):
    return tbt.FIBSettings(
        microscope=microscope,
        image=ion_image(microscope=microscope),
        mill_beam=mill_beam(),
        pattern=tbt.FIBPattern(
            application=tbt.FIBApplication.AL,
            type=tbt.FIBPatternType.REGULAR_CROSS_SECTION,
            geometry=tbt.FIBRegularCrossSection(
                center_um=tbt.Point(
                    x=5.11,
                    y=0.0,
                ),
                width_um=500.0,
                height_um=40.0,
                depth_um=5.0,
                scan_direction=tbt.FIBPatternScanDirection.TOP_TO_BOTTOM,
                scan_type=tbt.FIBPatternScanType.RASTER,
            ),
        ),
    )


def cleaning_cross_section_pattern(microscope: tbt.Microscope):
    return tbt.FIBSettings(
        microscope=microscope,
        image=ion_image(microscope=microscope),
        mill_beam=mill_beam(),
        pattern=tbt.FIBPattern(
            application=tbt.FIBApplication.AL,
            type=tbt.FIBPatternType.CLEANING_CROSS_SECTION,
            geometry=tbt.FIBCleaningCrossSection(
                center_um=tbt.Point(
                    x=5.11,
                    y=0.0,
                ),
                width_um=500.0,
                height_um=40.0,
                depth_um=5.0,
                scan_direction=tbt.FIBPatternScanDirection.TOP_TO_BOTTOM,
                scan_type=tbt.FIBPatternScanType.RASTER,
            ),
        ),
    )


# @ut.run_on_standalone_machine
def test_prepare_milling():
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    fib_settings = rectangle_pattern(microscope=microscope)
    fib.prepare_milling(
        microscope=microscope,
        application=fib_settings.pattern.application,
    )

    class dummy_enum(Enum):
        INVALID: str = "invalid"

    with pytest.raises(ValueError) as err:
        fib.prepare_milling(microscope=microscope, application=dummy_enum.INVALID)
    assert err.type == ValueError
    assert (
        err.value.args[0]
        == f"Invalid application file on this system, there is not patterning application with name: 'invalid'."
    )
    microscope.patterning.clear_patterns()
    microscope.disconnect()


def validate_box_pattern(pattern: tbt.FIBBoxPattern, fib_settings: tbt.FIBSettings):
    assert pattern.scan_direction == fib_settings.pattern.geometry.scan_direction.value
    assert pattern.scan_type == fib_settings.pattern.geometry.scan_type.value
    assert pattern.application_file == fib_settings.pattern.application.value
    assert pattern.center_x == pytest.approx(
        fib_settings.pattern.geometry.center_um.x * Conversions.UM_TO_M,
        abs=0.005,
    )
    assert pattern.center_y == pytest.approx(
        fib_settings.pattern.geometry.center_um.y * Conversions.UM_TO_M,
        abs=0.005,
    )
    assert pattern.depth == pytest.approx(
        fib_settings.pattern.geometry.depth_um * Conversions.UM_TO_M,
        abs=0.005,
    )
    assert pattern.width == pytest.approx(
        fib_settings.pattern.geometry.width_um * Conversions.UM_TO_M,
        abs=0.005,
    )
    assert pattern.height == pytest.approx(
        fib_settings.pattern.geometry.height_um * Conversions.UM_TO_M,
        abs=0.005,
    )
    return


# @ut.run_on_standalone_machine
def test_create_rectangle_pattern():
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    # rectangle pattern
    fib_settings = rectangle_pattern(microscope=microscope)
    fib.prepare_milling(
        microscope=microscope,
        application=fib_settings.pattern.application,
    )
    pattern = fib.create_pattern(
        fib_settings.pattern.geometry,
        microscope=microscope,
    )
    assert isinstance(pattern, tbt.as_dynamics.RectanglePattern)
    validate_box_pattern(pattern, fib_settings)
    microscope.patterning.clear_patterns()
    microscope.disconnect()


# @ut.run_on_standalone_machine
def test_create_regular_cross_section_pattern():
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    # pattern
    fib_settings = regular_cross_section_pattern(microscope=microscope)
    fib.prepare_milling(
        microscope=microscope,
        application=fib_settings.pattern.application,
    )
    pattern = fib.create_pattern(
        fib_settings.pattern.geometry,
        microscope=microscope,
    )
    assert isinstance(pattern, tbt.as_dynamics.RegularCrossSectionPattern)
    validate_box_pattern(pattern, fib_settings)
    microscope.patterning.clear_patterns()
    microscope.disconnect()


# @ut.run_on_standalone_machine
def test_create_cleaning_cross_section_pattern():
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    # pattern
    fib_settings = cleaning_cross_section_pattern(microscope=microscope)
    fib.prepare_milling(
        microscope=microscope,
        application=fib_settings.pattern.application,
    )
    pattern = fib.create_pattern(
        fib_settings.pattern.geometry,
        microscope=microscope,
        # input_image_path=None,
    )
    assert isinstance(pattern, tbt.as_dynamics.CleaningCrossSectionPattern)
    validate_box_pattern(pattern, fib_settings)
    microscope.patterning.clear_patterns()
    microscope.disconnect()


def process_image(in_path: Path, out_path: Path):
    """Helper function to generate mask for fib stream pattern"""
    with pil_img.open(in_path) as test_img:
        # threshold
        fib_img = np.asarray(test_img)
        threshold = filters.threshold_otsu(fib_img)
        segmented = fib_img > threshold

    # label connected components
    labeled_img, num_features = measure.label(
        segmented,
        return_num=True,
        connectivity=1,
    )

    # find largest componet:
    largest = None
    max_size = 0
    for component in range(1, num_features + 1):
        size = np.sum(labeled_img == component)
        if size > max_size:
            max_size = size
            largest = component

    # mask largest component
    mask = labeled_img == largest

    # write out image
    mask = pil_img.fromarray(mask)
    mask.save(out_path)


def stream_pattern(
    microscope: tbt.Microscope,
    recipe_path: Path,
    mask_path: Path,
):

    return tbt.FIBSettings(
        microscope=microscope,
        image=ion_image(microscope=microscope),
        mill_beam=mill_beam(),
        pattern=tbt.FIBPattern(
            application=tbt.FIBApplication.SI,
            type=tbt.FIBPatternType.SELECTED_AREA,
            geometry=tbt.FIBStreamPattern(
                dwell_us=1.0,
                repeats=3,
                recipe_file=recipe_path,
                mask_file=mask_path,
            ),
        ),
    )


def test_create_stream_pattern():
    microscope = tbt.Microscope()
    microscope.connect("localhost")

    test_dir = Path(__file__).parent.joinpath("files")
    mask_path = test_dir.joinpath("fib_mask_test.tif")
    recipe_path = test_dir.joinpath("fib_stream_recipe.py")
    img_path = test_dir.joinpath("fib_image.tif")

    # pattern
    fib_settings = stream_pattern(
        microscope=microscope, recipe_path=recipe_path, mask_path=mask_path
    )
    fib.prepare_milling(
        microscope=microscope,
        application=fib_settings.pattern.application,
    )
    pattern = fib.create_pattern(
        fib_settings.pattern.geometry,
        microscope=microscope,
        kwargs={"input_image_path": img_path},
    )
    assert isinstance(pattern, tbt.as_dynamics.StreamPattern)

    mask_path.unlink()

    microscope.patterning.clear_patterns()
    microscope.disconnect()
