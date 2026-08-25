@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo [KBO FM 2025] Python을 찾을 수 없습니다.
    echo https://www.python.org/downloads/windows/ 에서 Python 3.10 이상을 설치하고,
    echo 설치 화면에서 "Add Python to PATH"를 선택해 주세요.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [KBO FM 2025] 처음 실행을 준비하고 있습니다...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :setup_error
)

".venv\Scripts\python.exe" -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    echo [KBO FM 2025] 필요한 패키지를 설치하고 있습니다...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    if errorlevel 1 goto :setup_error
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :setup_error
)

if not exist "models\Qwen3-4B-Q4_K_M.gguf" if not exist "models\Qwen3-1.7B-Q4_K_M.gguf" (
    set "KBOFM_AI_ENABLED=0"
    echo [KBO FM 2025] 로컬 AI 모델이 없어 규칙 기반 모드로 실행합니다.
)

echo [KBO FM 2025] 게임을 실행합니다.
".venv\Scripts\python.exe" main.py
set "GAME_EXIT_CODE=%ERRORLEVEL%"
if not "%GAME_EXIT_CODE%"=="0" (
    echo.
    echo 게임이 비정상 종료되었습니다. data\logs\crash.log를 확인해 주세요.
    pause
)
exit /b %GAME_EXIT_CODE%

:setup_error
echo.
echo [KBO FM 2025] 실행 환경 준비에 실패했습니다.
echo 인터넷 연결과 Python 설치 상태를 확인한 뒤 다시 실행해 주세요.
pause
exit /b 1
