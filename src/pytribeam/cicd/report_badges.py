#!/usr/bin/env python3
"""
Generates SVG badges for Lint and Coverage scores.
"""

import argparse
import os
import re
import xml.etree.ElementTree as ET

from pytribeam.cicd.utilities import (
    get_score_color_coverage,
    get_score_color_lint,
)


def get_pylint_score(input_file: str) -> str:
    """Extract score from pylint report text."""
    if not os.path.exists(input_file):
        return "0.00"
    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r"Your code has been rated at (\d+\.\d+)/10", content)
    return match.group(1) if match else "0.00"


def get_coverage_score(input_file: str) -> str:
    """Extract percentage from coverage XML."""
    if not os.path.exists(input_file):
        return "0.0"
    try:
        tree = ET.parse(input_file)
        root = tree.getroot()
        lines_valid = float(root.attrib.get("lines-valid", 0))
        lines_covered = float(root.attrib.get("lines-covered", 0))
        if lines_valid == 0:
            return "0.0"
        return f"{(lines_covered / lines_valid * 100):.1f}"
    except Exception:
        return "0.0"


def generate_badge_svg(label: str, value: str, color_key: str) -> str:
    """Generate a flat-style SVG badge."""
    # Map color keys to hex
    color_map = {
        "brightgreen": "#4c1",
        "green": "#97ca00",
        "yellow": "#dfb317",
        "orange": "#fe7d37",
        "red": "#e05d44",
        "gray": "#9f9f9f",
    }
    color = color_map.get(color_key, color_map["gray"])

    # Simple width calculation
    label_w = len(label) * 7 + 10
    value_w = len(value) * 7 + 10
    total_w = label_w + value_w

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="20" viewBox="0 0 {total_w} 20" preserveAspectRatio="xMidYMid meet">
    <linearGradient id="b" x2="0" y2="100%">
        <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
        <stop offset="1" stop-opacity=".1"/>
    </linearGradient>
    <mask id="a">
        <rect width="{total_w}" height="20" rx="3" fill="#fff"/>
    </mask>
    <g mask="url(#a)">
        <path fill="#555" d="M0 0h{label_w}v20H0z"/>
        <path fill="{color}" d="M{label_w} 0h{value_w}v20H{label_w}z"/>
        <path fill="url(#b)" d="M0 0h{total_w}v20H0z"/>
    </g>
    <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
        <text x="{label_w / 2}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
        <text x="{label_w / 2}" y="14">{label}</text>
        <text x="{label_w + value_w / 2}" y="15" fill="#010101" fill-opacity=".3">{value}</text>
        <text x="{label_w + value_w / 2}" y="14">{value}</text>
    </g>
    </svg>"""


def main():
    parser = argparse.ArgumentParser(
        description="Generate SVG badges for CI/CD results."
    )
    parser.add_argument("--lint_file", help="Path to pylint report text file")
    parser.add_argument("--coverage_file", help="Path to coverage XML file")
    parser.add_argument("--output_dir", required=True, help="Directory to save badges")

    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    if args.lint_file:
        score = get_pylint_score(args.lint_file)
        color = get_score_color_lint(score)
        svg = generate_badge_svg("lint", f"{score}/10", color)
        with open(os.path.join(args.output_dir, "lint.svg"), "w") as f:
            f.write(svg)
        print(f"[OK] Lint badge generated: {score}/10")

    if args.coverage_file:
        score = get_coverage_score(args.coverage_file)
        color = get_score_color_coverage(score)
        svg = generate_badge_svg("coverage", f"{score}%", color)
        with open(os.path.join(args.output_dir, "coverage.svg"), "w") as f:
            f.write(svg)
        print(f"[OK] Coverage badge generated: {score}%")


if __name__ == "__main__":
    main()
