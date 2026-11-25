@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
echo Stop Neural Scaling, PPO and other GPU sessions BEFORE launching this lab.
set /p "OK=Type YES if training is stopped: "
if /i not "%OK%"=="YES" exit /b 1
call scripts\SELECT_PYTHON.bat
if not defined CHESSAI_PYTHON goto fail
echo 1. Stockfish 19 check
echo 2. Leela Chess Zero CUDA check
echo 3. Stockfish local play
echo 4. Leela local play
choice /c 1234 /n /m "Select [1-4]: "
if errorlevel 4 goto playlc
if errorlevel 3 goto playsf
if errorlevel 2 goto checklc
"%CHESSAI_PYTHON%" -B -m external_core.lab --engine stockfish --mode check
goto done
:checklc
"%CHESSAI_PYTHON%" -B -m external_core.lab --engine lc0 --mode check
goto done
:playsf
"%CHESSAI_PYTHON%" -B -m external_core.lab --engine stockfish --mode play
goto done
:playlc
"%CHESSAI_PYTHON%" -B -m external_core.lab --engine lc0 --mode play
:done
if errorlevel 1 goto fail
pause
exit /b 0
:fail
echo External lab failed. Check engine installation and GPU runtime.
pause
exit /b 1
