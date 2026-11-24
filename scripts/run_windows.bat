@echo off
setlocal
cd /d "%~dp0\.."
set EXE=build\Release\chessai.exe
if not exist "%EXE%" set EXE=build\chessai.exe
if not exist "%EXE%" (
 echo Engine not found. First run scripts\build_windows.bat
 pause
 exit /b 1
)
"%EXE%" play 3
pause
