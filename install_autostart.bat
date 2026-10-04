@echo off
setlocal enabledelayedexpansion

:: ============================================================================
:: Karachi Gymkhana Club - RFID Vehicle Access Management System (VAMS)
:: Auto-Start Setup Script (Runs automatically on Windows Server Restart/Boot)
:: ============================================================================

title RFID VAMS - Configure Automatic Startup on Server Reboot
cd /d "%~dp0"

echo ============================================================================
echo   KARACHI GYMKHANA CLUB - RFID VEHICLE ACCESS SYSTEM (VAMS)
echo   Configure Auto-Start on System Boot / Server Restart
echo ============================================================================
echo.

set "TARGET_BAT=%~dp0start_server.bat"
if not exist "%TARGET_BAT%" (
    echo [ERROR] start_server.bat not found in: %~dp0
    pause
    exit /b 1
)

:: 1. Call PowerShell helper to create Windows Startup shortcut
echo [1/2] Creating Windows Startup folder shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\manage_autostart.ps1" -Action enable -TargetBat "%TARGET_BAT%"

:: 2. Check for Administrator privileges for pre-login boot service
echo.
echo [2/2] Checking for Administrator privileges (for pre-login boot service)...
net session >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo   [INFO] Administrator privileges detected.
    echo   Registering Windows Task Scheduler job for pre-login boot...
    schtasks /Create /TN "RFID_VAMS_AutoStart" /TR "\"%TARGET_BAT%\"" /SC ONSTART /RU "SYSTEM" /RL HIGHEST /F >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo   [OK] Task Scheduler job 'RFID_VAMS_AutoStart' created successfully!
        echo   The server will start automatically even BEFORE any user logs in.
    ) else (
        echo   [NOTE] Task Scheduler creation skipped. Startup folder shortcut is active.
    )
) else (
    echo   [INFO] Running under standard user permissions.
    echo   [OK] Startup folder shortcut is active in:
    echo        %%APPDATA%%\Microsoft\Windows\Start Menu\Programs\Startup
    echo.
    echo   The application will start automatically every time Windows boots and logs in.
    echo   (Tip: If you want the server to boot before user login, right-click
    echo    this script and select 'Run as administrator'.)
)

echo.
echo ============================================================================
echo [SUCCESS] Auto-start configuration is ACTIVE!
echo.
echo Useful Commands:
echo   - To start the server right now: Double-click 'start_server.bat'
echo   - To disable automatic startup : Double-click 'uninstall_autostart.bat'
echo ============================================================================
echo.
pause
