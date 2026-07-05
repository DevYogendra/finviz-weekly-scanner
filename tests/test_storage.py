from __future__ import annotations

from datetime import UTC, datetime

from finviz_scanner.models import ResolvedSymbol, RunRecord, RunStatus
from finviz_scanner.storage.sqlite import SQLiteStore


def test_failed_run_does_not_replace_previous_successful_snapshot(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = SQLiteStore(tmp_path / "scanner.sqlite3")
    success = RunRecord("success", finished_at=datetime.now(UTC), status=RunStatus.SUCCESS)
    failed = RunRecord("failed", finished_at=datetime.now(UTC), status=RunStatus.FAILED)
    store.upsert_run(success)
    store.save_membership(
        "success",
        (ResolvedSymbol("AAA", "NASDAQ", "NASDAQ:AAA", "AAA", 1, 1),),
    )
    store.upsert_run(failed)
    latest = store.latest_successful_symbols()
    assert latest is not None
    assert [item.ticker for item in latest] == ["AAA"]
