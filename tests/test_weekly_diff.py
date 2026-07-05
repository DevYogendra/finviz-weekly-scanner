from __future__ import annotations

from finviz_scanner.comparison.diff import compare_snapshots
from finviz_scanner.models import ResolvedSymbol


def symbol(ticker: str, rank: int = 1) -> ResolvedSymbol:
    return ResolvedSymbol(ticker, "NASDAQ", f"NASDAQ:{ticker}", ticker, rank, 1)


def test_identical_runs_have_zero_additions_and_removals() -> None:
    previous = (symbol("AAA"), symbol("BBB", 2))
    current = (symbol("AAA"), symbol("BBB", 2))
    diff = compare_snapshots(current, previous)
    assert diff.additions == ()
    assert diff.removals == ()
    assert len(diff.unchanged) == 2


def test_two_additions_and_one_removal() -> None:
    previous = (symbol("AAA"), symbol("BBB", 2), symbol("CCC", 3))
    current = (symbol("AAA"), symbol("CCC", 3), symbol("NEW1", 4), symbol("NEW2", 5))
    diff = compare_snapshots(current, previous)
    assert {item.ticker for item in diff.additions} == {"NEW1", "NEW2"}
    assert {item.ticker for item in diff.removals} == {"BBB"}


def test_first_successful_run_is_baseline() -> None:
    diff = compare_snapshots((symbol("AAA"), symbol("BBB", 2)), None)
    assert diff.is_baseline
    assert diff.additions == ()
    assert diff.removals == ()
