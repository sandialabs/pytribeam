# Multi-version AutoScript support plan (4.8 / 4.10 / 4.11 + forward upgrades)

## 1. Purpose / goals
We need to:
- Support multiple physical instruments running Thermo AutoScript product releases: **4.8, 4.10, 4.11** (currently deployed on hardware).
- Enable a small developer team to build and maintain a **single Python package repo** with a test suite that validates behavior across these releases.
- Create a sustainable upgrade path to newer AutoScript releases without exploding maintenance burden.

## 2. Constraints / realities
- Instruments are offline or intermittently connected; upgrades are sporadic.
- At least one instrument is **Windows 7**, which effectively caps AutoScript at **4.10**.
- AutoScript installers include a Thermo-managed Python environment (often Enthought-based). Reproducing the full environment is brittle (numpy/h5py/CPU instruction set issues, etc.).
- Current instruments (4.8/4.10/4.11) use **Python 3.8**.
- We intentionally **pin Python patch versions** to prevent installs on untested Thermo Python builds:
  - `requires-python = ">=3.8.12, <=3.8.18"`
  - This range currently corresponds to the Thermo Python shipped with AutoScript **4.8/4.10/4.11** in our deployments.
- We cannot assume we control the customer installation process: customers will typically install AutoScript from a Thermo **.iso** and then install our package “on top” using whatever Thermo Python got installed.
- AutoScript usage requires licensing: automated testing will require a license key/server and/or Thermo’s Windows “offline" tool.

## 3. Strategy overview
**Core strategy:** maintain *one* repo + a small compatibility layer, and test it against **pinned “client environments” per AutoScript release**.

We separate concerns:
- **Microscope “server”** runs on the instrument PC (or virtualization).
- Our code runs as a **client** using Thermo’s installed client libraries.
- For developer testing we can recreate each client environment in isolation using *per-release wheel bundles* (wheelhouses).

## 4. Support policy (two-tier)
- **Tier 1 (fully supported + continuously tested):** AutoScript **4.8, 4.10, 4.11**
  - Required because these versions exist on active instruments.
  - Every release of our package must pass tests for these versions (offline tests always; integration/sim tests as available from manually running test suites).
- **Tier 2 (forward-looking / best-effort):** newest available AutoScript (e.g., 4.12.1+)
  - Validate early (imports + smoke tests) to reduce upgrade risk.
  - Promote to Tier 1 only after deployment to at least one instrument + successful smoke tests.

## 5. Packaging and dependency policy (important)

### 5.1 Separate runtime dependencies from dev/test tools
Avoid shipping formatter/test tools as runtime dependencies on instrument machines. Target model:
- `[project.dependencies]`: runtime only (what is required to run experiments)
- `[project.optional-dependencies].dev`: pytest/black/linters/docs tools

This reduces offline-install complexity and keeps “production” installs smaller and more stable.

### 5.2 Prefer wheel installs on instruments; editable installs for development
- **Instrument/customer default:** install a built `pytribeam` wheel for reproducibility and easier support.
- **Developer/debug mode:** `pip install -e .` is acceptable, but not the default for deployment.

### 5.3 Versioning discipline
We should move away from “forgetting to bump version” and adopt one of:
- **Manual version bumping** (minimal change, but requires discipline), or
- **Automatic versioning** via `setuptools-scm` (recommended) so versions come from git tags or releases.

## 6. Versioned client environments (“wheelhouses”)
For each AutoScript product release `v` in (`v4.8`, `v4.10`, `v4.11`), we maintain a reproducible client environment spec.

### 6.1 Artifacts per release
- `vendor/autoscript/<v>/wheels/` *(optional in-repo; may be restricted by licensing/IP)*  
  Thermo-provided client wheels for that AutoScript release. We can obtain these for 4.8/4.10/4.11.
- `constraints/autoscript_<v>-py38.txt` *(optional)*  
  Pinned third-party dependencies if required (numpy/h5py/etc.), especially for older CPUs/Win7. May want to separate between what ships with Enthought and what we need for our repo.
- `metadata/autoscript_<v>.json`  
  Records:
  - Thermo wheel names + versions
  - expected Python version(s)
  - source (portal/ISO path)
  - notes (known issues, special pins)

### 6.2 Why this helps
- Developers can recreate environments deterministically.
- Offline installs become manageable (install from wheelhouse, not the internet).
- We avoid relying on the installer’s full environment as the canonical dev setup.

## 7. One repo + compatibility layer
We keep one codebase and isolate version differences in a small module.

- `src/pytribeam/compat/`
  - wrappers that normalize behavior across versions
  - feature detection first, version checks second

**Rule:** no scattered version checks across the codebase; all cross-version logic goes through `compat/`.
- not actually sure how this will be implemented

## 8. Testing approach

### 8.1 Test categories
- **AutoScript-dependent tests (licensed / client bundle required):**
  - run only on a controlled environment (self-hosted runner)
  - validate imports + “virtualized tool” behaviors and/or limited integration logic
- **Unit/contract tests (no AutoScript required):**
  - run anywhere (GitHub-hosted CI)
  - use mocks/stubs to validate wrapper logic and compatibility layer
    - may be more trouble than its worth

### 8.2 Pytest markers
Use markers to split tests cleanly:
- `@pytest.mark.autoscript`: requires AutoScript libraries/license/virtualization
- `@pytest.mark.integration`: requires instrument or virtualization connectivity
- Can we add additional layers of markers for differing hardware types?

CI can then run:
- `pytest -m "not autoscript"` on GitHub-hosted runners
- `pytest -m "autoscript"` on self-hosted licensed runners

Suggested `pytest.ini` at repo root:

```ini
[pytest]
testpaths = tests
markers =
    autoscript: tests requiring Thermo AutoScript (licensed or client bundle)
    integration: tests requiring virtualization or instrument access
addopts = -ra
```

## 9. Developer workflow tooling: tox/nox (multi-version orchestration)
We use an environment orchestration tool to standardize multi-version testing:

- **tox**: declarative test environments (e.g., `as48`, `as410`, `as411`) created automatically.
- **nox**: similar, but sessions are written in Python (useful for conditional offline logic).

Each environment installs:
1) Thermo client wheels for a specific AutoScript release from `vendor/autoscript/<v>/wheels/` (or equivalent external location)
2) Pytribeam runtime deps (offline wheelhouse as needed)
3) Pytribeam itself (preferably as a wheel install for reproducibility)
4) Test deps and runs pytest

## 10. CI/CD plan (GitHub Actions)

Self-hosted runner (licensed, Windows, Thermo Python). Runs on a Windows machine we control with:
- Thermo Python environment installed
- license key/server configured (one-time)
- Thermo virtualized tool installed/configured (as needed)

This can run:
- `pytest -m "autoscript"` tests
- a matrix across AutoScript versions (4.8/4.10/4.11) using venvs + per-version client wheelhouses

Can we transition to anything up in github (non-autoscript tests)?

## 11. Self-hosted runner design: one machine, multiple AutoScript versions
Goal: run tests against **multiple AutoScript versions on one machine** without uninstall/reinstall cycles.

### 11.1 Preferred approach: per-version venvs created from Thermo Python
- Keep Thermo Python as the interpreter (to match customer reality).
- Create venvs:
  - `C:\autoscript_test_envs\as48`
  - `C:\autoscript_test_envs\as410`
  - `C:\autoscript_test_envs\as411`
- Install the per-version Thermo client wheels into the corresponding venv from:
  - `C:\autoscript_wheelhouses\4.8`
  - `C:\autoscript_wheelhouses\4.10`
  - `C:\autoscript_wheelhouses\4.11`
- Install pytribeam + dev/test deps into each venv and run tests.

### 11.2 Open question: virtualization version sensitivity
We need to confirm whether the Windows “virtualized tool” emulates the **server** component in a way that is:
- version-sensitive (must pair 4.8 virtual server with 4.8 client), or
- broadly compatible across multiple client versions.

This affects whether a single virtualization install can cover all versions or we need multiple virtual server setups.

## 12. Instrument/customer installation model (offline, using Thermo Python)
On instrument PCs we will typically use Thermo’s installed Python, e.g.:
`C:\Program Files\Enthought\Python\envs\Autoscript\python.exe`

We ship:
- a `pytribeam` wheel (preferred) and/or source tree (for dev/debug)
- an offline dependency wheelhouse
- an install script that:
  - detects installed AutoScript client version
  - installs compatible pytribeam build
  - installs deps from wheelhouse without internet
  - optionally runs smoke/unit tests

**Default is non-editable wheel install** on instruments for reproducibility. Editable installs are reserved for active development/debug.

## 13. Scripts folder layout (repo-level tooling; does not replace `src/`)
Recommended additions:

```text
scripts/
  README.md
  common.cmd
  install_instrument.cmd
  run_tests_no_autoscript.cmd
  run_tests_autoscript_matrix.cmd
  runner/
    bootstrap_venvs.cmd
    run_autoscript_tests.cmd
```

### 13.1 Script responsibilities
- scripts/common.cmd: shared paths and defaults (Thermo python path, wheelhouse roots).
- scripts/install_instrument.cmd: offline installer for instrument/customer machines (wheel-first; supports --editable and --test).
- scripts/run_tests_no_autoscript.cmd: runs pytest -m "not autoscript".
- scripts/run_tests_autoscript_matrix.cmd: runs AutoScript tests for 4.8/4.10/4.11 sequentially on a properly configured machine.
- scripts/runner/bootstrap_venvs.cmd: one-time setup on the self-hosted runner to create venvs and install per-version AutoScript client wheels + pytribeam dev deps.
- scripts/runner/run_autoscript_tests.cmd: run AutoScript-marked tests for a given AutoScript version venv.

### 13.2 Script templates

#### scripts/common.cmd
```bat
@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Default Thermo python (override by setting THERMO_PY in environment)
if "%THERMO_PY%"=="" set THERMO_PY=C:\Program Files\Enthought\Python\envs\Autoscript\python.exe

REM Instrument install wheelhouse locations (override as needed)
if "%PYTRIBEAM_WHEELHOUSE%"=="" set PYTRIBEAM_WHEELHOUSE=%~dp0..\wheelhouse
if "%PYTRIBEAM_WHEELS%"=="" set PYTRIBEAM_WHEELS=%~dp0..\pytribeam_wheels

REM Self-hosted runner locations (override on runner machine)
if "%AS_ENVROOT%"=="" set AS_ENVROOT=C:\autoscript_test_envs
if "%AS_WHEELROOT%"=="" set AS_WHEELROOT=C:\autoscript_wheelhouses

exit /b 0
```

#### scripts/install_instrument.cmd
```bat

@echo off
setlocal EnableExtensions EnableDelayedExpansion
call "%~dp0common.cmd"

set MODE=wheel
set RUN_TESTS=0

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--editable" set MODE=editable
if /I "%~1"=="--test" set RUN_TESTS=1
shift
goto parse_args
:args_done

if not exist "%THERMO_PY%" (
  echo ERROR: Thermo python not found: "%THERMO_PY%"
  exit /b 1
)

set PYEXE="%THERMO_PY%"

%PYEXE% -m pip install --no-index --find-links "%PYTRIBEAM_WHEELHOUSE%" pip setuptools wheel
if errorlevel 1 exit /b 1

for /f "usebackq delims=" %%v in (`%PYEXE% -c "import importlib.metadata as m; print(m.version('autoscript_sdb_microscope_client'))"`) do set ASCLIENT=%%v
if "%ASCLIENT%"=="" (
  echo ERROR: Could not detect autoscript_sdb_microscope_client version.
  exit /b 1
)

for /f "tokens=1,2 delims=." %%a in ("%ASCLIENT%") do set ASMAJOR=%%a.%%b
echo Detected AutoScript client: %ASCLIENT%  (major.minor=%ASMAJOR%)

set PYTRIBEAM_SPEC=
if "%ASMAJOR%"=="4.8"  set PYTRIBEAM_SPEC=pytribeam
if "%ASMAJOR%"=="4.10" set PYTRIBEAM_SPEC=pytribeam
if "%ASMAJOR%"=="4.11" set PYTRIBEAM_SPEC=pytribeam

if "%PYTRIBEAM_SPEC%"=="" (
  echo ERROR: Unsupported AutoScript client major.minor: %ASMAJOR%
  echo Supported: 4.8, 4.10, 4.11
  exit /b 2
)

if exist "%~dp0..\requirements-runtime.txt" (
  %PYEXE% -m pip install --no-index --find-links "%PYTRIBEAM_WHEELHOUSE%" -r "%~dp0..\requirements-runtime.txt"
  if errorlevel 1 exit /b 1
)

if /I "%MODE%"=="wheel" (
  %PYEXE% -m pip install --no-index --find-links "%PYTRIBEAM_WHEELS%" %PYTRIBEAM_SPEC%
  if errorlevel 1 exit /b 1
) else (
  %PYEXE% -m pip install -e "%~dp0.." --no-index --no-build-isolation --find-links "%PYTRIBEAM_WHEELHOUSE%"
  if errorlevel 1 exit /b 1
)

if "%RUN_TESTS%"=="1" (
  %PYEXE% -m pytest -q -m "not autoscript"
  if errorlevel 1 exit /b 1
)

echo Done.
exit /b 0
```

#### scripts/runner/run_autoscript_tests.cmd
```bat

@echo off
setlocal EnableExtensions EnableDelayedExpansion
call "%~dp0..\common.cmd"

set AS_VER=%~1
if "%AS_VER%"=="" (
  echo Usage: run_autoscript_tests.cmd ^<4.8^|4.10^|4.11^>
  exit /b 2
)

set VENV=%AS_ENVROOT%\as%AS_VER:.=%
set PYEXE=%VENV%\Scripts\python.exe

if not exist "%PYEXE%" (
  echo ERROR: venv missing: "%VENV%"
  echo Run scripts\runner\bootstrap_venvs.cmd first.
  exit /b 1
)

"%PYEXE%" -m pytest -q -m "autoscript"
exit /b %ERRORLEVEL%

scripts/runner/bootstrap_venvs.cmd
bat

@echo off
setlocal EnableExtensions EnableDelayedExpansion
call "%~dp0..\common.cmd"

if not exist "%THERMO_PY%" (
  echo ERROR: Thermo python not found: "%THERMO_PY%"
  exit /b 1
)

for %%V in (4.8 4.10 4.11) do (
  set VENV=%AS_ENVROOT%\as%%V:.=%
  set ASW=%AS_WHEELROOT%\%%V

  echo === Bootstrapping %%V ===
  if not exist "!ASW!" (
    echo ERROR: Missing AutoScript wheelhouse: "!ASW!"
    exit /b 1
  )

  if not exist "!VENV!\Scripts\python.exe" (
    "%THERMO_PY%" -m venv "!VENV!"
    if errorlevel 1 exit /b 1
  )

  set PYEXE=!VENV!\Scripts\python.exe

  "!PYEXE!" -m pip install --upgrade pip setuptools wheel
  if errorlevel 1 exit /b 1

  "!PYEXE!" -m pip install --no-index --find-links "!ASW!" ^
    autoscript_sdb_microscope_client autoscript_toolkit autoscript_core thermoscientific_logging
  if errorlevel 1 exit /b 1

  "!PYEXE!" -m pip install "%~dp0..\.."[dev]
  if errorlevel 1 exit /b 1
)

echo All venvs bootstrapped.
exit /b 0
```

# 14. pyproject.toml recommendation (patch-pinned Python kept)

We keep patch pinning to prevent installs on untested Thermo Python builds.
## 14.1 Minimal (manual version bumping)

```toml

[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "pytribeam"
authors = [
  { name="Andrew Polonsky", email="apolon@sandia.gov" },
  { name="Chad Hovey", email="chovey@sandia.gov" },
  { name="James Lamb", email="jlamb@ucsb.edu" },
]
description = "automated data collection on TriBeam tools"
readme = "README.md"
requires-python = ">=3.8.12, <=3.8.18"

# Runtime deps only (keep minimal for instrument installs)
dependencies = [
  "schema",
]

version = "0.0.1"

[project.optional-dependencies]
dev = [
  "black",
  "flake8",
  "pycodestyle",
  "pytest==8.3.3",
  "pytest-cov==5.0.0",
  "pdoc",
]

ci_cd = [
  "pytribeam[dev]",
  "anybadge",
  "pylint",
  "docstr-coverage",
]

[docstr-coverage]
ignore = [
  "tests/",
  "src/pytribeam/GUI/",
]

[project.urls]
documentation = "https://gitlab-ex.sandia.gov/tribeam/pytribeam/"
repository = "https://gitlab-ex.sandia.gov/tribeam/pytribeam"

[project.scripts]
pytribeam = "pytribeam.command_line:pytribeam"
pytribeam_info = "pytribeam.command_line:module_info"
pytribeam_gui = "pytribeam.command_line:launch_gui"
pytribeam_exp = "pytribeam.command_line:run_experiment"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

14.2 Recommended (automatic versioning via git tags using setuptools-scm)
toml

[build-system]
requires = ["setuptools>=61.0", "wheel", "setuptools-scm>=8"]
build-backend = "setuptools.build_meta"

[project]
name = "pytribeam"
authors = [
  { name="Andrew Polonsky", email="apolon@sandia.gov" },
  { name="Chad Hovey", email="chovey@sandia.gov" },
  { name="James Lamb", email="jlamb@ucsb.edu" },
]
description = "automated data collection on TriBeam tools"
readme = "README.md"
requires-python = ">=3.8.12, <=3.8.18"

dependencies = [
  "schema",
]

dynamic = ["version"]

[project.optional-dependencies]
dev = [
  "black",
  "flake8",
  "pycodestyle",
  "pytest==8.3.3",
  "pytest-cov==5.0.0",
  "pdoc",
]

ci_cd = [
  "pytribeam[dev]",
  "anybadge",
  "pylint",
  "docstr-coverage",
]

[docstr-coverage]
ignore = [
  "tests/",
  "src/pytribeam/GUI/",
]

[project.urls]
documentation = "https://gitlab-ex.sandia.gov/tribeam/pytribeam/"
repository = "https://gitlab-ex.sandia.gov/tribeam/pytribeam"

[project.scripts]
pytribeam = "pytribeam.command_line:pytribeam"
pytribeam_info = "pytribeam.command_line:module_info"
pytribeam_gui = "pytribeam.command_line:launch_gui"
pytribeam_exp = "pytribeam.command_line:run_experiment"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools_scm]
version_scheme = "post-release"
local_scheme = "no-local-version"
```

# 15. GitHub Actions + self-hosted runner summary

Always-on (GitHub-hosted): build wheel, smoke install/import, run pytest -m "not autoscript".

Licensed (self-hosted Windows runner): run pytest -m "autoscript" across a matrix of AutoScript versions (4.8/4.10/4.11) using per-version venvs created from Thermo Python.

# 16. Open needs / external asks (Thermo)

To make this sustainable we need, for AutoScript 4.8 / 4.10 / 4.11:

- authoritative client wheel bundle definitions (mapping from product release label to component wheels/versions)
- Python version support guidance per release (confirming the patch-pinned range we rely on)
- third-party dependency constraints guidance (esp. numpy/h5py, Win7/older CPUs)
- API-breaking change notes (Python API behavior changes)
- recommended workflow confirmation (venv + client wheels)
- guidance on virtualization: whether the “virtualized tool” emulates the server in a version-sensitive way, and what client/server version combinations are supported
