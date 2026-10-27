# Creates desktop and Start menu shortcuts that start Pomodoro Tracker through the
# project's Python (pythonw.exe, signed by the Python Software Foundation).
#
# Use this when Windows Smart App Control blocks the unsigned installer/exe.
# The app then runs straight from this folder, so updating = changing the code.
#
#   powershell -ExecutionPolicy Bypass -File create_shortcuts.ps1 [-Name "Pomodoro Tracker"] [-Startup]
#
#   -Name     Shortcut name (default "Pomodoro Tracker (Python)")
#   -Startup  Also start the app when you sign in to Windows

param(
    [string]$Name = "Pomodoro Tracker (Python)",
    [switch]$Startup
)

$project = $PSScriptRoot
$pythonw = Join-Path $project ".venv\Scripts\pythonw.exe"
$main = Join-Path $project "main.py"
$icon = Join-Path $project "assets\icon.ico"

if (-not (Test-Path $pythonw)) {
    Write-Error "Python not found at $pythonw. Create the virtual environment first (see README)."
    exit 1
}

$targets = @(
    [Environment]::GetFolderPath("Desktop"),
    [Environment]::GetFolderPath("Programs")      # Start menu
)
if ($Startup) { $targets += [Environment]::GetFolderPath("Startup") }

$shell = New-Object -ComObject WScript.Shell
foreach ($folder in $targets) {
    $path = Join-Path $folder "$Name.lnk"
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $pythonw
    $link.Arguments = "`"$main`""
    $link.WorkingDirectory = $project
    if (Test-Path $icon) { $link.IconLocation = "$icon,0" }
    $link.Description = "Pomodoro Tracker"
    $link.Save()
    Write-Output "Created: $path"
}
