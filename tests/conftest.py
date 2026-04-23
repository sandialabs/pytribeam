# conftest.py
"""
Shared pytest configuration for the pytribeam test suite.

Test capability tiers:

- detached:
    Always runnable. Does not require AutoScript or hardware.
- simulated:
    Runs only on simulated/offline microscope systems.
- hardware:
    Runs only on physical hardware systems, including laser and non-laser.
- laser_hardware:
    Runs only on physical hardware systems with a laser subsystem.

"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import platform
from typing import Iterable, Any
import textwrap

import pytest
import yaml
from PIL import Image, ImageDraw

import pytribeam.constants as cs
import pytribeam.utilities as ut


# ----------------------------------------------------------------------
# Shared fixtures
# ----------------------------------------------------------------------
@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the repository root."""
    return Path(__file__).resolve().parent


@pytest.fixture
def test_dir(request) -> Path:
    """Return the ``files`` directory adjacent to the requesting test module."""
    return Path(request.fspath).parent / "files"


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Return a pytest-managed temporary directory."""
    return tmp_path


# ----------------------------------------------------------------------
# Environment detection
# ----------------------------------------------------------------------
def _node_name() -> str:
    """Return the current hostname in normalized form."""
    return platform.uname().node.lower()


def _matches_machine_list(machine_names: Iterable[str]) -> bool:
    """Return True if the current hostname matches any configured machine name."""
    node = _node_name()
    return any(node in machine.lower() or machine.lower() in node for machine in machine_names)


def is_simulated_system() -> bool:
    """Return True if running on a configured simulated/offline microscope system."""
    return _matches_machine_list(cs.Constants.offline_machines)


def is_hardware_system() -> bool:
    """Return True if running on a configured physical microscope system."""
    return _matches_machine_list(cs.Constants.microscope_machines)


def has_laser_hardware() -> bool:
    """Return True if the current environment has laser hardware available."""
    return ut.is_laser_available()


CAN_RUN_DETACHED = True
CAN_RUN_SIMULATED = is_simulated_system()
CAN_RUN_HARDWARE = is_hardware_system()
CAN_RUN_LASER_HARDWARE = is_hardware_system() and has_laser_hardware()

SIMULATED_ONLY_REASON = "requires a simulated microscope environment"
HARDWARE_ONLY_REASON = "requires physical microscope hardware"
LASER_HARDWARE_ONLY_REASON = "requires physical microscope hardware with laser support"


def pytest_collection_modifyitems(config, items):
    """Skip marked tests automatically based on the current environment."""
    skip_simulated = pytest.mark.skip(reason=SIMULATED_ONLY_REASON)
    skip_hardware = pytest.mark.skip(reason=HARDWARE_ONLY_REASON)
    skip_laser_hardware = pytest.mark.skip(reason=LASER_HARDWARE_ONLY_REASON)

    for item in items:
        if "simulated" in item.keywords and not CAN_RUN_SIMULATED:
            item.add_marker(skip_simulated)

        if "hardware" in item.keywords and not CAN_RUN_HARDWARE:
            item.add_marker(skip_hardware)

        if "laser_hardware" in item.keywords and not CAN_RUN_LASER_HARDWARE:
            item.add_marker(skip_laser_hardware)


# ----------------------------------------------------------------------
# YAML config builders
# ----------------------------------------------------------------------
def _base_general(
    *,
    exp_dir: str | None = None,
    step_count: int = 1,
    max_slice_num: int = 400,
    ebsd_oem: str | None = "Oxford",
    eds_oem: str | None = "Oxford",
    h5_log_name: str = "log",
) -> dict[str, Any]:
    return {
        "slice_thickness_um": 2.0,
        "max_slice_num": max_slice_num,
        "pre_tilt_deg": 36.0,
        "sectioning_axis": "Z",
        "stage_translational_tol_um": 0.5,
        "stage_angular_tol_deg": 0.02,
        "connection_host": "localhost",
        "connection_port": None,
        "EBSD_OEM": ebsd_oem,
        "EDS_OEM": eds_oem,
        "exp_dir": exp_dir,
        "h5_log_name": h5_log_name,
        "step_count": step_count,
    }


def _base_stage(
    *,
    x_mm: float = 1.0,
    y_mm: float = 2.0,
    z_mm: float = 5.0,
    r_deg: float = -50.0,
    t_deg: float = 0.0,
    rotation_side: str = "fsl_mill",
) -> dict[str, Any]:
    return {
        "rotation_side": rotation_side,
        "initial_position": {
            "x_mm": x_mm,
            "y_mm": y_mm,
            "z_mm": z_mm,
            "r_deg": r_deg,
            "t_deg": t_deg,
        },
    }


def _image_step(
    *,
    step_name: str = "image_test",
    step_number: int = 1,
    beam_type: str = "electron",
    voltage_kv: float = 5.0,
    voltage_tol_kv: float = 0.5,
    current_na: float = 5.0,
    current_tol_na: float = 0.5,
    hfw_mm: float = 0.9,
    working_dist_mm: float = 4.093,
    dynamic_focus: bool = False,
    tilt_correction: bool = False,
    detector_type: str = "ETD",
    detector_mode: str = "SecondaryElectrons",
    brightness: float | None = 0.2,
    contrast: float | None = 0.3,
    auto_cb: dict[str, Any] | None = None,
    rotation_deg: float = 180.0,
    dwell_time_us: float = 1.0,
    resolution: str = "768x512",
    bit_depth: int = 8,
    stage: dict[str, Any] | None = None,
    frequency: int = 1,
) -> dict[str, Any]:
    if auto_cb is None:
        auto_cb = {
            "left": None,
            "top": None,
            "width": None,
            "height": None,
        }

    if stage is None:
        stage = _base_stage()

    return {
        step_name: {
            "step_general": {
                "step_number": step_number,
                "step_type": "image",
                "frequency": frequency,
                "stage": stage,
            },
            "beam": {
                "type": beam_type,
                "voltage_kv": voltage_kv,
                "voltage_tol_kv": voltage_tol_kv,
                "current_na": current_na,
                "current_tol_na": current_tol_na,
                "hfw_mm": hfw_mm,
                "working_dist_mm": working_dist_mm,
                "dynamic_focus": dynamic_focus,
                "tilt_correction": tilt_correction,
            },
            "detector": {
                "type": detector_type,
                "mode": detector_mode,
                "brightness": brightness,
                "contrast": contrast,
                "auto_cb": auto_cb,
            },
            "scan": {
                "rotation_deg": rotation_deg,
                "dwell_time_us": dwell_time_us,
                "resolution": resolution,
            },
            "bit_depth": bit_depth,
        }
    }


def _write_yaml(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)
    return path


def _full_config(*, general: dict[str, Any], steps: dict[str, Any]) -> dict[str, Any]:
    return {
        "config_file_version": 1.0,
        "general": general,
        "steps": steps,
    }


# ----------------------------------------------------------------------
# Named config definitions
# ----------------------------------------------------------------------
def build_named_config(name: str, *, exp_dir: str | None = None) -> dict[str, Any]:
    """Return one of the legacy test configs as a Python dictionary."""
    if name == "image_config.yml":
        return _full_config(
            general=_base_general(exp_dir=exp_dir or "./"),
            steps=_image_step(),
        )

    if name == "general_config.yml":
        return _full_config(
            general=_base_general(exp_dir=exp_dir, ebsd_oem=None, eds_oem=None),
            steps=_image_step(),
        )

    if name == "image_config_custom_resolution.yml":
        return _full_config(
            general=_base_general(exp_dir=exp_dir),
            steps=_image_step(
                voltage_kv=10.0,
                voltage_tol_kv=2.0,
                resolution="400x800",
            ),
        )

    if name == "image_insertable_config.yml":
        step = _image_step(
            beam_type="electron",
            voltage_kv=5.0,
            voltage_tol_kv=2.0,
            current_na=0.1,
            current_tol_na=0.02,
            dynamic_focus=True,
            tilt_correction=False,
            detector_type="CBS",
            detector_mode="All",
            brightness=None,
            contrast=None,
            auto_cb={
                "left": 0.3,
                "top": 0.3,
                "width": 0.4,
                "height": 0.4,
            },
            rotation_deg=0.0,
            resolution="3072x2048",
        )
        step["image_test"]["scan"]["mode"] = 1
        return _full_config(
            general=_base_general(exp_dir=exp_dir or "./"),
            steps=step,
        )

    if name == "ebsd_config.yml":
        steps = {
            "ebsd_test": {
                "step_general": {
                    "step_number": 1,
                    "step_type": "ebsd",
                    "frequency": 1,
                    "stage": _base_stage(),
                },
                "concurrent_EDS": True,
                "beam": {
                    "type": "electron",
                    "voltage_kv": 5.0,
                    "voltage_tol_kv": 0.5,
                    "current_na": 5.0,
                    "current_tol_na": 0.5,
                    "hfw_mm": 0.9,
                    "working_dist_mm": 4.093,
                    "dynamic_focus": True,
                    "tilt_correction": True,
                },
                "detector": {
                    "type": "ETD",
                    "mode": "SecondaryElectrons",
                    "brightness": 0.2,
                    "contrast": 0.3,
                    "auto_cb": {
                        "left": None,
                        "top": None,
                        "width": None,
                        "height": None,
                    },
                },
                "scan": {
                    "rotation_deg": 0.0,
                    "dwell_time_us": 1.0,
                    "resolution": "768x512",
                },
                "bit_depth": 8,
            }
        }
        return _full_config(
            general=_base_general(exp_dir=exp_dir),
            steps=steps,
        )

    if name == "fib_config.yml":
        steps = {
            "fib_test": {
                "step_general": {
                    "step_number": 1,
                    "step_type": "fib",
                    "frequency": 1,
                    "stage": _base_stage(),
                },
                "image": {
                    "beam": {
                        "type": "ion",
                        "voltage_kv": 5.0,
                        "voltage_tol_kv": 0.5,
                        "current_na": 5.0,
                        "current_tol_na": 0.5,
                        "hfw_mm": 0.75,
                        "working_dist_mm": 10.021,
                        "dynamic_focus": None,
                        "tilt_correction": None,
                    },
                    "detector": {
                        "type": "ETD",
                        "mode": "SecondaryElectrons",
                        "brightness": 0.2,
                        "contrast": 0.3,
                        "auto_cb": {
                            "left": None,
                            "top": None,
                            "width": None,
                            "height": None,
                        },
                    },
                    "scan": {
                        "rotation_deg": 0.0,
                        "dwell_time_us": 1.0,
                        "resolution": "768x512",
                    },
                    "bit_depth": 8,
                },
                "mill": {
                    "beam": {
                        "type": "ion",
                        "voltage_kv": 30.0,
                        "voltage_tol_kv": 1.0,
                        "current_na": 12.0,
                        "current_tol_na": 1.0,
                        "hfw_mm": 0.75,
                        "working_dist_mm": 15.001,
                        "dynamic_focus": None,
                        "tilt_correction": None,
                    },
                    "pattern": {
                        "application_file": "Al",
                        "type": {
                            "rectangle": {
                                "center": {
                                    "x_um": 5.11,
                                    "y_um": 0.0,
                                },
                                "width_um": 500.0,
                                "height_um": 40.0,
                                "depth_um": 5.0,
                                "scan_direction": "BottomToTop",
                                "scan_type": "Serpentine",
                            },
                            "regular_cross_section": {
                                "center": {"x_um": None, "y_um": None},
                                "width_um": None,
                                "height_um": None,
                                "depth_um": None,
                                "scan_direction": None,
                                "scan_type": None,
                            },
                            "cleaning_cross_section": {
                                "center": {"x_um": None, "y_um": None},
                                "width_um": None,
                                "height_um": None,
                                "depth_um": None,
                                "scan_direction": None,
                                "scan_type": None,
                            },
                            "selected_area": {
                                "dwell_us": None,
                                "repeats": None,
                                "recipe_file": None,
                                "mask_file": None,
                            },
                        },
                    },
                },
            }
        }
        return _full_config(
            general=_base_general(exp_dir=exp_dir),
            steps=steps,
        )

    if name == "laser_config.yml":
        steps = {
            "laser_test": {
                "step_general": {
                    "step_number": 1,
                    "step_type": "laser",
                    "frequency": 1,
                    "stage": _base_stage(
                        x_mm=0.0,
                        y_mm=0.0,
                        z_mm=0.0,
                        r_deg=0.0,
                        t_deg=30.0,
                    ),
                },
                "pulse": {
                    "wavelength_nm": 515,
                    "divider": 2,
                    "energy_uj": 5.0,
                    "polarization": "vertical",
                },
                "objective_position_mm": 2.5,
                "beam_shift": {
                    "x_um": 0.0,
                    "y_um": 0.0,
                },
                "pattern": {
                    "type": {
                        "box": {
                            "passes": 3,
                            "size_x_um": 200.0,
                            "size_y_um": 100.0,
                            "pitch_x_um": 2.0,
                            "pitch_y_um": 3.0,
                            "scan_type": "serpentine",
                            "coordinate_ref": "uppercenter",
                        },
                        "line": {
                            "passes": None,
                            "size_um": None,
                            "pitch_um": None,
                            "scan_type": None,
                        },
                    },
                    "rotation_deg": 0.0,
                    "mode": "fine",
                    "pulses_per_pixel": 2,
                    "pixel_dwell_ms": None,
                },
            }
        }
        return _full_config(
            general=_base_general(exp_dir=exp_dir),
            steps=steps,
        )

    if name == "custom_config.yml":
        steps = {
            "custom_test": {
                "step_general": {
                    "step_number": 1,
                    "step_type": "custom",
                    "frequency": 1,
                    "stage": _base_stage(),
                },
                "script_path": None,
                "executable_path": "C:/Program Files/Enthought/Python/envs/AutoScript/python.exe",
            }
        }
        return _full_config(
            general=_base_general(
                exp_dir=exp_dir,
                max_slice_num=2,
                ebsd_oem=None,
                eds_oem=None,
            ),
            steps=steps,
        )

    if name == "image_test_exp.yml":
        step1 = _image_step(step_name="image_test", step_number=1)
        step2 = _image_step(
            step_name="image_test2",
            step_number=2,
            stage=_base_stage(
                x_mm=1.0,
                y_mm=2.0,
                z_mm=5.0,
                r_deg=0.0,
                t_deg=30.0,
            ),
        )
        return _full_config(
            general=_base_general(
                exp_dir=exp_dir,
                step_count=2,
                max_slice_num=2,
                ebsd_oem=None,
                eds_oem=None,
            ),
            steps={**step1, **step2},
        )

    if name == "test_config.yml":
        return {
            "config_file_version": 1.0,
            "general": {
                "slice_thickness_um": 2.0,
                "max_slice_num": 400,
            },
            "image_test": {
                "step_type": "image",
                "beam_type": "electron",
                "auto_cb": True,
                "dwell_time_us": 0.45,
            },
        }

    raise KeyError(f"Unknown test config template: {name}")


# ----------------------------------------------------------------------
# Config fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Directory containing generated YAML test configs."""
    path = tmp_path / "generated_configs"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def config_factory(config_dir: Path):
    """Return a factory that writes named YAML configs into a temp directory.

    Example
    -------
    .. code-block:: python

        def test_something(config_factory):
            path = config_factory("image_config.yml")
    """
    def _factory(name: str, *, exp_dir: str | None = None, overrides: dict[str, Any] | None = None) -> Path:
        resolved_exp_dir = exp_dir if exp_dir is not None else str(config_dir)
        data = build_named_config(name, exp_dir=resolved_exp_dir)
        if overrides:
            data = _deep_update(data, overrides)
        return _write_yaml(config_dir / name, data)

    return _factory


@pytest.fixture
def generated_configs(config_factory) -> dict[str, Path]:
    """Generate all currently used YAML test configs and return a name-to-path map."""
    names = [
        "custom_config.yml",
        "ebsd_config.yml",
        "fib_config.yml",
        "general_config.yml",
        "image_config.yml",
        "image_config_custom_resolution.yml",
        "image_insertable_config.yml",
        "image_test_exp.yml",
        "laser_config.yml",
        "test_config.yml",
    ]
    return {name: config_factory(name) for name in names}


def _deep_update(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Recursively update a nested dictionary."""
    result = deepcopy(base)
    for key, value in updates.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_update(result[key], value)
        else:
            result[key] = value
    return result



# ----------------------------------------------------------------------
# FIB stream fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def fib_stream_input_image(tmp_path: Path) -> Path:
    """Create a simple grayscale input image with a bright circular region."""
    path = tmp_path / "fib_image.tif"

    size = (256, 256)
    image = Image.new("L", size, color=0)

    draw = ImageDraw.Draw(image)
    draw.ellipse((64, 64, 192, 192), fill=220)

    image.save(path)
    return path


@pytest.fixture
def fib_stream_mask_path(tmp_path: Path) -> Path:
    """Return the output mask path to be created by the stream recipe."""
    return tmp_path / "fib_mask_test.tif"


@pytest.fixture
def fib_stream_recipe_path(tmp_path: Path) -> Path:
    """Create a FIB stream recipe script that generates a mask from an input image."""
    path = tmp_path / "fib_stream_recipe.py"
    path.write_text(
        textwrap.dedent(
            """\
            from pathlib import Path
            import sys

            from PIL import Image as pil_img
            import numpy as np
            from skimage import filters, measure


            def process_image(input_path: Path, output_path: Path):
                with pil_img.open(input_path) as test_img:
                    fib_img = np.asarray(test_img)
                    threshold = filters.threshold_otsu(fib_img)
                    segmented = fib_img > threshold

                labeled_img, num_features = measure.label(
                    segmented,
                    return_num=True,
                    connectivity=1,
                )

                largest = None
                max_size = 0
                for component in range(1, num_features + 1):
                    size = np.sum(labeled_img == component)
                    if size > max_size:
                        max_size = size
                        largest = component

                mask = labeled_img == largest
                mask = pil_img.fromarray(mask)
                mask.save(output_path)


            if __name__ == "__main__":
                input_path = Path(sys.argv[1])
                output_path = Path(sys.argv[2])

                process_image(
                    input_path=input_path,
                    output_path=output_path,
                )
            """
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def fib_stream_assets(
    fib_stream_input_image: Path,
    fib_stream_recipe_path: Path,
    fib_stream_mask_path: Path,
) -> dict[str, Path]:
    """Return all generated assets required for FIB stream pattern tests."""
    return {
        "input_image": fib_stream_input_image,
        "recipe": fib_stream_recipe_path,
        "mask": fib_stream_mask_path,
    }
