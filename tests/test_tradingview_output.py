from __future__ import annotations

from pathlib import Path

from finviz_scanner.comparison.diff import compare_snapshots
from finviz_scanner.output.artifacts import tradingview_line, write_outputs
from finviz_scanner.symbols.resolver import SymbolResolver
from tests.helpers import TICKERS_44, pages_for


def test_tradingview_output_is_one_utf8_comma_separated_line(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from finviz_scanner.extraction.finviz_dom import extract_pages

    resolver = SymbolResolver.from_csv(Path("tests/fixtures/symbol_master.csv"))
    symbols = resolver.resolve_rows(extract_pages(pages_for(TICKERS_44)).rows)
    line = tradingview_line(symbols)
    assert "\n" not in line
    assert line.startswith("NASDAQ:AAA,NASDAQ:BBB,NYSE:CCC")
    assert len(line.split(",")) == 44


def test_additions_only_file_contains_only_new_additions(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from finviz_scanner.extraction.finviz_dom import extract_pages

    resolver = SymbolResolver.from_csv(Path("tests/fixtures/symbol_master.csv"))
    previous = resolver.resolve_rows(extract_pages(pages_for(TICKERS_44[:3], total=3)).rows)
    current = resolver.resolve_rows(
        extract_pages(pages_for(("AAA", "BBB", "NEW1", "NEW2"), total=4)).rows
    )
    comparison = compare_snapshots(current, previous)
    write_outputs(tmp_path, current, comparison, run_id="run", displayed_count=4)
    assert (tmp_path / "tradingview-additions.txt").read_text(encoding="utf-8") == (
        "NASDAQ:NEW1,NYSE:NEW2"
    )
