@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
call scripts\SELECT_PYTHON.bat
if not defined CHESSAI_PYTHON goto fail
"%CHESSAI_PYTHON%" -B -m external_core.multi_gui
if errorlevel 1 goto fail
exit /b 0
:fail
echo Local Multi-Engine Lab failed.
pause
exit /b 1
