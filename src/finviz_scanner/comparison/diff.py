"""Weekly set comparison."""

from __future__ import annotations

from finviz_scanner.models import ComparisonResult, ResolvedSymbol


def compare_snapshots(
    current: tuple[ResolvedSymbol, ...],
    previous: tuple[ResolvedSymbol, ...] | None,
) -> ComparisonResult:
    current_by_ticker = {item.ticker: item for item in current}
    if previous is None:
        return ComparisonResult(additions=(), removals=(), unchanged=(), is_baseline=True)

    previous_by_ticker = {item.ticker: item for item in previous}
    current_tickers = set(current_by_ticker)
    previous_tickers = set(previous_by_ticker)
    additions = tuple(
        current_by_ticker[ticker] for ticker in sorted(current_tickers - previous_tickers)
    )
    removals = tuple(
        previous_by_ticker[ticker] for ticker in sorted(previous_tickers - current_tickers)
    )
    unchanged = tuple(
        current_by_ticker[ticker] for ticker in sorted(current_tickers & previous_tickers)
    )
    return ComparisonResult(
        additions=additions,
        removals=removals,
        unchanged=unchanged,
        is_baseline=False,
    )
