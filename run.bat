@echo off
echo.
echo =============================================
echo  RTMS - Reliability Test Management System
echo =============================================
echo.

echo [1/4] Connecting to network path...
pushd "%~dp0"
if errorlevel 1 (
    echo [ERROR] Cannot access network path.
    pause & exit /b 1
)
echo       OK: %CD%
echo.

echo [2/4] Checking virtual environment...
set VENV=C:\ProgramData\RTMS\venv
if not exist "%VENV%\Scripts\activate.bat" (
    echo       Creating venv - first time only, please wait 1-2 min...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] Failed to create venv. Check Python installation.
        pause & exit /b 1
    )
)
echo       OK: %VENV%
echo.

echo [3/4] Installing / checking packages...
call "%VENV%\Scripts\activate.bat"
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Package installation failed.
    pause & exit /b 1
)
echo.

echo [4/4] Starting server...
echo  Browser : http://localhost:5001
echo  Stop    : Close this window or Ctrl+C
echo =============================================
echo.
python app.py

popd
pause
