# Operations

1. Run `scripts\install.ps1`.
2. Run `finviz-scanner configure` and paste the exact Finviz screener URL.
3. Place a `symbol-master.csv` file in the configured output directory with columns `ticker,exchange`.
4. Run `finviz-scanner scan --headed` for the first scan.
5. Review `latest\report.md`, `latest\tradingview-current.txt`, and `latest\tradingview-additions.txt`.
6. Run `finviz-scanner install-schedule` or `scripts\create_scheduled_task.ps1`.

The scheduled task writes timestamped logs under the configured data directory. The browser may require the user to be logged in depending on Finviz session behavior.
