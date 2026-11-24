@echo off
setlocal
cd /d "%~dp0.."
call scripts\SELECT_PYTHON.bat
set /p "RUN=Training run ID (copy from Training Studio): "
if not exist "runs\%RUN%\checkpoints\latest.pt" (
 echo [ERROR] No checkpoint found under runs.
 goto :fail
)
set "ENGINE=build\Release\chessai.exe"
if not exist "%ENGINE%" set "ENGINE=build\chessai.exe"
if not exist "%ENGINE%" (
 echo [ERROR] Build engine first (scripts\build_windows.bat).
 goto :fail
)
set "REFERENCE=models\neural_best.pt"
set /p "MODE=Opponent (press Enter for baseline, type best for best.pt): "
if /I "%MODE%"=="best" set "REFERENCE=runs\%RUN%\checkpoints\best.pt"
if not exist "%REFERENCE%" (
 echo [ERROR] Reference checkpoint missing: %REFERENCE%
 goto :fail
)
if not exist "runs\%RUN%\evaluations" mkdir "runs\%RUN%\evaluations"
set "OUT=runs\%RUN%\evaluations\eval_v06_%RANDOM%_%RANDOM%.json"
echo [CHESS AI v0.6] Diverse paired-color evaluation; 40 games, 8 opening plies.
echo Training weights and optimizer will NOT be modified.
"%CHESSAI_PYTHON%" -m neural.evaluation --engine "%ENGINE%" --checkpoint "runs\%RUN%\checkpoints\latest.pt" --reference "%REFERENCE%" --games 40 --max-plies 400 --opening-plies 8 --seed 20261123 --suite holdout --output "%OUT%" --device auto
if errorlevel 1 goto :fail
echo Evaluation saved: %OUT%
pause
exit /b 0
:fail
echo Evaluation did not complete. Training files were not changed.
pause
exit /b 1
