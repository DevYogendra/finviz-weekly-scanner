Build a production-quality Python application using docs/SPEC.md as the
authoritative product specification.

Application name:
finviz-weekly-scanner

Primary objective:
Run a weekly Finviz screener scan, collect all ticker symbols across every
results page, save an auditable weekly snapshot, compare it against the previous
successful snapshot, and generate a TradingView-compatible watchlist file.

Environment:
- Windows 11
- Python 3.12
- America/Denver timezone
- Local unattended execution through Windows Task Scheduler
- Playwright with Chromium
- SQLite for history
- pytest for tests
- Ruff for linting and formatting
- mypy for type checking
- Typer for the CLI
- Pydantic Settings for configuration

Important implementation requirements:

1. Read the exact Finviz screener URL from configuration or environment variable.
   Never hard-code the filters inferred from an image.

2. Use Playwright and direct DOM extraction as the primary collection mechanism.

3. Save a full-page screenshot of every results page for auditing.

4. Do not use OCR unless DOM extraction fails. Keep OCR as an optional,
   separately configurable fallback.

5. Do not bypass CAPTCHA, login controls, rate limits, or anti-automation
   protections. Abort the run and write an actionable error report when such a
   condition is detected.

6. Navigate through all Finviz result pages until there is no next page.

7. Extract:
   - ticker
   - company name when available
   - sector when available
   - industry when available
   - country when available
   - result rank
   - source page
   - extraction timestamp

8. Parse the total result count displayed by Finviz.

9. Validation must fail when:
   - extracted unique ticker count differs from the displayed result count
   - any page fails to load
   - duplicate symbols remain after normalization
   - a ticker cannot be normalized
   - exchange resolution is incomplete
   - the current result is suspiciously empty
   - an incomplete run would overwrite the latest successful snapshot

10. Normalize ticker symbols carefully, including symbols containing dots,
    dashes, or share-class suffixes.

11. Resolve each ticker to a TradingView-compatible exchange-qualified symbol.

12. Generate:
    - current.csv
    - current.json
    - tradingview.txt
    - additions.csv
    - removals.csv
    - unchanged.csv
    - report.md
    - run.json
    - one screenshot for each result page

13. Comparison logic:
    additions = current_symbols - previous_successful_symbols
    removals = previous_successful_symbols - current_symbols
    unchanged = current_symbols intersect previous_successful_symbols

14. Treat the first successful execution as a baseline. Do not report every
    baseline ticker as a new addition.

15. Persist run history and ticker history in SQLite.

16. Store snapshots in:
    data/snapshots/YYYY-MM-DD/

17. Never overwrite a prior successful snapshot with a failed or incomplete run.

18. Add CLI commands:

    finviz-scanner scan
    finviz-scanner validate
    finviz-scanner compare
    finviz-scanner export-tradingview
    finviz-scanner history
    finviz-scanner doctor

19. The doctor command must verify:
    - Python configuration
    - Playwright installation
    - Chromium installation
    - data directory permissions
    - database accessibility
    - configuration validity
    - screener URL presence

20. Generate Windows PowerShell scripts for:
    - installation
    - running a scan
    - validating installation
    - creating a Saturday 8:00 AM scheduled task
    - removing the scheduled task

21. The scheduled task must:
    - use the America/Denver schedule supplied by the user
    - run even when the normal terminal is closed
    - write stdout and stderr to timestamped logs
    - use an absolute executable path
    - prevent overlapping executions

22. Add retries for temporary network failures:
    - maximum 3 attempts
    - exponential backoff
    - no retry for validation, CAPTCHA, or configuration errors

23. Include structured logging with run IDs.

24. Never log credentials, cookies, secrets, or complete session information.

25. Generate an .env.example and settings.example.yaml containing placeholders,
    not real secrets.

26. Write comprehensive unit tests using stored HTML fixtures. Tests must not
    depend on the live Finviz website.

27. Add an optional live integration test that is disabled by default.

28. Add tests proving:
    - 44 results over three pages produce 44 unique tickers
    - identical consecutive runs produce zero changes
    - two additions and one removal are calculated correctly
    - the first run is treated as the baseline
    - a partial page load is rejected
    - a count mismatch is rejected
    - unresolved exchanges prevent publication
    - a failed run does not replace the previous successful snapshot
    - TradingView output is correctly comma-separated and exchange-qualified

29. Generate:
    - README.md with exact installation and operating instructions
    - AGENTS.md with repository conventions and required validation commands
    - docs/ARCHITECTURE.md
    - docs/OPERATIONS.md
    - docs/TROUBLESHOOTING.md

30. Add GitHub Actions to run:
    - pytest
    - Ruff
    - mypy

31. Use clean architecture and dependency injection where it improves
    testability, but do not overengineer the application.

32. Do not leave placeholders, TODO-only functions, fake implementations, or
    tests that merely assert True.

Implementation process:

A. First inspect docs/SPEC.md.
B. Produce an implementation plan.
C. Create the repository structure.
D. Implement the application in small coherent stages.
E. Run tests, Ruff, and mypy.
F. Fix all failures.
G. Run the doctor command.
H. Provide a final report containing:
   - files created
   - commands executed
   - test results
   - assumptions
   - remaining manual configuration
   - exact commands I should run next

Do not claim completion unless all non-live tests pass.