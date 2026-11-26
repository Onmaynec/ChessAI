@echo off
setlocal
cd /d "%~dp0"
set "PY="
if exist ".venv-cuda\Scripts\python.exe" set "PY=.venv-cuda\Scripts\python.exe"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist ".venv-qt\Scripts\python.exe" set "PY=.venv-qt\Scripts\python.exe"
if not defined PY set "PY=python"
echo [INFO] Qt Reborn Python: %PY%
"%PY%" -c "from PySide6.QtQuick import QQuickWindow; import cv2,mss,PIL,pyautogui" >nul 2>&1
if not errorlevel 1 goto launch
echo [INFO] Missing Qt or vision packages.
choice /C YN /N /M "Install missing dependencies in this Python environment? [Y/N] "
if errorlevel 2 goto launch
"%PY%" -m pip install -r requirements-vision-reborn.txt
if errorlevel 1 goto failed
:launch
"%PY%" -m visionbot.qt_reborn
if errorlevel 1 goto failed
exit /b 0
:failed
echo [ERROR] Reborn startup failed. Existing models and training data were not changed.
pause
exit /b 1
