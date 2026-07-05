from __future__ import annotations

import json
from pathlib import Path

import pytest

from finviz_scanner.browser.finviz_browser import ScreenCollection
from finviz_scanner.config import FinvizConfig, OutputConfig, ScreenConfig, Settings
from finviz_scanner.errors import ExtractionError
from finviz_scanner.models import FinvizScreenConfig, PageCapture
from finviz_scanner.storage.sqlite import SQLiteStore
from finviz_scanner.symbols.resolver import SymbolResolver
from finviz_scanner.workflow.multi_screen_runner import run_multi_screen_scan, select_screens
from tests.helpers import multi_settings_for, pages_for


class MultiCollector:
    def __init__(self, mapping: dict[str, tuple[PageCapture, ...] | BaseException]) -> None:
        self.mapping = mapping
        self.calls: list[str] = []
        self.delay: int | None = None

    def collect_many(
        self,
        screens: list[FinvizScreenConfig],
        *,
        delay_between_screens_ms: int = 1000,
    ) -> list[ScreenCollection]:
        self.delay = delay_between_screens_ms
        results: list[ScreenCollection] = []
        for screen in screens:
            self.calls.append(screen.id)
            value = self.mapping[screen.id]
            if isinstance(value, BaseException):
                results.append(ScreenCollection(screen=screen, error=value))
            else:
                results.append(ScreenCollection(screen=screen, pages=value))
        return results


class BrowserWideFailureCollector:
    def collect_many(
        self,
        screens: list[FinvizScreenConfig],
        *,
        delay_between_screens_ms: int = 1000,
    ) -> list[ScreenCollection]:
        _ = delay_between_screens_ms
        return [
            ScreenCollection(
                screen=screens[0],
                error=ExtractionError("Chromium crashed"),
                browser_wide=True,
            )
        ]


def resolver() -> SymbolResolver:
    return SymbolResolver.from_csv(Path("tests/fixtures/symbol_master.csv"))


def test_multi_screen_scan_publishes_independent_watchlists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = multi_settings_for(tmp_path)
    collector = MultiCollector(
        {
            "stage-2": pages_for(("AAA", "BBB"), total=2),
            "momentum": pages_for(("CCC", "DDD"), total=2),
        }
    )
    result = run_multi_screen_scan(settings, collector, resolver(), run_id="run1")
    assert result.status == "success"
    assert collector.calls == ["stage-2", "momentum"]
    assert (tmp_path / "watchlists" / "stage-2.txt").read_text(encoding="utf-8") == (
        "NASDAQ:AAA,NASDAQ:BBB"
    )
    assert (tmp_path / "watchlists" / "momentum.txt").read_text(encoding="utf-8") == (
        "NYSE:CCC,NYSE:DDD"
    )
    assert (tmp_path / "snapshots" / "run1" / "stage-2" / "tradingview-watchlist.txt").exists()
    assert (tmp_path / "snapshots" / "run1" / "momentum" / "metadata.json").exists()


def test_failed_screen_retains_previous_stable_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = multi_settings_for(tmp_path)
    run_multi_screen_scan(
        settings,
        MultiCollector(
            {
                "stage-2": pages_for(("AAA", "BBB"), total=2),
                "momentum": pages_for(("CCC", "DDD"), total=2),
            }
        ),
        resolver(),
        run_id="run1",
    )
    result = run_multi_screen_scan(
        settings,
        MultiCollector(
            {
                "stage-2": pages_for(("EEE", "FFF"), total=2),
                "momentum": ExtractionError("Finviz displayed a CAPTCHA"),
            }
        ),
        resolver(),
        run_id="run2",
    )
    assert result.status == "partial_success"
    assert (tmp_path / "watchlists" / "stage-2.txt").read_text(encoding="utf-8") == (
        "NASDAQ:EEE,NYSE:FFF"
    )
    assert (tmp_path / "watchlists" / "momentum.txt").read_text(encoding="utf-8") == (
        "NYSE:CCC,NYSE:DDD"
    )


def test_history_comparison_is_screen_scoped(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = multi_settings_for(tmp_path)
    run_multi_screen_scan(
        settings,
        MultiCollector(
            {
                "stage-2": pages_for(("AAA", "BBB"), total=2),
                "momentum": pages_for(("AAA", "CCC"), total=2),
            }
        ),
        resolver(),
        run_id="run1",
    )
    run_multi_screen_scan(
        settings,
        MultiCollector(
            {
                "stage-2": pages_for(("AAA", "DDD"), total=2),
                "momentum": pages_for(("AAA", "EEE"), total=2),
            }
        ),
        resolver(),
        run_id="run2",
    )
    stage_metadata = json.loads(
        (tmp_path / "snapshots" / "run2" / "stage-2" / "metadata.json").read_text(encoding="utf-8")
    )
    momentum_metadata = json.loads(
        (tmp_path / "snapshots" / "run2" / "momentum" / "metadata.json").read_text(encoding="utf-8")
    )
    assert stage_metadata["previous_successful_run_id"] == "run1:stage-2"
    assert momentum_metadata["previous_successful_run_id"] == "run1:momentum"
    assert stage_metadata["additions_count"] == 1
    assert momentum_metadata["additions_count"] == 1


def test_manifest_records_success_and_failure(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = multi_settings_for(tmp_path)
    run_multi_screen_scan(
        settings,
        MultiCollector(
            {
                "stage-2": pages_for(("AAA", "BBB"), total=2),
                "momentum": ExtractionError("bad page"),
            }
        ),
        resolver(),
        run_id="run1",
        headed=True,
    )
    manifest = json.loads((tmp_path / "snapshots" / "run1" / "manifest.json").read_text())
    assert manifest["mode"] == "headed"
    assert manifest["status"] == "partial_success"
    assert manifest["screens"][0]["output"] == "stage-2/tradingview-watchlist.txt"
    assert manifest["screens"][1]["error"] == "bad page"
    assert "html" not in json.dumps(manifest).lower()
    assert "cookie" not in json.dumps(manifest).lower()


def test_browser_wide_failure_marks_remaining_not_attempted(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = multi_settings_for(tmp_path)
    result = run_multi_screen_scan(
        settings,
        BrowserWideFailureCollector(),
        resolver(),
        run_id="run1",
    )
    assert [item.status for item in result.screens] == ["failed", "not_attempted"]


def test_select_screens_rejects_unknown_and_disabled(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(
        finviz=FinvizConfig(
            screens=[
                ScreenConfig(id="stage-2", name="Stage 2", url="https://finviz.com/screener?v=111"),
                ScreenConfig(
                    id="momentum",
                    name="Momentum",
                    url="https://finviz.com/screener?v=111",
                    enabled=False,
                ),
            ]
        ),
        output=OutputConfig(root_directory=tmp_path),
    )
    with pytest.raises(Exception, match="Unknown screen ID"):
        select_screens(settings.finviz.resolved_screens(), selected_screen_ids=("missing",))
    with pytest.raises(Exception, match="disabled"):
        select_screens(settings.finviz.resolved_screens(), selected_screen_ids=("momentum",))
    assert [item.id for item in select_screens(settings.finviz.resolved_screens())] == ["stage-2"]


def test_sqlite_screen_history_does_not_mix_tickers(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = multi_settings_for(tmp_path)
    run_multi_screen_scan(
        settings,
        MultiCollector(
            {
                "stage-2": pages_for(("AAA", "BBB"), total=2),
                "momentum": pages_for(("CCC", "DDD"), total=2),
            }
        ),
        resolver(),
        run_id="run1",
    )
    store = SQLiteStore(tmp_path / "scanner.sqlite3")
    stage_symbols = store.latest_successful_symbols_for_screen("stage-2") or ()
    momentum_symbols = store.latest_successful_symbols_for_screen("momentum") or ()
    assert [item.ticker for item in stage_symbols] == [
        "AAA",
        "BBB",
    ]
    assert [item.ticker for item in momentum_symbols] == [
        "CCC",
        "DDD",
    ]


def test_selected_screens_process_in_configuration_order(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = multi_settings_for(tmp_path)
    collector = MultiCollector(
        {
            "stage-2": pages_for(("AAA",), total=1),
            "momentum": pages_for(("CCC",), total=1),
        }
    )
    run_multi_screen_scan(
        settings,
        collector,
        resolver(),
        selected_screen_ids=("momentum", "stage-2"),
        run_id="run1",
    )
    assert collector.calls == ["stage-2", "momentum"]
