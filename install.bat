@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM Configuration
REM ============================================================
set "PYTHON=C:\Program Files\Enthought\Python\envs\Autoscript\python.exe"
set "WHEELHOUSE=%~dp0wheelhouse"


echo ===========================================================
echo Install pyTriBeam - %DATE% %TIME%                          
echo Script: %~f0                                               
echo Wheelhouse: "%WHEELHOUSE%"                                 
echo ===========================================================


REM ============================================================
REM Helpers
REM ============================================================
set "PIP="%PYTHON%" -u -m pip"


REM ============================================================
REM Jump over subroutines to main execution
REM ============================================================
goto :MAIN


REM Call as:  call :RUN "Description" command args...
:RUN
setlocal EnableExtensions EnableDelayedExpansion
set "DESC=%~1"
echo.
echo [INFO] !DESC!
REM Build a command line from arg2..end (preserve quotes!)
set "CMDLINE=%2"
shift
shift
:RUN_MORE
if "%~1"=="" goto RUN_EXEC
set "CMDLINE=!CMDLINE! %1"
shift
goto RUN_MORE
:RUN_EXEC
REM echo [CMD ] !CMDLINE!
REM Run the command in a child cmd, capture its exit code immediately
cmd /v:on /c "!CMDLINE!"
set "RC=!ERRORLEVEL!"
REM echo [DEBUG] ExitCode = !RC!
if not "!RC!"=="0" (
  echo [ERROR] Failed: !DESC!
  echo [ERROR] ExitCode: !RC!
  endlocal & exit /b !RC!
)
endlocal & exit /b 0

REM Function to verify all wheels are present
:REQUIRE_FILE
setlocal
set "F=%~1"
if exist "%F%" (
  endlocal & exit /b 0
) else (
  echo [ERROR] Required file not found: "%F%"
  endlocal & exit /b 1
)


REM ============================================================
REM Preflight checks
REM ============================================================
call :REQUIRE_FILE "%PYTHON%" || exit /b 1
if not exist "%WHEELHOUSE%\" (
  echo [ERROR] Wheelhouse folder not found: "%WHEELHOUSE%"
  echo [ERROR] Wheelhouse folder not found: "%WHEELHOUSE%">>"%LOG%"
  exit /b 1
)

call :RUN "Python version" "%PYTHON%" -V
call :RUN "Python executable" "%PYTHON%" -c "import sys; print(sys.executable)"
call :RUN "Ensure pip is available (may already be installed)" "%PYTHON%" -m ensurepip --upgrade


REM Optional: keep pip from ever reaching out to the internet
REM (If you have a corporate index configured in pip.ini, this forces offline use.)
set "PIP_NO_INDEX=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

:MAIN
REM ============================================================
REM Verify wheels exist before starting (fail fast)
REM ============================================================
call :REQUIRE_FILE "%WHEELHOUSE%\pip-24.0-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\setuptools-69.5.1-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\packaging-26.0-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\trove_classifiers-2026.1.14.14-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\tomli-2.0.1-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\click-8.1.7-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\colorama-0.4.6-py2.py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\pathspec-0.12.1-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\iniconfig-2.0.0-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\pluggy-1.5.0-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\coverage-7.5.1-cp38-cp38-win_amd64.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\contextlib2-21.6.0-py2.py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\exceptiongroup-1.2.1-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\schema-0.7.5-py2.py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\setuptools_scm-6.4.0-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\editables-0.5-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\hatchling-1.26.3-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\hatch_vcs-0.4.0-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\pytest-7.4.3-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\pytest_cov-4.1.0-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\ruff-0.15.11-py3-none-win_amd64.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\pygments-2.19.2-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\markdown2-2.5.1-py2.py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\astunparse-1.6.3-py2.py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\pdoc-14.7.0-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\py-1.11.0-py2.py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\tabulate-0.9.0-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\interrogate-1.7.0-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\anybadge-1.16.0-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\astroid-3.2.4-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\isort-5.13.2-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\mccabe-0.7.0-py2.py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\tomlkit-0.13.3-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\dill-0.4.0-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\pylint-3.2.7-py3-none-any.whl" || goto :FAIL
call :REQUIRE_FILE "%WHEELHOUSE%\pylint_exit-1.2.0-py2.py3-none-any.whl" || goto :FAIL
REM call :REQUIRE_FILE "%WHEELHOUSE%\typing_extensions-4.11.0-py3-none-any.whl" || goto :FAIL
REM call :REQUIRE_FILE "%WHEELHOUSE%\mypy_extensions-1.0.0-py3-none-any.whl" || goto :FAIL
REM call :REQUIRE_FILE "%WHEELHOUSE%\platformdirs-4.2.1-py3-none-any.whl" || goto :FAIL
REM call :REQUIRE_FILE "%WHEELHOUSE%\vcs_versioning-0.0.1-py3-none-any.whl" || goto :FAIL
REM call :REQUIRE_FILE "%WHEELHOUSE%\black-24.2.0-cp38-cp38-win_amd64.whl" || goto :FAIL


REM pip uninstall vcs_versioning, editables, colorama, click, contextlib2, schema, setuptools, packaging, tomli, setuptools_scm, trove_classifiers, pluggy, pathspec, hatchling, hatch_vcs, iniconfig, exceptiongroup, pytest, coverage, pytest_cov, ruff, typing_extensions, mypy_extensions, platformdirs, black, pytribeam
REM ============================================================
REM Install
REM ============================================================
REM:MAIN
echo.
echo Installing pyTriBeam...
REM call :RUN "Upgrade/install pip wheel"        %PIP% install "%WHEELHOUSE%\pip-24.0-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install setuptools"         %PIP% install "%WHEELHOUSE%\setuptools-69.5.1-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install colorama"           %PIP% install "%WHEELHOUSE%\colorama-0.4.6-py2.py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install packaging"          %PIP% install "%WHEELHOUSE%\packaging-26.0-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install tomli"              %PIP% install "%WHEELHOUSE%\tomli-2.0.1-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install click"              %PIP% install "%WHEELHOUSE%\click-8.1.7-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install contextlib2"        %PIP% install "%WHEELHOUSE%\contextlib2-21.6.0-py2.py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install schema"             %PIP% install "%WHEELHOUSE%\schema-0.7.5-py2.py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install setuptools_scm"     %PIP% install "%WHEELHOUSE%\setuptools_scm-6.4.0-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install trove_classifiers"  %PIP% install "%WHEELHOUSE%\trove_classifiers-2026.1.14.14-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install pluggy"             %PIP% install "%WHEELHOUSE%\pluggy-1.5.0-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install pathspec"           %PIP% install "%WHEELHOUSE%\pathspec-0.12.1-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install hatchling"          %PIP% install "%WHEELHOUSE%\hatchling-1.26.3-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install hatch_vcs"          %PIP% install "%WHEELHOUSE%\hatch_vcs-0.4.0-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install iniconfig"          %PIP% install "%WHEELHOUSE%\iniconfig-2.0.0-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install exceptiongroup"     %PIP% install "%WHEELHOUSE%\exceptiongroup-1.2.1-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install pytest"             %PIP% install "%WHEELHOUSE%\pytest-7.4.3-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install coverage"           %PIP% install "%WHEELHOUSE%\coverage-7.5.1-cp38-cp38-win_amd64.whl" --no-index || goto :FAIL
REM call :RUN "Install pytest_cov"         %PIP% install "%WHEELHOUSE%\pytest_cov-4.1.0-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install editables"          %PIP% install "%WHEELHOUSE%\editables-0.5-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install ruff"               %PIP% install "%WHEELHOUSE%\ruff-0.15.11-py3-none-win_amd64.whl" --no-index || goto :FAIL
REM call :RUN "Install markdown2"          %PIP% install "%WHEELHOUSE%\markdown2-2.5.1-py2.py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install pygments"           %PIP% install "%WHEELHOUSE%\pygments-2.19.2-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install astunparse"         %PIP% install "%WHEELHOUSE%\astunparse-1.6.3-py2.py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install pdoc"               %PIP% install "%WHEELHOUSE%\pdoc-14.7.0-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install py"                 %PIP% install "%WHEELHOUSE%\py-1.11.0-py2.py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install tabulate"                 %PIP% install "%WHEELHOUSE%\tabulate-0.9.0-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install interrogate"        %PIP% install "%WHEELHOUSE%\interrogate-1.7.0-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install anybadge"           %PIP% install "%WHEELHOUSE%\anybadge-1.16.0-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install astroid"            %PIP% install "%WHEELHOUSE%\astroid-3.2.4-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install isort"              %PIP% install "%WHEELHOUSE%\isort-5.13.2-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install mccabe"             %PIP% install "%WHEELHOUSE%\mccabe-0.7.0-py2.py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install tomlkit"            %PIP% install "%WHEELHOUSE%\tomlkit-0.13.3-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install dill"               %PIP% install "%WHEELHOUSE%\dill-0.4.0-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install pylint"             %PIP% install "%WHEELHOUSE%\pylint-3.2.7-py3-none-any.whl" --no-index || goto :FAIL
call :RUN "Install pylint-exit"        %PIP% install "%WHEELHOUSE%\pylint_exit-1.2.0-py2.py3-none-any.whl" --no-index || goto :FAIL

REM black needs mypy-extensions, platformdirs, typing-extensions
REM call :RUN "Install typing_extensions"  %PIP% install "%WHEELHOUSE%\typing_extensions-4.11.0-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install mypy_extensions"    %PIP% install "%WHEELHOUSE%\mypy_extensions-1.0.0-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install platformdirs"       %PIP% install "%WHEELHOUSE%\platformdirs-4.2.1-py3-none-any.whl" --no-index || goto :FAIL
REM call :RUN "Install black"              %PIP% install "%WHEELHOUSE%\black-24.2.0-cp38-cp38-win_amd64.whl" --no-index || goto :FAIL
REM call :RUN "Install vcs_versioning"     %PIP% install "%WHEELHOUSE%\vcs_versioning-0.0.1-py3-none-any.whl" --no-index || goto :FAIL

REM Install pyTriBeam from the current folder
call :RUN "Install pyTriBeam" %PIP% install -e . --no-index --no-build-isolation --find-links "%WHEELHOUSE%" || goto :FAIL


REM ============================================================
REM Verification / reporting
REM ============================================================
REM call :RUN "pip list" %PIP% list


REM If the import name differs, change this accordingly (e.g., pyTriBeam -> pytribeam)
call :RUN "Import test: pytribeam" "%PYTHON%" -c "import pytribeam; print('pytribeam import OK; version=', getattr(pytribeam,'__version__','(unknown)'))" || goto :FAIL

echo.
echo [INFO] Install completed successfully.

echo .
echo To see available commands, please run `pytribeam.exe` in your terminal.
goto :EOF

:FAIL
echo [ERROR] Install failed.
