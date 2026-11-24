@echo off
setlocal
cd /d "%~dp0.."
call scripts\SELECT_PYTHON.bat
set /p "RUN=Enter training run ID (e.g. run_20261123_063134_12e844): "
if not exist "runs\%RUN%\checkpoints\latest.pt" (
 echo No checkpoint for that run.
 pause
 exit /b 1
)
set "CORE=build\Release\chessai.exe"
if not exist "%CORE%" set "CORE=build\chessai.exe"
"%CHESSAI_PYTHON%" -m neural.search --checkpoint "runs\%RUN%\checkpoints\latest.pt" --engine "%CORE%" --depth 2 --width 8
pause
