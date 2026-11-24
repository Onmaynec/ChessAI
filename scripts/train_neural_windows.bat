@echo off
setlocal
cd /d "%~dp0\.."
set EXE=build\Release\chessai.exe
if not exist "%EXE%" set EXE=build\chessai.exe
if not exist "%EXE%" (echo [ERROR] Run scripts\build_windows.bat first. & pause & exit /b 1)
if not exist .venv\Scripts\python.exe (echo [ERROR] Run scripts\setup_neural_windows.bat first. & pause & exit /b 1)
if not exist output mkdir output
"%EXE%" teacherdata 4000 2 "output\teacher.jsonl" 20261123
if errorlevel 1 (pause & exit /b 1)
.venv\Scripts\python.exe -m neural.train --data output\teacher.jsonl --out models --epochs 8 --batch-size 64 --channels 32 --blocks 2 --device auto --seed 42
if errorlevel 1 (pause & exit /b 1)
echo.
echo Training completed. Run scripts\play_neural_windows.bat
pause
