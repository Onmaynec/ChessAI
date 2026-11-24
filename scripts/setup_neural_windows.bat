@echo off
setlocal
cd /d "%~dp0\.."
where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python launcher not found. Install Python 3.11+ and rerun.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 (pause & exit /b 1)
)
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 (pause & exit /b 1)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (pause & exit /b 1)
.venv\Scripts\python.exe -c "import torch; print('PyTorch:', torch.__version__, '| CUDA available:', torch.cuda.is_available())"
if errorlevel 1 (pause & exit /b 1)
echo.
echo Setup completed. If CUDA=False on an NVIDIA PC, install a CUDA PyTorch wheel from https://pytorch.org/get-started/locally/
pause
