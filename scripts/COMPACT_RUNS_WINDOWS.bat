@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
call scripts\SELECT_PYTHON.bat
echo ============================================================
echo     CHESS AI v0.7.0 - LOSSLESS STORAGE COMPACTION
 echo ============================================================
echo STOP TRAINING and close all old Chess AI server windows first.
echo Makes verified gzip archives; no checkpoint / optimizer is deleted.
echo.
set /p "RUN_ID=Training run ID (run_...): "
if not defined RUN_ID goto :failed
if not exist "runs\%RUN_ID%\checkpoints\latest.pt" (
  echo [ERROR] No latest.pt under runs\%RUN_ID%
  goto :failed
)
set "PYTHON=%CHESSAI_PYTHON%"
if not exist "%PYTHON%" (
  echo [ERROR] Python environment not found. Run START_CHESS_AI.bat first.
  goto :failed
)
echo [1/2] Storage report (no changes):
"%PYTHON%" -m tools.compact_runs --run "runs\%RUN_ID%"
if errorlevel 1 goto :failed
echo.
set /p "CONFIRM=Type YES to compress old game/experience logs: "
if /I not "%CONFIRM%"=="YES" goto :failed
echo [2/2] Verifying SHA-256 and moving journal bytes into gzip archives...
"%PYTHON%" -m tools.compact_runs --run "runs\%RUN_ID%" --apply
if errorlevel 1 goto :failed
echo SUCCESS. All original records remain available inside archives/.
pause
exit /b 0
:failed
echo No checkpoint or model was changed by this installer.
pause
exit /b 1
