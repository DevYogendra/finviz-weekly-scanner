"""Build symbol-master.csv from Nasdaq Trader symbol directory files."""

from __future__ import annotations

import csv
import logging
import shutil
import tempfile
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from finviz_scanner.errors import SymbolMasterValidationError
from finviz_scanner.symbols.resolver import DEFAULT_EXCHANGE_MAP, load_symbol_master
from finviz_scanner.utils import ensure_directory, normalize_ticker

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SymbolMasterRecord:
    ticker: str
    exchange: str


@dataclass(slots=True)
class SymbolMasterBuildReport:
    total_records: int = 0
    loaded_records: int = 0
    skipped_records: int = 0
    duplicated_records: int = 0
    invalid_records: int = 0
    invalid_examples: list[str] = field(default_factory=list)


Downloader = Callable[[str], str]


def download_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as response:
        data = cast(bytes, response.read())
        return data.decode("utf-8-sig")


def refresh_symbol_master(
    destination: Path,
    *,
    downloader: Downloader = download_text,
    minimum_usable_rows: int = 1000,
) -> SymbolMasterBuildReport:
    nasdaq_text = downloader(NASDAQ_LISTED_URL)
    other_text = downloader(OTHER_LISTED_URL)
    records, report = build_symbol_master_records(nasdaq_text, other_text)
    ensure_directory(destination.parent)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        delete=False,
        dir=destination.parent,
        prefix="symbol-master-",
        suffix=".csv",
    ) as file:
        temp_path = Path(file.name)
        writer = csv.DictWriter(file, fieldnames=["ticker", "exchange"])
        writer.writeheader()
        for record in sorted(records.values(), key=lambda item: item.ticker):
            writer.writerow({"ticker": record.ticker, "exchange": record.exchange})
    try:
        validation = load_symbol_master(temp_path).validation
        if validation.blank_value_rows:
            raise SymbolMasterValidationError(
                f"Generated symbol master {temp_path} contains blank ticker or exchange values."
            )
        if validation.usable_rows < minimum_usable_rows:
            raise SymbolMasterValidationError(
                f"Generated symbol master {temp_path} has {validation.usable_rows} usable rows; "
                f"expected at least {minimum_usable_rows}."
            )
        shutil.move(str(temp_path), str(destination))
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return report


def build_symbol_master_records(
    nasdaq_text: str,
    other_text: str,
) -> tuple[dict[str, SymbolMasterRecord], SymbolMasterBuildReport]:
    report = SymbolMasterBuildReport()
    records: dict[str, SymbolMasterRecord] = {}
    _add_records(records, report, parse_nasdaqlisted(nasdaq_text))
    _add_records(records, report, parse_otherlisted(other_text))
    report.loaded_records = len(records)
    return records, report


def parse_nasdaqlisted(text: str) -> Iterable[SymbolMasterRecord | None]:
    reader = csv.DictReader(_data_lines(text), delimiter="|")
    for row in reader:
        if (row.get("Test Issue") or "").strip().upper() != "N":
            continue
        ticker = (row.get("Symbol") or "").strip()
        yield _record_or_skip(ticker, "NASDAQ")


def parse_otherlisted(text: str) -> Iterable[SymbolMasterRecord | None]:
    reader = csv.DictReader(_data_lines(text), delimiter="|")
    for row in reader:
        if (row.get("Test Issue") or "").strip().upper() != "N":
            continue
        ticker = (row.get("ACT Symbol") or "").strip() or (row.get("CQS Symbol") or "").strip()
        exchange_code = (row.get("Exchange") or "").strip().upper()
        exchange = DEFAULT_EXCHANGE_MAP.get(exchange_code)
        if exchange is None:
            yield _record_or_skip(ticker, "")
            continue
        yield _record_or_skip(ticker, exchange)


def _add_records(
    records: dict[str, SymbolMasterRecord],
    report: SymbolMasterBuildReport,
    candidates: Iterable[SymbolMasterRecord | None],
) -> None:
    for candidate in candidates:
        report.total_records += 1
        if candidate is None:
            report.skipped_records += 1
            report.invalid_records += 1
            continue
        existing = records.get(candidate.ticker)
        if existing is not None:
            report.duplicated_records += 1
            if existing.exchange != candidate.exchange:
                report.skipped_records += 1
            continue
        records[candidate.ticker] = candidate


def _record_or_skip(ticker_value: str, exchange: str) -> SymbolMasterRecord | None:
    try:
        ticker = normalize_ticker(ticker_value)
    except ValueError:
        logger.warning(
            "symbol_master_invalid_record",
            extra={"ticker": ticker_value, "reason": "unsupported_ticker_syntax"},
        )
        return None
    if not exchange:
        logger.warning(
            "symbol_master_invalid_record",
            extra={"ticker": ticker, "reason": "unsupported_exchange"},
        )
        return None
    return SymbolMasterRecord(ticker=ticker, exchange=exchange)


def _data_lines(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if line.strip() and not line.lower().startswith("file creation time:")
    ]
