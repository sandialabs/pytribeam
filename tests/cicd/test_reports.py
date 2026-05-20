"""
Tests for CI/CD report generation scripts.
"""

import argparse
import xml.etree.ElementTree as ET

from pytribeam.cicd.report_coverage import generate_report as generate_coverage_report

# from pathlib import Path
from pytribeam.cicd.report_lint import generate_report as generate_lint_report
from pytribeam.cicd.utilities import ReportMetadata


def test_generate_lint_report(tmp_path):
    """Test that report_lint generates expected HTML."""
    input_file = tmp_path / "lint.txt"
    output_file = tmp_path / "lint.html"

    # Mock pylint output
    lint_content = (
        "src/file.py:10:5: C0111: Missing docstring\n"
        "-------------------\n"
        "Your code has been rated at 9.50/10\n"
    )
    input_file.write_text(lint_content)

    args = argparse.Namespace(input_file=str(input_file), output_file=str(output_file))
    metadata = ReportMetadata(
        timestamp="20260424_215553_UTC",
        run_id="12345",
        ref_name="main",
        github_sha="abc1234",
        github_repo="owner/repo",
    )

    generate_lint_report(args, metadata)

    assert output_file.exists()
    html = output_file.read_text()
    assert "9.50/10" in html
    assert "Missing docstring" in html
    assert "src/file.py" in html


def test_generate_coverage_report(tmp_path):
    """Test that report_coverage generates expected HTML."""
    input_file = tmp_path / "coverage.xml"
    output_file = tmp_path / "coverage.html"

    # Mock coverage XML
    root = ET.Element("coverage")
    root.attrib["lines-valid"] = "100"
    root.attrib["lines-covered"] = "85"
    tree = ET.ElementTree(root)
    tree.write(input_file)

    args = argparse.Namespace(input_file=str(input_file), output_file=str(output_file))
    metadata = ReportMetadata(
        timestamp="20260424_215553_UTC",
        run_id="12345",
        ref_name="main",
        github_sha="abc1234",
        github_repo="owner/repo",
    )

    generate_coverage_report(args, metadata)

    assert output_file.exists()
    html = output_file.read_text()
    assert "85.00%" in html
    assert "<strong>Lines Covered:</strong> 85" in html
    assert "<strong>Total Lines:</strong> 100" in html
    assert "85.00%" in html
    assert "<strong>Lines Covered:</strong> 85" in html
    assert "<strong>Total Lines:</strong> 100" in html
