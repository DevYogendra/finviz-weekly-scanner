# AGENTS.md

## Project objective

Build and maintain the Finviz Weekly Scanner described in docs/SPEC.md.

## Source of truth

1. docs/SPEC.md
2. Tests
3. README.md
4. Implementation

When these conflict, docs/SPEC.md takes precedence unless a later approved
decision is documented.

## Engineering requirements

- Python 3.12
- Fully typed public interfaces
- No hard-coded user paths
- No committed credentials
- No CAPTCHA bypass
- No silent handling of incomplete scans
- No replacement of successful snapshots by failed runs
- DOM extraction before OCR
- Unit tests must not access live websites

## Required checks

Before declaring a task complete, run:

```powershell
pytest
ruff check .
ruff format --check .
mypy src