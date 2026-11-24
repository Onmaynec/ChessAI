@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
call scripts\SELECT_PYTHON.bat
if not defined CHESSAI_PYTHON goto fail
set "ENGINE=build\Release\chessai.exe"
if not exist "%ENGINE%" set "ENGINE=build\chessai.exe"
if not exist "%ENGINE%" goto fail
"%CHESSAI_PYTHON%" -m neural.tactical_experiment --engine "%ENGINE%"
if errorlevel 1 goto fail
pause
exit /b 0
:fail
echo Experiment interrupted or failed. Use Resume with the experiment directory.
echo Original checkpoint and PPO state were not replaced.
pause
exit /b 1
