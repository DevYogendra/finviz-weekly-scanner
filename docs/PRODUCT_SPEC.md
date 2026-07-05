# Finviz Weekly Stage-2 Scanner Product Specification

This document summarizes the authoritative requirements from `CODEX_BUILD_REQUEST.md`.

The application opens a configured Finviz screener URL once per week, extracts every ticker across every results page using DOM extraction, saves page screenshots, validates the unique ticker count against Finviz's displayed total, resolves exchanges, writes CSV/JSON/TradingView outputs, compares the result with the latest prior successful run, and refuses to publish partial or suspicious results.

Key requirements:

- Windows 11, Python 3.12, Playwright Chromium, Typer CLI, SQLite, pytest, Ruff, mypy.
- Default timezone: `America/Denver`.
- Default weekly schedule: Saturday at 08:00 local time.
- Default output directory: `Documents\FinvizWeeklyScanner` inside this project unless the user chooses another path.
- `finviz-scanner configure` prompts for the exact Finviz screener URL after installation.
- The saved Finviz URL must use HTTPS, point to `finviz.com`, be a screener URL, and not be a placeholder.
- Real URLs, cookies, browser profiles, credentials, logs, screenshots, and databases are never committed.
- DOM extraction is primary. OCR is disabled by default and cannot publish ambiguous results.
- TradingView files use exchange-qualified comma-separated symbols.
- The first successful run is a baseline and does not report all symbols as additions.
- Only the latest fully successful run may become the comparison baseline.
- Failed, count-mismatched, CAPTCHA-blocked, unresolved-exchange, and partial runs cannot replace the latest successful snapshot.
- Offline tests use sanitized fixtures and never access live Finviz.

See `CODEX_BUILD_REQUEST.md` for the complete build brief.
