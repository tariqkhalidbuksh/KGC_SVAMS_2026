@echo off
setlocal enabledelayedexpansion

:: ============================================================================
:: Karachi Gymkhana Club - RFID Vehicle Access Management System (VAMS)
:: Uninstall Auto-Start Script
:: ============================================================================

title RFID VAMS - Remove Automatic Startup
cd /d "%~dp0"

echo ============================================================================
echo   KARACHI GYMKHANA CLUB - RFID VEHICLE ACCESS SYSTEM (VAMS)
echo   Disable Auto-Start on System Boot / Server Restart
echo ============================================================================
echo.

:: 1. Remove Windows Startup Folder Shortcut via helper
echo [1/2] Removing Windows Startup folder shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\manage_autostart.ps1" -Action disable

:: 2. Remove Task Scheduler entry if present
echo [2/2] Checking Windows Task Scheduler...
schtasks /Delete /TN "RFID_VAMS_AutoStart" /F >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo   [OK] Removed scheduled task 'RFID_VAMS_AutoStart'.
) else (
    echo   [INFO] No scheduled task found.
)

echo.
echo ============================================================================
echo [SUCCESS] Automatic startup has been DISABLED.
echo The application will now only start when manually run via start_server.bat.
echo ============================================================================
echo.
pause
