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

## Launch the web app

After installation and configuration:

1. Open the `finviz-weekly-scanner` repository folder in File Explorer.
2. Double-click **`web.bat`** in that folder.
3. The launcher starts the local server in the background and opens the dashboard in your
   default browser automatically.

To launch from PowerShell, open PowerShell in the repository folder and run:

```powershell
.\web.bat
```

The default address is `http://127.0.0.1:8765/`. If that port is already occupied, the launcher
uses another available local port and opens that address. Use the newly opened browser tab.

If the browser does not open or the launcher appears to do nothing, run this in PowerShell
from the repository folder to see startup messages and the dashboard address:

```powershell
.\.venv\Scripts\python.exe -m finviz_scanner.cli web
```

Keep that PowerShell window open while using the dashboard; press **Ctrl+C** there to stop
the server. If `.venv\Scripts\python.exe` is missing, complete the installation steps above.

The browser dashboard can run a visible scan, check installation health, repair the weekly task,
show recent outcomes, and open the generated watchlist or log folders. It listens only on
`127.0.0.1` and requires a per-session request token for actions.

After a code update, an older server may still be running. If the page shows **Dashboard needs
reopening**, an empty screen selector, or missing preset settings, launch `web.bat` again and
use the newly opened tab. Refreshing the old tab alone does not update its server.

## First scan

Click **Run visible scan** in the dashboard. Complete Finviz human verification in the scan
browser if prompted. After a successful scan, choose a screen to review its results.

### Review results and create a watchlist

1. Choose a Finviz screen in **Screen results**. The table uses its latest successful scan;
   the latest attempt is displayed separately, including failures. The preset summary below
   the screen selector shows its configured filters, view, and sort order for the next scan.
2. Review **Current**, **New additions**, **Unchanged**, or **Removed**. Search by ticker or
   company and click a column heading to sort. The first successful scan is a baseline with no changes.
3. All current stocks start selected. Uncheck individual stocks, **Clear selection**, or
   **Select visible** after filtering. Removed stocks are review-only. Selections survive
   filters and screen switches while this page stays open.
4. **Copy selected** copies all selected current stocks as one comma-separated line with
   exchange prefixes. If clipboard access fails, copy the highlighted preview manually.
5. **Download TXT** saves exactly the same line as `<screen-id>-selected.txt`. In TradingView,
   open the watchlist menu and choose **Import / Upload list** to import the file.

Export always preserves the original Finviz rank order, even after table sorting. Selections
are session-only and never alter scan snapshots or stable watchlist files. When another scan
succeeds, **Update results** loads it and selects all current stocks again. Incomplete stored
results disable export and show an error. The results view does not request live stock data.

You can also run the scanner directly from PowerShell.

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
Scheduled scans open a visible browser so Finviz human verification can be completed. The
Windows task runs only while the configured user is logged in, and its result code reflects
whether the scan succeeded, partially succeeded, or failed.

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
