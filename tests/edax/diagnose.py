#!/usr/bin/python3
"""
Explain why the EDAX hardware tests are running or skipping.

The gating lives in ``tests/conftest.py`` and depends only on environment
variables, so this reports exactly what the Python process sees. Run it from
the repository root with the same shell and environment used for pytest::

    python tests/edax/diagnose.py

Environment variables set in one terminal do not reach a different one, and
``$env:NAME`` in PowerShell silently creates whatever name is typed, so a
mis-typed or unprefixed variable looks identical to an unset one. This prints
every EDAX-related variable it can find, which makes that case obvious.
"""

# Default python modules
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests"))

import conftest  # noqa: E402

ACCEPTED_FLAGS = ("1", "true", "yes", "on")


def _show(name: str) -> str:
    """Print one variable as Python sees it and return its raw value."""
    raw = os.environ.get(name)
    if raw is None:
        print(f"  {name:<30} NOT SET")
    else:
        print(f"  {name:<30} {raw!r}")
    return raw or ""


def main() -> int:
    """Report the gating decision and the reason behind it."""
    print("EDAX hardware test gating\n")
    print(f"working directory: {Path.cwd()}")
    print(f"interpreter:       {sys.executable}\n")

    print("Required variables, as this Python process sees them:")
    host = _show(conftest.EDAX_HOST_ENV_VAR)
    flag = _show(conftest.RUN_EDAX_IPAPI_ENV_VAR)
    hardware_flag = _show(conftest.RUN_HARDWARE_ENV_VAR)

    related = {
        key: value
        for key, value in os.environ.items()
        if "EDAX" in key.upper() or "PYTRIBEAM" in key.upper()
    }
    print("\nEvery PYTRIBEAM/EDAX variable in this environment:")
    if related:
        for key in sorted(related):
            print(f"  {key:<30} {related[key]!r}")
    else:
        print("  (none)")

    host_ok = bool(host.strip())
    flag_ok = flag.strip().lower() in ACCEPTED_FLAGS
    hardware_ok = hardware_flag.strip().lower() in ACCEPTED_FLAGS

    print("\nChecks:")
    print(f"  host is non-empty                 {host_ok}")
    print(f"  run flag is one of {ACCEPTED_FLAGS}  {flag_ok}")
    print(f"  hardware flag accepted instead    {hardware_ok}")

    enabled = conftest.can_run_edax_ipapi()
    print(f"\ncan_run_edax_ipapi() -> {enabled}")

    if enabled:
        print("\nThe hardware tests should run. If they still skip, the skip")
        print("reason will name a different gate; paste it and check that")
        print("marker instead.")
        return 0

    print("\nThey will skip. Cause:")
    if not host_ok:
        print(f"  {conftest.EDAX_HOST_ENV_VAR} is empty or unset in THIS process.")
        print("  Check the spelling, including the PYTRIBEAM_ prefix, and that")
        print("  it was set in the same terminal that runs pytest.")
    elif not (flag_ok or hardware_ok):
        print(f"  {conftest.RUN_EDAX_IPAPI_ENV_VAR} is not an accepted value.")
        print(f"  Set it to one of {ACCEPTED_FLAGS}, for example \"1\".")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
