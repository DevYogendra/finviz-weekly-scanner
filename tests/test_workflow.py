from __future__ import annotations

from pathlib import Path

import pytest

from finviz_scanner.errors import ExchangeResolutionError, ExtractionError, LockError
from finviz_scanner.models import PageCapture
from finviz_scanner.storage.lock import ProcessLock
from finviz_scanner.symbols.resolver import SymbolResolver
from finviz_scanner.workflow.runner import run_scan
from tests.helpers import TICKERS_44, pages_for, settings_for


class FakeCollector:
    def __init__(self, pages: tuple[PageCapture, ...]) -> None:
        self._pages = pages

    def collect(self, _url: str) -> tuple[PageCapture, ...]:
        return self._pages


class FlakyNavigationCollector:
    def __init__(self, pages: tuple[PageCapture, ...]) -> None:
        self._pages = pages
        self.calls = 0

    def collect(self, _url: str) -> tuple[PageCapture, ...]:
        self.calls += 1
        if self.calls == 1:
            raise ExtractionError("page remained unstable or navigating")
        return self._pages


def resolver() -> SymbolResolver:
    return SymbolResolver.from_csv(Path("tests/fixtures/symbol_master.csv"))


def test_workflow_publishes_successful_baseline(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = settings_for(tmp_path)
    run_dir = run_scan(settings, FakeCollector(pages_for(TICKERS_44)), resolver(), run_id="run1")
    assert (run_dir / "current.csv").exists()
    assert "# Baseline run" in (run_dir / "tradingview-additions.txt").read_text(encoding="utf-8")
    assert (tmp_path / "latest" / "tradingview-current.txt").exists()


def test_workflow_second_same_run_has_zero_changes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = settings_for(tmp_path)
    run_scan(settings, FakeCollector(pages_for(TICKERS_44)), resolver(), run_id="run1")
    run_dir = run_scan(settings, FakeCollector(pages_for(TICKERS_44)), resolver(), run_id="run2")
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "New additions: 0" in report
    assert "Fell off: 0" in report


def test_unresolved_exchange_prevents_publication(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = settings_for(tmp_path)
    pages = pages_for(("AAA", "MISSING"), total=2)
    with pytest.raises(ExchangeResolutionError):
        run_scan(settings, FakeCollector(pages), resolver(), run_id="bad")
    assert not (tmp_path / "latest").exists()
    exception_report = tmp_path / "tmp" / "bad" / "exchange_exceptions.csv"
    assert "MISSING,unresolved_exchange" in exception_report.read_text(encoding="utf-8")


def test_process_lock_prevents_two_concurrent_runs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    lock_path = tmp_path / ".scan.lock"
    with ProcessLock(lock_path), pytest.raises(LockError):
        ProcessLock(lock_path).acquire()


def test_workflow_retries_transient_navigation_extraction_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = settings_for(tmp_path)
    collector = FlakyNavigationCollector(pages_for(TICKERS_44))
    run_dir = run_scan(settings, collector, resolver(), run_id="retry-run")
    assert (run_dir / "current.csv").exists()
    assert collector.calls == 2
