@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0\.."
call scripts\SELECT_PYTHON.bat
if not defined CHESSAI_PYTHON (
  echo [ERROR] Run START_CHESS_AI.bat to install dependencies first.
  pause
  exit /b 1
)
if exist "build\Release\chessai.exe" (
  set "CHESS_ENGINE=build\Release\chessai.exe"
) else (
  set "CHESS_ENGINE=build\chessai.exe"
)
echo ChessAI v0.7.0 CPU/CUDA benchmark. Does not modify training.
"%CHESSAI_PYTHON%" -m tools.benchmark_runtime --engine "%CHESS_ENGINE%" --samples 10
pause
