param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string]$LogDirectory,
    [switch]$Headed
)

$ErrorActionPreference = "Stop"
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Scanner Python executable not found: $python"
}
if (-not $LogDirectory) {
    $LogDirectory = & $python -c "from finviz_scanner.config import load_settings; print(load_settings().output.root_directory / 'logs')"
    if ($LASTEXITCODE -ne 0 -or -not $LogDirectory) {
        throw "Could not determine the configured scanner log directory."
    }
}

New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stdout = Join-Path $LogDirectory "scan-$stamp.out.log"
$stderr = Join-Path $LogDirectory "scan-$stamp.err.log"

$scanArguments = @("-m", "finviz_scanner.cli", "scan")
if ($Headed) {
    $scanArguments += "--headed"
}

Push-Location $ProjectRoot
try {
    & $python @scanArguments 1> $stdout 2> $stderr
    $scanExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $scanExitCode
