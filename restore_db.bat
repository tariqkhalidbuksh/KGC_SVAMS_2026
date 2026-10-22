@echo off
title "Karachi Gymkhana - RFID VAMS Database Restore"
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
    for /f "tokens=*" %%i in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
)
if "%PYTHON_EXE%"=="" (
    for /f "tokens=*" %%i in ('where py 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
)

if "%PYTHON_EXE%"=="" goto :python_not_found

REM Ensure psycopg2 is available
"%PYTHON_EXE%" -c "import psycopg2" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] Installing required database adapter [psycopg2-binary]...
    "%PYTHON_EXE%" -m pip install psycopg2-binary
)

"%PYTHON_EXE%" restore_db.py
echo.
pause
exit /b 0

:python_not_found
echo ============================================================================
echo [ERROR] Python runtime not found!
echo Please install Python 3.10+ and check "Add Python to PATH".
echo ============================================================================
echo.
pause
exit /b 1
