# One-time setup on a new PC: checks Python, creates the virtual environment, installs
# PySide6 and adds desktop + Start menu shortcuts. Safe to run again (it updates things).
#
#   Right-click -> Run with PowerShell, or:  powershell -ExecutionPolicy Bypass -File setup.ps1 [-Startup]
#
#   -Startup  Also start Pomodoro Tracker when you sign in to Windows

param([switch]$Startup)

$ErrorActionPreference = "Stop"
$project = $PSScriptRoot
Set-Location $project

function Find-Python {
    # The "py" launcher comes with python.org installs; "python" with the Microsoft Store one.
    foreach ($candidate in @(@{ Exe = "py"; Args = @("-3") }, @{ Exe = "python"; Args = @() })) {
        if (Get-Command $candidate.Exe -ErrorAction SilentlyContinue) {
            $pyArgs = $candidate.Args
            $version = & $candidate.Exe @pyArgs -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $version -and [version]"$version" -ge [version]"3.10") {
                return $candidate
            }
        }
    }
    return $null
}

Write-Host "Pomodoro Tracker setup" -ForegroundColor Cyan

$venvPython = Join-Path $project ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $python = Find-Python
    if (-not $python) {
        Write-Host ""
        Write-Host "Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/"
        Write-Host "(tick 'Add python.exe to PATH'), or run:  winget install Python.Python.3.12"
        Write-Host "Then run this setup again."
        exit 1
    }
    Write-Host "1/3 Creating the virtual environment (.venv)..."
    $pyArgs = $python.Args
    & $python.Exe @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Error "Couldn't create the virtual environment." }
} else {
    Write-Host "1/3 Virtual environment found."
}

Write-Host "2/3 Installing PySide6 (first time: about 1-2 minutes)..."
& $venvPython -m pip install --disable-pip-version-check --quiet --upgrade pip
& $venvPython -m pip install --disable-pip-version-check --quiet -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Error "Installing the requirements failed - check your internet connection." }

Write-Host "3/3 Creating shortcuts..."
$shortcutArgs = @{ Name = "Pomodoro Tracker" }
if ($Startup) { $shortcutArgs.Startup = $true }
& (Join-Path $project "create_shortcuts.ps1") @shortcutArgs

Write-Host ""
Write-Host "Done. Start Pomodoro Tracker from the desktop or the Start menu." -ForegroundColor Green
Write-Host "Your data will live in $env:APPDATA\PomodoroTracker\pomodoro.db"
