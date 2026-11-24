@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Chess AI v0.9.3.2 - Training Studio

echo.
echo  =========================================================
echo     CHESS AI 0.9.3.2 - ONE-CLICK LOCAL TRAINING STUDIO
 echo  =========================================================
echo.
if not exist "build\Release\chessai.exe" if not exist "build\chessai.exe" (
  where cmake >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] CMake missing. Install Visual Studio C++ tools and CMake.
    goto :fail
  )
  echo [1/3] Building C++ Chess Core...
  cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
  if errorlevel 1 goto :fail
  cmake --build build --config Release --parallel
  if errorlevel 1 goto :fail
  ctest --test-dir build -C Release --output-on-failure
  if errorlevel 1 goto :fail
) else (
  echo [1/3] Chess Core found.
)
call scripts\SELECT_PYTHON.bat
if not defined CHESSAI_PYTHON (
  where py >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python 3.11+ is required. CUDA interpreter was not found.
    goto :fail
  )
  echo [2/3] Creating Python environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :fail
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :fail
  set "CHESSAI_PYTHON=.venv\Scripts\python.exe"
) else (
  echo [2/3] Existing Python environment found.
)
"%CHESSAI_PYTHON%" -c "import torch,fastapi,uvicorn,numpy" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Missing dependencies in selected Python environment.
  echo Fix it there or update config\python_path.txt. No checkpoint was modified.
  goto :fail
)
echo [3/3] Starting dashboard on http://127.0.0.1:8765
echo Selected Python: %CHESSAI_PYTHON%
echo Keep this window open while using the dashboard.
echo.
"%CHESSAI_PYTHON%" -m dashboard.server
if errorlevel 1 goto :fail
exit /b 0
:fail
echo.
echo Setup or launch failed. See the error message above.
pause
exit /b 1
