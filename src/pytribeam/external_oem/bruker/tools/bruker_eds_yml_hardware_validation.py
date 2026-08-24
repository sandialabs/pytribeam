"""Bruker EDS YAML Hardware Validation Script

Thin wrapper around the Bruker EDS workflow runner.
Loads a YAML config, runs the workflow, and logs results.

Usage:
    python bruker_eds_yml_hardware_validation.py <config.yml>
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# If package is not installed, uncomment/adjust this block.
REPO_ROOT = Path(__file__).resolve().parents[5]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


from pytribeam.external_oem.bruker.config import load_bruker_eds_yaml
from pytribeam.external_oem.bruker.runtime import validate_bruker_runtime_environment
from pytribeam.external_oem.bruker.workflow import run_bruker_eds_workflow


class TextLogger:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, msg: str):
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        print(line)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def main():

    parser = argparse.ArgumentParser(
        description="Run Bruker EDS hardware validation from YAML config"
    )
    parser.add_argument("config", help="Path to Bruker EDS validation YAML file")
    args = parser.parse_args()

    config_path = Path(args.config)

    config_yaml_text = config_path.read_text(encoding="utf-8")

    # Parse and validate config
    settings = load_bruker_eds_yaml(config_path)

    # Set up logger in the output directory
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = Path(settings.output.output_dir) / f"{settings.output.run_name}_{stamp}"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = TextLogger(log_dir / f"{settings.output.run_name}_{stamp}.log")

    log(f"Config: {config_path}")

    log("Validated settings loaded successfully")
    dll_info = validate_bruker_runtime_environment(settings.session)
    log(f"Bruker runtime preflight passed: {dll_info['esprit_dll']}")

    # Run the workflow
    result = run_bruker_eds_workflow(
        settings=settings,
        log_fn=log,
        config_yaml_text=config_yaml_text,
    )

    # Final summary
    log(f"Result: success={result.success}, elapsed={result.elapsed_s:.1f}s")
    if result.errors:
        for err in result.errors:
            log(f"  ERROR: {err}")


if __name__ == "__main__":
    main()
