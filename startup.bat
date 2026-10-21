@echo off
title Karachi Gymkhana - RFID VAMS Automated Setup & Launcher
cd /d "%~dp0"

REM ============================================================================
REM Karachi Gymkhana Club - RFID Vehicle Access Management System (VAMS)
REM Automated Setup, Dependency Installer & Production Startup
REM Default Administrator: admin / admin123
REM ============================================================================

cls
echo ============================================================================
echo   KARACHI GYMKHANA CLUB - RFID VEHICLE ACCESS MANAGEMENT SYSTEM (VAMS)
echo   Automated Environment Setup & Production Launcher
echo ============================================================================
echo.

REM 1. Detect Python Runtime
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
    echo [ERROR] Python was not found on your system!
    echo.
    echo Please install Python 3.10 or higher from:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANT: Make sure to check "Add Python to PATH" during installation.
    echo ============================================================================
    echo.
    pause
    exit /b 1
)

echo [1/4] Python Runtime Detected: %PYTHON_EXE%

REM 2. Install / Verify Dependencies
echo [2/4] Verifying and installing required packages from requirements.txt...
"%PYTHON_EXE%" -m pip install --upgrade pip >nul 2>nul
"%PYTHON_EXE%" -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Dependency installation failed!
    echo Please verify your internet connection or run pip with administrator rights.
    echo.
    pause
    exit /b 1
)

REM 3. Check / Start PostgreSQL Service
echo [3/4] Verifying PostgreSQL Database Service (Port 5432)...
"%PYTHON_EXE%" -c "import socket; s = socket.socket(); s.settimeout(1.5); s.connect(('127.0.0.1', 5432)); s.close()" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] PostgreSQL not responding on 127.0.0.1:5432. Attempting auto-start...
    if exist "C:\PostgreSQL\pgsql\bin\pg_ctl.exe" (
        "C:\PostgreSQL\pgsql\bin\pg_ctl.exe" -D "C:\PostgreSQL\data" -l "C:\PostgreSQL\data\server.log" start >nul 2>nul
    ) else (
        net start postgresql-x64-16 >nul 2>nul
        if %ERRORLEVEL% neq 0 (
            net start postgresql-x64-15 >nul 2>nul
        )
        if %ERRORLEVEL% neq 0 (
            net start postgresql-x64-14 >nul 2>nul
        )
        if %ERRORLEVEL% neq 0 (
            net start postgresql >nul 2>nul
        )
    )
    ping 127.0.0.1 -n 3 >nul
)

REM 4. Initialize Database Schema & Verify Default Admin User
echo [4/4] Initializing Database Schema & Verifying Admin User (admin / admin123)...
"%PYTHON_EXE%" -c "from database import init_db, get_db_connection; from services.auth_service import init_auth_tables, hash_password; init_db(); init_auth_tables(); conn = get_db_connection(); u = conn.execute('SELECT id FROM users WHERE LOWER(username)=\'admin\'').fetchone(); (None if u else (conn.execute('INSERT INTO users (username, password_hash, salt, full_name, role, is_active) VALUES (?, ?, ?, ?, ?, 1)', ('admin', hash_password('admin123')[0], hash_password('admin123')[1], 'System Administrator', 'Admin')), conn.commit())); conn.close(); print('[SUCCESS] Database & Admin user (admin / admin123) verified.')"

echo.
echo ============================================================================
echo   KARACHI GYMKHANA CLUB - SYSTEM READY
echo ============================================================================
echo   Web Portal URL    : http://localhost:8000
echo   Admin Username    : admin
echo   Admin Password    : admin123
echo   Kiosk Terminal    : http://localhost:8000/kiosk
echo   Diagnostics       : http://localhost:8000/dashboard
echo ============================================================================
echo.

REM Automatically open browser in background
start "" http://localhost:8000

REM 5. Continuous Production Execution with Watchdog
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
