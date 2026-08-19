<#
.SYNOPSIS
    Adds Claude Usage Tray to Windows startup, like any other tray app
    (Spotify, Discord, etc.) so it launches automatically at sign-in.

.DESCRIPTION
    Creates a shortcut in your per-user Startup folder
    (shell:startup) pointing at the "claude-usage-tray" GUI entry point
    installed in this repo's virtual environment, so it runs silently
    (no console window) in the system tray.

    Run this from the repo root after `pip install -e .` inside .venv:
        powershell -ExecutionPolicy Bypass -File scripts\install-startup.ps1

.PARAMETER Remove
    Removes the startup shortcut instead of creating it.
#>

param(
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$exePath = Join-Path $repoRoot ".venv\Scripts\claude-usage-tray.exe"
$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "Claude Usage Tray.lnk"

if ($Remove) {
    if (Test-Path $shortcutPath) {
        Remove-Item $shortcutPath -Force
        Write-Host "Removed startup shortcut: $shortcutPath"
    } else {
        Write-Host "No startup shortcut found at: $shortcutPath"
    }
    exit 0
}

if (-not (Test-Path $exePath)) {
    Write-Error "Couldn't find $exePath`nRun this first: python -m venv .venv; .venv\Scripts\pip install -e ."
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $exePath
$shortcut.WorkingDirectory = $repoRoot
$shortcut.Description = "Claude plan usage in the system tray"
$shortcut.Save()

Write-Host "Installed startup shortcut: $shortcutPath"
Write-Host "It will launch automatically next time you sign in, or run it now:"
Write-Host "  & `"$exePath`""
