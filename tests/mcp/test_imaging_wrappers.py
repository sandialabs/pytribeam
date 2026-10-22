"""The thin pytribeam wrappers in ``imaging`` (``_validate``, ``_collect``),
run against stand-in pytribeam modules. No AutoScript.

``test_imaging.py`` replaces these wrappers wholesale, so it cannot catch a
wrong assumption about what pytribeam passes them. These tests run the real
wrappers on the types pytribeam actually produces, e.g. ``factory.image``
returning ``bit_depth`` as a plain int.
"""

## python standard libraries
import sys
import types
from enum import Enum, IntEnum
from typing import NamedTuple

# 3rd party libraries
import pytest

pytest.importorskip("mcp")  # the mcp extra needs Python >= 3.10

pytestmark = pytest.mark.detached


class ColorDepth(IntEnum):
    BITS_8 = 8
    BITS_16 = 16


class Resolution(NamedTuple):
    width: int
    height: int

    @property
    def value(self):
        return f"{self.width}x{self.height}"


class PresetResolution(Resolution, Enum):
    PRESET_768X512 = Resolution(768, 512)


class Scan(NamedTuple):
    resolution: object


class ImageSettings(NamedTuple):
    scan: Scan
    bit_depth: object


@pytest.fixture
def pytribeam_stubs(monkeypatch):
    """Install stand-ins for the pytribeam modules the wrappers import."""
    import pytribeam

    calls = {}
    tbt = types.ModuleType("pytribeam.types")
    tbt.ColorDepth = ColorDepth
    tbt.PresetResolution = PresetResolution
    tbt.ViewQuad = IntEnum("ViewQuad", {"UPPER_LEFT": 1})
    tbt.Device = IntEnum("Device", {"ELECTRON_BEAM": 1})
    tbt.YMLFormatVersion = types.SimpleNamespace(V_1_0="1.0")

    image = types.ModuleType("pytribeam.image")
    image.set_view = lambda *args: calls.setdefault("restored", []).append(args[1])
    image.set_beam_device = lambda *args: calls.setdefault("restored", []).append(args[1])
    image.collect_single_image = lambda save_path, img_settings: calls.update(
        collected=(save_path, img_settings)
    )

    factory = types.ModuleType("pytribeam.factory")

    def factory_image(microscope, step, step_name, yml_format):
        if step.get("invalid"):
            raise ValueError("invalid")
        # As the real factory.image: bit_depth is checked but left an int.
        return ImageSettings(Scan(step["resolution"]), step["bit_depth"])

    factory.image = factory_image

    for name, module in (("types", tbt), ("image", image), ("factory", factory)):
        monkeypatch.setitem(sys.modules, f"pytribeam.{name}", module)
        monkeypatch.setattr(pytribeam, name, module, raising=False)
    return calls


@pytest.fixture
def imaging(pytribeam_stubs):
    from pytribeam.mcp.capabilities import imaging

    return imaging


@pytest.mark.parametrize("bits", [8, 16])
def test_validate_returns_a_color_depth(imaging, bits):
    settings = imaging._validate(None, {"resolution": Resolution(640, 480), "bit_depth": bits})
    assert settings.bit_depth is ColorDepth(bits)


def test_validate_restores_quad_1_even_on_failure(imaging, pytribeam_stubs):
    with pytest.raises(ValueError):
        imaging._validate(None, {"invalid": True})
    assert pytribeam_stubs["restored"] == [1, 1]  # UPPER_LEFT, ELECTRON_BEAM


@pytest.mark.parametrize("bits", [8, 16])
def test_collect_hands_validated_settings_to_pytribeam(imaging, pytribeam_stubs, tmp_path, bits):
    """_collect is image.collect_single_image, given the settings _validate
    returned, ColorDepth included, and the server-chosen path."""
    settings = imaging._validate(
        None, {"resolution": PresetResolution.PRESET_768X512, "bit_depth": bits}
    )
    imaging._collect(settings, tmp_path / "i0001.tif")
    assert pytribeam_stubs["collected"] == (tmp_path / "i0001.tif", settings)
    assert pytribeam_stubs["collected"][1].bit_depth is ColorDepth(bits)
