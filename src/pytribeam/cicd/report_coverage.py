#!/usr/bin/env python3
"""
Coverage HTML Report Generator

This module extracts key coverage metrics from a coverage XML file and generates a custom HTML report.
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from pytribeam.cicd.utilities import (
    ReportMetadata,
    add_common_args,
    extend_timestamp,
    get_score_color_coverage,
    report_main_runner,
    write_report,
)


@dataclass(frozen=True)
class CoverageMetric:
    """Represents coverage metrics for a codebase.

    Attributes:
        lines_valid (int): The total number of valid lines in the codebase.
        lines_covered (int): The number of lines that are covered by tests.
    """

    lines_valid: int = 0
    lines_covered: int = 0

    @property
    def coverage(self) -> float:
        """
        Calculates the coverage percentage.
        """
        return (self.lines_covered / self.lines_valid * 100) if self.lines_valid > 0 else 0.0

    @property
    def color(self) -> str:
        """
        Determines the badge color based on the coverage percentage.
        """
        return get_score_color_coverage(str(self.coverage))


def get_coverage_metric(coverage_file: Path) -> CoverageMetric:
    """
    Parses the coverage XML file to extract metrics.
    """
    try:
        tree = ET.parse(coverage_file)
        root = tree.getroot()
        lines_valid = int(root.attrib["lines-valid"])
        lines_covered = int(root.attrib["lines-covered"])
        return CoverageMetric(
            lines_valid=lines_valid,
            lines_covered=lines_covered,
        )
    except (FileNotFoundError, ET.ParseError, KeyError, AttributeError) as e:
        print(f"Error processing coverage file: {e}")
        return CoverageMetric()


def get_report_html(
    coverage_metric: CoverageMetric,
    metadata: ReportMetadata,
) -> str:
    """
    Generates an HTML report from the coverage metrics.
    """
    # Map badge colors to valid CSS colors
    color_map = {
        "brightgreen": "#4c1",
        "green": "#97ca00",
        "yellow": "#dfb317",
        "orange": "#fe7d37",
        "red": "#e05d44",
        "gray": "#9f9f9f",
    }
    raw_color = coverage_metric.color
    score_color = color_map.get(raw_color, raw_color)
    
    timestamp_ext = extend_timestamp(metadata.timestamp)

    # Programmatically construct the full report URL
    try:
        owner, repo_name = metadata.github_repo.split("/")
        subdir = "main" if metadata.ref_name == "main" else "dev"
        full_report_url = (
            f"https://{owner}.github.io/{repo_name}/{subdir}/reports/coverage/htmlcov/index.html"
        )
    except ValueError:
        full_report_url = "#"

    # Pre-calculate GitHub URLs
    github_url = f"https://github.com/{metadata.github_repo}"
    run_url = f"{github_url}/actions/runs/{metadata.run_id}"
    branch_url = f"{github_url}/tree/{metadata.ref_name}"
    commit_url = f"{github_url}/commit/{metadata.github_sha}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>pyTriBeam | Coverage Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0; padding: 20px; background: #f6f8fa; line-height: 1.6;
        }}
        .container {{
            max-width: 1200px; margin: 0 auto;
        }}
        .header {{
            background: white; padding: 30px; border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px;
        }}
        .score {{
            font-size: 2.5em; font-weight: bold; color: {score_color};
        }}
        .metadata {{
            color: #6a737d; font-size: 0.9em; margin-top: 10px;
        }}
        .metadata div {{ margin-bottom: 4px; }}
        .nav {{
            background: white; padding: 20px; border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px;
        }}
        .nav a {{
            background: #0366d6; color: white; padding: 10px 20px;
            text-decoration: none; border-radius: 6px; margin-right: 10px;
            display: inline-block;
        }}
        .nav a:hover {{
            background: #0256cc;
        }}
        .section {{
            background: white; padding: 20px; border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px;
        }}
        .footer {{ text-align: center; margin: 40px 0; color: #6a737d; font-size: 0.8em; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Coverage Report</h1>
            <div class="score">Coverage: {coverage_metric.coverage:.2f}%</div>
            <div class="metadata">
                <div><strong>Lines Covered:</strong> {coverage_metric.lines_covered}</div>
                <div><strong>Total Lines:</strong> {coverage_metric.lines_valid}</div>
                <div>&nbsp;</div>
                <div><strong>Generated:</strong> {timestamp_ext}</div>
                <div><strong>Run ID:</strong>
                    <a href="{run_url}">{metadata.run_id}</a></div>
                <div><strong>Branch:</strong>
                    <a href="{branch_url}">{metadata.ref_name}</a></div>
                <div><strong>Commit:</strong>
                    <a href="{commit_url}">{metadata.github_sha[:7]}</a></div>
                <div><strong>Repository:</strong>
                    <a href="{github_url}">{metadata.github_repo}</a></div>
                <div>&nbsp;</div>
                <div><strong>Full report:</strong> <a href="{full_report_url}" style="color: #0366d6;">Detailed HTML Report</a></div>
            </div>
        </div>

        <div class="nav">
            <a href="../../index.html">← Back to Dashboard</a>
        </div>
        
        <div class="footer">
            <p>&copy; 2026 Sandia National Laboratories | Generated by GitHub Actions</p>
        </div>
    </div>
</body>
</html>"""


def generate_report(args: argparse.Namespace, metadata: ReportMetadata) -> None:
    """
    Orchestrate report generation.
    """
    coverage_metric = get_coverage_metric(coverage_file=Path(args.input_file))
    
    html_content = get_report_html(coverage_metric, metadata)
    
    # Ensure output directory exists
    output_dir = os.path.dirname(args.output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        
    write_report(html_content, args.output_file)

    print(f"[OK] Coverage report generated: {args.output_file}")
    print(f"[I] - valid lines: {coverage_metric.lines_valid}")
    print(f"[I] - covered lines: {coverage_metric.lines_covered}")
    print(f"[I] - coverage: {coverage_metric.coverage:.2f}%")


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Generate enhanced HTML report from coverage XML"
    )
    parser.add_argument("--input_file", required=True, help="Input coverage XML file")
    parser.add_argument("--output_file", required=True, help="Output HTML report file")
    add_common_args(parser)
    return parser.parse_args()


def main() -> int:
    """
    Main entry point.
    """
    args = parse_arguments()
    return report_main_runner(generate_report, args)


if __name__ == "__main__":
    sys.exit(main())
