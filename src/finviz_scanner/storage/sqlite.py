"""SQLite run history persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from finviz_scanner.models import ResolvedSymbol, RunRecord, RunStatus
from finviz_scanner.utils import ensure_directory


class SQLiteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        ensure_directory(db_path.parent)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    scheduled_for TEXT,
                    status TEXT NOT NULL,
                    source_url_fingerprint TEXT,
                    displayed_count INTEGER,
                    extracted_count INTEGER,
                    page_count INTEGER,
                    extraction_mode TEXT,
                    software_version TEXT,
                    error_category TEXT,
                    error_summary TEXT
                )
                """
            )
            columns = {row["name"] for row in db.execute("PRAGMA table_info(runs)").fetchall()}
            if "screen_id" not in columns:
                db.execute("ALTER TABLE runs ADD COLUMN screen_id TEXT")
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS screen_membership (
                    run_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    tv_symbol TEXT NOT NULL,
                    company_name TEXT,
                    finviz_rank INTEGER NOT NULL,
                    source_page INTEGER NOT NULL,
                    first_seen TEXT,
                    last_seen TEXT,
                    consecutive_weeks INTEGER,
                    reentry INTEGER,
                    PRIMARY KEY (run_id, ticker)
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS screen_symbol_membership (
                    run_id TEXT NOT NULL,
                    screen_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    tv_symbol TEXT NOT NULL,
                    company_name TEXT,
                    finviz_rank INTEGER NOT NULL,
                    source_page INTEGER NOT NULL,
                    first_seen TEXT,
                    last_seen TEXT,
                    consecutive_weeks INTEGER,
                    reentry INTEGER,
                    PRIMARY KEY (run_id, screen_id, ticker)
                )
                """
            )

    def upsert_run(self, run: RunRecord) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO runs (
                    run_id,
                    started_at,
                    finished_at,
                    scheduled_for,
                    status,
                    source_url_fingerprint,
                    displayed_count,
                    extracted_count,
                    page_count,
                    extraction_mode,
                    software_version,
                    error_category,
                    error_summary,
                    screen_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    finished_at=excluded.finished_at,
                    status=excluded.status,
                    displayed_count=excluded.displayed_count,
                    extracted_count=excluded.extracted_count,
                    page_count=excluded.page_count,
                    error_category=excluded.error_category,
                    error_summary=excluded.error_summary,
                    screen_id=excluded.screen_id
                """,
                (
                    run.run_id,
                    run.started_at.isoformat(),
                    run.finished_at.isoformat() if run.finished_at else None,
                    run.scheduled_for.isoformat() if run.scheduled_for else None,
                    run.status.value,
                    run.source_url_fingerprint,
                    run.displayed_count,
                    run.extracted_count,
                    run.page_count,
                    run.extraction_mode.value,
                    run.software_version,
                    run.error_category,
                    run.error_summary,
                    getattr(run, "screen_id", None),
                ),
            )

    def save_membership(self, run_id: str, symbols: tuple[ResolvedSymbol, ...]) -> None:
        with self._connect() as db:
            db.executemany(
                """
                INSERT INTO screen_membership VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        item.ticker,
                        item.exchange,
                        item.tv_symbol,
                        item.company_name,
                        item.finviz_rank,
                        item.source_page,
                        item.first_seen,
                        item.last_seen,
                        item.weeks_on_list,
                        1 if item.reentry else 0,
                    )
                    for item in symbols
                ],
            )

    def latest_successful_symbols(
        self,
        *,
        before_run_id: str | None = None,
    ) -> tuple[ResolvedSymbol, ...] | None:
        with self._connect() as db:
            params: tuple[str, ...] = (RunStatus.SUCCESS.value,)
            query = "SELECT run_id FROM runs WHERE status = ?"
            if before_run_id is not None:
                query += " AND run_id != ?"
                params = (RunStatus.SUCCESS.value, before_run_id)
            query += " ORDER BY finished_at DESC LIMIT 1"
            run = db.execute(query, params).fetchone()
            if run is None:
                return None
            return self.symbols_for_run(str(run["run_id"]))

    def save_screen_membership(
        self,
        run_id: str,
        screen_id: str,
        symbols: tuple[ResolvedSymbol, ...],
    ) -> None:
        with self._connect() as db:
            db.executemany(
                """
                INSERT INTO screen_symbol_membership VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        screen_id,
                        item.ticker,
                        item.exchange,
                        item.tv_symbol,
                        item.company_name,
                        item.finviz_rank,
                        item.source_page,
                        item.first_seen,
                        item.last_seen,
                        item.weeks_on_list,
                        1 if item.reentry else 0,
                    )
                    for item in symbols
                ],
            )

    def latest_successful_symbols_for_screen(
        self,
        screen_id: str,
        *,
        before_run_id: str | None = None,
    ) -> tuple[ResolvedSymbol, ...] | None:
        run_id = self.latest_successful_run_id_for_screen(screen_id, before_run_id=before_run_id)
        if run_id is None:
            return None
        return self.symbols_for_screen_run(run_id, screen_id)

    def latest_successful_run_id_for_screen(
        self,
        screen_id: str,
        *,
        before_run_id: str | None = None,
    ) -> str | None:
        with self._connect() as db:
            params: list[str] = [RunStatus.SUCCESS.value, screen_id]
            query = "SELECT run_id FROM runs WHERE status = ? AND screen_id = ?"
            if before_run_id is not None:
                query += " AND run_id != ?"
                params.append(before_run_id)
            query += " ORDER BY finished_at DESC LIMIT 1"
            run = db.execute(query, tuple(params)).fetchone()
            if run is None:
                return None
            return str(run["run_id"])

    def symbols_for_screen_run(
        self,
        run_id: str,
        screen_id: str,
    ) -> tuple[ResolvedSymbol, ...]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT * FROM screen_symbol_membership
                WHERE run_id = ? AND screen_id = ?
                ORDER BY finviz_rank
                """,
                (run_id, screen_id),
            ).fetchall()
        return tuple(
            ResolvedSymbol(
                ticker=str(row["ticker"]),
                exchange=str(row["exchange"]),
                tv_symbol=str(row["tv_symbol"]),
                company_name=str(row["company_name"]) if row["company_name"] else None,
                finviz_rank=int(row["finviz_rank"]),
                source_page=int(row["source_page"]),
                first_seen=str(row["first_seen"]) if row["first_seen"] else None,
                last_seen=str(row["last_seen"]) if row["last_seen"] else None,
                weeks_on_list=int(row["consecutive_weeks"] or 1),
                reentry=bool(row["reentry"]),
            )
            for row in rows
        )

    def symbols_for_run(self, run_id: str) -> tuple[ResolvedSymbol, ...]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT * FROM screen_membership WHERE run_id = ? ORDER BY finviz_rank
                """,
                (run_id,),
            ).fetchall()
        return tuple(
            ResolvedSymbol(
                ticker=str(row["ticker"]),
                exchange=str(row["exchange"]),
                tv_symbol=str(row["tv_symbol"]),
                company_name=str(row["company_name"]) if row["company_name"] else None,
                finviz_rank=int(row["finviz_rank"]),
                source_page=int(row["source_page"]),
                first_seen=str(row["first_seen"]) if row["first_seen"] else None,
                last_seen=str(row["last_seen"]) if row["last_seen"] else None,
                weeks_on_list=int(row["consecutive_weeks"] or 1),
                reentry=bool(row["reentry"]),
            )
            for row in rows
        )

    def recent_runs(self, limit: int = 10) -> list[sqlite3.Row]:
        with self._connect() as db:
            return list(
                db.execute(
                    "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            )
