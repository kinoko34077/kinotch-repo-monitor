@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

rem Prefer a directly runnable Python 3 interpreter.
python -c "import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)" >nul 2>&1
if not errorlevel 1 (
  python -m repo_monitor %*
  goto :result
)

rem Fall back to the Windows Python Launcher only if it can actually start Python 3.
py -3 -c "import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)" >nul 2>&1
if not errorlevel 1 (
  py -3 -m repo_monitor %*
  goto :result
)

rem Some installations expose python3 instead of python.
python3 -c "import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)" >nul 2>&1
if not errorlevel 1 (
  python3 -m repo_monitor %*
  goto :result
)

echo ERROR: No working Python 3 interpreter was found.
echo Tried: python, py -3, python3
echo.
echo If py -3 points to a removed Anaconda installation, reinstall Python
echo or repair the Windows Python Launcher registration.
pause
exit /b 1

:result
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo.
  echo ERROR: Repo Monitor exited with code %RC%.
  pause
)
exit /b %RC%
