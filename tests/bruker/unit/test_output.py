from pytribeam.external_oem.bruker.output import (
    make_run_dir_name,
    make_run_paths,
    make_file_prefix,
)
from pytribeam.external_oem.bruker.types import BrukerEDSOutputSettings


def test_run_dir_name_standalone():
    output = BrukerEDSOutputSettings(
        output_dir="C:/output",
        run_name="eds_map",
    )
    name = make_run_dir_name(output, "20260821_131304")
    assert name == "eds_map_20260821_131304"


def test_run_dir_name_with_slice():
    output = BrukerEDSOutputSettings(
        output_dir="C:/output",
        run_name="eds_map",
        slice_number=1,
    )
    name = make_run_dir_name(output, "20260821_131304")
    assert name == "eds_map_Slice_0001_20260821_131304"


def test_run_dir_name_with_slice_large_number():
    output = BrukerEDSOutputSettings(
        output_dir="C:/output",
        run_name="eds_map",
        slice_number=42,
    )
    name = make_run_dir_name(output, "20260821_131304")
    assert name == "eds_map_Slice_0042_20260821_131304"


def test_run_dir_name_with_repeat_zero():
    """repeat_index=0 means first attempt, should NOT be appended."""
    output = BrukerEDSOutputSettings(
        output_dir="C:/output",
        run_name="eds_map",
        slice_number=5,
        repeat_index=0,
    )
    name = make_run_dir_name(output, "20260821_131304")
    assert name == "eds_map_Slice_0005_20260821_131304"


def test_run_dir_name_with_repeat_nonzero():
    """repeat_index > 0 means re-acquisition, should be appended."""
    output = BrukerEDSOutputSettings(
        output_dir="C:/output",
        run_name="eds_map",
        slice_number=5,
        repeat_index=2,
    )
    name = make_run_dir_name(output, "20260821_131304")
    assert name == "eds_map_Slice_0005_2_20260821_131304"


def test_run_dir_name_no_slice_ignores_repeat():
    """If slice_number is None, repeat_index is ignored."""
    output = BrukerEDSOutputSettings(
        output_dir="C:/output",
        run_name="eds_map",
        slice_number=None,
        repeat_index=3,
    )
    name = make_run_dir_name(output, "20260821_131304")
    assert name == "eds_map_20260821_131304"


def test_file_prefix_standalone():
    output = BrukerEDSOutputSettings(
        output_dir="C:/output",
        run_name="eds_map",
    )
    prefix = make_file_prefix(output)
    assert prefix == "eds_map"


def test_file_prefix_with_slice():
    output = BrukerEDSOutputSettings(
        output_dir="C:/output",
        run_name="eds_map",
        slice_number=7,
    )
    prefix = make_file_prefix(output)
    assert prefix == "eds_map_Slice_0007"


def test_file_prefix_with_repeat():
    output = BrukerEDSOutputSettings(
        output_dir="C:/output",
        run_name="eds_map",
        slice_number=7,
        repeat_index=1,
    )
    prefix = make_file_prefix(output)
    assert prefix == "eds_map_Slice_0007_1"


def test_make_run_paths_creates_directory(tmp_path):
    output = BrukerEDSOutputSettings(
        output_dir=str(tmp_path),
        run_name="test_run",
        slice_number=3,
    )
    paths = make_run_paths(output, "20260821_140000")

    assert paths["run_dir"].exists()
    assert paths["run_dir"].is_dir()
    assert "Slice_0003" in str(paths["run_dir"])
    assert paths["bcf_path"].suffix == ".bcf"
    assert paths["summary_json_path"].suffix == ".json"
    assert "readback" in str(paths["readback_dir"])
