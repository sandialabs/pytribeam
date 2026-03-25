@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
set "VENV_DIR=%ROOT%Autoscript"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "WHEELHOUSE=%ROOT%wheelhouse"

REM ---------------------------------------------------------------------------
REM Create Autoscript venv with uv, install version-specific requirements from
REM .\wheelhouse\requirements_[AUTOSCRIPT_VERSION].txt, then install local pkg.
REM ---------------------------------------------------------------------------

REM Supported autoscript versions:
set "SUPPORTED=4.8.1 4.10 4.11 4.12 4.13"

echo.
echo Select an Autoscript version:
echo   1) 4.8.1
echo   2) 4.10
echo   3) 4.11
echo   4) 4.12
echo   5) 4.13
echo.

set "ASVER="
set /p "choice=Enter choice (1-5) or type version exactly: "

REM Allow either numeric menu choice or direct version entry
if "%choice%"=="1" set "ASVER=4.8.1"
if "%choice%"=="2" set "ASVER=4.10"
if "%choice%"=="3" set "ASVER=4.11"
if "%choice%"=="4" set "ASVER=4.12"
if "%choice%"=="5" set "ASVER=4.13"

if not defined ASVER set "ASVER=%choice%"

REM Validate selection
set "OK="
for %%V in (%SUPPORTED%) do (
  if "%%V"=="%ASVER%" set "OK=1"
)
if not defined OK (
  echo.
  echo ERROR: Invalid Autoscript version "%ASVER%".
  echo Allowed: %SUPPORTED%
  exit /b 1
)

set "REQFILE=%WHEELHOUSE%\requirements_%ASVER%.txt"

if not exist "%REQFILE%" (
  echo.
  echo ERROR: Requirements file not found:
  echo   "%REQFILE%"
  exit /b 1
)

REM Extract python version from first line like:  # python=3.8
set "PYVER="
for /f "usebackq delims=" %%L in ("%REQFILE%") do (
  set "LINE=%%L"
  goto :parse_first_line
)

:parse_first_line
REM Trim leading spaces
for /f "tokens=* delims= " %%A in ("!LINE!") do set "LINE=%%A"

REM Expect "# python=3.x" (case-insensitive for 'python')
echo(!LINE! | findstr /I /R "^# *python=" >nul
if errorlevel 1 (
  echo.
  echo ERROR: First line of "%REQFILE%" must be like:
  echo   # python=3.8
  exit /b 1
)

for /f "tokens=1,2 delims==" %%A in ("!LINE!") do (
  set "PYVER=%%B"
)

REM Trim spaces around PYVER
for /f "tokens=* delims= " %%A in ("!PYVER!") do set "PYVER=%%A"

if not defined PYVER (
  echo.
  echo ERROR: Could not parse python version from:
  echo   !LINE!
  exit /b 1
)

echo.
echo Autoscript version: %ASVER%
echo Python version:    %PYVER%
echo Requirements:      %REQFILE%
echo.

REM Create venv
uv venv Autoscript --python %PYVER%
if errorlevel 1 (
  echo ERROR: uv venv failed.
  exit /b 1
)

REM ---- verify interpreter exists ----
if not exist "%VENV_PY%" (
  echo ERROR: venv python not found at:
  echo   "%VENV_PY%"
  dir "%VENV_DIR%"
  exit /b 1
)

echo.
echo Using venv python:
"%VENV_PY%" -c "import sys; print(sys.executable)"
echo.

REM Install requirements. Run from wheelhouse so relative wheel paths work.
pushd "%WHEELHOUSE%"
uv pip install --python "%VENV_PY%" -r "requirements_%ASVER%.txt" || goto :fail
popd

REM Install local package editable from repo root
pushd "%ROOT%"
uv pip install --python "%VENV_PY%" -e .[dev] || goto fail
popd

REM Optional: attempt activation so the user drops into an activated env
if exist "%ROOT%Autoscript\Scripts\activate" (
  call "%ROOT%Autoscript\Scripts\activate"
  echo Activated env in this cmd session: %VIRTUAL_ENV%
) else (
  echo NOTE: activate.bat not found; skipping activation.
)

echo.
echo Done.
echo To use it later:
echo   call "%ROOT%Autoscript\Scripts\activate"
echo.

goto :eof

:fail
echo.
echo ERROR: Command failed with exit code %errorlevel%.
popd 2>nul

exit /b %errorlevel%
