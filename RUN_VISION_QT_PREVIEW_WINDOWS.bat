@echo off
setlocal
cd /d "%~dp0"
if exist ".venv-qt\Scripts\python.exe" (
    ".venv-qt\Scripts\python.exe" -m visionbot.qt_preview %*
) else (
    python -m visionbot.qt_preview %*
)
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
    echo.
    echo Qt preview failed. Install requirements-vision-qt.txt in the selected Python environment.
    pause
)
exit /b %CODE%
