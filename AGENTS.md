# AGENTS.md

## Project Rules

- `CODEX_BUILD_REQUEST.md` and `docs/PRODUCT_SPEC.md` are the product source of truth.
- Use DOM extraction as the primary Finviz path. OCR is optional, disabled by default, and must never silently publish ambiguous results.
- Never commit real Finviz URLs, cookies, browser profiles, email credentials, logs, screenshots, SQLite databases, or runtime data.
- Failed, partial, count-mismatched, CAPTCHA-blocked, or unresolved-exchange runs must not replace the latest successful snapshot.
- Keep tests offline by default. Live Finviz tests must be opt-in.

## Required Checks

Run these before claiming completion:

```powershell
pytest
ruff check .
ruff format --check .
mypy src
finviz-scanner doctor
```
