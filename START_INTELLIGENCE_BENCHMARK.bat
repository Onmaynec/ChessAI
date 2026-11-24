@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
call scripts\SELECT_PYTHON.bat
if not defined CHESSAI_PYTHON goto :fail
set "ENGINE=build\Release\chessai.exe"
if not exist "%ENGINE%" set "ENGINE=build\chessai.exe"
if not exist "%ENGINE%" (echo Build the C++ engine first. & goto :fail)
set "RUN=runs\run_20261123_072154_6a110b"
set /p "RUN=Run path (Enter for default): "
if not exist "%RUN%\checkpoints" (echo Checkpoint directory missing. & goto :fail)
echo Stop training and other GPU workloads before benchmarking.
echo 1. Quick: both position modes, 2 opening pairs, policy tournament
echo 2. Standard: both position modes, 6 opening pairs, policy tournament
echo 3. Full: both position modes and tournaments, 8 opening pairs ^(expensive^)
choice /C 123 /N /M "Select profile: "
set "PICK=%ERRORLEVEL%"
set "PROFILE=quick"
if "%PICK%"=="2" set "PROFILE=standard"
if "%PICK%"=="3" set "PROFILE=full"
echo.
echo Training overlap audit:
echo 1. Fast diagnostic - skip archive scan ^(not independent holdout^)
echo 2. Full read-only archive scan with progress
choice /C 12 /N /M "Audit mode: "
set "AUDIT_PICK=%ERRORLEVEL%"
if not "%AUDIT_PICK%"=="1" if not "%AUDIT_PICK%"=="2" goto :fail
set "AUDIT_ARG="
if "%AUDIT_PICK%"=="1" set "AUDIT_ARG=--skip-audit"
set "OUT=benchmark_reports\v0932_%RANDOM%_%RANDOM%"
"%CHESSAI_PYTHON%" -m benchmark.run --run "%RUN%" --engine "%ENGINE%" --output "%OUT%" --profile "%PROFILE%" %AUDIT_ARG%
if errorlevel 1 goto :fail
echo Saved: %OUT%\report.md
pause
exit /b 0
:fail
echo Benchmark did not complete. No training weights were updated.
pause
exit /b 1
