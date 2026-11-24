@echo off
setlocal
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Install Python dependencies first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m unittest discover -s tests -p test_selfplay.py -v
if errorlevel 1 (pause & exit /b 1)
pause
