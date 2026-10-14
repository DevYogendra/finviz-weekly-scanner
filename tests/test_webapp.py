from __future__ import annotations

from datetime import UTC, datetime
from http.server import ThreadingHTTPServer

import pytest

from finviz_scanner.models import RunRecord, RunStatus
from finviz_scanner.storage.sqlite import SQLiteStore
from finviz_scanner.webapp import ASSET_DIRECTORY, load_run_summaries, parse_schedule_json
from tests.helpers import settings_for


def test_load_run_summaries_returns_latest_outcomes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = settings_for(tmp_path)
    store = SQLiteStore(tmp_path / "scanner.sqlite3")
    store.upsert_run(
        RunRecord(
            run_id="older:default",
            screen_id="default",
            started_at=datetime(2026, 7, 5, 14, 0, tzinfo=UTC),
            finished_at=datetime(2026, 7, 5, 14, 1, tzinfo=UTC),
            status=RunStatus.SUCCESS,
            displayed_count=44,
            extracted_count=44,
        )
    )
    store.upsert_run(
        RunRecord(
            run_id="newer:default",
            screen_id="default",
            started_at=datetime(2026, 7, 12, 14, 0, tzinfo=UTC),
            finished_at=datetime(2026, 7, 12, 14, 1, tzinfo=UTC),
            status=RunStatus.FAILED,
            error_summary="Finviz displayed a CAPTCHA.",
        )
    )

    summaries = load_run_summaries(settings)

    assert [item["status"] for item in summaries] == ["FAILED", "SUCCESS"]
    assert summaries[0]["error_summary"] == "Finviz displayed a CAPTCHA."
    assert summaries[1]["extracted_count"] == 44


def test_parse_schedule_json() -> None:
    info = parse_schedule_json(
        '{"State":"Ready","LastRunTime":"2026-07-05T08:00:00-06:00",'
        '"NextRunTime":"2026-07-12T08:00:00-06:00","LastTaskResult":1}'
    )
    assert info.installed is True
    assert info.state == "Ready"
    assert info.last_result == 1


def test_web_assets_are_packaged_and_local() -> None:
    html = (ASSET_DIRECTORY / "index.html").read_text(encoding="utf-8")
    assert "__SCANNER_TOKEN__" in html
    assert "https://" not in html
    assert (ASSET_DIRECTORY / "app.css").is_file()
    assert (ASSET_DIRECTORY / "app.js").is_file()


def test_launcher_opens_current_dashboard_when_port_is_occupied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import finviz_scanner.webapp as webapp

    opened: list[str] = []
    served: list[int] = []
    monkeypatch.setattr(webapp.webbrowser, "open", lambda url: opened.append(url))

    def serve(server: ThreadingHTTPServer) -> None:
        served.append(server.server_port)

    class ImmediateTimer:
        def __init__(self, delay: float, callback: object) -> None:
            self.callback = callback

        def start(self) -> None:
            assert callable(self.callback)
            self.callback()

    monkeypatch.setattr(webapp.threading, "Timer", ImmediateTimer)
    monkeypatch.setattr(ThreadingHTTPServer, "serve_forever", serve)
    with ThreadingHTTPServer(("127.0.0.1", 0), webapp.ScannerRequestHandler) as occupied:
        webapp.run_web_app(occupied.server_port)
        assert served[0] != occupied.server_port
        assert opened == [f"http://127.0.0.1:{served[0]}/"]
