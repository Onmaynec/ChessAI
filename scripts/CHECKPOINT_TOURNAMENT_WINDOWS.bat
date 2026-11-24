@echo off
setlocal
cd /d "%~dp0.."
call scripts\SELECT_PYTHON.bat
set /p "RUN=Training run ID: "
if not exist "runs\%RUN%\checkpoints\latest.pt" (
 echo [ERROR] Checkpoint not found.
 goto :fail
)
set "ENGINE=build\Release\chessai.exe"
if not exist "%ENGINE%" set "ENGINE=build\chessai.exe"
if not exist "%ENGINE%" goto :fail
if not exist "runs\%RUN%\evaluations" mkdir "runs\%RUN%\evaluations"
set "OUT=runs\%RUN%\evaluations\tournament_v06_%RANDOM%_%RANDOM%.json"
echo Comparing last 8 checkpoints on the same seeded opening suite.
"%CHESSAI_PYTHON%" -m neural.tournament --run "runs\%RUN%" --engine "%ENGINE%" --reference "models\neural_best.pt" --last 8 --games 20 --max-plies 400 --opening-plies 8 --output "%OUT%"
if errorlevel 1 goto :fail
echo Saved: %OUT%
pause
exit /b 0
:fail
echo Tournament failed; saved models were not modified.
pause
exit /b 1
