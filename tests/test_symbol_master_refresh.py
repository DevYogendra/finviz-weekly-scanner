from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from finviz_scanner.cli import app
from finviz_scanner.config import FinvizConfig, OutputConfig, Settings
from finviz_scanner.errors import SymbolMasterValidationError
from finviz_scanner.symbols.master_builder import (
    NASDAQ_LISTED_URL,
    build_symbol_master_records,
    refresh_symbol_master,
)
from finviz_scanner.symbols.resolver import load_symbol_master
from finviz_scanner.utils import normalize_ticker

NASDAQ_HEADER = (
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"
)
OTHERLISTED_HEADER = (
    "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol"
)

NASDAQ_FIXTURE = f"""{NASDAQ_HEADER}
MSFT|Microsoft Corporation|Q|N|N|100|N|N
TEST|Test Security|Q|Y|N|100|N|N
File Creation Time: 0705202620:00
"""

OTHERLISTED_AAC_FIXTURE = f"""{OTHERLISTED_HEADER}
AAC.U|Ares Acquisition Corporation III Units|N|AAC.U|N|100|N|AAC=
FAKE|Test Issue Should Be Excluded|N|FAKE|N|100|Y|FAKE=
File Creation Time: 0705202620:00
"""


def test_otherlisted_uses_act_symbol_not_nasdaq_symbol() -> None:
    records, report = build_symbol_master_records(NASDAQ_FIXTURE, OTHERLISTED_AAC_FIXTURE)
    assert records["AAC.U"].ticker == "AAC.U"
    assert records["AAC.U"].exchange == "NYSE"
    assert "AAC=" not in records
    assert report.loaded_records == 2


def test_normalize_ticker_does_not_accept_nasdaq_symbol_equals_suffix() -> None:
    with pytest.raises(ValueError, match="Invalid ticker"):
        normalize_ticker("AAC=")


def test_refresh_never_writes_aac_equals_to_symbol_master(tmp_path: Path) -> None:
    destination = tmp_path / "symbol-master.csv"

    def downloader(url: str) -> str:
        return NASDAQ_FIXTURE if url == NASDAQ_LISTED_URL else OTHERLISTED_AAC_FIXTURE

    report = refresh_symbol_master(destination, downloader=downloader, minimum_usable_rows=1)
    contents = destination.read_text(encoding="utf-8")
    result = load_symbol_master(destination)
    assert "AAC.U,NYSE" in contents
    assert "AAC=" not in contents
    assert result.entries["AAC.U"].exchange == "NYSE"
    assert report.loaded_records == 2


def test_refresh_skips_unsupported_broad_master_records(tmp_path: Path) -> None:
    otherlisted = f"""{OTHERLISTED_HEADER}
|Unsupported Nasdaq Symbol Only|N|AAC=|N|100|N|AAC=
AAC.U|Ares Acquisition Corporation III Units|N|AAC.U|N|100|N|AAC=
"""
    destination = tmp_path / "symbol-master.csv"

    def downloader(url: str) -> str:
        return NASDAQ_FIXTURE if url == NASDAQ_LISTED_URL else otherlisted

    report = refresh_symbol_master(destination, downloader=downloader, minimum_usable_rows=1)
    contents = destination.read_text(encoding="utf-8")
    assert "AAC.U,NYSE" in contents
    assert "AAC=" not in contents
    assert report.invalid_records == 1
    assert report.skipped_records == 1


def test_existing_symbol_master_is_not_replaced_when_refresh_fails(tmp_path: Path) -> None:
    destination = tmp_path / "symbol-master.csv"
    original = "ticker,exchange\nMSFT,NASDAQ\n"
    destination.write_text(original, encoding="utf-8")

    def downloader(_url: str) -> str:
        return "Symbol|Security Name|Market Category|Test Issue\n"

    with pytest.raises(SymbolMasterValidationError):
        refresh_symbol_master(destination, downloader=downloader, minimum_usable_rows=1000)
    assert destination.read_text(encoding="utf-8") == original


def test_doctor_reports_malformed_symbol_master_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        finviz=FinvizConfig(saved_screen_url="https://finviz.com/screener?v=111&f=cap_smallover"),
        output=OutputConfig(root_directory=tmp_path),
    )
    (tmp_path / "symbol-master.csv").write_text("ticker,exchange\nAAC=,NYSE\n", encoding="utf-8")
    monkeypatch.setattr("finviz_scanner.cli.load_settings", lambda: settings)
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "Symbol master: invalid" in result.output
    assert "Invalid ticker" in result.output
    assert "Traceback" not in result.output
