## python standard libraries
import ast
from pathlib import Path

# 3rd party libraries
import pytest

STATE_DIR = Path(__file__).parent.parent.parent / "src" / "pytribeam" / "mcp" / "state"

# capture.py is the one module under state/ allowed to touch the vendor SDK
# and the rest of pytribeam -- it is the module that talks to the hardware.
# See mcp_context_transfer.md R1 and state/capture.py's own docstring.
EXEMPT_FILES = {"capture.py"}

FORBIDDEN_MODULES = (
    "autoscript_sdb_microscope_client",
    "pytribeam.types",
    "pytribeam.utilities",
    "pytribeam.constants",
)
# `from pytribeam import types` (etc) form: same modules, different AST shape.
FORBIDDEN_FROM_PYTRIBEAM_NAMES = {"types", "utilities", "constants"}


def _forbidden_imports(tree: ast.AST) -> list:
    """Return a list of human-readable descriptions of forbidden imports found in *tree*."""
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (
                    alias.name == "autoscript_sdb_microscope_client"
                    or alias.name.startswith("autoscript_sdb_microscope_client.")
                ):
                    violations.append(f"import {alias.name}")
                for forbidden in FORBIDDEN_MODULES:
                    if alias.name == forbidden or alias.name.startswith(
                        forbidden + "."
                    ):
                        violations.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            if (
                node.module == "autoscript_sdb_microscope_client"
                or node.module.startswith("autoscript_sdb_microscope_client.")
            ):
                violations.append(f"from {node.module} import ...")
            for forbidden in FORBIDDEN_MODULES:
                if node.module == forbidden or node.module.startswith(forbidden + "."):
                    violations.append(f"from {node.module} import ...")
            if node.module == "pytribeam":
                for alias in node.names:
                    if alias.name in FORBIDDEN_FROM_PYTRIBEAM_NAMES:
                        violations.append(f"from pytribeam import {alias.name}")
    return violations


def _state_files():
    return sorted(p for p in STATE_DIR.glob("*.py") if p.name not in EXEMPT_FILES)


@pytest.mark.detached
@pytest.mark.parametrize("path", _state_files(), ids=lambda p: p.name)
def test_no_forbidden_imports(path: Path):
    """state/*.py (except capture.py) must not import AutoScript or the
    parts of pytribeam that hard-import it.

    This is R1 from mcp_context_transfer.md: `pytribeam.types` hard-imports
    the vendor client at module scope, and `utilities`/`constants` both
    import `types`, so any of them poisons the whole subpackage for anyone
    without the vendor software installed. If this test fails, the import
    you just added is the bug -- don't relax this test to make it pass.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = _forbidden_imports(tree)
    assert not violations, f"{path.name} has forbidden imports: {violations}"


@pytest.mark.detached
def test_capture_is_the_only_exempt_file():
    """Guards against the exemption list quietly growing.

    If you're adding a new file here, ask first -- state/ being importable
    without AutoScript is the entire point of splitting it out.
    """
    assert EXEMPT_FILES == {"capture.py"}
