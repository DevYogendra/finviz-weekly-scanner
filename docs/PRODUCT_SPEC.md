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

## Local results review and watchlist export

The selected screen shows a read-only preset summary of its configured filters, view,
and sort order, updating when the screen changes. Known filter codes use plain-language
labels; unrecognized settings are explicitly labeled rather than guessed. Source URLs
and unrelated URL parameters are not exposed. The summary describes the next scan's
configuration; saved results may reflect earlier settings.

The dashboard provides per-screen current, additions, unchanged, and removed tables with
ticker/company search and column sorting. All current symbols start selected; choices persist
across filters and screen switches only during the current page session. Removed symbols are
review-only. Baseline runs report no changes. New successful results require an explicit
Update results action, which resets selections to all current symbols.

The successful-result timestamp and latest-attempt status are separate. Read-only SQLite
queries select the latest two successful runs for the chosen screen, including legacy default
records, independent of the history display limit. Stored membership must match both extracted
and displayed counts before export is allowed. Missing, invalid, or inaccessible data must
produce a clear empty/error state and cannot silently supply an incomplete watchlist.

Copy selected and Download TXT generate identical comma-separated exchange-qualified symbols
in original Finviz rank order. Clipboard success is reported only after completion; failures
offer manual copying from the preview. Downloads use `<screen-id>-selected.txt` for TradingView
manual import. This feature does not persist selections, merge screens, enrich market data,
rank candidates, upload to TradingView, or modify scan publication behavior.
