@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "RUN=%CD%\runs\run_20261123_072154_6a110b"
set "ENGINE=%CD%\build\Release\chessai.exe"
if not exist "%ENGINE%" set "ENGINE=%CD%\build\chessai.exe"
set "PYEXE=%CD%\.venv-cuda\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYEXE%" if exist "config\python_path.txt" for /f "usebackq delims=" %%P in ("config\python_path.txt") do if exist "%%P" set "PYEXE=%%P"
if not exist "%PYEXE%" (echo [ERROR] Python not found. Configure your Chess AI environment first.& pause & exit /b 1)
if not exist "%ENGINE%" (echo [ERROR] Chess C++ engine not compiled. Run START_CHESS_AI.bat.& pause & exit /b 1)
if not exist "%RUN%\checkpoints\skillboost_v2.pt" (echo [ERROR] skillboost_v2.pt is missing from this run.& pause & exit /b 1)
echo =============================================
echo  CHESS AI - DEFENDER AGENT DISTILLATION
echo =============================================
"%PYEXE%" -m neural.agent_specialization --run "%RUN%" --engine "%ENGINE%" --profile defender --device auto --epochs 5 --max-rows 950 --teacher-depth 3 --batch-size 64
set "RESULT=%ERRORLEVEL%"
echo Exit code: %RESULT%
if not "%RESULT%"=="0" echo [ERROR] Agent not created. Read the output; original models are safe.
pause
exit /b %RESULT%
