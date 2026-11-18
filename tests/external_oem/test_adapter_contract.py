"""Every backend adapter implements the dispatcher's adapter contract."""

import importlib
import inspect

import pytest

pytest.importorskip("autoscript_sdb_microscope_client")

import pytribeam.external_oem.dispatch as external_devices  # noqa: E402
import pytribeam.types as tbt  # noqa: E402

#: Function name -> parameter names, as documented in dispatch.py.
CONTRACT = {
    "test_connection": ("general_settings", "technique"),
    "preflight_ebsd": ("general_settings", "step_settings"),
    "preflight_eds": ("general_settings", "step_settings"),
    "get_ebsd_camera_state": ("general_settings",),
    "get_eds_detector_state": ("general_settings",),
    "insert_ebsd_camera": ("microscope", "general_settings"),
    "insert_eds_detector": ("microscope", "general_settings"),
    "retract_ebsd_camera": ("microscope", "general_settings"),
    "retract_eds_detector": ("microscope", "general_settings"),
    "set_ebsd_parameters": ("general_settings", "step_settings"),
    "set_eds_parameters": ("general_settings", "step_settings"),
    "map_ebsd": ("general_settings", "step_settings", "slice_number", "on_metric"),
    "map_eds": ("general_settings", "step_settings", "slice_number", "on_metric"),
}


# Ids must not equal a marker name: conftest gates on keywords, which include ids.
@pytest.fixture(
    params=list(tbt.ExternalBackend), ids=lambda b: b.value.replace("_", "-")
)
def adapter(request):
    return importlib.import_module(external_devices.ADAPTER_MODULES[request.param])


@pytest.mark.parametrize("name", sorted(CONTRACT))
def test_adapter_implements_the_contract(adapter, name):
    function = getattr(adapter, name, None)
    assert callable(function), f"{adapter.__name__} lacks {name}"
    parameters = tuple(inspect.signature(function).parameters)
    assert parameters == CONTRACT[name], f"{adapter.__name__}.{name}{parameters}"


def test_test_connection_is_not_collected_by_pytest(adapter):
    assert adapter.test_connection.__test__ is False
