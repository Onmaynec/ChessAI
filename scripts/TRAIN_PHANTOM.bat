@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "PYTHON=.venv-cuda\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "ENGINE=build\Release\chessai.exe"
if not exist "%ENGINE%" set "ENGINE=build\chessai.exe"
if not exist "%ENGINE%" (echo [ERROR] ChessAI C++ chessai.exe is missing. & pause & exit /b 1)
if not exist "runs\run_20261123_072154_6a110b\checkpoints" (echo [ERROR] Run checkpoints missing. & pause & exit /b 1)
"%PYTHON%" -m neural.phantom_trainer --run "runs\run_20261123_072154_6a110b" --engine "%ENGINE%" --source auto --epochs 9 --lr 0.00001
if errorlevel 1 (echo [ERROR] Phantom training did not complete. & pause & exit /b 1)
echo [SUCCESS] Phantom trainer completed. See Training Studio Agent Lab for report.
pause
