from __future__ import annotations

import sys
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def results_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, object]]:
    import finviz_scanner.webapp as webapp
    from finviz_scanner.storage.sqlite import SQLiteStore
    from finviz_scanner.webapp import DashboardService, ScannerRequestHandler
    from tests.helpers import multi_settings_for
    from tests.test_results import save_run, symbol

    settings = multi_settings_for(tmp_path)
    store = SQLiteStore(tmp_path / "scanner.sqlite3")
    save_run(store, "old", (symbol("AAA"), symbol("CCC", 2)), screen_id="stage-2")
    save_run(store, "new", (symbol("BBB"), symbol("AAA", 2)), screen_id="stage-2", day=2)
    save_run(store, "momentum", (symbol("DDD"),), screen_id="momentum")
    monkeypatch.setattr(webapp, "load_settings", lambda: settings)
    monkeypatch.setattr(
        webapp, "read_schedule_info", lambda: webapp.ScheduleInfo(False, "Not installed")
    )
    handler = type(
        "TestResultsHandler",
        (ScannerRequestHandler,),
        {"service": DashboardService(), "token": "test-token"},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", store
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
