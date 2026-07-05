param(
    [string]$TaskName = "FinvizWeeklyScanner"
)

$ErrorActionPreference = "Stop"
schtasks /Delete /TN $TaskName /F
