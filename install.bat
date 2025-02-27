echo off
:begin
echo Select an install mode for pyTriBeam:
echo 1: Client install
echo 2: Developer install
echo:
set /p op=Type option:
if "%op%"=="1" goto client
if "%op%"=="2" goto developer

echo:
echo Error, invalid response
echo:
cmd /k

:client
echo Installing for client use...
"C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install %~dp0\wheelhouse\pip-24.0-py3-none-any.whl
"C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install %~dp0\wheelhouse\setuptools-69.5.1-py3-none-any.whl
for %%x in (%~dp0\wheelhouse\*.whl) do "C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install %%x
for %%x in (%~dp0\wheelhouse\*.whl) do "C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install %%x
"C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install . --no-index --no-build-isolation
goto end

:developer
echo Installing for developer use...
"C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install %~dp0\wheelhouse\pip-24.0-py3-none-any.whl
"C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install %~dp0\wheelhouse\setuptools-69.5.1-py3-none-any.whl
for %%x in (%~dp0\wheelhouse\*.whl) do "C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install %%x
for %%x in (%~dp0\wheelhouse\*.whl) do "C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install %%x
"C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install -e . --no-index --no-build-isolation
goto end 

:end
cmd /k
