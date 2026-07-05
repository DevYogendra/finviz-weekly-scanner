from __future__ import annotations

from pathlib import Path

import pytest

from finviz_scanner.errors import ConfigurationError
from finviz_scanner.symbols.resolver import SymbolResolver, load_symbol_master


def write_csv(path: Path, content: str, *, encoding: str = "utf-8") -> Path:
    path.write_text(content, encoding=encoding)
    return path


def test_normal_utf8_csv_loads(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "symbol-master.csv", "ticker,exchange\nAAA,NASDAQ\nBBB,NYSE\n")
    result = load_symbol_master(path)
    resolver = SymbolResolver.from_csv(path)
    assert result.validation.actual_headers == ("ticker", "exchange")
    assert result.validation.usable_rows == 2
    assert resolver.resolve_rows(()) == ()


def test_utf8_bom_csv_loads(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "symbol-master.csv",
        "\ufeffticker,exchange\nAAA,NASDAQ\n",
        encoding="utf-8",
    )
    result = load_symbol_master(path)
    assert result.validation.actual_headers == ("ticker", "exchange")
    assert result.validation.usable_rows == 1


def test_header_case_is_normalized(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "symbol-master.csv", "Ticker,Exchange\nAAA,NASDAQ\n")
    result = load_symbol_master(path)
    assert result.validation.actual_headers == ("ticker", "exchange")
    assert result.validation.usable_rows == 1


def test_header_whitespace_is_normalized(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "symbol-master.csv", " ticker , exchange \nAAA,NASDAQ\n")
    result = load_symbol_master(path)
    assert result.validation.actual_headers == ("ticker", "exchange")
    assert result.validation.usable_rows == 1


def test_missing_ticker_column_raises_configuration_error(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "symbol-master.csv", "exchange\nNASDAQ\n")
    with pytest.raises(ConfigurationError) as exc_info:
        load_symbol_master(path)
    message = str(exc_info.value)
    assert str(path) in message
    assert "Expected headers: ('ticker', 'exchange')" in message
    assert "Actual headers: ('exchange',)" in message


def test_missing_exchange_column_raises_configuration_error(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "symbol-master.csv", "ticker\nAAA\n")
    with pytest.raises(ConfigurationError) as exc_info:
        load_symbol_master(path)
    message = str(exc_info.value)
    assert str(path) in message
    assert "Expected headers: ('ticker', 'exchange')" in message
    assert "Actual headers: ('ticker',)" in message


def test_empty_csv_raises_configuration_error(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "symbol-master.csv", "")
    with pytest.raises(ConfigurationError) as exc_info:
        load_symbol_master(path)
    message = str(exc_info.value)
    assert str(path) in message
    assert "Actual headers: ()" in message
