"""Typed domain models for scanner runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


class RunStatus(StrEnum):
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DEGRADED_OCR = "DEGRADED_OCR"


class ExtractionMode(StrEnum):
    DOM = "dom"
    OCR = "ocr"


@dataclass(frozen=True, slots=True)
class ExtractedRow:
    ticker: str
    company_name: str | None
    finviz_rank: int
    source_page: int
    source_url: str
    captured_at: datetime
    sector: str | None = None
    industry: str | None = None
    country: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedSymbol:
    ticker: str
    exchange: str
    tv_symbol: str
    company_name: str | None
    finviz_rank: int
    source_page: int
    first_seen: str | None = None
    last_seen: str | None = None
    weeks_on_list: int = 1
    reentry: bool = False


@dataclass(frozen=True, slots=True)
class PageCapture:
    page_number: int
    url: str
    html: str
    screenshot_path: Path | None = None


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    displayed_count: int
    rows: tuple[ExtractedRow, ...]
    pages: tuple[PageCapture, ...]
    duplicate_tickers: tuple[str, ...] = ()
    extraction_mode: ExtractionMode = ExtractionMode.DOM

    @property
    def unique_count(self) -> int:
        return len({row.ticker for row in self.rows})


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    additions: tuple[ResolvedSymbol, ...]
    removals: tuple[ResolvedSymbol, ...]
    unchanged: tuple[ResolvedSymbol, ...]
    is_baseline: bool


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    status: RunStatus = RunStatus.STARTED
    scheduled_for: datetime | None = None
    source_url_fingerprint: str | None = None
    displayed_count: int | None = None
    extracted_count: int | None = None
    page_count: int | None = None
    extraction_mode: ExtractionMode = ExtractionMode.DOM
    software_version: str = "0.1.0"
    error_category: str | None = None
    error_summary: str | None = None
