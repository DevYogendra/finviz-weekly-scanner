"""Exchange-qualified symbol resolution."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from finviz_scanner.errors import ExchangeResolutionError, SymbolMasterValidationError
from finviz_scanner.models import ExtractedRow, ResolvedSymbol
from finviz_scanner.utils import normalize_ticker

DEFAULT_EXCHANGE_MAP = {
    "Q": "NASDAQ",
    "NASDAQ": "NASDAQ",
    "N": "NYSE",
    "NYSE": "NYSE",
    "A": "AMEX",
    "AMEX": "AMEX",
    "P": "AMEX",
    "Z": "BATS",
    "BATS": "BATS",
}


@dataclass(frozen=True, slots=True)
class SymbolDirectoryEntry:
    ticker: str
    exchange: str


@dataclass(frozen=True, slots=True)
class SymbolMasterValidation:
    path: Path
    expected_headers: tuple[str, ...]
    actual_headers: tuple[str, ...]
    total_rows: int
    usable_rows: int
    blank_value_rows: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SymbolMasterLoadResult:
    entries: dict[str, SymbolDirectoryEntry]
    validation: SymbolMasterValidation


class SymbolResolver:
    def __init__(self, entries: dict[str, SymbolDirectoryEntry]) -> None:
        self._entries = entries

    @classmethod
    def from_csv(cls, path: Path) -> SymbolResolver:
        return cls(load_symbol_master(path).entries)

    def resolve_rows(self, rows: tuple[ExtractedRow, ...]) -> tuple[ResolvedSymbol, ...]:
        unresolved: list[str] = []
        resolved: list[ResolvedSymbol] = []
        seen: set[str] = set()
        for row in sorted(rows, key=lambda item: item.finviz_rank):
            ticker = normalize_ticker(row.ticker)
            if ticker in seen:
                continue
            seen.add(ticker)
            entry = self._entries.get(ticker)
            if entry is None:
                unresolved.append(ticker)
                continue
            tv_ticker = ticker.replace("-", ".")
            resolved.append(
                ResolvedSymbol(
                    ticker=ticker,
                    exchange=entry.exchange,
                    tv_symbol=f"{entry.exchange}:{tv_ticker}",
                    company_name=row.company_name,
                    finviz_rank=row.finviz_rank,
                    source_page=row.source_page,
                )
            )
        if unresolved:
            sorted_unresolved = tuple(sorted(unresolved))
            raise ExchangeResolutionError(
                "Unresolved symbols: " + ", ".join(sorted_unresolved),
                sorted_unresolved,
            )
        return tuple(resolved)


EXPECTED_HEADERS = ("ticker", "exchange")


def load_symbol_master(path: Path) -> SymbolMasterLoadResult:
    entries: dict[str, SymbolDirectoryEntry] = {}
    blank_rows: list[int] = []
    total_rows = 0
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        actual_headers = _normalized_headers(reader.fieldnames)
        _validate_headers(path, actual_headers)
        reader.fieldnames = list(actual_headers)

        for row_number, row in enumerate(reader, start=2):
            total_rows += 1
            ticker_value = (row.get("ticker") or "").strip()
            exchange_value = (row.get("exchange") or "").strip()
            if not ticker_value or not exchange_value:
                blank_rows.append(row_number)
                continue
            try:
                ticker = normalize_ticker(ticker_value)
            except ValueError as exc:
                raise SymbolMasterValidationError(
                    f"Invalid ticker in symbol master {path} at CSV row {row_number}: "
                    f"{ticker_value!r}."
                ) from exc
            exchange_code = exchange_value.upper()
            tv_exchange = DEFAULT_EXCHANGE_MAP.get(exchange_code)
            if tv_exchange is None:
                continue
            if ticker in entries and entries[ticker].exchange != tv_exchange:
                entries.pop(ticker)
                continue
            entries[ticker] = SymbolDirectoryEntry(ticker=ticker, exchange=tv_exchange)
    validation = SymbolMasterValidation(
        path=path,
        expected_headers=EXPECTED_HEADERS,
        actual_headers=actual_headers,
        total_rows=total_rows,
        usable_rows=len(entries),
        blank_value_rows=tuple(blank_rows),
    )
    return SymbolMasterLoadResult(entries=entries, validation=validation)


def _normalized_headers(headers: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(header.strip().lower() for header in headers or ())


def _validate_headers(path: Path, actual_headers: tuple[str, ...]) -> None:
    if set(actual_headers) != set(EXPECTED_HEADERS) or len(actual_headers) != len(EXPECTED_HEADERS):
        raise SymbolMasterValidationError(
            f"Invalid symbol master headers in {path}. "
            f"Expected headers: {EXPECTED_HEADERS!r}. "
            f"Actual headers: {actual_headers!r}."
        )
