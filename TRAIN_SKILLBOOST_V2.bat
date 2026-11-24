@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================================
echo CHESS AI - SKILLBOOST II
 echo Tactical / trade / defense / opening curriculum
 echo Safe output: checkpoints\skillboost_v2.pt
 echo Source: skillboost.pt if present, otherwise latest.pt
 echo ==========================================================
set "RUN=runs\run_20261123_072154_6a110b"
if not exist "%RUN%\checkpoints\latest.pt" if not exist "%RUN%\checkpoints\skillboost.pt" (
  echo [ERROR] Training run missing. Check migration of runs.
  pause
  exit /b 1
)
if exist "%RUN%\checkpoints\skillboost_v2.pt" (
  echo [ERROR] skillboost_v2.pt already exists. Never overwrite your candidate.
  pause
  exit /b 1
)
set "ENGINE=build\Release\chessai.exe"
if not exist "%ENGINE%" set "ENGINE=build\chessai.exe"
if not exist "%ENGINE%" (
  echo [ERROR] chessai.exe missing. Build C++ project first.
  pause
  exit /b 1
)
set "PYTHON="
if exist ".venv-cuda\Scripts\python.exe" set "PYTHON=.venv-cuda\Scripts\python.exe"
if not defined PYTHON if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
if not defined PYTHON if exist "config\python_path.txt" (
  for /f "usebackq delims=" %%P in ("config\python_path.txt") do (
    if not defined PYTHON if exist "%%P" set "PYTHON=%%P"
  )
)
if not defined PYTHON (
  echo [ERROR] Python environment missing. Configure .venv-cuda or .venv first.
  pause
  exit /b 1
)
echo.
echo The original PPO optimizer, latest.pt, best.pt and skillboost.pt are READ ONLY.
echo C++ teacher is the local baseline, NOT a grandmaster or Stockfish.
echo This produces a candidate for independent evaluation, NOT direct PPO resume.
echo.
set /p "YES=Type YES to generate training data and fine-tune candidate: "
if /i not "%YES%"=="YES" exit /b 0
"%PYTHON%" -m neural.skill_boost_v2 --run "%RUN%" --engine "%ENGINE%" --source auto --samples 600 --teacher-depth 4 --branch-depth 3 --branches 64 --epochs 8 --batch-size 64 --device auto
if errorlevel 1 (
  echo [ERROR] Training failed. Original checkpoint was not replaced.
  pause
  exit /b 1
)
echo.
echo Report: %RUN%\skillboost_v2\report.json
 echo Candidate: %RUN%\checkpoints\skillboost_v2.pt (only if validation improved)
pause
