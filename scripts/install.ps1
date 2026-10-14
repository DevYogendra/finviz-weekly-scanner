param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot
py -3.12 -m venv .venv
& "$ProjectRoot\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$ProjectRoot\.venv\Scripts\python.exe" -m pip install -e ".[dev]"
& "$ProjectRoot\.venv\Scripts\python.exe" -m playwright install chromium
& "$ProjectRoot\.venv\Scripts\python.exe" -m finviz_scanner.cli doctor
Write-Host "Next: run finviz-scanner configure, then finviz-scanner scan --headed."
