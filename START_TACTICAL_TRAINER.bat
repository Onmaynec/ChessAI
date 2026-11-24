@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
call scripts\SELECT_PYTHON.bat
if not defined CHESSAI_PYTHON goto fail
set "ENGINE=build\Release\chessai.exe"
if not exist "%ENGINE%" set "ENGINE=build\chessai.exe"
if not exist "%ENGINE%" goto fail
set "SOURCE=runs\run_20261123_072154_6a110b\checkpoints\latest.pt"
set /p "SOURCE=Source checkpoint (Enter for default latest.pt): "
if not exist "%SOURCE%" goto fail
echo Stop PPO training and Vision before this experiment.
echo 1. Small experiment (80 positions, 4 epochs)
echo 2. Standard experiment (160 positions, 8 epochs)
choice /C 12 /N /M "Profile: "
set "PICK=%ERRORLEVEL%"
if not "%PICK%"=="1" if not "%PICK%"=="2" goto fail
set "COUNT=80"
set "EPOCHS=4"
if "%PICK%"=="2" set "COUNT=160"
if "%PICK%"=="2" set "EPOCHS=8"
set "OUT=tactical_experiments\v093_%RANDOM%_%RANDOM%"
"%CHESSAI_PYTHON%" -m neural.tactical_data --engine "%ENGINE%" --output "%OUT%\data" --count %COUNT%
if errorlevel 1 goto fail
"%CHESSAI_PYTHON%" -m neural.tactical_train --source "%SOURCE%" --dataset "%OUT%\data\dataset.jsonl" --engine "%ENGINE%" --output "%OUT%\train" --epochs %EPOCHS%
if errorlevel 1 goto fail
echo Results: %OUT%
pause
exit /b 0
:fail
echo Experiment failed or cancelled. Existing checkpoints were not replaced.
pause
exit /b 1
