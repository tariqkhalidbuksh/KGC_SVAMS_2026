@echo off
title "Karachi Gymkhana - RFID VAMS Core Server"
cd /d "%~dp0"

REM ============================================================================
REM Karachi Gymkhana Club - RFID Vehicle Access Management System (VAMS)
REM Production Startup and Crash Recovery Watchdog Script
REM ============================================================================

set "PYTHON_EXE="

REM 1. Detect Python Runtime
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

REM 2. Verify Core Dependencies
"%PYTHON_EXE%" -c "import fastapi, uvicorn, reportlab, psycopg2" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] Installing required dependencies from requirements.txt...
    "%PYTHON_EXE%" -m pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 goto :pip_failed
)

REM 3. Verify and Auto-Start PostgreSQL Engine
echo [INFO] Checking PostgreSQL Database Service (127.0.0.1:5432)...
set "DB_ENGINE=Enterprise PostgreSQL (kgc_vams @ 127.0.0.1:5432)"
"%PYTHON_EXE%" -c "import socket, sys; s = socket.socket(); s.settimeout(1.0); res = s.connect_ex(('127.0.0.1', 5432)); s.close(); sys.exit(res)" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] PostgreSQL not responding on 127.0.0.1:5432. Attempting auto-start...
    "%PYTHON_EXE%" -c "import database; database.ensure_pg_service_started()" >nul 2>nul
    if exist "C:\PostgreSQL\pgsql\bin\pg_ctl.exe" (
        "C:\PostgreSQL\pgsql\bin\pg_ctl.exe" status -D "C:\PostgreSQL\data" >nul 2>nul
        if %ERRORLEVEL% neq 0 (
            "C:\PostgreSQL\pgsql\bin\pg_ctl.exe" -D "C:\PostgreSQL\data" -l "C:\PostgreSQL\server.log" start -w -t 10 >nul 2>nul
        )
    ) else (
        powershell -NoProfile -Command "Get-Service *postgres* -ErrorAction SilentlyContinue | Start-Service" >nul 2>nul
        net start postgresql-x64-17 >nul 2>nul
        if %ERRORLEVEL% neq 0 net start postgresql-x64-16 >nul 2>nul
        if %ERRORLEVEL% neq 0 net start postgresql-x64-15 >nul 2>nul
        if %ERRORLEVEL% neq 0 net start postgresql-x64-14 >nul 2>nul
        if %ERRORLEVEL% neq 0 net start postgresql >nul 2>nul
    )
    ping 127.0.0.1 -n 2 >nul
)
"%PYTHON_EXE%" -c "import socket, sys; s = socket.socket(); s.settimeout(1.5); res = s.connect_ex(('127.0.0.1', 5432)); s.close(); sys.exit(res)" >nul 2>nul
if %ERRORLEVEL% neq 0 goto :pg_error

REM 4. Display System Banner
cls
echo ============================================================================
echo   KARACHI GYMKHANA CLUB - RFID VEHICLE ACCESS SYSTEM (VAMS)
echo ============================================================================
echo   Directory         : %~dp0
echo   Python Runtime    : %PYTHON_EXE%
echo   Database Engine   : %DB_ENGINE%
echo   Web Dashboard     : http://localhost:8000/dashboard
echo   Kiosk Display     : http://localhost:8000/kiosk
echo   Camera Audit      : http://localhost:8000/?tab=camera_audit
echo   Watchdog Status   : ACTIVE (Auto-restarts automatically if crashed)
echo ============================================================================
echo.

REM 5. Continuous Execution Loop
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

:python_not_found
echo ============================================================================
echo [ERROR] Python environment not found!
echo Please install Python 3.10+ or check "Add Python to PATH" during installation.
echo ============================================================================
echo.
pause
exit /b 1

:pip_failed
echo ============================================================================
echo [ERROR] Failed to install required packages from requirements.txt.
echo Please run this script as Administrator or check internet access.
echo ============================================================================
echo.
pause
exit /b 1

:pg_error
echo ============================================================================
echo [ERROR] PostgreSQL Database Service is NOT reachable on 127.0.0.1:5432!
echo ============================================================================
echo RFID VAMS runs exclusively on PostgreSQL.
echo.
echo QUICK FIX INSTRUCTIONS:
echo 1. IF POSTGRESQL IS INSTALLED ON THIS SERVER:
echo    - Press Win + R, type services.msc, and press Enter.
echo    - Locate postgresql-x64-... or PostgreSQL Server.
echo    - Right-click and select Start.
echo.
echo 2. IF POSTGRESQL IS NOT INSTALLED YET:
echo    - Download and install official PostgreSQL for Windows from:
echo      https://www.postgresql.org/download/windows/
echo    - During setup, keep port 5432 and set your superuser password.
echo.
echo 3. IF POSTGRESQL USES A PASSWORD OR RUNS ON A DIFFERENT IP/PORT:
echo    - Create a .env file in this directory [see .env.example] and set:
echo        PG_HOST=127.0.0.1
echo        PG_PORT=5432
echo        PG_USER=postgres
echo        PG_PASSWORD=your_password
echo ============================================================================
echo.
pause
exit /b 1
