"""Multi-screen scan orchestration."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

from finviz_scanner.browser.finviz_browser import ScreenCollection
from finviz_scanner.comparison.diff import compare_snapshots
from finviz_scanner.config import Settings
from finviz_scanner.errors import ConfigurationError, ExchangeResolutionError, ScannerError
from finviz_scanner.extraction.finviz_dom import extract_pages
from finviz_scanner.models import (
    FinvizScreenConfig,
    MultiScreenRunResult,
    PageCapture,
    RunRecord,
    RunStatus,
    ScreenScanResult,
)
from finviz_scanner.output.artifacts import tradingview_line, write_outputs, write_screen_aliases
from finviz_scanner.storage.lock import ProcessLock
from finviz_scanner.storage.sqlite import SQLiteStore
from finviz_scanner.symbols.resolver import SymbolResolver
from finviz_scanner.utils import ensure_directory, fingerprint_url
from finviz_scanner.validation import validate_extraction


class MultiScreenCollector(Protocol):
    def collect_many(
        self,
        screens: list[FinvizScreenConfig],
        *,
        delay_between_screens_ms: int = 1000,
    ) -> list[ScreenCollection]:
        """Collect Finviz pages for multiple screens in one browser session."""


class SingleScreenCollector(Protocol):
    def collect(self, url: str) -> tuple[PageCapture, ...]:
        """Collect Finviz pages for one screen."""


def run_multi_screen_scan(
    settings: Settings,
    collector: MultiScreenCollector | SingleScreenCollector,
    resolver: SymbolResolver,
    *,
    selected_screen_ids: tuple[str, ...] = (),
    include_disabled: bool = False,
    run_id: str | None = None,
    headed: bool = False,
) -> MultiScreenRunResult:
    screens = select_screens(
        settings.finviz.resolved_screens(),
        selected_screen_ids=selected_screen_ids,
        include_disabled=include_disabled,
    )
    root = ensure_directory(settings.output.root_directory)
    actual_run_id = run_id or str(uuid.uuid4())
    started_at = datetime.now(UTC)
    run_dir = root / "snapshots" / actual_run_id
    temp_root = root / "tmp" / actual_run_id
    lock_path = root / ".scan.lock"
    store = SQLiteStore(root / "scanner.sqlite3")
    results: list[ScreenScanResult] = []

    with ProcessLock(lock_path):
        ensure_directory(run_dir)
        ensure_directory(temp_root)
        collections = _collect_screens(settings, collector, screens)
        for collection in collections:
            if collection.error is not None:
                result = _record_failed_screen(
                    store,
                    actual_run_id,
                    collection.screen,
                    started_at,
                    collection.error,
                )
            else:
                result = _publish_successful_screen(
                    settings,
                    store,
                    resolver,
                    run_id=actual_run_id,
                    started_at=started_at,
                    screen=collection.screen,
                    pages=collection.pages,
                    run_dir=run_dir,
                    temp_root=temp_root,
                )
            results.append(result)
            if collection.browser_wide and collection.error is not None:
                attempted = {item.screen_id for item in results}
                for screen in screens:
                    if screen.id not in attempted:
                        results.append(
                            _record_not_attempted_screen(store, actual_run_id, screen, started_at)
                        )
                break
        _write_manifest(
            run_dir,
            run_id=actual_run_id,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            headed=headed,
            results=results,
        )

    completed_at = datetime.now(UTC)
    return MultiScreenRunResult(
        run_id=actual_run_id,
        started_at=started_at,
        completed_at=completed_at,
        status=_overall_status(results),
        screens=results,
    )


def select_screens(
    screens: list[FinvizScreenConfig],
    *,
    selected_screen_ids: tuple[str, ...] = (),
    include_disabled: bool = False,
) -> list[FinvizScreenConfig]:
    if not screens:
        raise ConfigurationError("At least one Finviz screen must be configured.")
    requested = {screen_id.lower() for screen_id in selected_screen_ids}
    known = {screen.id.lower(): screen for screen in screens}
    unknown = requested - set(known)
    if unknown:
        raise ConfigurationError(f"Unknown screen ID: {sorted(unknown)[0]}")
    selected: list[FinvizScreenConfig] = []
    for screen in screens:
        is_requested = not requested or screen.id.lower() in requested
        if not is_requested:
            continue
        if not screen.enabled and not include_disabled:
            if requested:
                raise ConfigurationError(
                    f"Screen '{screen.id}' is disabled. Use --include-disabled to scan it."
                )
            continue
        selected.append(screen)
    if not selected:
        raise ConfigurationError("No enabled Finviz screens are selected.")
    return selected


def _collect_screens(
    settings: Settings,
    collector: MultiScreenCollector | SingleScreenCollector,
    screens: list[FinvizScreenConfig],
) -> list[ScreenCollection]:
    if hasattr(collector, "collect_many"):
        typed_collector = cast(MultiScreenCollector, collector)
        return typed_collector.collect_many(
            screens,
            delay_between_screens_ms=settings.finviz.delay_between_screens_ms,
        )
    collections: list[ScreenCollection] = []
    for screen in screens:
        try:
            pages = collector.collect(screen.url)
        except ScannerError as exc:
            collections.append(ScreenCollection(screen=screen, error=exc))
        else:
            collections.append(ScreenCollection(screen=screen, pages=pages))
    return collections


def _publish_successful_screen(
    settings: Settings,
    store: SQLiteStore,
    resolver: SymbolResolver,
    *,
    run_id: str,
    started_at: datetime,
    screen: FinvizScreenConfig,
    pages: tuple[PageCapture, ...],
    run_dir: Path,
    temp_root: Path,
) -> ScreenScanResult:
    screen_run_id = _screen_run_id(run_id, screen.id)
    temp_dir = temp_root / screen.id
    final_dir = run_dir / screen.id
    try:
        ensure_directory(temp_dir)
        extraction = extract_pages(pages)
        validate_extraction(
            extraction,
            require_exact_count=settings.validation.require_exact_count,
        )
        current = resolver.resolve_rows(extraction.rows)
        previous_run_id = store.latest_successful_run_id_for_screen(
            screen.id,
            before_run_id=screen_run_id,
        )
        previous = store.latest_successful_symbols_for_screen(
            screen.id,
            before_run_id=screen_run_id,
        )
        comparison = compare_snapshots(current, previous)
        write_outputs(
            temp_dir,
            current,
            comparison,
            run_id=screen_run_id,
            displayed_count=extraction.displayed_count,
        )
        write_screen_aliases(
            temp_dir,
            current,
            comparison,
            screen_id=screen.id,
            screen_name=screen.name,
            previous_successful_run_id=previous_run_id,
        )
        if current and not tradingview_line(current):
            raise ScannerError(f"[{screen.id}] TradingView output was empty.")
        if final_dir.exists():
            raise ScannerError(f"Screen snapshot already exists: {final_dir}")
        shutil.move(str(temp_dir), str(final_dir))
        _publish_stable_watchlist(settings, screen, final_dir / "tradingview-watchlist.txt")
        finished = datetime.now(UTC)
        store.upsert_run(
            RunRecord(
                run_id=screen_run_id,
                started_at=started_at,
                finished_at=finished,
                status=RunStatus.SUCCESS,
                source_url_fingerprint=fingerprint_url(screen.url),
                displayed_count=extraction.displayed_count,
                extracted_count=extraction.unique_count,
                page_count=len(extraction.pages),
                extraction_mode=extraction.extraction_mode,
                screen_id=screen.id,
            )
        )
        store.save_screen_membership(screen_run_id, screen.id, current)
        return ScreenScanResult(
            screen_id=screen.id,
            screen_name=screen.name,
            url=screen.url,
            status="success",
            ticker_count=extraction.unique_count,
            resolved_count=len(current),
            rejected_count=0,
            output_directory=final_dir,
        )
    except Exception as exc:
        if isinstance(exc, ExchangeResolutionError):
            _write_exception_report(temp_dir, exc.unresolved)
        return _record_failed_screen(store, run_id, screen, started_at, exc)


def _record_failed_screen(
    store: SQLiteStore,
    run_id: str,
    screen: FinvizScreenConfig,
    started_at: datetime,
    error: BaseException,
) -> ScreenScanResult:
    store.upsert_run(
        RunRecord(
            run_id=_screen_run_id(run_id, screen.id),
            started_at=started_at,
            finished_at=datetime.now(UTC),
            status=RunStatus.FAILED,
            source_url_fingerprint=fingerprint_url(screen.url),
            error_category=getattr(error, "category", "unexpected"),
            error_summary=str(error),
            screen_id=screen.id,
        )
    )
    return ScreenScanResult(
        screen_id=screen.id,
        screen_name=screen.name,
        url=screen.url,
        status="failed",
        ticker_count=0,
        resolved_count=0,
        rejected_count=0,
        output_directory=None,
        error=str(error),
    )


def _record_not_attempted_screen(
    store: SQLiteStore,
    run_id: str,
    screen: FinvizScreenConfig,
    started_at: datetime,
) -> ScreenScanResult:
    error = "Browser session ended before this screen."
    store.upsert_run(
        RunRecord(
            run_id=_screen_run_id(run_id, screen.id),
            started_at=started_at,
            finished_at=datetime.now(UTC),
            status=RunStatus.FAILED,
            source_url_fingerprint=fingerprint_url(screen.url),
            error_category="not_attempted",
            error_summary=error,
            screen_id=screen.id,
        )
    )
    return ScreenScanResult(
        screen_id=screen.id,
        screen_name=screen.name,
        url=screen.url,
        status="not_attempted",
        ticker_count=0,
        resolved_count=0,
        rejected_count=0,
        output_directory=None,
        error=error,
    )


def _publish_stable_watchlist(
    settings: Settings,
    screen: FinvizScreenConfig,
    watchlist_path: Path,
) -> Path:
    watchlists_dir = ensure_directory(settings.output.root_directory / "watchlists")
    filename = settings.finviz.tradingview_filename_for(screen)
    destination = watchlists_dir / filename
    temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(watchlist_path.read_text(encoding="utf-8"), encoding="utf-8")
    os.replace(temp, destination)
    return destination


def _write_manifest(
    run_dir: Path,
    *,
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
    headed: bool,
    results: list[ScreenScanResult],
) -> None:
    manifest = {
        "run_id": run_id,
        "started_at": _iso_utc(started_at),
        "completed_at": _iso_utc(completed_at),
        "mode": "headed" if headed else "headless",
        "status": _overall_status(results),
        "screens": [
            {
                "id": result.screen_id,
                "name": result.screen_name,
                "status": result.status,
                "finviz_total": result.ticker_count if result.status == "success" else None,
                "extracted_count": result.ticker_count,
                "published_count": result.resolved_count,
                "output": f"{result.screen_id}/tradingview-watchlist.txt"
                if result.output_directory
                else None,
                "error": result.error,
            }
            for result in results
        ],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _overall_status(results: list[ScreenScanResult]) -> str:
    successes = sum(1 for result in results if result.status == "success")
    failures = sum(1 for result in results if result.status != "success")
    if successes and failures:
        return "partial_success"
    if successes:
        return "success"
    return "failed"


def _screen_run_id(run_id: str, screen_id: str) -> str:
    return f"{run_id}:{screen_id}"


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _write_exception_report(temp_dir: Path, unresolved: tuple[str, ...]) -> None:
    ensure_directory(temp_dir)
    report = temp_dir / "exchange_exceptions.csv"
    lines = ["ticker,reason", *(f"{ticker},unresolved_exchange" for ticker in unresolved)]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
