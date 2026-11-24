@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
rem Universal launch: works from installed project OR extracted addon folder.
rem No trained model or run data is changed by this script.
set "LAUNCH_DIR=%~dp0"
set "CHESSAI_ROOT=%LAUNCH_DIR%"
call :is_project "%CHESSAI_ROOT%"
if not errorlevel 1 goto :project_found

rem The installer saves the location of the real project near the addon launcher.
set "CHESSAI_ROOT="
if not exist "%LAUNCH_DIR%BOT_LAB_INSTALL_ROOT.txt" goto :ask_for_project
set /p "CHESSAI_ROOT="<"%LAUNCH_DIR%BOT_LAB_INSTALL_ROOT.txt"
call :is_project "%CHESSAI_ROOT%"
if not errorlevel 1 goto :project_found

:ask_for_project
echo.
echo [INFO] This launcher is not inside the installed ChessAI project.
echo [INFO] You can run it from here by selecting the installed root.
echo [INFO] Paste the FULL path to the ChessAI-v0.7.0 folder.
echo.
set /p "CHESSAI_ROOT=ChessAI project path (Enter to cancel): "
if not defined CHESSAI_ROOT goto :cancelled
rem Strip quotes when a quoted path was pasted.
set "CHESSAI_ROOT=%CHESSAI_ROOT:"=%"
call :is_project "%CHESSAI_ROOT%"
if errorlevel 1 goto :bad_root

rem Remember location for the next source-folder launch.
>"%LAUNCH_DIR%BOT_LAB_INSTALL_ROOT.txt" echo(%CHESSAI_ROOT%

:project_found
pushd "%CHESSAI_ROOT%" 2>nul
if errorlevel 1 goto :bad_directory

echo.
echo [OK] Bot Lab project: %CD%
call "scripts\SELECT_PYTHON.bat"
if defined CHESSAI_PYTHON goto :python_ready

echo.
echo [INFO] No Python configured in this installation.
echo [INFO] Reuse the Python installed for the original ChessAI v0.6.0.
echo [INFO] Example: C:\...\ChessAI-v0.6.0\.venv-cuda\Scripts\python.exe
echo [INFO] Your PyTorch CUDA environment does NOT need reinstalling.
echo.
set /p "CHESSAI_PYTHON=Path to existing python.exe (Enter to cancel): "
if not defined CHESSAI_PYTHON goto :no_python

:python_ready
set "CHESSAI_PYTHON=%CHESSAI_PYTHON:"=%"
if exist "%CHESSAI_PYTHON%\Scripts\python.exe" set "CHESSAI_PYTHON=%CHESSAI_PYTHON%\Scripts\python.exe"
if not exist "%CHESSAI_PYTHON%" goto :bad_python

"%CHESSAI_PYTHON%" -c "import torch, numpy, tkinter; from botlab.session import BotLabSession" >nul 2>nul
if errorlevel 1 goto :missing_deps

rem Only write interpreter configuration. Never touch model/run/checkpoint files.
"%CHESSAI_PYTHON%" -c "import pathlib,sys; p=pathlib.Path('config/python_path.txt'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(sys.executable+'\n',encoding='utf-8')"
if errorlevel 1 echo [WARNING] Python setting could not be saved; launch will be attempted.

if not exist "runs\run_20261123_072154_6a110b\checkpoints\latest.pt" goto :no_checkpoint
if not exist "build\Release\chessai.exe" if not exist "build\chessai.exe" goto :no_engine

echo.
echo [OK] Python: %CHESSAI_PYTHON%
echo [INFO] Computer bots only. Enter Chess.com moves MANUALLY.
echo [INFO] Self-play training runs separately in Training Studio.
echo.
"%CHESSAI_PYTHON%" -m botlab.gui --run-id run_20261123_072154_6a110b --device cpu
if errorlevel 1 goto :launch_failed
popd
exit /b 0

:is_project
rem Verify using ABSOLUTE paths, regardless of current working directory.
if "%~1"=="" exit /b 1
if not exist "%~1\neural\agent.py" exit /b 1
if not exist "%~1\scripts\SELECT_PYTHON.bat" exit /b 1
if not exist "%~1\botlab\gui.py" exit /b 1
exit /b 0

:bad_root
echo.
echo [ERROR] Not an installed ChessAI-v0.7.0 project: %CHESSAI_ROOT%
echo [DETAIL] Expected neural\agent.py, scripts\SELECT_PYTHON.bat, botlab\gui.py.
echo [FIX] Run INSTALL_BOT_LAB.bat once, then specify that same project folder.
goto :fail_no_pop
:bad_directory
echo [ERROR] Cannot open ChessAI project directory: %CHESSAI_ROOT%
goto :fail_no_pop
:cancelled
echo [CANCELLED] No data was changed.
goto :fail_no_pop
:no_python
echo [ERROR] No Python selected. Existing training data is untouched.
goto :fail
:bad_python
echo [ERROR] Python not found: %CHESSAI_PYTHON%
goto :fail
:missing_deps
echo [ERROR] Python is missing torch, numpy, tkinter or project imports.
echo [FIX] Select the old .venv-cuda\Scripts\python.exe from v0.6.0.
goto :fail
:no_checkpoint
echo [ERROR] Trained checkpoint missing from the selected v0.7.0 folder.
echo [DETAIL] runs\run_20261123_072154_6a110b\checkpoints\latest.pt
echo [FIX] Migrate/copy this run from v0.6.0 without overwriting trained weights.
goto :fail
:no_engine
echo [ERROR] C++ engine not found in build\Release or build.
echo [FIX] Run START_CHESS_AI.bat to build the engine first.
goto :fail
:launch_failed
echo [ERROR] Bot Lab exited with an error. See the traceback above.
goto :fail
:fail
echo.
pause
popd
exit /b 1
:fail_no_pop
echo.
pause
exit /b 1
