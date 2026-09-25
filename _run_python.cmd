@echo off
setlocal EnableExtensions EnableDelayedExpansion

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 (
  python %*
  exit /b !errorlevel!
)

py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 (
  py -3 %*
  exit /b !errorlevel!
)

python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 (
  python3 %*
  exit /b !errorlevel!
)

echo ERROR: No working Python 3.11+ interpreter was found.
echo Tried: python, py -3, python3
exit /b 9009
