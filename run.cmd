@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

call "%~dp0_run_python.cmd" -m repo_monitor %*
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo.
  echo ERROR: Repo Monitor exited with code %RC%.
  pause
)
exit /b %RC%
