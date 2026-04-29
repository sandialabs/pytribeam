#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import anybadge

import itertools
import sys
import threading
import time


class Spinner:
    def __init__(self, message: str):
        self.message = message
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._final_status = "complete"

    def _spin(self) -> None:
        for ch in itertools.cycle("|/-\\"):
            if self._stop_event.is_set():
                break
            sys.stdout.write(f"\r{self.message}... {ch}")
            sys.stdout.flush()
            time.sleep(0.1)

        sys.stdout.write(f"\r{self.message}... {self._final_status}      \n")
        sys.stdout.flush()

    def start(self) -> None:
        self._thread.start()

    def stop(self, status: str = "complete") -> None:
        self._final_status = status
        self._stop_event.set()
        self._thread.join()


REPO_ROOT = Path.cwd()
SRC_DIR = "src/pytribeam"
PACKAGE_NAME = "pytribeam"

BADGES_DIR = REPO_ROOT / "badges"
LOGS_DIR = REPO_ROOT / "logs"
DOCS_DIR = REPO_ROOT / "docs"
DOCS_API_DIR = DOCS_DIR / "api"
COVERAGE_DIR = REPO_ROOT / "coverage_reports"

MDBOOK_LOG = LOGS_DIR / "mdbook.log"
PDOC_LOG = LOGS_DIR / "pdoc.log"
DOCSTRING_LOG = LOGS_DIR / "docstring_coverage.log"
PYTEST_LOG = LOGS_DIR / "pytest.log"
PYLINT_LOG = LOGS_DIR / "lint.log"
COVERAGE_COMBINE_LOG = LOGS_DIR / "coverage_combine.log"
COVERAGE_HTML_LOG = LOGS_DIR / "coverage_html.log"
COVERAGE_XML_LOG = LOGS_DIR / "coverage_xml.log"


def need(cmd: str) -> None:
    if shutil.which(cmd) is None:
        print(f"ERROR: Missing command: {cmd}", file=sys.stderr)
        sys.exit(1)


def run_to_log(
    cmd: list[str],
    log_file: Path,
    *,
    check: bool = True,
    spinner_message: str | None = None,
) -> subprocess.CompletedProcess[str]:
    spinner = Spinner(spinner_message) if spinner_message else None
    proc = None

    try:
        if spinner:
            spinner.start()

        with log_file.open("w", encoding="utf-8") as f:
            proc = subprocess.run(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
    finally:
        if spinner:
            status = (
                "complete" if proc is not None and proc.returncode == 0 else "failed"
            )
            spinner.stop(status=status)

    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)

    return proc


def run_capture(
    cmd: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
    )


def badge_color(coverage: float) -> str:
    if coverage < 40:
        return "red"
    if coverage < 80:
        return "orange"
    if coverage < 90:
        return "yellow"
    return "green"


def require_repo_root() -> None:
    if not (
        (REPO_ROOT / "pyproject.toml").exists() or (REPO_ROOT / "README.md").exists()
    ):
        print(
            "ERROR: Run from repo root (expected pyproject.toml and/or README.md).",
            file=sys.stderr,
        )
        sys.exit(1)


def ensure_dirs() -> None:
    BADGES_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_API_DIR.mkdir(parents=True, exist_ok=True)
    COVERAGE_DIR.mkdir(parents=True, exist_ok=True)


def get_test_description() -> str:
    result = run_capture(
        [
            sys.executable,
            "-c",
            "from pytribeam.utilities import get_test_description; print(get_test_description())",
        ]
    )
    desc = result.stdout.strip()
    if not desc:
        raise RuntimeError("get_test_description() returned an empty string")
    return desc


def is_hardware_mode(test_description: str) -> bool:
    return "hardware" in test_description.lower()


def store_run_coverage(test_description: str) -> Path | None:
    src = REPO_ROOT / ".coverage"
    if not src.exists():
        return None

    dest_dir = COVERAGE_DIR / test_description
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / ".coverage"
    if dest.exists():
        dest.unlink()

    shutil.move(str(src), str(dest))
    return dest


def find_all_coverage_files() -> list[Path]:
    files: list[Path] = []

    if not COVERAGE_DIR.exists():
        return files

    for child in COVERAGE_DIR.iterdir():
        if not child.is_dir():
            continue
        if child.name == "combined":
            continue

        cov_file = child / ".coverage"
        if cov_file.exists():
            files.append(cov_file)

    return sorted(files)


def create_userguide_badge() -> None:
    badge = anybadge.Badge(
        label="userguide",
        value="\U0001f4da",
        default_color="blue",
        num_value_padding_chars=1,
    )
    out_path = BADGES_DIR / "userguide.svg"
    out_path.write_text(badge.badge_svg_text, encoding="utf-8")
    print(f"Userguide badge updated: {BADGES_DIR / 'userguide.svg'}")


def build_userguide() -> None:
    print("\n[STEP] Userguide (mdbook)")
    try:
        run_to_log(
            ["mdbook", "build", "."], MDBOOK_LOG, spinner_message="Building userguide"
        )
        print(f"userguide build completed successfully. See {MDBOOK_LOG}")
    except subprocess.CalledProcessError:
        print(f"userguide build failed. See {MDBOOK_LOG}")


def build_api_docs() -> None:
    print("\n[INFO] API docs (pdoc)")

    if DOCS_API_DIR.exists():
        shutil.rmtree(DOCS_API_DIR)
    DOCS_API_DIR.mkdir(parents=True, exist_ok=True)

    try:
        run_to_log(
            [
                "pdoc",
                "-o",
                str(DOCS_API_DIR),
                PACKAGE_NAME,
            ],
            PDOC_LOG,
            spinner_message="Building API docs",
        )
        print(f"API documentation build completed successfully. See {PDOC_LOG}")
    except subprocess.CalledProcessError:
        print(f"API documentation build failed. See {PDOC_LOG}")


def run_docstring_coverage() -> None:
    print("\n[STEP] Docstring coverage (interrogate)")

    result = run_to_log(
        ["interrogate", "-v", "--fail-under", "0", "src"],
        DOCSTRING_LOG,
        check=False,
        spinner_message="Calculating docstring coverage",
    )

    coverage_value = None
    try:
        text = DOCSTRING_LOG.read_text(encoding="utf-8")
        match = re.search(r"actual:\s*([0-9.]+)%", text)
        if match:
            coverage_value = float(match.group(1))
    except Exception:
        coverage_value = None

    if result.returncode != 0:
        print(f"Docstring coverage failed. See {DOCSTRING_LOG}")
        return

    if coverage_value is None:
        print(
            f"Docstring coverage completed, but coverage percentage could not be parsed. See {DOCSTRING_LOG}"
        )
        return

    coverage_str = f"{coverage_value:.1f}"
    color = badge_color(coverage_value)
    run_capture(
        [
            "anybadge",
            "-o",
            "-l",
            "api",
            "-v",
            f"{coverage_str}% coverage",
            "-f",
            str(BADGES_DIR / "api.svg"),
            "-c",
            color,
        ]
    )
    print(f"Docstring coverage completed successfully: {coverage_str}%")


def run_tests_and_store_coverage() -> int:
    print("\n[STEP] Tests (pytest)")

    try:
        test_description = get_test_description()
    except Exception as exc:
        print(f"ERROR: Could not determine test description: {exc}", file=sys.stderr)
        return 2

    cmd = ["pytest"]
    if is_hardware_mode(test_description):
        cmd.append("-x")
    cmd.extend(
        [
            "--cov=pytribeam",
            "--cov-report=term-missing",
        ]
    )

    result = run_to_log(cmd, PYTEST_LOG, check=False, spinner_message="Running tests")
    pytest_rc = result.returncode

    if pytest_rc != 0:
        print(
            f"WARNING: pytest failed (exit code {pytest_rc}). Continuing workflow... See {PYTEST_LOG}"
        )
    else:
        print(f"Tests completed successfully. See {PYTEST_LOG}")

    moved = store_run_coverage(test_description)
    if moved is None:
        print("WARNING: No .coverage file was produced by pytest.")
    else:
        print(f"Stored coverage data: {moved}")

    return pytest_rc


def build_combined_coverage() -> None:
    print("\n[STEP] Test coverage (coverage)")

    coverage_files = find_all_coverage_files()
    combined_dir = COVERAGE_DIR / "combined"
    combined_dir.mkdir(parents=True, exist_ok=True)

    if not coverage_files:
        print("No coverage files found; skipping combined coverage generation.")
        return

    root_cov = REPO_ROOT / ".coverage"
    if root_cov.exists():
        root_cov.unlink()

    if len(coverage_files) > 1:
        print(f"Combining {len(coverage_files)} coverage files into {combined_dir}")
        run_to_log(
            ["coverage", "combine", "--keep", *[str(p) for p in coverage_files]],
            COVERAGE_COMBINE_LOG,
            spinner_message="Combining coverages",
        )
    else:
        print(f"Using single coverage file: {coverage_files[0]}")
        shutil.copyfile(coverage_files[0], root_cov)
        COVERAGE_COMBINE_LOG.write_text(
            f"Single coverage file used without combine:\n{coverage_files[0]}\n",
            encoding="utf-8",
        )

    run_to_log(
        ["coverage", "html", "-d", str(combined_dir / "htmlcov")],
        COVERAGE_HTML_LOG,
        spinner_message="Generating HTML coverage report",
    )
    run_to_log(
        ["coverage", "xml", "-o", str(combined_dir / "coverage.xml")],
        COVERAGE_XML_LOG,
        spinner_message="Generating XML coverage report",
    )
    print(f"Combined coverage report generated in {combined_dir}")


def make_test_coverage_badge() -> None:
    xml_path = COVERAGE_DIR / "combined" / "coverage.xml"
    if not xml_path.exists():
        print(f"WARNING: Coverage XML not found: {xml_path} (skipping coverage badge)")
        return

    try:
        root = ET.parse(xml_path).getroot()
        lines_covered = int(root.attrib["lines-covered"])
        lines_valid = int(root.attrib["lines-valid"])
    except Exception:
        print(f"WARNING: Could not parse coverage totals from {xml_path}")
        return

    if lines_valid == 0:
        print(f"WARNING: Could not parse coverage totals from {xml_path}")
        return

    pct = (lines_covered / lines_valid) * 100.0
    pct_str = f"{pct:.1f}"
    color = badge_color(pct)

    run_capture(
        [
            "anybadge",
            "-o",
            "-l",
            "Coverage",
            "-v",
            f"{pct_str}%",
            "-f",
            str(BADGES_DIR / "test-coverage.svg"),
            "-c",
            color,
        ]
    )
    print(f"Coverage: {pct_str}% ({color})")


def run_pylint_and_badge() -> None:
    print("\n[STEP] Linting (pylint)")

    pylint_proc = run_to_log(
        ["pylint", "-v", SRC_DIR],
        PYLINT_LOG,
        check=False,
        spinner_message="Running pylint",
    )

    if pylint_proc.returncode != 0:
        subprocess.run(["pylint-exit", str(pylint_proc.returncode)], check=False)

    lint_output = PYLINT_LOG.read_text(encoding="utf-8")
    score = None
    try:
        matches = re.findall(
            r"^Your code has been rated at ([\-0-9.]+)/",
            lint_output,
            flags=re.MULTILINE,
        )
        if matches:
            score = matches[-1]
    except Exception:
        score = None

    if score is not None:
        run_capture(
            [
                "anybadge",
                "-o",
                "--label=lint",
                f"--file={BADGES_DIR / 'lint.svg'}",
                f"--value={score}",
                "2=red",
                "4=orange",
                "8=yellow",
                "10=green",
            ]
        )
        print(f"pylint completed successfully: score {score}. See {PYLINT_LOG}")
    else:
        print(
            f"WARNING: Could not parse pylint score; skipping lint badge. See {PYLINT_LOG}"
        )


def main() -> int:
    for cmd in [
        "mdbook",
        "pdoc",
        "interrogate",
        "anybadge",
        "pytest",
        "coverage",
        "pylint",
        "pylint-exit",
    ]:
        need(cmd)

    require_repo_root()
    ensure_dirs()

    print("=== Local CI workflow (no git actions) ===")

    build_userguide()
    create_userguide_badge()
    build_api_docs()
    run_docstring_coverage()
    run_tests_and_store_coverage()
    build_combined_coverage()
    make_test_coverage_badge()
    run_pylint_and_badge()

    print("\nDone. Artifacts updated in: badges/, logs/, docs/, coverage_reports/")


if __name__ == "__main__":
    main()
    # raise SystemExit(main())
