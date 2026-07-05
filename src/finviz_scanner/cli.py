"""Typer command-line interface."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from finviz_scanner.browser.finviz_browser import FinvizBrowserCollector
from finviz_scanner.config import (
    CONFIG_PATH,
    DEFAULT_OUTPUT_DIR,
    FinvizConfig,
    OutputConfig,
    ScheduleConfig,
    Settings,
    load_settings,
    write_settings,
)
from finviz_scanner.errors import ConfigurationError, ScannerError, SymbolMasterValidationError
from finviz_scanner.scheduler import schtasks_create_args
from finviz_scanner.storage.sqlite import SQLiteStore
from finviz_scanner.symbols.master_builder import refresh_symbol_master
from finviz_scanner.symbols.resolver import SymbolResolver, load_symbol_master
from finviz_scanner.workflow.runner import run_scan

app = typer.Typer(help="Finviz Weekly Stage-2 Scanner")


@app.command()
def configure() -> None:
    """Create or update the user-local scanner configuration."""
    url = typer.prompt("Exact Finviz screener URL")
    output_dir = typer.prompt("Output directory", default=str(DEFAULT_OUTPUT_DIR))
    day = typer.prompt("Weekly run day", default="saturday")
    time = typer.prompt("Weekly run time", default="08:00")
    allow_ocr = typer.confirm("Enable OCR fallback?", default=False)
    enable_email = typer.confirm("Enable email notification?", default=False)
    settings = Settings(
        finviz=FinvizConfig(saved_screen_url=url, allow_ocr_fallback=allow_ocr),
        schedule=ScheduleConfig(day=day, time=time),
        output=OutputConfig(root_directory=Path(output_dir)),
    )
    if enable_email:
        settings.notification.provider = "email"
    path = write_settings(settings)
    typer.echo(f"Wrote configuration to {path}")


@app.command()
def scan(headed: bool = typer.Option(False, help="Open a visible Chromium browser.")) -> None:
    """Run the complete Finviz collection workflow."""
    try:
        settings = load_settings()
        collector = FinvizBrowserCollector(
            output_dir=settings.output.root_directory / "working",
            headed=headed,
        )
        resolver = _resolver(settings.output.root_directory)
        run_dir = run_scan(settings, collector, resolver)
    except ScannerError as exc:
        typer.echo(f"Scan failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Scan succeeded: {run_dir}")


@app.command()
def validate() -> None:
    """Validate the latest generated artifacts."""
    settings = load_settings()
    latest = settings.output.root_directory / "latest"
    required = [
        "current.csv",
        "current.json",
        "tradingview-current.txt",
        "tradingview-additions.txt",
        "report.md",
        "run.json",
    ]
    missing = [name for name in required if not (latest / name).exists()]
    if missing:
        typer.echo("Missing latest artifacts: " + ", ".join(missing), err=True)
        raise typer.Exit(1)
    typer.echo("Latest artifacts are present.")


@app.command("compare")
def compare_command() -> None:
    """Compare the latest successful snapshots."""
    settings = load_settings()
    store = SQLiteStore(settings.output.root_directory / "scanner.sqlite3")
    rows = [row for row in store.recent_runs(20) if row["status"] == "SUCCESS"]
    if len(rows) < 2:
        typer.echo("Fewer than two successful runs are available.")
        return
    typer.echo(f"Latest: {rows[0]['run_id']} Previous: {rows[1]['run_id']}")


@app.command("export-tradingview")
def export_tradingview() -> None:
    """Recreate TradingView files from the latest successful snapshot."""
    validate()
    typer.echo("TradingView files are available in the latest artifact directory.")


@app.command()
def history(limit: int = 10) -> None:
    """Print recent run status."""
    settings = load_settings()
    store = SQLiteStore(settings.output.root_directory / "scanner.sqlite3")
    for row in store.recent_runs(limit):
        typer.echo(
            f"{row['started_at']} {row['status']} run_id={row['run_id']} "
            f"displayed={row['displayed_count']} extracted={row['extracted_count']}"
        )


@app.command()
def doctor() -> None:
    """Verify Python, config, Playwright, filesystem, SQLite, and scheduler prerequisites."""
    ok = True
    typer.echo(f"Python: {sys.version.split()[0]}")
    try:
        settings = load_settings()
        typer.echo(f"Config: {CONFIG_PATH}")
    except ConfigurationError as exc:
        typer.echo(f"Config: not ready ({exc})")
        settings = None
    try:
        import playwright  # noqa: F401
        from playwright.sync_api import sync_playwright

        typer.echo("Playwright: installed")
        with sync_playwright() as playwright_runner:
            chromium_path = Path(playwright_runner.chromium.executable_path)
        if chromium_path.exists():
            typer.echo(f"Chromium: installed at {chromium_path}")
        else:
            typer.echo("Chromium: missing; run 'python -m playwright install chromium'", err=True)
            ok = False
    except ImportError:
        typer.echo("Playwright: missing", err=True)
        ok = False
    if settings is not None:
        settings.output.root_directory.mkdir(parents=True, exist_ok=True)
        probe = settings.output.root_directory / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        SQLiteStore(settings.output.root_directory / "scanner.sqlite3")
        typer.echo("Filesystem and SQLite: writable")
        symbol_master_path = settings.output.root_directory / "symbol-master.csv"
        try:
            symbol_master = load_symbol_master(symbol_master_path)
        except FileNotFoundError:
            typer.echo(f"Symbol master: missing ({symbol_master_path})", err=True)
            ok = False
        except SymbolMasterValidationError as exc:
            typer.echo(f"Symbol master: invalid ({exc})", err=True)
            ok = False
        except ConfigurationError as exc:
            typer.echo(f"Symbol master: invalid ({exc})", err=True)
            ok = False
        else:
            validation = symbol_master.validation
            if validation.blank_value_rows:
                typer.echo(
                    "Symbol master: blank ticker or exchange values at CSV rows "
                    + ", ".join(str(row) for row in validation.blank_value_rows[:10]),
                    err=True,
                )
                ok = False
            if validation.usable_rows < 1000:
                typer.echo(
                    f"Symbol master: only {validation.usable_rows} usable rows; "
                    "expected at least 1000",
                    err=True,
                )
                ok = False
            if not validation.blank_value_rows and validation.usable_rows >= 1000:
                typer.echo(f"Symbol master: {validation.usable_rows} usable rows")
    typer.echo("Scheduler: Windows schtasks expected for install-schedule")
    if not ok:
        raise typer.Exit(1)


@app.command("install-schedule")
def install_schedule() -> None:
    """Create or update the Windows scheduled task."""
    settings = load_settings()
    args = schtasks_create_args(settings)
    subprocess.run(args, check=True)
    typer.echo("Scheduled task installed.")


@app.command("refresh-symbol-master")
def refresh_symbol_master_command() -> None:
    """Download Nasdaq Trader directories and atomically rebuild symbol-master.csv."""
    try:
        settings = load_settings()
        destination = settings.output.root_directory / "symbol-master.csv"
        report = refresh_symbol_master(destination)
    except ScannerError as exc:
        typer.echo(f"Symbol master refresh failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Symbol master refreshed: {destination}")
    typer.echo(
        "Records: "
        f"loaded={report.loaded_records} "
        f"skipped={report.skipped_records} "
        f"duplicated={report.duplicated_records} "
        f"invalid={report.invalid_records} "
        f"total={report.total_records}"
    )


@app.command("remove-schedule")
def remove_schedule() -> None:
    """Remove only the scheduled task created by this application."""
    subprocess.run(["schtasks", "/Delete", "/TN", "FinvizWeeklyScanner", "/F"], check=True)
    typer.echo("Scheduled task removed.")


def _resolver(root: Path) -> SymbolResolver:
    path = root / "symbol-master.csv"
    if not path.exists():
        msg = f"Symbol master not found: {path}. Create ticker,exchange CSV before scanning."
        raise ConfigurationError(msg)
    return SymbolResolver.from_csv(path)


if __name__ == "__main__":
    app()
