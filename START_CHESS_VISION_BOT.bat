@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
pushd "%~dp0" || goto :bad
if not exist "visionbot\gui.py" goto :bad
if not exist "neural\agent.py" goto :bad
if not exist "botlab\session.py" goto :bad
call "scripts\SELECT_PYTHON.bat"
if not defined CHESSAI_PYTHON goto :no_py
if not exist "%CHESSAI_PYTHON%" goto :no_py
echo [INFO] Python: %CHESSAI_PYTHON%
"%CHESSAI_PYTHON%" -c "import cv2,mss,pyautogui,PIL,torch;from visionbot.recognizer import VisionRecognizer"
if errorlevel 1 goto :deps
if not exist "runs\run_20261123_072154_6a110b\checkpoints\latest.pt" goto :ckpt
if not exist "build\Release\chessai.exe" if not exist "build\chessai.exe" goto :core
"%CHESSAI_PYTHON%" -m visionbot.gui
if errorlevel 1 goto :err
popd
exit /b 0
:no_py
echo [ERROR] Python not found in this v0.7.0 installation.
echo [FIX] Set up .venv-cuda in v0.7.0 and save interpreter to config\python_path.txt.
goto :err
:deps
echo [ERROR] Missing Vision Bot dependencies.
echo [FIX] Run: "%CHESSAI_PYTHON%" -m pip install -r requirements-vision.txt
goto :err
:ckpt
echo [ERROR] Trained latest.pt not found. Verify that runs were migrated.
goto :err
:core
echo [ERROR] C++ chessai.exe not found. Run START_CHESS_AI.bat to build first.
goto :err
:bad
echo [ERROR] Run this BAT in the installed ChessAI-v0.7.0 project root.
:err
pause
popd
exit /b 1
