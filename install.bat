echo off

echo Installing pytribeam...
"C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install %~dp0\wheelhouse\pip-24.0-py3-none-any.whl
"C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install %~dp0\wheelhouse\setuptools-69.5.1-py3-none-any.whl
for %%x in (%~dp0\wheelhouse\*.whl) do "C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install %%x
for %%x in (%~dp0\wheelhouse\*.whl) do "C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install %%x
"C:/Program Files/Enthought/Python/envs/Autoscript/python.exe" -m pip install -e . --no-index --no-build-isolation

cmd /k
