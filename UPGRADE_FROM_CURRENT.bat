@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo     CHESS AI v0.7.0 - SAFE PROGRESS MIGRATION
 echo ============================================================
echo Close ALL old training processes before proceeding.
echo Old project folder will NOT be changed, renamed or deleted.
echo Compatible with v0.3-v0.6 data, even when previous root folder was renamed.
echo.
set /p "SOURCE=FULL PATH to previous installation: "
if not defined SOURCE goto :failed
if not exist "%SOURCE%\neural\selfplay.py" (
 echo Previous installation not found. Use its ROOT folder.
 goto :failed
)
echo.
echo [1/2] Checking for conflicts, file sizes and SHA-256 checksums...
py -3 tools\migrate_current.py --source "%SOURCE%" --dry-run
if errorlevel 1 goto :failed
echo.
echo Confirm all training is stopped and you have a separate backup.
set /p "CONFIRM=Type YES to copy saved runs: "
if /I not "%CONFIRM%"=="YES" goto :failed
echo [2/2] Copying with SHA-256 validation. This may take time...
py -3 tools\migrate_current.py --source "%SOURCE%"
if errorlevel 1 goto :failed
echo SUCCESS. Start START_CHESS_AI.bat from this new folder.
pause
exit /b 0
:failed
echo Migration not performed or not completed. Your old source is untouched.
pause
exit /b 1
