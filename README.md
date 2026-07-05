# finviz-weekly-scanner

A local Windows application that runs a weekly Finviz screener, saves an auditable snapshot, compares it with the previous successful run, and writes TradingView watchlist files.

## Install

1. Install Python 3.12 from <https://www.python.org/downloads/windows/> if it is absent. Check "Add python.exe to PATH".
2. Open PowerShell in this repository.
3. Run:

```powershell
scripts\install.ps1
```

4. Configure after the app is installed:

```powershell
finviz-scanner configure
```

Copy the exact Finviz screener URL from your browser address bar after setting the filters. The app validates the URL but does not ask for it during code generation.

## First Scan

Run a visible browser first:

```powershell
finviz-scanner scan --headed
```

Review:

- `latest\current.csv`
- `latest\additions.csv`
- `latest\removals.csv`
- `latest\report.md`
- `latest\tradingview-current.txt`
- `latest\tradingview-additions.txt`

Import `tradingview-current.txt` into TradingView when you want the full current list. Import `tradingview-additions.txt` when you only want new names.

## Schedule

Install the weekly task:

```powershell
finviz-scanner install-schedule
```

Remove it:

```powershell
finviz-scanner remove-schedule
```

The default schedule is Saturday at 08:00 America/Denver. The configured schedule is used after `configure`.

## Logs And Failures

Run:

```powershell
finviz-scanner history
finviz-scanner doctor
```

If Finviz changes its page structure, update the isolated DOM selectors in `src\finviz_scanner\extraction\finviz_dom.py` and add or update sanitized HTML fixtures under `tests\fixtures`.

## Developer Checks

```powershell
pytest
ruff check .
ruff format --check .
mypy src
```
