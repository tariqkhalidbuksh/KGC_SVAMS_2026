@echo off
setlocal enabledelayedexpansion

:: ============================================================================
:: Karachi Gymkhana Club - RFID Vehicle Access Management System (VAMS)
:: Production Startup & Crash Recovery Watchdog Script
:: ============================================================================

title Karachi Gymkhana - RFID VAMS Core Server
cd /d "%~dp0"

:: 1. Detect Python Interpreter (Verify fastapi availability)
set "PYTHON_EXE="

:: Check system python first
python -c "import fastapi" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python"
) else (
    :: Fallback to .venv if system python doesn't have it
    if exist "%~dp0.venv\Scripts\python.exe" (
        "%~dp0.venv\Scripts\python.exe" -c "import fastapi" >nul 2>nul
        if !ERRORLEVEL! equ 0 (
            set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
        )
    )
)

if "%PYTHON_EXE%"=="" (
    :: If neither passed the import test, default to system python
    where python >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_EXE=python"
    ) else if exist "%~dp0.venv\Scripts\python.exe" (
        set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
    ) else (
        echo [ERROR] Python environment not found!
        echo Please ensure Python is installed with the required dependencies.
        pause
        exit /b 1
    )
)

:: Check if reportlab and easyocr are installed
"%PYTHON_EXE%" -c "import reportlab" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] Installing missing PDF reporting engine (reportlab)...
    "%PYTHON_EXE%" -m pip install reportlab>=4.1.0
)
"%PYTHON_EXE%" -c "import easyocr" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] Installing missing OCR AI engine (easyocr)...
    "%PYTHON_EXE%" -m pip install easyocr>=1.7.0
)

:: 2. Display System Banner
cls
echo ============================================================================
echo   KARACHI GYMKHANA CLUB - RFID VEHICLE ACCESS SYSTEM (VAMS)
echo ============================================================================
echo   Working Directory : %~dp0
echo   Python Runtime    : %PYTHON_EXE%
echo   Local Web Portal  : http://localhost:8000
echo   Kiosk Display     : http://localhost:8000/kiosk
echo   Camera Audit      : http://localhost:8000/?tab=camera_audit
echo   Watchdog Status   : ACTIVE (Auto-restarts automatically if crashed)
echo ============================================================================
echo.

:: 3. Continuous Execution Loop (Watchdog / Auto-Restart)
:server_loop
echo [%DATE% %TIME%] Starting RFID VAMS Core Application...
"%PYTHON_EXE%" app.py

set EXIT_CODE=%ERRORLEVEL%
echo.
echo ============================================================================
echo [WARNING] Server process exited with code %EXIT_CODE% at %TIME%.
echo [WATCHDOG] Restarting server automatically in 5 seconds...
echo            (Press Ctrl+C to stop the watchdog loop)
echo ============================================================================
timeout /t 5 /nobreak >nul
goto server_loop
