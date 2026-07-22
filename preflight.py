#!/usr/bin/env python3
"""
Preflight script to verify likely CI/CD readiness through extensive local testing.
Runs lint checks and tests relevant to the CI/CD reporting logic.

This script has an early check that attempts to connect to the package index (PyPI)
to detect common network issues (e.g. corporate firewalls with SSL interception).
If such issues are detected, it provides feedback to the user on how to proceed
(e.g. setting SSL_CERT_FILE or using --no-sync to skip dependency synchronization).
This helps users understand and resolve connectivity issues before they cause failures
in the actual CI/CD pipeline.

The `--no-sync` flag allows users to skip the dependency synchronization step,
which is useful when they are behind a firewall or have already installed dependencies.
The `--all-tests` flag allows users to run the full test suite and a full lint check.

Usage:
    python preflight.py [--no-sync] [--skip-network-check] [--all-tests] [--force]

Examples:
    python preflight.py --no-sync      # Skip dependency sync (useful when offline/firewall)
    python preflight.py --all-tests    # Run the full test suite and full lint check
    python preflight.py --force        # Continue even if network/sync checks fail
    python preflight.py --skip-network-check  # Skip the initial connectivity check

"""

import argparse
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from typing import List


def check_connectivity(timeout: int = 5) -> tuple:
    """
    Check if the network (specifically the package index and file host) is reachable.
    Returns (success, error_message).
    """
    endpoints = [
        os.environ.get("UV_INDEX_URL", "https://pypi.org/simple/"),
        "https://files.pythonhosted.org/",
    ]

    for url in endpoints:
        try:
            urllib.request.urlopen(url, timeout=timeout)
        except urllib.error.URLError as e:
            if "CERTIFICATE_VERIFY_FAILED" in str(e.reason):
                return (
                    False,
                    f"SSL certificate verification failed for {url} (Unknown Issuer).",
                )
            return False, f"Connection failed to {url}: {e.reason}"
        except Exception as e:
            return False, f"Unexpected error connecting to {url}: {e}"

    return True, ""


def run_step(
    command: List[str], description: str, capture_output: bool = False
) -> subprocess.CompletedProcess:
    """
    Executes a shell command and prints the result.
    """
    print(f"\n--- {description} ---")
    try:
        # We allow output to flow to stdout/stderr for real-time feedback
        # unless capture_output is True.
        result = subprocess.run(
            command, capture_output=capture_output, text=True, check=True
        )
        print("Result: [SUCCESS]")
        return result
    except subprocess.CalledProcessError as e:
        if not capture_output:
            print(f"Result: [FAILED] (Exit code: {e.returncode})")
        return e
    except FileNotFoundError:
        print("Result: [ERROR] (Command not found.)")
        sys.exit(1)


def autoscript_sdk_available(sync_flag: str) -> bool:
    """
    Checks whether the (proprietary, non-PyPI) AutoScript SDK is importable in
    the project's environment. It's only ever present inside the AutoScript CI
    container image (see ci.yml's api-docs job) or a contributor's own AutoScript
    install — never via 'uv sync', since it isn't a declared dependency.
    """
    cmd = shlex.split(
        f'uv run {sync_flag} python -c "import autoscript_sdb_microscope_client"'
    )
    cmd = [c for c in cmd if c]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def find_uncollectable_modules(sync_flag: str) -> List[str]:
    """
    Dry-runs pytest collection over the full test suite and returns the test
    file paths that fail to even import. Only called when the AutoScript SDK is
    missing, to find which modules need it (directly or transitively, e.g. via
    the pandas/scikit-image versions AutoScript's vendor wheels provide) so they
    can be skipped instead of failing preflight for an environment gap that's
    expected outside the AutoScript container.
    """
    cmd = shlex.split(
        f"uv run {sync_flag} python -m pytest tests/ --collect-only -q --no-cov --color=no"
    )
    cmd = [c for c in cmd if c]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return sorted(set(re.findall(r"ERROR collecting (\S+)", result.stdout)))


def main() -> None:
    """
    Main entry point for preflight checks.
    """
    parser = argparse.ArgumentParser(
        description="Preflight checks for CI/CD readiness."
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Skip 'uv' dependency synchronization (useful when offline or behind a firewall).",
    )
    parser.add_argument(
        "--skip-network-check",
        action="store_true",
        help="Skip the initial network connectivity check.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Continue even if network checks or synchronization fails.",
    )
    parser.add_argument(
        "--all-tests",
        action="store_true",
        help="Run all tests in the 'tests/' directory and lint all source files.",
    )
    args = parser.parse_args()

    print("Starting Preflight Checks...")

    # 1. Check if 'uv' is installed
    try:
        subprocess.run(["uv", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[X] Error: 'uv' is not installed or not in PATH.")
        print("    Please install uv: https://github.com/astral-sh/uv")
        sys.exit(1)

    # 2. Network connectivity check
    if not args.skip_network_check and not args.no_sync:
        print("Checking network connectivity...", end=" ", flush=True)
        success, err = check_connectivity()
        if success:
            print("[OK]")
        else:
            print("[FAILED]")
            print(f"\n[!] Network check failed: {err}")
            print("    It is highly likely that 'uv' will fail to sync dependencies.")

            print("\n    Suggestions:")
            if "CERTIFICATE" in err:
                print("    - Set SSL_CERT_FILE to your corporate CA bundle.")
                print(
                    "    - On macOS, ensure your certificate is in the System Keychain."
                )
                print(
                    "    - Or use '--no-sync' if your environment is already prepared."
                )
            else:
                print("    - Ensure HTTP_PROXY and HTTPS_PROXY are set correctly.")
                print("    - Use '--no-sync' to bypass network synchronization.")

            if not args.force:
                print("\n[!] Aborting to avoid long 'uv' error messages.")
                print("    Use '--force' if you believe this check is incorrect.")
                print("-" * 20)
                sys.exit(1)
            print("-" * 20)

    # 3. Environment Synchronization (Fail Fast)
    if not args.no_sync:
        print(
            "\nChecking/Syncing environment dependencies (including extras)...",
            flush=True,
        )
        # We sync all extras to ensure tools like pytest and ruff are available
        sync_res = subprocess.run(
            ["uv", "sync", "--all-extras"], capture_output=True, text=True
        )
        if sync_res.returncode != 0:
            print("Result: [FAILED]")
            print(
                "\n[!] 'uv sync' failed. This usually indicates a network or SSL issue."
            )

            # Extract common error patterns from uv output
            if (
                "UnknownIssuer" in sync_res.stderr
                or "invalid peer certificate" in sync_res.stderr
            ):
                print("\n    Detected SSL Certificate Issue (Unknown Issuer).")
                print(
                    "    - Solution: export SSL_CERT_FILE=/path/to/your/ca-bundle.pem"
                )
            elif "Connect" in sync_res.stderr or "timeout" in sync_res.stderr:
                print("\n    Detected Connection Issue.")
                print(
                    "    - Solution: Check your proxy settings (HTTP_PROXY/HTTPS_PROXY)."
                )

            print("\n    Full error from 'uv':")
            print("-" * 20)
            print(sync_res.stderr.strip())
            print("-" * 20)

            if not args.force:
                print(
                    "\n[!] Aborting preflight. Fix the environment or use '--no-sync'."
                )
                sys.exit(1)
        else:
            print("Result: [SUCCESS]")

    # 4. Run actual validation steps
    sync_flag = "--no-sync" if args.no_sync else ""

    if args.all_tests:
        test_cmd = f"uv run {sync_flag} python -m pytest tests/"
        if not autoscript_sdk_available(sync_flag):
            skipped = find_uncollectable_modules(sync_flag)
            if skipped:
                print(
                    f"\n[i] AutoScript SDK not installed locally — skipping "
                    f"{len(skipped)} module(s) that require it (only available "
                    f"inside the AutoScript CI container):"
                )
                for path in skipped:
                    print(f"    - {path}")
                test_cmd += "".join(f" --ignore={path}" for path in skipped)

        steps = [
            (
                f"uv run {sync_flag} python -m ruff format --check src/",
                "Full Lint Format Check",
            ),
            (test_cmd, "Full Test Suite"),
        ]
    else:
        steps = [
            (
                f"uv run {sync_flag} python -m ruff format --check src/pytribeam/cicd/",
                "Lint Format Check (CICD)",
            ),
            (f"uv run {sync_flag} python -m pytest tests/cicd", "CICD Logic Tests"),
            # (f"uv run {sync_flag} python -m pytest --no-cov tests/test_example.py", "Example Tests"),
        ]

    all_passed = True
    for cmd_str, desc in steps:
        cmd = shlex.split(cmd_str)
        # Filter out empty strings from shlex.split if any
        cmd = [c for c in cmd if c]

        res = run_step(cmd, desc)
        if isinstance(res, subprocess.CalledProcessError):
            all_passed = False

    print("\n" + "=" * 40)
    if all_passed:
        print("PREFLIGHT PASSED: Ready to push!")
        sys.exit(0)
    else:
        print("PREFLIGHT FAILED: Fix errors before pushing.")
        if not args.no_sync:
            print(
                "\n[TIP] If synchronization failed, try 'python preflight.py --no-sync'."
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
