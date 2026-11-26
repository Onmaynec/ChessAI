@echo off
setlocal
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist ".venv-cuda\Scripts\python.exe" set "PY=.venv-cuda\Scripts\python.exe"
"%PY%" -m visionbot.gui --legacy
if errorlevel 1 pause
