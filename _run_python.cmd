@echo off
setlocal EnableExtensions

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 goto :use_python

py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 goto :use_py

python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 goto :use_python3

echo ERROR: No working Python 3.11+ interpreter was found.
echo Tried: python, py -3, python3
exit /b 9009

:use_python
python %*
exit /b %errorlevel%

:use_py
py -3 %*
exit /b %errorlevel%

:use_python3
python3 %*
exit /b %errorlevel%
