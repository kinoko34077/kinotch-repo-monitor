@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
py -3 -m unittest discover -s tests -v || exit /b 1
py -3 -m compileall -q src tests || exit /b 1
py -3 -m repo_monitor --smoke || exit /b 1
