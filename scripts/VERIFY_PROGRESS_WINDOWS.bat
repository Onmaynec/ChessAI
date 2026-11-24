@echo off
setlocal
cd /d "%~dp0.."
call scripts\SELECT_PYTHON.bat
if not defined CHESSAI_PYTHON (
 echo First run START_CHESS_AI.bat to install Python dependencies.
 pause
 exit /b 1
)
"%CHESSAI_PYTHON%" tools\verify_progress.py
if errorlevel 1 echo [ERROR] One or more checkpoints failed verification.
pause
