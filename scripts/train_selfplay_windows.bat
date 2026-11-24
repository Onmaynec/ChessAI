@echo off
setlocal
cd /d "%~dp0\.."
set "ENGINE=build\Release\chessai.exe"
if not exist "%ENGINE%" set "ENGINE=build\chessai.exe"
if not exist "%ENGINE%" (
  echo [ERROR] Build C++ core first: scripts\build_windows.bat
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Install Python dependencies first: scripts\setup_neural_windows.bat
  pause
  exit /b 1
)
set "RUN=runs\cli_run_%RANDOM%_%RANDOM%"
".venv\Scripts\python.exe" -m neural.selfplay --engine "%ENGINE%" --out "%RUN%" --iterations 10 --games-per-iteration 8 --parallel 4 --max-plies 240 --arena-games 2
if errorlevel 1 (
  echo [ERROR] Self-play failed; inspect the error above.
  pause
  exit /b 1
)
echo.
echo Finished! Run saved under %RUN%.
echo Open START_CHESS_AI.bat to view this run in the dashboard.
pause
