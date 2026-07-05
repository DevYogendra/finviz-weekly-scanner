"""Write CSV, JSON, TradingView, and report artifacts."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from finviz_scanner.models import ComparisonResult, ResolvedSymbol
from finviz_scanner.utils import ensure_directory


def tradingview_line(symbols: tuple[ResolvedSymbol, ...]) -> str:
    ordered = sorted(symbols, key=lambda item: item.finviz_rank)
    return ",".join(symbol.tv_symbol for symbol in ordered)


def write_outputs(
    output_dir: Path,
    current: tuple[ResolvedSymbol, ...],
    comparison: ComparisonResult,
    *,
    run_id: str,
    displayed_count: int,
) -> None:
    ensure_directory(output_dir)
    _write_symbol_csv(output_dir / "current.csv", current)
    _write_symbol_csv(output_dir / "additions.csv", comparison.additions)
    _write_symbol_csv(output_dir / "removals.csv", comparison.removals)
    _write_symbol_csv(output_dir / "unchanged.csv", comparison.unchanged)
    (output_dir / "current.json").write_text(
        json.dumps([asdict(item) for item in current], indent=2),
        encoding="utf-8",
    )
    (output_dir / "tradingview-current.txt").write_text(tradingview_line(current), encoding="utf-8")
    additions_note = "# Baseline run: no additions reported.\n" if comparison.is_baseline else ""
    (output_dir / "tradingview-additions.txt").write_text(
        additions_note + tradingview_line(comparison.additions),
        encoding="utf-8",
    )
    run_json = {
        "run_id": run_id,
        "displayed_count": displayed_count,
        "current_count": len(current),
        "additions": len(comparison.additions),
        "removals": len(comparison.removals),
        "unchanged": len(comparison.unchanged),
        "baseline": comparison.is_baseline,
        "status": "SUCCESS",
    }
    (output_dir / "run.json").write_text(json.dumps(run_json, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(
        _report_markdown(current, comparison, displayed_count),
        encoding="utf-8",
    )


def write_screen_aliases(
    output_dir: Path,
    current: tuple[ResolvedSymbol, ...],
    comparison: ComparisonResult,
    *,
    screen_id: str,
    screen_name: str,
    previous_successful_run_id: str | None,
) -> None:
    """Write multi-screen friendly filenames alongside legacy artifact names."""
    (output_dir / "tradingview-watchlist.txt").write_text(
        tradingview_line(current),
        encoding="utf-8",
    )
    (output_dir / "additions.txt").write_text(
        tradingview_line(comparison.additions),
        encoding="utf-8",
    )
    (output_dir / "removals.txt").write_text(
        tradingview_line(comparison.removals),
        encoding="utf-8",
    )
    source_csv = output_dir / "current.csv"
    if source_csv.exists():
        (output_dir / "tickers.csv").write_text(
            source_csv.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    metadata = {
        "screen_id": screen_id,
        "screen_name": screen_name,
        "previous_successful_run_id": previous_successful_run_id,
        "current_count": len(current),
        "previous_count": len(comparison.unchanged) + len(comparison.removals),
        "additions_count": len(comparison.additions),
        "removals_count": len(comparison.removals),
        "baseline": comparison.is_baseline,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def _write_symbol_csv(path: Path, symbols: tuple[ResolvedSymbol, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "ticker",
                "exchange",
                "tv_symbol",
                "company_name",
                "first_seen",
                "last_seen",
                "weeks_on_list",
                "finviz_rank",
            ],
        )
        writer.writeheader()
        for symbol in symbols:
            writer.writerow(
                {
                    "ticker": symbol.ticker,
                    "exchange": symbol.exchange,
                    "tv_symbol": symbol.tv_symbol,
                    "company_name": symbol.company_name or "",
                    "first_seen": symbol.first_seen or "",
                    "last_seen": symbol.last_seen or "",
                    "weeks_on_list": symbol.weeks_on_list,
                    "finviz_rank": symbol.finviz_rank,
                }
            )


def _report_markdown(
    current: tuple[ResolvedSymbol, ...],
    comparison: ComparisonResult,
    displayed_count: int,
) -> str:
    lines = [
        "# Stage-2 Weekly Scan",
        "",
        f"Current matches: {len(current)}",
        f"Displayed Finviz count: {displayed_count}",
        f"New additions: {len(comparison.additions)}",
        f"Fell off: {len(comparison.removals)}",
        f"Unchanged: {len(comparison.unchanged)}",
        f"Run status: {'BASELINE SUCCESS' if comparison.is_baseline else 'SUCCESS'}",
        "",
        "## New additions",
    ]
    lines.extend(f"- {item.tv_symbol}" for item in comparison.additions)
    if comparison.is_baseline:
        lines.append("- Baseline run: no additions reported.")
    lines.append("")
    lines.append("## Fell off")
    lines.extend(f"- {item.tv_symbol}" for item in comparison.removals)
    lines.append("")
    lines.append("TradingView file: tradingview-current.txt")
    return "\n".join(lines) + "\n"
