@echo off
title Karachi Gymkhana - RFID VAMS Core Server
cd /d "%~dp0"

REM ============================================================================
REM Karachi Gymkhana Club - RFID Vehicle Access Management System (VAMS)
REM Production Startup & Crash Recovery Watchdog Script
REM ============================================================================

set "PYTHON_EXE="

REM 1. Detect Python Runtime
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
)
if "%PYTHON_EXE%"=="" (
    where python >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_EXE=python"
    )
)

if "%PYTHON_EXE%"=="" (
    echo ============================================================================
    echo [ERROR] Python environment not found!
    echo Please install Python 3.10+ or configure Python in system PATH.
    echo ============================================================================
    echo.
    pause
    exit /b 1
)

REM 2. Verify Core Dependencies
"%PYTHON_EXE%" -c "import fastapi, uvicorn, reportlab" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] Installing required dependencies from requirements.txt...
    "%PYTHON_EXE%" -m pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install required packages.
        pause
        exit /b 1
    )
)

REM 3. Display System Banner
cls
echo ============================================================================
echo   KARACHI GYMKHANA CLUB - RFID VEHICLE ACCESS SYSTEM (VAMS)
echo ============================================================================
echo   Directory         : %~dp0
echo   Python Runtime    : %PYTHON_EXE%
echo   Web Dashboard     : http://localhost:8000/dashboard
echo   Kiosk Display     : http://localhost:8000/kiosk
echo   Camera Audit      : http://localhost:8000/?tab=camera_audit
echo   Watchdog Status   : ACTIVE (Auto-restarts automatically if crashed)
echo ============================================================================
echo.

REM 4. Continuous Execution Loop
:server_loop
echo [%DATE% %TIME%] Starting RFID VAMS Core Application...
"%PYTHON_EXE%" app.py

set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo ============================================================================
echo [WARNING] Server process exited with code %EXIT_CODE% at %TIME%.
echo [WATCHDOG] Restarting server in 5 seconds... (Press Ctrl+C to stop)
echo ============================================================================
ping 127.0.0.1 -n 6 >nul
goto server_loop
