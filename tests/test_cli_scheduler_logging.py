from __future__ import annotations

from finviz_scanner.scheduler import scheduled_task_command, schtasks_create_args
from finviz_scanner.utils import redact_secrets
from tests.helpers import settings_for


def test_secrets_and_cookies_are_redacted_from_logs() -> None:
    text = "url=https://x.test?a=1&token=abc cookie=secret password=hunter2"
    redacted = redact_secrets(text)
    assert "abc" not in redacted
    assert "secret" not in redacted
    assert "hunter2" not in redacted


def test_windows_scheduler_command_uses_absolute_paths_and_schedule(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = settings_for(tmp_path)
    command = scheduled_task_command(settings, tmp_path)
    args = schtasks_create_args(settings, tmp_path)
    assert str((tmp_path / "scripts" / "run_scan.ps1").resolve()) in command
    assert command.endswith("-Headed")
    assert len(command) <= 261
    assert "/ST" in args
    assert "08:00" in args


def test_finviz_new_screener_path_is_valid() -> None:
    from finviz_scanner.utils import validate_finviz_url

    url = "https://finviz.com/screener?v=111&f=cap_smallover"
    assert validate_finviz_url(url) == url
