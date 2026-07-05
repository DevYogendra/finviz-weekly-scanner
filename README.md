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

The legacy `finviz.saved_screen_url` setting still works. For multiple screens, configure `finviz.screens` instead:

```yaml
finviz:
  screens:
    - id: stage-2
      name: Stage 2 Candidates
      url: "https://finviz.com/screener?..."
      enabled: true
      tradingview_filename: "stage-2.txt"
    - id: momentum
      name: Momentum Candidates
      url: "https://finviz.com/screener?..."
      enabled: true
  delay_between_screens_ms: 1000
```

## First Scan

Run a visible browser first:

```powershell
finviz-scanner scan --headed
```

List configured screens:

```powershell
finviz-scanner list-screens
```

Scan selected screens:

```powershell
finviz-scanner scan --screen stage-2 --screen momentum --headed
```

Review:

- `snapshots\<run-id>\manifest.json`
- `snapshots\<run-id>\<screen-id>\current.csv`
- `snapshots\<run-id>\<screen-id>\additions.csv`
- `snapshots\<run-id>\<screen-id>\removals.csv`
- `snapshots\<run-id>\<screen-id>\report.md`
- `snapshots\<run-id>\<screen-id>\tradingview-watchlist.txt`
- `watchlists\<screen-id>.txt`

Import the stable per-screen files under `watchlists\` into TradingView. A failed screen keeps its previous stable watchlist file.

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
finviz-scanner doctor
```
