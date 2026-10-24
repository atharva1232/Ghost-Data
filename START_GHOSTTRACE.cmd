@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  py -3 code\start_app.py --open
) else (
  python code\start_app.py --open
)
if errorlevel 1 (
  echo.
  echo GhostTrace could not start. Check Python 3.11+ and whether port 8765 is free.
  pause
)
