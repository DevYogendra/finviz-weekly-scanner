# Architecture

The scanner is split into source-independent core modules and a Finviz adapter.

- `browser`: Playwright collection of Finviz result pages, screenshots, and HTML.
- `extraction`: DOM parsing, displayed-count parsing, blocker detection, and repeated-page detection.
- `symbols`: exchange resolution from a replaceable local symbol master.
- `validation`: exact-count and suspicious-result checks.
- `comparison`: set comparison against the latest successful snapshot.
- `output`: CSV, JSON, Markdown, and TradingView artifact writing.
- `storage`: SQLite history and process locking.
- `workflow`: atomic run orchestration.
- `cli`: user commands and operational entry points.

The workflow writes artifacts to a temporary run directory first, validates and resolves everything, moves the temp directory into `snapshots/<run_id>`, records success in SQLite, then refreshes `latest`. Failures are recorded but do not update `latest`.
