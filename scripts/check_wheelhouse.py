#!/usr/bin/env python3
"""
Check that wheelhouse/ contains everything pytribeam_install.bat needs.

The offline installer resolves against two sources: the wheels in wheelhouse/,
and whatever the AutoScript Python environment already has installed. On a PC
that already has a package, a missing wheel goes unnoticed, so the installer
itself cannot tell whether the wheelhouse is complete. This script can, by
resolving the full developer install for the AutoScript target (Windows,
CPython 3.8.12) as if nothing were installed:

1. Offline check of each wheel, from wheelhouse/ alone. Catches wheels built
   for the wrong Python version or platform.
2. Online resolve of the full install, pinned to the wheelhouse versions.
   Every package in the result must either have a wheel in wheelhouse/ or be
   listed in AUTOSCRIPT_PROVIDED below. PyPI stands in for the AutoScript
   environment here, which is why this step needs internet access. It also
   catches wheels whose Requires-Python excludes the target.

Resolution is done by `uv pip compile`, which evaluates environment markers
(python_version, sys_platform, ...) for the target rather than for the
machine running this script. pip's --python-version/--platform do not, so a
pip-based check would miss dependencies that only apply on Windows or on
Python 3.8.

Needs uv on PATH and internet access; only the standard library is imported.
From the repository root:

    uv run --no-project python scripts/check_wheelhouse.py

Exit code is 0 when the wheelhouse is complete, 1 otherwise.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WHEELHOUSE = REPO_ROOT / "wheelhouse"
VERSION_FILE = REPO_ROOT / "src" / "pytribeam" / "_version.py"

# The AutoScript environment on the microscope PCs.
TARGET_PLATFORM = "x86_64-pc-windows-msvc"
TARGET_PYTHON = "3.8.12"
TARGET = f"Windows x86-64 / CPython {TARGET_PYTHON}"

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

# One line of `uv pip compile --annotation-style line` output:
#   "colorama==0.4.6  # via click, pytest, -c /tmp/constraints.txt"
COMPILED_LINE = re.compile(r"^(\S+)==(\S+)\s*(?:#\s*via\s+(.*))?$")


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


def uv_compile(requirements: list[str], *args: str) -> subprocess.CompletedProcess[str]:
    """Resolve requirements for the AutoScript target without installing."""
    # `uv run` exports its own path as UV.
    uv = os.environ.get("UV") or shutil.which("uv")
    if not uv:
        sys.exit("[FAIL] uv is required: https://docs.astral.sh/uv/")
    cmd = [
        uv, "pip", "compile", "-",
        "--quiet", "--no-header", "--annotation-style", "line",
        "--python-platform", TARGET_PLATFORM,
        "--python-version", TARGET_PYTHON,
        # The offline installer never builds from source; pytribeam itself is
        # the one exception.
        "--only-binary", ":all:", "--no-binary", "pytribeam",
        "--find-links", str(WHEELHOUSE),
        *args,
    ]  # fmt: skip
    return subprocess.run(
        cmd,
        input="\n".join(requirements),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def uv_errors(proc: subprocess.CompletedProcess[str]) -> str:
    return "\n".join("    " + line for line in proc.stderr.strip().splitlines())


def unusable_wheels(pins: dict[str, str]) -> list[str]:
    """Pinned packages whose wheelhouse wheel can't install on the target."""
    reqs = [f"{name}=={version}" for name, version in pins.items()]
    offline = ["--no-index", "--no-deps"]
    if uv_compile(reqs, *offline).returncode == 0:
        return []
    # uv stops at the first failure; retry one at a time to name them all.
    return [req for req in reqs if uv_compile([req], *offline).returncode != 0]


def main() -> int:
    pins = wheelhouse_versions()
    print(f"Checking wheelhouse/ ({len(pins)} packages) for {TARGET}")

    # 1. Every wheel must install on the target without PyPI.
    bad = unusable_wheels(pins)
    for req in bad:
        print(f"[FAIL] The wheelhouse/ wheel for {req} does not support {TARGET}.")
    if bad:
        # Step 2 would only fail on the same pins, less legibly.
        return 1

    # 2. Resolve everything, letting PyPI stand in for the AutoScript env.
    with tempfile.TemporaryDirectory() as tmp:
        constraints = Path(tmp) / "constraints.txt"
        constraints.write_text("".join(f"{n}=={v}\n" for n, v in pins.items()))
        # Building pytribeam's metadata can run the hatch-vcs build hook, which
        # rewrites _version.py. That file is a release-managed fallback, so
        # put it back afterwards.
        saved_version_file = VERSION_FILE.read_bytes()
        try:
            proc = uv_compile(REQUIREMENTS, "--constraint", str(constraints))
        finally:
            VERSION_FILE.write_bytes(saved_version_file)
    if proc.returncode != 0:
        print("[FAIL] Could not resolve the install. uv says:")
        print(uv_errors(proc))
        return 1

    needed: dict[str, str] = {}
    required_by: dict[str, list[str]] = {}
    for line in proc.stdout.splitlines():
        match = COMPILED_LINE.match(line.strip())
        if not match:
            continue  # pytribeam itself, listed as "."
        name, version, via = match.groups()
        needed[normalize(name)] = version
        required_by[normalize(name)] = [
            parent
            for parent in (via or "").split(", ")
            if parent and not parent.startswith(("-c ", "-r ")) and parent != "."
        ]

    missing = sorted(set(needed) - set(pins) - AUTOSCRIPT_PROVIDED)
    for name in missing:
        parents = required_by.get(name)
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
