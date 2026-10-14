# Operations

1. Run `scripts\install.ps1`.
2. Run `finviz-scanner configure` and paste the exact Finviz screener URL.
3. Place a `symbol-master.csv` file in the configured output directory with columns `ticker,exchange`.
4. Run `finviz-scanner scan --headed` for the first scan.
5. Review `snapshots\<run-id>\<screen-id>\report.md` and the stable files in `watchlists\`.
6. Run `finviz-scanner install-schedule` or `scripts\create_scheduled_task.ps1`.

## Open the web app

Open the repository folder in File Explorer and double-click **`web.bat`**. It starts the
dashboard server in the background and opens your default browser automatically.

Alternatively, open PowerShell in the repository folder and run:

```powershell
.\web.bat
```

The dashboard normally opens at `http://127.0.0.1:8765/`. If that port is occupied, the
launcher opens a different available local port. Use the tab opened by the launcher.

Choose a **Finviz screen** to see its preset settings and latest successful results. Click
**Run visible scan** to scan, or **Check health** to check the installation. The dashboard
also provides schedule repair, run history, watchlist exports, and folder controls.

## Troubleshoot opening the dashboard

- **Nothing opens:** run the command below from the repository folder. It displays startup
  errors and prints the address to open in your browser. Keep the terminal open while using
  the app; press **Ctrl+C** to stop the server.
- **Missing virtual environment:** run `scripts\install.ps1` to create `.venv` and install
  the dependencies, then complete configuration.
- **Dashboard needs reopening, blank screen selector, or missing preset summary after an
  update:** launch `web.bat` again and use the newly opened tab. An older server can still
  hold the default port; refreshing its tab does not reload the Python application.
- **Dashboard disconnected:** launch the app again and use the new tab. If it remains
  disconnected, use the terminal command below to inspect startup errors.

```powershell
.\.venv\Scripts\python.exe -m finviz_scanner.cli web
```

## Weekly task

The scheduled task writes timestamped logs under the configured data directory and opens a
visible browser. The task requires the user to be logged in so Finviz human verification can be
completed when prompted. Task Scheduler records the scanner's actual exit status.
