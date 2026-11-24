@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0.."
echo ============================================================
echo  CHESS AI - OPTIONAL SUPERVISED SKILL BOOST CANDIDATE
 echo ============================================================
echo.
echo [SAFE] Only creates runs\...\checkpoints\skillboost.pt.
echo [SAFE] Does NOT modify latest.pt, best.pt or PPO optimizer.
echo [NOTE] Uses WEAK built-in C++ baseline as teacher, not Stockfish.
echo.
call "scripts\SELECT_PYTHON.bat"
if not defined CHESSAI_PYTHON goto :nopython
set "ENGINE=build\Release\chessai.exe"
if not exist "%ENGINE%" set "ENGINE=build\chessai.exe"
if not exist "%ENGINE%" goto :noengine
set "RUN=runs\run_20261123_072154_6a110b"
if not exist "%RUN%\checkpoints\latest.pt" goto :norun
if exist "%RUN%\checkpoints\skillboost.pt" goto :exists
echo RUN: %RUN%
echo Teacher positions: 1200, search depth: 4, fine-tuning epochs: 6.
echo This changes the behavior of a separate CANDIDATE model only.
set /p "CONFIRM=Type YES to train candidate: "
if /I not "%CONFIRM%"=="YES" goto :cancel
"%CHESSAI_PYTHON%" -m neural.skill_boost --run "%RUN%" --engine "%ENGINE%" --samples 1200 --depth 4 --epochs 6 --device auto
if errorlevel 1 goto :fail
echo.
echo [NEXT] If candidate is accepted, choose skillboost.pt in Vision Bot.
echo [NEXT] Compare it to latest.pt before choosing which is stronger.
pause
exit /b 0
:nopython
echo [ERROR] Python not configured. Run START_CHESS_AI.bat first.
goto :fail
:noengine
echo [ERROR] Missing compiled chessai.exe. Run START_CHESS_AI.bat first.
goto :fail
:norun
echo [ERROR] Missing trained checkpoint for this run.
goto :fail
:exists
echo [ERROR] skillboost.pt already exists. Preserve/evaluate it first.
goto :fail
:cancel
echo [INFO] Cancelled.
pause
exit /b 0
:fail
pause
exit /b 1
