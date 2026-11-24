@echo off
setlocal
cd /d "%~dp0\.."
where cmake >nul 2>nul
if errorlevel 1 (
  echo [ERROR] CMake not found. Install CMake and Visual Studio 2022 C++ tools.
  pause
  exit /b 1
)
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
if errorlevel 1 (pause & exit /b 1)
cmake --build build --config Release --parallel
if errorlevel 1 (pause & exit /b 1)
ctest --test-dir build -C Release --output-on-failure
if errorlevel 1 (pause & exit /b 1)
echo.
echo Build and tests completed. Use scripts\run_windows.bat
pause
