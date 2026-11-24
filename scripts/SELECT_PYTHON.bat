@echo off
rem Call after changing directory to the ChessAI project root.
rem Reuse the original CUDA Python environment without copying a 2+ GB torch.
set "CHESSAI_PYTHON="
if exist "config\python_path.txt" set /p "CHESSAI_PYTHON="<"config\python_path.txt"
if defined CHESSAI_PYTHON if not exist "%CHESSAI_PYTHON%" (
  echo [WARNING] Original CUDA Python not found. Check config\python_path.txt
  set "CHESSAI_PYTHON="
)
if not defined CHESSAI_PYTHON if exist ".venv-cuda\Scripts\python.exe" set "CHESSAI_PYTHON=.venv-cuda\Scripts\python.exe"
if not defined CHESSAI_PYTHON if exist ".venv\Scripts\python.exe" set "CHESSAI_PYTHON=.venv\Scripts\python.exe"
