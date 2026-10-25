@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" code\start_app.py --open
) else (
  python code\start_app.py --open
)
if errorlevel 1 (
  echo.
  echo Setup: python -m pip install -r code\requirements.txt
  echo Check Python 3.11+, Windows English OCR, and whether port 8765 is free.
  pause
)
