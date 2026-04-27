#!/usr/bin/env python3
"""
Preflight script to verify CI/CD readiness.
Runs lint checks and tests relevant to the CI/CD reporting logic.
"""

import shlex
import subprocess
import sys
from typing import List


def run_step(command: List[str], description: str) -> bool:
    """
    Executes a shell command and prints the result.

    Args:
        command: The command to execute as a list of strings.
        description: A human-readable description of the step.

    Returns:
        True if the command succeeded, False otherwise.
    """
    print(f"\n--- {description} ---")
    try:
        # We allow output to flow to stdout/stderr for real-time feedback
        subprocess.check_call(command)
        print("Result: [SUCCESS]")
        return True
    except subprocess.CalledProcessError:
        print("Result: [FAILED]")
        return False
    except FileNotFoundError:
        print("Result: [ERROR] (Command not found. Is 'uv' installed?)")
        return False


def main() -> None:
    """
    Main entry point for preflight checks.
    """
    print("Starting Preflight Checks...")

    steps: List[str] = [
        "uv run ruff format --check src/pytribeam/cicd/",
        "uv run pytest tests/cicd",
        "uv run pytest --no-cov tests/test_example.py",
    ]

    all_passed: bool = True
    for cmd_str in steps:
        if not run_step(shlex.split(cmd_str), cmd_str):
            all_passed = False

    print("\n" + "=" * 40)
    if all_passed:
        print("PREFLIGHT PASSED: Ready to push!")
        sys.exit(0)
    else:
        print("PREFLIGHT FAILED: Fix errors before pushing.")
        sys.exit(1)


if __name__ == "__main__":
    main()
    main()
