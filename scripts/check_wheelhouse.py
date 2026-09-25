#!/usr/bin/env python3
"""
Check that wheelhouse/ contains everything pytribeam_install.bat needs.

The offline installer resolves against two sources: the wheels in wheelhouse/,
and whatever the AutoScript Python environment already has installed. On a PC
that already has a package, a missing wheel goes unnoticed, so the installer
itself cannot tell whether the wheelhouse is complete. This script can, by
resolving the full developer install for the AutoScript target (Windows,
CPython 3.8.12) as if nothing were installed:

1. Offline check of each wheel, from wheelhouse/ alone. Catches wheels that
   are present but unusable on the target (wrong Python version or
   platform).
2. Online resolve of the full install, pinned to the wheelhouse versions.
   Every package in the result must either have a wheel in wheelhouse/ or be
   listed in AUTOSCRIPT_PROVIDED below. PyPI stands in for the AutoScript
   environment here, which is why this step needs internet access.

Needs internet access, and pip, hatchling and hatch-vcs in the running
interpreter (hatchling builds pytribeam's metadata). Only the standard
library is imported. From the repository root:

    uv run --no-project --with pip --with hatchling --with hatch-vcs python scripts/check_wheelhouse.py

Exit code is 0 when the wheelhouse is complete, 1 otherwise.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WHEELHOUSE = REPO_ROOT / "wheelhouse"
VERSION_FILE = REPO_ROOT / "src" / "pytribeam" / "_version.py"

# The AutoScript environment on the microscope PCs.
TARGET_PLATFORM = "win_amd64"
TARGET_PYTHON = "3.8.12"

# What pytribeam_install.bat installs: the developer install (a superset of
# the standard one) plus the tools it bootstraps before building.
REQUIREMENTS = [".[dev]", "pip", "setuptools", "hatchling", "hatch-vcs", "editables"]

# Packages the installer takes from the AutoScript environment rather than
# the wheelhouse. Add to this list only after confirming the package ships
# with AutoScript; otherwise, add its wheel to wheelhouse/ instead.
AUTOSCRIPT_PROVIDED = {
    # pytribeam's scientific stack
    "h5py",
    "numpy",
    "opencv-python",
    "pandas",
    "pytz",
    "pyyaml",
    "scikit-image",
    # ...and what those depend on
    "imageio",
    "lazy-loader",
    "networkx",
    "python-dateutil",
    "pywavelets",
    "scipy",
    "six",
    "tifffile",
    "tzdata",
    "zipp",
    # Developer tool dependencies
    "attrs",  # interrogate
    "jinja2",  # pdoc
    "markupsafe",  # pdoc
    "wheel",  # astunparse
}


def normalize(name: str) -> str:
    """PEP 503 normalized project name, e.g. 'Hatch_VCS' -> 'hatch-vcs'."""
    return re.sub(r"[-_.]+", "-", name).lower()


def wheelhouse_versions() -> dict[str, str]:
    """Map each project in the wheelhouse to its version, from the filenames."""
    versions: dict[str, str] = {}
    for wheel in sorted(WHEELHOUSE.glob("*.whl")):
        name, version = wheel.stem.split("-")[:2]
        name = normalize(name)
        if versions.setdefault(name, version) != version:
            sys.exit(
                f"[FAIL] {name} has wheels for two versions ({versions[name]} and"
                f" {version}); the installer pins one version per package."
            )
    return versions


def pip_dry_run(args: list[str], report: Path) -> subprocess.CompletedProcess[str]:
    """Resolve an install for the AutoScript target without installing it."""
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--dry-run", "--ignore-installed", "--quiet",
        "--disable-pip-version-check",
        "--only-binary=:all:",
        "--platform", TARGET_PLATFORM,
        "--python-version", TARGET_PYTHON,
        "--implementation", "cp",
        # Required with --platform; nothing is written there with --dry-run.
        "--target", str(report.parent / "target"),
        "--no-build-isolation",
        "--find-links", str(WHEELHOUSE),
        "--report", str(report),
        *args,
    ]  # fmt: skip
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)


def pip_errors(proc: subprocess.CompletedProcess[str]) -> str:
    return "\n".join("    " + line for line in proc.stderr.strip().splitlines())


def unusable_wheels(pins: dict[str, str], tmp: Path) -> list[str]:
    """Pinned packages whose wheelhouse wheel can't install on the target."""
    reqs = [f"{name}=={version}" for name, version in pins.items()]
    offline = ["--no-index", "--no-deps"]
    if pip_dry_run([*offline, *reqs], tmp / "offline.json").returncode == 0:
        return []
    # pip stops at the first failure; retry one at a time to name them all.
    return [
        req
        for req in reqs
        if pip_dry_run([*offline, req], tmp / "offline.json").returncode != 0
    ]


def main() -> int:
    pins = wheelhouse_versions()
    print(
        f"Checking wheelhouse/ ({len(pins)} packages) for"
        f" {TARGET_PLATFORM} / CPython {TARGET_PYTHON}"
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # 1. Every wheel must install on the target without PyPI.
        bad = unusable_wheels(pins, tmp)
        for req in bad:
            print(
                f"[FAIL] The wheelhouse/ wheel for {req} does not support"
                f" {TARGET_PLATFORM} / CPython {TARGET_PYTHON}."
            )
        if bad:
            # Step 2 would only fail on the same pins, less legibly.
            return 1

        # 2. Resolve everything, letting PyPI stand in for the AutoScript env.
        constraints = tmp / "constraints.txt"
        constraints.write_text("".join(f"{n}=={v}\n" for n, v in pins.items()))
        # Building pytribeam's metadata runs the hatch-vcs build hook, which
        # rewrites _version.py. That file is a release-managed fallback, so
        # put it back afterwards.
        saved_version_file = VERSION_FILE.read_bytes()
        try:
            proc = pip_dry_run(
                ["--constraint", str(constraints), *REQUIREMENTS], tmp / "online.json"
            )
        finally:
            VERSION_FILE.write_bytes(saved_version_file)
        if proc.returncode != 0:
            print("[FAIL] Could not resolve the install. pip says:")
            print(pip_errors(proc))
            return 1
        report = json.loads((tmp / "online.json").read_text())

    needed = {}
    required_by: dict[str, set[str]] = {}
    for item in report["install"]:
        meta = item["metadata"]
        name = normalize(meta["name"])
        if name == "pytribeam":
            continue
        needed[name] = meta["version"]
        for req in meta.get("requires_dist", []):
            dep = re.match(r"[A-Za-z0-9._-]+", req)
            if dep:
                required_by.setdefault(normalize(dep.group()), set()).add(name)

    missing = sorted(set(needed) - set(pins) - AUTOSCRIPT_PROVIDED)
    for name in missing:
        parents = sorted(required_by.get(name, set()) & set(needed))
        by = f" (required by {', '.join(parents)})" if parents else ""
        print(
            f"[FAIL] {name} {needed[name]}{by} has no wheel in wheelhouse/"
            " and is not in AUTOSCRIPT_PROVIDED."
        )

    for name in sorted(set(pins) - set(needed)):
        print(f"[WARN] {name} {pins[name]} is in wheelhouse/ but nothing needs it.")

    if missing:
        return 1
    from_wheelhouse = len(set(needed) & set(pins))
    print(
        f"[PASS] All {len(needed)} dependencies are covered: {from_wheelhouse}"
        f" from wheelhouse/, {len(needed) - from_wheelhouse} from the AutoScript"
        " environment."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
