"""
Tests for CI/CD badge generation script.
"""

import xml.etree.ElementTree as ET
from pytribeam.cicd.report_badges import (
    get_pylint_score,
    get_coverage_score,
    generate_badge_svg,
)


def test_get_pylint_score(tmp_path):
    """Test extracting score from pylint text."""
    lint_file = tmp_path / "report_pylint.txt"
    lint_file.write_text("Your code has been rated at 8.45/10\n")
    assert get_pylint_score(str(lint_file)) == "8.45"


def test_get_coverage_score(tmp_path):
    """Test extracting score from coverage XML."""
    coverage_file = tmp_path / "report_coverage.xml"
    root = ET.Element("coverage")
    root.attrib["lines-valid"] = "200"
    root.attrib["lines-covered"] = "150"
    tree = ET.ElementTree(root)
    tree.write(coverage_file)
    assert get_coverage_score(str(coverage_file)) == "75.0"


def test_generate_badge_svg():
    """Test SVG content generation."""
    svg = generate_badge_svg("test-label", "test-value", "brightgreen")
    assert "<svg" in svg
    assert "test-label" in svg
    assert "test-value" in svg
    assert "#4c1" in svg  # Hex for brightgreen
