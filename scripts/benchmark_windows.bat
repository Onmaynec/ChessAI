@echo off
setlocal
cd /d "%~dp0\.."
set EXE=build\Release\chessai.exe
if not exist "%EXE%" set EXE=build\chessai.exe
if not exist "%EXE%" (echo Build first. & pause & exit /b 1)
"%EXE%" bench
if errorlevel 1 (pause & exit /b 1)
"%EXE%" selfplay 100 6 "output\selfplay_100.jsonl" 300 42
pause
