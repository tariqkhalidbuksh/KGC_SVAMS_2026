@echo off
title Karachi Gymkhana - RFID VAMS Database Restore
cd /d "%~dp0"

REM ============================================================================
REM Karachi Gymkhana Club - RFID Vehicle Access Management System (VAMS)
REM 1-Click Database Restore Utility (Restores kgc_vams_backup.sql to PostgreSQL)
REM ============================================================================

set "PYTHON_EXE="
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
    where py >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_EXE=py"
    )
)

if "%PYTHON_EXE%"=="" (
    echo ============================================================================
    echo [ERROR] Python runtime not found!
    echo Please install Python 3.10+ and check "Add Python to PATH".
    echo ============================================================================
    echo.
    pause
    exit /b 1
)

REM Ensure psycopg2 is available
"%PYTHON_EXE%" -c "import psycopg2" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] Installing required database adapter (psycopg2-binary)...
    "%PYTHON_EXE%" -m pip install psycopg2-binary
)

"%PYTHON_EXE%" restore_db.py
echo.
pause
