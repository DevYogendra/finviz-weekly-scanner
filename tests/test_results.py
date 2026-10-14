from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from finviz_scanner.models import ResolvedSymbol, RunRecord, RunStatus
from finviz_scanner.results import ResultsUnavailableError, load_screen_results
from finviz_scanner.storage.sqlite import SQLiteStore
from finviz_scanner.webapp import DashboardService
from tests.helpers import multi_settings_for, settings_for


def symbol(ticker: str, rank: int = 1) -> ResolvedSymbol:
    return ResolvedSymbol(ticker, "NASDAQ", f"NASDAQ:{ticker}", f"{ticker} Corp", rank, 1)


def save_run(
    store: SQLiteStore,
    run_id: str,
    symbols: tuple[ResolvedSymbol, ...],
    *,
    screen_id: str | None = "default",
    day: int = 1,
    status: RunStatus = RunStatus.SUCCESS,
    count: int | None = None,
) -> None:
    time = datetime(2026, 7, 1, tzinfo=UTC) + timedelta(days=day)
    store.upsert_run(
        RunRecord(
            run_id=run_id,
            screen_id=screen_id,
            started_at=time,
            finished_at=time + timedelta(minutes=1),
            status=status,
            extracted_count=len(symbols) if count is None else count,
            displayed_count=len(symbols) if count is None else count,
        )
    )
    if screen_id is None:
        store.save_membership(run_id, symbols)
    else:
        store.save_screen_membership(run_id, screen_id, symbols)


def test_baseline_and_legacy_records_are_read_only(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "scanner.sqlite3")
    save_run(store, "legacy", (symbol("BBB", 1), symbol("AAA", 2)), screen_id=None)
    before = store.db_path.read_bytes()
    result = load_screen_results(settings_for(tmp_path), "default")
    assert result["baseline"] is True
    assert result["additions"] == result["unchanged"] == result["removals"] == []
    assert [item["ticker"] for item in result["current"]] == ["BBB", "AAA"]  # type: ignore[union-attr]
    assert store.db_path.read_bytes() == before


def test_changes_are_screen_scoped_and_ignore_failed_runs(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "scanner.sqlite3")
    save_run(store, "older", (symbol("AAA"), symbol("CCC", 2)), screen_id="stage-2")
    save_run(store, "current", (symbol("BBB"), symbol("AAA", 2)), screen_id="stage-2", day=2)
    save_run(store, "other", (symbol("DDD"),), screen_id="momentum", day=3)
    for day in range(4, 50):
        save_run(store, f"failed-{day}", (), screen_id="stage-2", day=day, status=RunStatus.FAILED)
    result = load_screen_results(multi_settings_for(tmp_path), "stage-2")
    assert result["latest_attempt"]["status"] == "FAILED"  # type: ignore[index]
    assert result["successful_run"]["run_id"] == "current"  # type: ignore[index]
    assert [s["ticker"] for s in result["additions"]] == ["BBB"]  # type: ignore[union-attr]
    assert [s["ticker"] for s in result["removals"]] == ["CCC"]  # type: ignore[union-attr]
    assert [s["ticker"] for s in result["unchanged"]] == ["AAA"]  # type: ignore[union-attr]
    assert result["baseline"] is False


@pytest.mark.parametrize("broken_run", ["current", "previous"])
def test_incomplete_current_or_previous_membership_blocks_export(
    tmp_path: Path, broken_run: str
) -> None:
    store = SQLiteStore(tmp_path / "scanner.sqlite3")
    save_run(store, "previous", (symbol("AAA"),), count=2 if broken_run == "previous" else 1)
    save_run(store, "current", (symbol("BBB"),), day=2, count=2 if broken_run == "current" else 1)
    with pytest.raises(ResultsUnavailableError, match="counts"):
        load_screen_results(settings_for(tmp_path), "default")


def test_mismatched_displayed_count_and_invalid_symbols_block_export(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "scanner.sqlite3")
    save_run(store, "current", (symbol("AAA"),))
    with closing(sqlite3.connect(store.db_path)) as db:
        db.execute("UPDATE runs SET displayed_count = 2")
        db.commit()
    with pytest.raises(ResultsUnavailableError, match="counts"):
        load_screen_results(settings_for(tmp_path), "default")
    with closing(sqlite3.connect(store.db_path)) as db:
        db.execute("UPDATE runs SET displayed_count = 1")
        db.execute("UPDATE screen_symbol_membership SET tv_symbol = 'UNKNOWN:AAA'")
        db.commit()
    with pytest.raises(ResultsUnavailableError, match="symbols"):
        load_screen_results(settings_for(tmp_path), "default")


def test_missing_results_do_not_create_database(tmp_path: Path) -> None:
    result = load_screen_results(settings_for(tmp_path), "default")
    assert result["successful_run"] is None
    assert result["current"] == []
    assert not (tmp_path / "scanner.sqlite3").exists()
    with pytest.raises(KeyError):
        load_screen_results(settings_for(tmp_path), "../../secret")


def test_failed_only_results(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "scanner.sqlite3")
    save_run(store, "failed", (), status=RunStatus.FAILED)
    result = load_screen_results(settings_for(tmp_path), "default")
    assert result["successful_run"] is None
    assert result["latest_attempt"]["status"] == "FAILED"  # type: ignore[index]


def test_unavailable_database(tmp_path: Path) -> None:
    (tmp_path / "scanner.sqlite3").write_text("invalid database", encoding="utf-8")
    with pytest.raises(ResultsUnavailableError, match="unavailable"):
        load_screen_results(settings_for(tmp_path), "default")


def test_database_before_screen_migration_is_supported_without_migration(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "scanner.sqlite3")
    save_run(store, "legacy", (symbol("AAA"),), screen_id=None)
    with closing(sqlite3.connect(store.db_path)) as db:
        db.execute("ALTER TABLE runs DROP COLUMN screen_id")
        db.execute("DROP TABLE screen_symbol_membership")
        db.commit()
    before = store.db_path.read_bytes()
    result = load_screen_results(settings_for(tmp_path), "default")
    assert result["successful_run"]["run_id"] == "legacy"  # type: ignore[index]
    assert store.db_path.read_bytes() == before


def test_results_http_contract(results_server: tuple[str, SQLiteStore]) -> None:
    url, _ = results_server
    with urlopen(url + "/api/results?screen_id=stage-2") as response:
        payload = json.load(response)
        assert payload["screen"]["id"] == "stage-2"
        assert response.headers["Cache-Control"] == "no-store"
        assert "source_url" not in json.dumps(payload)
    for query, code in [
        ("", 400),
        ("?screen_id=stage-2&screen_id=momentum", 400),
        ("?screen_id=unknown", 404),
    ]:
        with pytest.raises(HTTPError) as error:
            urlopen(url + "/api/results" + query)
        assert error.value.code == code


def test_results_service_configuration_and_integrity_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import finviz_scanner.webapp as webapp

    def bad_config() -> None:
        raise ValueError("sensitive URL")

    monkeypatch.setattr(webapp, "load_settings", bad_config)
    status, payload = DashboardService.results("default")
    assert status == HTTPStatus.SERVICE_UNAVAILABLE
    assert "sensitive" not in str(payload)
    monkeypatch.setattr(webapp, "load_settings", lambda: settings_for(tmp_path))
    (tmp_path / "scanner.sqlite3").write_text("broken", encoding="utf-8")
    status, payload = DashboardService.results("default")
    assert status == HTTPStatus.SERVICE_UNAVAILABLE
    assert "unavailable" in str(payload)
