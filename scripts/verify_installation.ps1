param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"
& "$ProjectRoot\.venv\Scripts\finviz-scanner.exe" doctor
& "$ProjectRoot\.venv\Scripts\python.exe" -m pytest
& "$ProjectRoot\.venv\Scripts\python.exe" -m ruff check .
& "$ProjectRoot\.venv\Scripts\python.exe" -m ruff format --check .
& "$ProjectRoot\.venv\Scripts\python.exe" -m mypy src
