@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

where py >nul 2>&1
if %errorlevel%==0 (
  py -3 -m repo_monitor
) else (
  where python >nul 2>&1
  if %errorlevel%==0 (
    python -m repo_monitor
  ) else (
    echo Python 3 が見つかりません。
    echo Python をインストールしてから再実行してください。
    pause
    exit /b 1
  )
)

if errorlevel 1 (
  echo.
  echo Repo Monitor がエラー終了しました。上の内容を確認してください。
  pause
  exit /b 1
)
