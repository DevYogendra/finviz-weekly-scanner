"""Read-only, screen-scoped results for the local review workspace."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import asdict

from finviz_scanner.comparison.diff import compare_snapshots
from finviz_scanner.config import Settings
from finviz_scanner.models import ResolvedSymbol
from finviz_scanner.utils import normalize_ticker


class ResultsUnavailableError(ValueError):
    """Stored results cannot safely be displayed or exported."""


def _run_summary(row: sqlite3.Row) -> dict[str, object]:
    return {
        "run_id": str(row["run_id"]),
        "started_at": str(row["started_at"]),
        "finished_at": row["finished_at"],
        "status": str(row["status"]),
        "extracted_count": row["extracted_count"],
    }


def _symbols(
    db: sqlite3.Connection, run: sqlite3.Row, screen_id: str
) -> tuple[ResolvedSymbol, ...]:
    if run["screen_id"] is None:
        rows = db.execute(
            "SELECT * FROM screen_membership WHERE run_id = ? ORDER BY finviz_rank, ticker",
            (run["run_id"],),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM screen_symbol_membership WHERE run_id = ? AND screen_id = ? "
            "ORDER BY finviz_rank, ticker",
            (run["run_id"], screen_id),
        ).fetchall()
    if (
        run["extracted_count"] is None
        or len(rows) != run["extracted_count"]
        or run["displayed_count"] != run["extracted_count"]
    ):
        raise ResultsUnavailableError(
            "Stored result counts are incomplete or inconsistent. Export is unavailable; "
            "retry after the scan finishes or run a new scan."
        )
    symbols: list[ResolvedSymbol] = []
    for row in rows:
        ticker = str(row["ticker"])
        exchange = str(row["exchange"])
        tv_symbol = str(row["tv_symbol"])
        if (
            normalize_ticker(ticker) != ticker
            or exchange not in {"NASDAQ", "NYSE", "AMEX", "BATS"}
            or tv_symbol != f"{exchange}:{ticker}"
        ):
            raise ResultsUnavailableError("Stored symbols are invalid. Export is unavailable.")
        symbols.append(
            ResolvedSymbol(
                ticker=ticker,
                exchange=exchange,
                tv_symbol=tv_symbol,
                company_name=row["company_name"],
                finviz_rank=int(row["finviz_rank"]),
                source_page=int(row["source_page"]),
            )
        )
    return tuple(symbols)


def load_screen_results(settings: Settings, screen_id: str) -> dict[str, object]:
    """Read two successes and their memberships within one SQLite snapshot."""
    screen = next((s for s in settings.finviz.resolved_screens() if s.id == screen_id), None)
    if screen is None:
        raise KeyError("Unknown screen ID.")
    result: dict[str, object] = {
        "screen": {"id": screen.id, "name": screen.name, "enabled": screen.enabled},
        "latest_attempt": None,
        "successful_run": None,
        "baseline": False,
        "current": [],
        "additions": [],
        "removals": [],
        "unchanged": [],
    }
    database = settings.output.root_directory / "scanner.sqlite3"
    if not database.exists():
        return result
    try:
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            columns = {r["name"] for r in db.execute("PRAGMA table_info(runs)")}
            # A pre-multi-screen database has no screen_id column and only legacy membership.
            screen_column = "screen_id" if "screen_id" in columns else "NULL AS screen_id"
            predicate = (
                "COALESCE(screen_id, 'default') = ?" if "screen_id" in columns else "? = 'default'"
            )
            select = f"SELECT *, {screen_column} FROM runs WHERE {predicate}"
            latest = db.execute(
                select + " ORDER BY started_at DESC, run_id DESC LIMIT 1", (screen_id,)
            ).fetchone()
            if latest is not None:
                result["latest_attempt"] = _run_summary(latest)
            runs = db.execute(
                select + " AND status = 'SUCCESS' ORDER BY finished_at DESC, run_id DESC LIMIT 2",
                (screen_id,),
            ).fetchall()
            if not runs:
                return result
            current = _symbols(db, runs[0], screen_id)
            previous = _symbols(db, runs[1], screen_id) if len(runs) == 2 else None
            comparison = compare_snapshots(current, previous)
            result.update(
                successful_run=_run_summary(runs[0]),
                baseline=comparison.is_baseline,
                current=[asdict(s) for s in current],
                additions=[asdict(s) for s in comparison.additions],
                removals=[asdict(s) for s in comparison.removals],
                unchanged=[asdict(s) for s in comparison.unchanged],
            )
    except (sqlite3.Error, OSError, TypeError, ValueError) as exc:
        if isinstance(exc, ResultsUnavailableError):
            raise
        raise ResultsUnavailableError(
            "Results database is unavailable or invalid. Check installation health and retry."
        ) from exc
    return result
