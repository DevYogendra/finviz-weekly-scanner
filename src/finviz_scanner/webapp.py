"""Local-only web control panel for scanner operations and outcomes."""

from __future__ import annotations

import errno
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import webbrowser
from collections import deque
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from finviz_scanner.config import Settings, load_settings
from finviz_scanner.preset_summary import summarize_preset
from finviz_scanner.results import ResultsUnavailableError, load_screen_results
from finviz_scanner.scheduler import TASK_NAME
from finviz_scanner.storage.sqlite import SQLiteStore

ASSET_DIRECTORY = Path(__file__).with_name("web")


class ScannerHTTPServer(ThreadingHTTPServer):
    """Keep one dashboard per port, including on Windows."""

    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


@dataclass(frozen=True, slots=True)
class ScheduleInfo:
    installed: bool
    state: str
    last_run_time: str | None = None
    next_run_time: str | None = None
    last_result: int | None = None
    error: str | None = None


def load_run_summaries(settings: Settings, limit: int = 40) -> list[dict[str, object]]:
    """Return display-safe run history without source URLs or secrets."""
    database = settings.output.root_directory / "scanner.sqlite3"
    if not database.exists():
        return []
    rows = SQLiteStore(database).recent_runs(limit)
    return [
        {
            "started_at": str(row["started_at"]),
            "status": str(row["status"]),
            "screen_id": str(row["screen_id"] or "default"),
            "displayed_count": _optional_int(row["displayed_count"]),
            "extracted_count": _optional_int(row["extracted_count"]),
            "error_summary": str(row["error_summary"]) if row["error_summary"] else None,
        }
        for row in rows
    ]


def parse_schedule_json(payload: str) -> ScheduleInfo:
    raw: dict[str, Any] = json.loads(payload)
    return ScheduleInfo(
        installed=True,
        state=str(raw.get("State", "Unknown")),
        last_run_time=_optional_text(raw.get("LastRunTime")),
        next_run_time=_optional_text(raw.get("NextRunTime")),
        last_result=_optional_int(raw.get("LastTaskResult")),
    )


def read_schedule_info() -> ScheduleInfo:
    script = (
        f"$task=Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction Stop;"
        f"$info=Get-ScheduledTaskInfo -TaskName '{TASK_NAME}' -ErrorAction Stop;"
        "$value=[pscustomobject]@{State=[string]$task.State;"
        "LastRunTime=$info.LastRunTime.ToString('o');"
        "NextRunTime=$info.NextRunTime.ToString('o');"
        "LastTaskResult=[int]$info.LastTaskResult};"
        "$value | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_no_window_flag(),
        )
    except OSError as exc:
        return ScheduleInfo(False, "Unavailable", error=str(exc))
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return ScheduleInfo(False, "Not installed", error=detail or None)
    try:
        return parse_schedule_json(result.stdout.strip())
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return ScheduleInfo(False, "Unreadable", error=str(exc))


class OperationManager:
    """Run one CLI operation at a time and retain a bounded live event stream."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._label: str | None = None
        self._started_at: str | None = None
        self._events: deque[dict[str, object]] = deque(maxlen=500)
        self._sequence = 0

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            running = self._process is not None and self._process.poll() is None
            return {
                "running": running,
                "label": self._label,
                "started_at": self._started_at,
                "events": list(self._events),
            }

    def start(self, label: str, arguments: list[str]) -> tuple[bool, str]:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return False, "Another operation is already running."
            command = [sys.executable, "-m", "finviz_scanner.cli", *arguments]
            try:
                process = subprocess.Popen(
                    command,
                    cwd=_project_root(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=_no_window_flag(),
                )
            except OSError as exc:
                return False, str(exc)
            self._process = process
            self._label = label
            self._started_at = _now_iso()
            self._append_locked("system", f"{label} started")
        threading.Thread(target=self._consume, args=(process, label), daemon=True).start()
        return True, f"{label} started."

    def cancel(self) -> tuple[bool, str]:
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                return False, "No operation is running."
            self._process.terminate()
            self._append_locked("system", "Cancellation requested")
            return True, "Cancellation requested."

    def _consume(self, process: subprocess.Popen[str], label: str) -> None:
        if process.stdout is not None:
            for line in process.stdout:
                with self._lock:
                    self._append_locked("output", line.rstrip())
        return_code = process.wait()
        with self._lock:
            outcome = "completed" if return_code == 0 else f"failed with exit code {return_code}"
            self._append_locked("system", f"{label} {outcome}")
            if self._process is process:
                self._process = None
                self._label = None
                self._started_at = None

    def _append_locked(self, kind: str, message: str) -> None:
        self._sequence += 1
        self._events.append(
            {"sequence": self._sequence, "kind": kind, "message": message, "at": _now_iso()}
        )


class DashboardService:
    def __init__(self) -> None:
        self.operations = OperationManager()

    @staticmethod
    def results(screen_id: str) -> tuple[HTTPStatus, dict[str, object]]:
        try:
            settings = load_settings()
        except Exception:  # Configuration boundary; do not expose URLs or secrets.
            return HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Configuration is unavailable."}
        try:
            return HTTPStatus.OK, load_screen_results(settings, screen_id)
        except KeyError:
            return HTTPStatus.NOT_FOUND, {"error": "Unknown screen ID."}
        except ResultsUnavailableError as exc:
            return HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)}

    def status(self) -> dict[str, object]:
        operation = self.operations.snapshot()
        schedule = asdict(read_schedule_info())
        try:
            settings = load_settings()
            history = load_run_summaries(settings)
            screens = [
                {
                    "id": item.id,
                    "name": item.name,
                    "enabled": item.enabled,
                    "preset_summary": summarize_preset(item.url),
                }
                for item in settings.finviz.resolved_screens()
            ]
            configuration: dict[str, object] = {
                "ready": True,
                "output_root": str(settings.output.root_directory),
                "screens": screens,
                "schedule": f"{settings.schedule.day.title()} at {settings.schedule.time}",
            }
        except Exception as exc:  # HTTP boundary: report configuration errors as state.
            configuration = {"ready": False, "error": str(exc), "screens": []}
            history = []
        latest = history[0] if history else None
        stable = next((item for item in history if item["status"] == "SUCCESS"), None)
        return {
            "configuration": configuration,
            "schedule": schedule,
            "latest": latest,
            "stable": stable,
            "history": history,
            "operation": operation,
        }

    def start_action(self, action: str) -> tuple[bool, str]:
        actions = {
            "scan": ("Visible scan", ["scan", "--headed"]),
            "doctor": ("Health check", ["doctor"]),
            "install-schedule": ("Weekly task repair", ["install-schedule"]),
        }
        selected = actions.get(action)
        if selected is None:
            return False, "Unknown action."
        return self.operations.start(*selected)

    @staticmethod
    def open_folder(name: str) -> tuple[bool, str]:
        if name not in {"watchlists", "logs"}:
            return False, "Unknown folder."
        try:
            settings = load_settings()
            destination = settings.output.root_directory / name
            destination.mkdir(parents=True, exist_ok=True)
            os.startfile(destination)
        except (OSError, ValueError) as exc:
            return False, str(exc)
        return True, f"Opened {name}."


class ScannerRequestHandler(BaseHTTPRequestHandler):
    service: DashboardService
    token: str

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            template = (ASSET_DIRECTORY / "index.html").read_text(encoding="utf-8")
            body = template.replace("__SCANNER_TOKEN__", self.token).encode()
            self._send_bytes(HTTPStatus.OK, body, "text/html; charset=utf-8")
        elif path == "/app.css":
            self._send_asset("app.css", "text/css; charset=utf-8")
        elif path == "/app.js":
            self._send_asset("app.js", "text/javascript; charset=utf-8")
        elif path == "/results.js":
            self._send_asset("results.js", "text/javascript; charset=utf-8")
        elif path == "/api/status":
            self._send_json(HTTPStatus.OK, self.service.status())
        elif path == "/api/results":
            values = parse_qs(urlparse(self.path).query).get("screen_id", [])
            if len(values) != 1:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "One screen_id is required."})
                return
            status, result = self.service.results(values[0])
            self._send_json(status, result)
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.headers.get("X-Scanner-Token") != self.token:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Invalid request token."})
            return
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            self._send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "JSON required."})
            return
        path = urlparse(self.path).path
        if path.startswith("/api/actions/"):
            action = path.removeprefix("/api/actions/")
            if action == "cancel":
                ok, message = self.service.operations.cancel()
            else:
                ok, message = self.service.start_action(action)
        elif path.startswith("/api/open/"):
            ok, message = self.service.open_folder(path.removeprefix("/api/open/"))
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        status = HTTPStatus.ACCEPTED if ok else HTTPStatus.CONFLICT
        self._send_json(status, {"ok": ok, "message": message})

    def _send_asset(self, filename: str, content_type: str) -> None:
        body = (ASSET_DIRECTORY / filename).read_bytes()
        self._send_bytes(HTTPStatus.OK, body, content_type)

    def _send_json(self, status: HTTPStatus, value: object) -> None:
        self._send_bytes(status, json.dumps(value).encode(), "application/json; charset=utf-8")

    def _send_bytes(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def run_web_app(port: int = 8765, *, open_browser: bool = True) -> None:
    """Serve the dashboard on loopback and optionally open it in the default browser."""
    service = DashboardService()
    token = secrets.token_urlsafe(24)
    handler = type(
        "BoundScannerRequestHandler",
        (ScannerRequestHandler,),
        {"service": service, "token": token},
    )
    try:
        server = ScannerHTTPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        if exc.errno not in {errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", 10048)}:
            raise
        # An older dashboard can still hold the default port after a code update.
        # Start the current version on an available loopback port and open its URL.
        server = ScannerHTTPServer(("127.0.0.1", 0), handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    if open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    print(f"Finviz Scanner dashboard: {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int | float | str | bytes | bytearray):
        return int(value)
    raise TypeError(f"Expected a number-like value, received {type(value).__name__}.")


def _optional_text(value: object) -> str | None:
    return str(value) if value else None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _no_window_flag() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    run_web_app()
