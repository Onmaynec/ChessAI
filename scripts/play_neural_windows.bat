@echo off
setlocal
cd /d "%~dp0\.."
set EXE=build\Release\chessai.exe
if not exist "%EXE%" set EXE=build\chessai.exe
if not exist "%EXE%" (echo [ERROR] Run scripts\build_windows.bat first. & pause & exit /b 1)
if not exist .venv\Scripts\python.exe (echo [ERROR] Run scripts\setup_neural_windows.bat first. & pause & exit /b 1)
if not exist models\neural_best.pt (echo [ERROR] Checkpoint missing. Run training first. & pause & exit /b 1)
.venv\Scripts\python.exe -m neural.agent play --engine "%EXE%" --checkpoint models\neural_best.pt --color white
pause
