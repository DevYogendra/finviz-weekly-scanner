"""End-to-end scan orchestration."""

from __future__ import annotations

import shutil
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from finviz_scanner.comparison.diff import compare_snapshots
from finviz_scanner.config import Settings
from finviz_scanner.errors import ExchangeResolutionError, ExtractionError, ScannerError
from finviz_scanner.extraction.finviz_dom import extract_pages
from finviz_scanner.models import PageCapture, RunRecord, RunStatus
from finviz_scanner.output.artifacts import write_outputs
from finviz_scanner.storage.lock import ProcessLock
from finviz_scanner.storage.sqlite import SQLiteStore
from finviz_scanner.symbols.resolver import SymbolResolver
from finviz_scanner.utils import ensure_directory, fingerprint_url
from finviz_scanner.validation import validate_extraction


class Collector(Protocol):
    def collect(self, url: str) -> tuple[PageCapture, ...]:
        """Collect all Finviz pages."""


def run_scan(
    settings: Settings,
    collector: Collector,
    resolver: SymbolResolver,
    *,
    run_id: str | None = None,
) -> Path:
    root = ensure_directory(settings.output.root_directory)
    actual_run_id = run_id or str(uuid.uuid4())
    run_dir = root / "snapshots" / actual_run_id
    temp_dir = root / "tmp" / actual_run_id
    lock_path = root / ".scan.lock"
    store = SQLiteStore(root / "scanner.sqlite3")
    screen_url = settings.finviz.resolved_screens()[0].url
    run = RunRecord(
        run_id=actual_run_id,
        source_url_fingerprint=fingerprint_url(screen_url),
    )
    store.upsert_run(run)
    with ProcessLock(lock_path):
        try:
            ensure_directory(temp_dir)
            pages = _collect_with_retries(
                collector,
                screen_url,
                attempts=3,
            )
            extraction = extract_pages(pages)
            validate_extraction(
                extraction,
                require_exact_count=settings.validation.require_exact_count,
            )
            current = resolver.resolve_rows(extraction.rows)
            previous = store.latest_successful_symbols(before_run_id=actual_run_id)
            comparison = compare_snapshots(current, previous)
            write_outputs(
                temp_dir,
                current,
                comparison,
                run_id=actual_run_id,
                displayed_count=extraction.displayed_count,
            )
            if run_dir.exists():
                msg = f"Snapshot already exists and will not be overwritten: {run_dir}"
                raise ScannerError(msg)
            ensure_directory(run_dir.parent)
            shutil.move(str(temp_dir), str(run_dir))
            finished = datetime.now(UTC)
            success = RunRecord(
                run_id=actual_run_id,
                started_at=run.started_at,
                finished_at=finished,
                status=RunStatus.SUCCESS,
                source_url_fingerprint=run.source_url_fingerprint,
                displayed_count=extraction.displayed_count,
                extracted_count=extraction.unique_count,
                page_count=len(extraction.pages),
                extraction_mode=extraction.extraction_mode,
            )
            store.upsert_run(success)
            store.save_membership(actual_run_id, current)
            latest = root / "latest"
            if latest.exists():
                shutil.rmtree(latest)
            shutil.copytree(run_dir, latest)
            return run_dir
        except Exception as exc:
            if isinstance(exc, ExchangeResolutionError):
                _write_exception_report(temp_dir, exc.unresolved)
            failed = RunRecord(
                run_id=actual_run_id,
                started_at=run.started_at,
                finished_at=datetime.now(UTC),
                status=RunStatus.FAILED,
                source_url_fingerprint=run.source_url_fingerprint,
                error_category=getattr(exc, "category", "unexpected"),
                error_summary=str(exc),
            )
            store.upsert_run(failed)
            raise


def _collect_with_retries(
    collector: Collector,
    url: str,
    *,
    attempts: int,
) -> tuple[PageCapture, ...]:
    retryable_terms = (
        "timed out",
        "timeout",
        "network",
        "temporarily",
        "unavailable",
        "page remained unstable or navigating",
        "playwright failed while collecting",
    )
    last_error: ExtractionError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return collector.collect(url)
        except ExtractionError as exc:
            last_error = exc
            if not any(term in str(exc).lower() for term in retryable_terms):
                raise
            if attempt == attempts:
                raise
            time.sleep(2 ** (attempt - 1))
    raise last_error or ExtractionError("Collection failed without an error.")


def _write_exception_report(temp_dir: Path, unresolved: tuple[str, ...]) -> None:
    ensure_directory(temp_dir)
    report = temp_dir / "exchange_exceptions.csv"
    lines = ["ticker,reason", *(f"{ticker},unresolved_exchange" for ticker in unresolved)]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
