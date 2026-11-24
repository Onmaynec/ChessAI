@echo off
setlocal
cd /d "%~dp0\.."
set EXE=build\Release\chessai.exe
if not exist "%EXE%" set EXE=build\chessai.exe
if not exist "%EXE%" (echo [ERROR] Build C++ first. & exit /b 1)
if not exist .venv\Scripts\python.exe (echo [ERROR] Setup Python first. & exit /b 1)
.venv\Scripts\python.exe -m neural.agent uci --engine "%EXE%" --checkpoint models\neural_best.pt
