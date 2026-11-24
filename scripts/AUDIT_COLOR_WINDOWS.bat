@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0\.."
call scripts\SELECT_PYTHON.bat
set /p "RUN=Training run ID: "
if not exist "runs\%RUN%\checkpoints\latest.pt" (
 echo [ERROR] No checkpoint found for this run.
 pause
 exit /b 1
)
"%CHESSAI_PYTHON%" -m tools.audit_color --run "runs\%RUN%"
pause
