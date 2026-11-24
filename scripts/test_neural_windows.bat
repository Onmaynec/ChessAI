@echo off
setlocal
cd /d "%~dp0\.."
if not exist .venv\Scripts\python.exe (echo [ERROR] Run setup_neural_windows.bat first. & pause & exit /b 1)
.venv\Scripts\python.exe -m unittest discover -s tests -p test_neural.py -v
if errorlevel 1 (pause & exit /b 1)
pause
