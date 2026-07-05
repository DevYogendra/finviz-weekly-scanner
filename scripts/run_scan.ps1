param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$LogDirectory = "$ProjectRoot\logs"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stdout = Join-Path $LogDirectory "scan-$stamp.out.log"
$stderr = Join-Path $LogDirectory "scan-$stamp.err.log"
$exe = Join-Path $ProjectRoot ".venv\Scripts\finviz-scanner.exe"
Start-Process -FilePath $exe -ArgumentList "scan" -WorkingDirectory $ProjectRoot -WindowStyle Hidden -Wait -RedirectStandardOutput $stdout -RedirectStandardError $stderr
