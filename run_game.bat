@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_CMD="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"

if defined PYTHON_CMD goto :python_ready
python -c "import sys" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=python"

:python_ready
if defined PYTHON_CMD goto :venv_check
echo [KBO FM 2025] Python 3.10 or newer was not found.
echo Install Python from https://www.python.org/downloads/windows/
echo Enable the "Add Python to PATH" option during installation.
pause
exit /b 1

:venv_check
if exist ".venv\Scripts\python.exe" goto :packages_check
echo [KBO FM 2025] Creating the Python environment...
%PYTHON_CMD% -m venv .venv
if errorlevel 1 goto :setup_error

:packages_check
".venv\Scripts\python.exe" -c "import PySide6" >nul 2>&1
if not errorlevel 1 goto :model_check
echo [KBO FM 2025] Installing required packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :setup_error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :setup_error

:model_check
if exist "models\Qwen3-4B-Q4_K_M.gguf" goto :launch
if exist "models\Qwen3-1.7B-Q4_K_M.gguf" goto :launch
set "KBOFM_AI_ENABLED=0"
echo [KBO FM 2025] Local AI model not found. Using rules-based mode.

:launch
echo [KBO FM 2025] Starting game...
".venv\Scripts\python.exe" main.py
set "GAME_EXIT_CODE=%ERRORLEVEL%"
if "%GAME_EXIT_CODE%"=="0" goto :finish
echo.
echo The game closed unexpectedly. Check data\logs\crash.log.
pause

:finish
exit /b %GAME_EXIT_CODE%

:setup_error
echo.
echo [KBO FM 2025] Environment setup failed.
echo Check the internet connection and Python installation, then try again.
pause
exit /b 1
