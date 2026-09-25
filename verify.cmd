@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

call "%~dp0_run_python.cmd" -c "import sys; sys.exit(7)"
set "RESOLVER_RC=%errorlevel%"
if not "%RESOLVER_RC%"=="7" (
  echo ERROR: Python resolver returned %RESOLVER_RC% instead of 7.
  exit /b 1
)

call "%~dp0_run_python.cmd" -m unittest discover -s tests -v
if errorlevel 1 exit /b %errorlevel%

call "%~dp0_run_python.cmd" -m compileall -q src tests
if errorlevel 1 exit /b %errorlevel%

call "%~dp0_run_python.cmd" -m repo_monitor --smoke
if errorlevel 1 exit /b %errorlevel%

exit /b 0
