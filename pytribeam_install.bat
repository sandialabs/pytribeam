@echo off
setlocal EnableExtensions

REM ============================================================
REM pyTriBeam offline installer
REM
REM Installs pyTriBeam into the AutoScript Python environment using only the
REM wheels in .\wheelhouse, so no internet connection is needed. The wheels
REM supply the build backend, the developer tools, and a few small runtime
REM dependencies; the scientific stack (numpy, h5py, ...) comes from the
REM AutoScript environment itself.
REM
REM Every wheel in the wheelhouse is treated as a pin: when pip needs one of
REM those packages, it gets exactly the wheelhouse version. To update a
REM dependency, swap its wheel; there is no version list to edit here.
REM ============================================================

set "PYTHON=C:\Program Files\Enthought\Python\envs\Autoscript\python.exe"
set "WHEELHOUSE=%~dp0wheelhouse"
set "LOG=%~dp0pytribeam_install.log"
set "CONSTRAINTS=%TEMP%\pytribeam_constraints.txt"

REM Installed by older versions of this script and no longer wanted.
set "STALE_PACKAGES=black mypy_extensions vcs_versioning"


REM ============================================================
REM Arguments
REM ============================================================
set "ORIG_ARGS=%*"
set "PS_WRAPPED=0"
set "DEV_INSTALL=0"

:PARSE_ARGS
if "%~1"=="" goto :ARGS_DONE
if /I "%~1"=="--ps-wrapped" (
  REM Internal: set when this script relaunches itself in PowerShell.
  set "PS_WRAPPED=1"
) else if /I "%~1"=="-d" (
  set "DEV_INSTALL=1"
) else if /I "%~1"=="--dev" (
  set "DEV_INSTALL=1"
) else if /I "%~1"=="--developer" (
  set "DEV_INSTALL=1"
) else if /I "%~1"=="-h" (
  call :USAGE & exit /b 0
) else if /I "%~1"=="--help" (
  call :USAGE & exit /b 0
) else (
  echo [ERROR] Unknown option: "%~1"
  call :USAGE & exit /b 1
)
shift /1
goto :PARSE_ARGS

:ARGS_DONE


REM ============================================================
REM When double-clicked from Explorer, relaunch in a PowerShell window that
REM stays open so the user can read the output. When run from an existing
REM terminal, just run in place.
REM ============================================================
if "%PS_WRAPPED%"=="1" goto :INSTALL
call :LAUNCHED_FROM_EXPLORER || goto :INSTALL

set "PYTRIBEAM_INSTALLER=%~f0"
powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -Command "& $env:PYTRIBEAM_INSTALLER --ps-wrapped %ORIG_ARGS%"
exit /b %ERRORLEVEL%


:INSTALL
if "%DEV_INSTALL%"=="1" (
  set "MODE=Developer/editable"
  set "EDITABLE=-e"
  set "TARGET=.[dev]"
  set "BUILD_DEPS=hatchling hatch-vcs editables"
) else (
  set "MODE=Standard/non-editable"
  set "EDITABLE="
  set "TARGET=."
  set "BUILD_DEPS=hatchling hatch-vcs"
)

echo ===========================================================
echo Install pyTriBeam - %DATE% %TIME%
echo Script:       %~f0
echo Python:       "%PYTHON%"
echo Wheelhouse:   "%WHEELHOUSE%"
echo Install mode: %MODE%
echo Pip log:      "%LOG%"
echo ===========================================================

if not exist "%PYTHON%" (
  echo [ERROR] AutoScript Python not found: "%PYTHON%"
  goto :FAIL
)
if not exist "%WHEELHOUSE%\" (
  echo [ERROR] Wheelhouse folder not found: "%WHEELHOUSE%"
  goto :FAIL
)

REM Build from the folder this script lives in, whatever the caller's current
REM directory is. SETLOCAL restores the caller's directory on exit.
pushd "%~dp0"

REM Offline only. pip appends a detailed record of every command to PIP_LOG;
REM it is the first thing to ask for when an install goes wrong.
set "PIP_NO_INDEX=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_LOG=%LOG%"
>>"%LOG%" echo ===== pyTriBeam install, %DATE% %TIME%, %MODE% =====

REM pyproject.toml computes the version via hatch-vcs, which shells out to git.
REM A zip download (the normal offline-install path) has no .git folder, so
REM hatch-vcs/setuptools-scm has nothing to compute from and raises LookupError.
REM Work around that by telling setuptools-scm to use the version already
REM baked into the tracked src\pytribeam\_version.py (kept in sync with each
REM release — see CONTRIBUTING.md). When .git IS present (e.g. installing
REM from a real clone), leave it alone so hatch-vcs reports the real,
REM git-derived version instead of the possibly-stale tracked one.
set "SETUPTOOLS_SCM_PRETEND_VERSION="
if exist "%~dp0.git" (
  echo [INFO] Git metadata found; version will be computed from git.
) else (
  set "VERSION_FILE=%~dp0src\pytribeam\_version.py"
  if not exist "%VERSION_FILE%" (
    echo [ERROR] Version file not found: "%VERSION_FILE%"
    goto :FAIL
  )
  for /f "tokens=2 delims='" %%V in ('findstr /b "__version__ = version = " "%VERSION_FILE%"') do set "SETUPTOOLS_SCM_PRETEND_VERSION=%%V"
  if not defined SETUPTOOLS_SCM_PRETEND_VERSION (
    echo [ERROR] Could not parse version from "%VERSION_FILE%"
    goto :FAIL
  )
  echo [INFO] No git metadata; pinning version to %SETUPTOOLS_SCM_PRETEND_VERSION% from _version.py
  >>"%LOG%" echo No .git found; SETUPTOOLS_SCM_PRETEND_VERSION=%SETUPTOOLS_SCM_PRETEND_VERSION%
)

REM Pin every package to its wheelhouse version. Pillow is the exception:
REM its wheel is a fallback for environments without a usable Pillow, so an
REM existing Pillow<10 in the AutoScript environment is left alone.
type nul >"%CONSTRAINTS%"
for %%W in ("%WHEELHOUSE%\*.whl") do (
  for /f "tokens=1,2 delims=-" %%A in ("%%~nW") do (
    if /I not "%%A"=="Pillow" (echo %%A==%%B)>>"%CONSTRAINTS%"
  )
)

REM --find-links and --constraint go on the command line, not in PIP_*
REM environment variables, because pip splits those on whitespace and would
REM break on paths with spaces.
set "PIP="%PYTHON%" -m pip"
set "PIP_INSTALL=%PIP% install --find-links "%WHEELHOUSE%" --constraint "%CONSTRAINTS%""


echo.
echo Updating pip, setuptools, and the build backend...
%PIP_INSTALL% pip setuptools %BUILD_DEPS% || goto :FAIL

REM Resolve the full install before removing anything, so an unsatisfiable
REM dependency fails here and leaves the environment untouched. Packages that
REM are already installed at an acceptable version count as satisfied, so this
REM does not prove the wheelhouse is complete.
echo.
echo Checking that all dependencies are available offline...
%PIP_INSTALL% --no-build-isolation --dry-run %EDITABLE% "%TARGET%" || goto :FAIL

echo.
echo Removing previous pyTriBeam install...
%PIP% uninstall -y pytribeam %STALE_PACKAGES% || goto :FAIL

echo.
echo Installing pyTriBeam (%MODE%)...
%PIP_INSTALL% --no-build-isolation %EDITABLE% "%TARGET%" || goto :FAIL

echo.
"%PYTHON%" -c "import pytribeam; print('pytribeam import OK; version=', getattr(pytribeam, '__version__', '(unknown)'))" || goto :FAIL

echo.
echo [INFO] Install completed successfully.
echo.
echo To see available commands, please run pytribeam.exe in your terminal.
exit /b 0


:FAIL
echo.
echo [ERROR] Install failed. Details are in "%LOG%"
exit /b 1


REM ============================================================
REM Subroutines
REM ============================================================

:USAGE
echo.
echo Usage:
echo   %~nx0              Standard install
echo   %~nx0 -d           Developer install: editable, plus test/lint/doc tools
echo                      (also --dev, --developer)
echo   %~nx0 -h           Show this help (also --help)
echo.
exit /b 0


:LAUNCHED_FROM_EXPLORER
REM Exit code 0 if this script was double-clicked in Explorer, else 1.
REM
REM Explorer runs a .bat as "cmd.exe /c ..." with explorer.exe as the parent.
REM Checking /c too matters: an interactive cmd opened from the Start menu
REM also has explorer.exe as its parent, but no /c. FOR /F runs PowerShell
REM inside an extra cmd.exe, so the loop steps past that one (its command line
REM contains this query) to reach the cmd.exe that is running this script.
set "FROM_EXPLORER="
for /f "usebackq delims=" %%A in (`powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $PID); do { $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $p.ParentProcessId) } while ($p -and $p.CommandLine -like '*Get-CimInstance*'); if ($p -and $p.CommandLine -match '\s/c\s') { $parent = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $p.ParentProcessId); if ($parent -and $parent.Name -eq 'explorer.exe') { 'yes' } }" 2^>nul`) do (
  set "FROM_EXPLORER=%%A"
)
if "%FROM_EXPLORER%"=="yes" exit /b 0
exit /b 1
