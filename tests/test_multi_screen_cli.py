from __future__ import annotations

from datetime import UTC, datetime

from typer.testing import CliRunner

from finviz_scanner import cli
from finviz_scanner.models import MultiScreenRunResult, ScreenScanResult
from tests.helpers import multi_settings_for


def test_list_screens_hides_urls_by_default(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(cli, "load_settings", lambda: multi_settings_for(tmp_path))
    result = CliRunner().invoke(cli.app, ["list-screens"])
    assert result.exit_code == 0
    assert "stage-2" in result.output
    assert "Momentum Candidates" in result.output
    assert "https://finviz.com" not in result.output


def test_list_screens_can_show_urls(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(cli, "load_settings", lambda: multi_settings_for(tmp_path))
    result = CliRunner().invoke(cli.app, ["list-screens", "--show-urls"])
    assert result.exit_code == 0
    assert "https://finviz.com" in result.output


def test_scan_passes_repeatable_screen_options(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = multi_settings_for(tmp_path)
    captured: dict[str, object] = {}

    def fake_run_multi_screen_scan(*args: object, **kwargs: object) -> MultiScreenRunResult:
        captured["selected"] = kwargs["selected_screen_ids"]
        captured["headed"] = kwargs["headed"]
        return _result("success")

    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "_resolver", lambda _root: object())
    monkeypatch.setattr(cli, "run_multi_screen_scan", fake_run_multi_screen_scan)
    result = CliRunner().invoke(
        cli.app,
        ["scan", "--screen", "stage-2", "--screen", "momentum", "--headed"],
    )
    assert result.exit_code == 0
    assert captured["selected"] == ("stage-2", "momentum")
    assert captured["headed"] is True


def test_scan_partial_success_exits_two(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = multi_settings_for(tmp_path)
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "_resolver", lambda _root: object())
    monkeypatch.setattr(
        cli, "run_multi_screen_scan", lambda *args, **kwargs: _result("partial_success")
    )
    result = CliRunner().invoke(cli.app, ["scan"])
    assert result.exit_code == 2
    assert "partial success" in result.output


def defake_screen_result(status: str) -> ScreenScanResult:
    return ScreenScanResult(
        screen_id="stage-2",
        screen_name="Stage 2",
        url="https://finviz.com/screener?v=111",
        status=status if status != "partial_success" else "success",
        ticker_count=1,
        resolved_count=1,
        rejected_count=0,
        output_directory=None,
        error=None,
    )


def _result(status: str) -> MultiScreenRunResult:
    now = datetime.now(UTC)
    screens = [defake_screen_result(status)]
    if status == "partial_success":
        screens.append(
            ScreenScanResult(
                screen_id="momentum",
                screen_name="Momentum",
                url="https://finviz.com/screener?v=111",
                status="failed",
                ticker_count=0,
                resolved_count=0,
                rejected_count=0,
                output_directory=None,
                error="bad page",
            )
        )
    return MultiScreenRunResult(
        run_id="run1",
        started_at=now,
        completed_at=now,
        status=status,
        screens=screens,
    )
