#!/usr/bin/python3
"""
Explain why the EDAX hardware tests are running or skipping.

The EDAX hardware tests come in two tiers with different gates:

- **IPAPI sweep** (``test_edax_ipapi_hardware.py``): read-only, runs from any
  machine that can reach the IPAPI. Needs ``PYTRIBEAM_EDAX_HOST`` and
  ``PYTRIBEAM_RUN_EDAX_IPAPI``.
- **Collection** (``test_edax_collection_hardware.py``): inserts detectors and
  writes maps, so it runs only on the microscope PC. Needs AutoScript, the laser
  API, ``PYTRIBEAM_RUN_HARDWARE``, and an EDAX-declared system.

The gating lives in ``tests/conftest.py``; this reuses those same functions and
reports each condition, in the order pytest applies them, so the first failure
is the one pytest reports. Run it from the repository root, in the same shell
and environment used for pytest::

    python tests/edax/diagnose.py

Add ``--apex`` to also ask APEX, read-only, what state its EDS and EBSD sides
are in. Nothing is changed and nothing moves, so it is safe to run while APEX
appears stuck, and it is worth capturing before restarting it::

    python tests/edax/diagnose.py --apex

Output is plain ASCII so it reads correctly in a default PowerShell console.
"""

# Default python modules
import os
import platform
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import conftest  # noqa: E402

ACCEPTED_FLAGS = ("1", "true", "yes", "on")

ALLOW_MAPPING_ENV_VAR = "PYTRIBEAM_EDAX_ALLOW_MAPPING"
MAP_FOLDER_ENV_VAR = "PYTRIBEAM_EDAX_MAP_FOLDER"


def _flag(name: str) -> bool:
    """Return True when a variable holds an accepted opt-in value."""
    return os.environ.get(name, "").strip().lower() in ACCEPTED_FLAGS


def _value(name: str) -> str:
    """Return a variable for display, marking it when unset."""
    raw = os.environ.get(name)
    return "NOT SET" if raw is None else repr(raw)


def _report(checks) -> bool:
    """Print a tier's checks and name the first failure. Return True if all pass."""
    for label, passed, detail, _fix in checks:
        print(f"  [{'ok' if passed else 'FAIL'}] {label:<42} {detail}")
    failures = [check for check in checks if not check[1]]
    if not failures:
        print("  -> will run")
        return True
    label, _passed, _detail, fix = failures[0]
    print(f"  -> will skip at: {label}")
    print(f"     fix: {fix}")
    return False


def _environment() -> None:
    """Print where settings come from."""
    print(f"working directory: {Path.cwd()}")
    print(f"interpreter:       {sys.executable}")
    print(f"hostname:          {platform.uname().node}")
    if conftest.ENV_FILE.is_file():
        print(f"env file:          {conftest.ENV_FILE}")
        applied = ", ".join(sorted(conftest.ENV_FILE_APPLIED)) or (
            "nothing (all already set in the shell)"
        )
        print(f"  supplied from it:  {applied}")
    else:
        print(f"env file:          none at {conftest.ENV_FILE}")

    related = {
        key: value
        for key, value in os.environ.items()
        if "EDAX" in key.upper() or "PYTRIBEAM" in key.upper()
    }
    print("\nEvery PYTRIBEAM/EDAX variable this process sees:")
    for key in sorted(related) or ["(none)"]:
        print(f"  {key:<30} {related[key]!r}" if key in related else f"  {key}")


def _ipapi_checks():
    """Gates for the read-only IPAPI sweep."""
    host = os.environ.get(conftest.EDAX_HOST_ENV_VAR, "").strip()
    run_flag = _flag(conftest.RUN_EDAX_IPAPI_ENV_VAR) or _flag(
        conftest.RUN_HARDWARE_ENV_VAR
    )
    return [
        (
            conftest.EDAX_HOST_ENV_VAR,
            bool(host),
            _value(conftest.EDAX_HOST_ENV_VAR),
            f"{conftest.EDAX_HOST_ENV_VAR}=<ipapi host>   (check the PYTRIBEAM_ prefix)",
        ),
        (
            f"{conftest.RUN_EDAX_IPAPI_ENV_VAR} (or RUN_HARDWARE)",
            run_flag,
            _value(conftest.RUN_EDAX_IPAPI_ENV_VAR),
            f"{conftest.RUN_EDAX_IPAPI_ENV_VAR}=1",
        ),
    ]


def _collection_checks():
    """Gates for the collection tests, in the order pytest applies them."""
    checks = []

    # 1. The module imports AutoScript, and is skipped whole without it.
    try:
        import autoscript_sdb_microscope_client  # noqa: F401

        autoscript = True
    except ImportError:
        autoscript = False
    checks.append(
        (
            "AutoScript importable",
            autoscript,
            "yes" if autoscript else "no",
            "run on the microscope PC, in the environment with AutoScript",
        )
    )
    if not autoscript:
        # Everything below needs pytribeam.constants, which needs AutoScript.
        return checks

    # 2. The module-level opt-in.
    checks.append(
        (
            ALLOW_MAPPING_ENV_VAR,
            _flag(ALLOW_MAPPING_ENV_VAR),
            _value(ALLOW_MAPPING_ENV_VAR),
            f"{ALLOW_MAPPING_ENV_VAR}=1",
        )
    )

    # 3-5. The marker gates, in the order conftest adds their skip markers.
    from pytribeam.constants import Constants

    hardware = conftest.is_hardware_system()
    checks.append(
        (
            "'hardware': hostname is a microscope PC",
            hardware,
            f"known: {Constants.microscope_machines}",
            "run on a listed PC, or add this hostname to Constants.microscope_machines",
        )
    )
    laser = hardware and conftest.has_laser_hardware()
    checks.append(
        (
            "'laser_hardware': laser API importable",
            laser,
            "yes" if laser else "no",
            "run in the environment where Laser.PythonControl imports",
        )
    )

    run_hardware = _flag(conftest.RUN_HARDWARE_ENV_VAR)
    checks.append(
        (
            f"'edax_hardware': {conftest.RUN_HARDWARE_ENV_VAR}",
            run_hardware,
            _value(conftest.RUN_HARDWARE_ENV_VAR),
            f"{conftest.RUN_HARDWARE_ENV_VAR}=1   "
            f"({conftest.RUN_EDAX_IPAPI_ENV_VAR} does not count here)",
        )
    )
    declared = conftest._declared_test_oem() == "edax"
    edax_host = conftest.is_edax_hardware_system()
    checks.append(
        (
            "'edax_hardware': system declared EDAX",
            declared or edax_host,
            f"{conftest.TEST_OEM_ENV_VAR}={_value(conftest.TEST_OEM_ENV_VAR)}, "
            f"EDAX hosts: {Constants.microscope_with_edax_machines}",
            f"{conftest.TEST_OEM_ENV_VAR}=edax",
        )
    )

    # 6. Checked by the module's fixture once the markers allow it to run.
    checks.append(
        (
            conftest.EDAX_HOST_ENV_VAR,
            bool(os.environ.get(conftest.EDAX_HOST_ENV_VAR, "").strip()),
            _value(conftest.EDAX_HOST_ENV_VAR),
            f"{conftest.EDAX_HOST_ENV_VAR}=localhost",
        )
    )
    checks.append(
        (
            MAP_FOLDER_ENV_VAR,
            bool(os.environ.get(MAP_FOLDER_ENV_VAR, "").strip()),
            _value(MAP_FOLDER_ENV_VAR),
            f"{MAP_FOLDER_ENV_VAR}=<existing scratch folder on the EDAX PC>",
        )
    )
    return checks


#: Read-only queries describing what APEX is doing, reported as raw payloads.
APEX_STATE_COMMANDS = (
    "get_system_isappstarted",
    "get_map_status",
    "get_system_detector_status",
    "get_eds_detector_status",
    "get_eds_detector_cooling_status",
    "get_map_params_folderpath",
    "get_map_params_numpoints",
    "get_map_params_numlines",
    "get_map_params_numframes",
    "get_map_params_presetdwell",
    "get_map_duration",
    "get_system_isappstarted_ebsd",
    "get_map_status_ebsd",
    "get_camera_status",
    "get_ebsd_params_folderpath",
)


def _apex_state() -> int:
    """Print APEX's raw EDS and EBSD state. Read-only."""
    from pytribeam.external_oem.edax.client import EdaxClient
    from pytribeam.external_oem.edax.errors import EdaxError
    from pytribeam.external_oem.edax.types import EdaxConnectionSettings

    host = os.environ.get(conftest.EDAX_HOST_ENV_VAR, "").strip() or "localhost"
    port = int(os.environ.get("PYTRIBEAM_EDAX_PORT", "8301"))
    print(f"\nAPEX state at {host}:{port}  (read-only)")
    try:
        client = EdaxClient(
            EdaxConnectionSettings(host=host, port=port, timeout_s=15.0), quiet=True
        ).connect()
    except EdaxError as error:
        print(f"  could not connect: {error}")
        return 1
    try:
        for command in APEX_STATE_COMMANDS:
            try:
                print(f"  {command:<34} {client.query(command)!r}")
            except EdaxError as error:
                print(f"  {command:<34} <{type(error).__name__}: {error}>")
        events = client.drain_events(timeout_s=1.0)
        print(f"  pending events: {[event.raw for event in events] or 'none'}")
    finally:
        client.close()
    return 0


def main() -> int:
    """Report both tiers. Exit 0 only when every tier would run."""
    if "--apex" in sys.argv[1:]:
        return _apex_state()

    print("EDAX hardware test gating\n")
    _environment()

    print("\nIPAPI sweep  (test_edax_ipapi_hardware.py)")
    sweep = _ipapi_checks()
    sweep_ok = _report(sweep)
    # Cross-check against the function pytest actually calls.
    if sweep_ok != conftest.can_run_edax_ipapi():
        print("  !! disagrees with conftest.can_run_edax_ipapi(); please report")

    print("\nCollection  (test_edax_collection_hardware.py)")
    collection = _collection_checks()
    collection_ok = _report(collection)

    return 0 if (sweep_ok and collection_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
