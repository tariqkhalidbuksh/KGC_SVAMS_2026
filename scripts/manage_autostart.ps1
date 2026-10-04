param(
    [Parameter(Mandatory=$false)]
    [ValidateSet('enable', 'disable', 'status')]
    [string]$Action = 'enable',
    [string]$TargetBat = ''
)

$startupFolder = [System.Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupFolder "RFID_VAMS.lnk"

if ($Action -eq 'enable') {
    if (-not $TargetBat) {
        $TargetBat = Join-Path $PSScriptRoot "..\start_server.bat"
    }
    $resolvedTarget = (Resolve-Path $TargetBat).Path
    $workingDir = Split-Path -Parent $resolvedTarget

    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $resolvedTarget
    $shortcut.WorkingDirectory = $workingDir
    $shortcut.Description = "Karachi Gymkhana RFID VAMS - Auto-start on boot"
    $shortcut.Save()

    if (Test-Path $shortcutPath) {
        Write-Host "[OK] Startup shortcut successfully created at: $shortcutPath" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Failed to create shortcut." -ForegroundColor Red
    }
}
elseif ($Action -eq 'disable') {
    if (Test-Path $shortcutPath) {
        Remove-Item -Force $shortcutPath
        Write-Host "[OK] Startup shortcut removed from: $shortcutPath" -ForegroundColor Green
    } else {
        Write-Host "[INFO] Startup shortcut did not exist." -ForegroundColor Yellow
    }
}
elseif ($Action -eq 'status') {
    if (Test-Path $shortcutPath) {
        $wsh = New-Object -ComObject WScript.Shell
        $sc = $wsh.CreateShortcut($shortcutPath)
        Write-Host "[ACTIVE] Auto-start is enabled. Points to: $($sc.TargetPath)" -ForegroundColor Green
    } else {
        Write-Host "[INACTIVE] Auto-start is not enabled." -ForegroundColor Yellow
    }
}
