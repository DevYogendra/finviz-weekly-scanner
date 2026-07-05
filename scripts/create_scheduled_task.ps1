param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$TaskName = "FinvizWeeklyScanner",
    [string]$Day = "SAT",
    [string]$Time = "08:00"
)

$ErrorActionPreference = "Stop"
$runner = Join-Path $ProjectRoot "scripts\run_scan.ps1"
$action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$runner`" -ProjectRoot `"$ProjectRoot`""
schtasks /Create /TN $TaskName /SC WEEKLY /D $Day /ST $Time /TR $action /F
