from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from finviz_scanner.config import FinvizConfig, OutputConfig, ScreenConfig, Settings
from finviz_scanner.models import PageCapture

TICKERS_44 = (
    "AAA",
    "BBB",
    "CCC",
    "DDD",
    "EEE",
    "FFF",
    "GGG",
    "HHH",
    "III",
    "JJJ",
    "KKK",
    "LLL",
    "MMM",
    "NNN",
    "OOO",
    "PPP",
    "QQQ",
    "RRR",
    "SSS",
    "TTT",
    "UUU",
    "VVV",
    "WWW",
    "XXX",
    "YYY",
    "ZZZ",
    "ABCD",
    "BCDE",
    "CDEF",
    "DEFG",
    "EFGH",
    "FGHI",
    "GHIJ",
    "HIJK",
    "IJKL",
    "JKLM",
    "KLMN",
    "LMNO",
    "MNOP",
    "NOPQ",
    "OPQR",
    "PQRS",
    "QRST",
    "RSTU",
)


def html_page(tickers: tuple[str, ...], *, total: int = 44, start_rank: int = 1) -> str:
    rows = "\n".join(
        f'<tr><td>{idx}</td><td><a class="screener-link-primary" '
        f'href="quote.ashx?t={ticker}">{ticker}</a></td><td>{ticker} Corp</td></tr>'
        for idx, ticker in enumerate(tickers, start=start_rank)
    )
    return f"""
    <html>
      <body>
        <div id="screener-total">Total: {total}</div>
        <table class="screener_table">{rows}</table>
      </body>
    </html>
    """


def pages_for(tickers: tuple[str, ...], *, total: int = 44) -> tuple[PageCapture, ...]:
    chunks = (tickers[:20], tickers[20:40], tickers[40:])
    pages: list[PageCapture] = []
    for number, chunk in enumerate(chunks, start=1):
        if chunk:
            pages.append(
                PageCapture(
                    page_number=number,
                    url=f"https://finviz.com/screener.ashx?v=111&r={1 + (number - 1) * 20}",
                    html=html_page(chunk, total=total, start_rank=1 + (number - 1) * 20),
                )
            )
    return tuple(pages)


def settings_for(tmp_path: Path) -> Settings:
    return Settings(
        finviz=FinvizConfig(
            saved_screen_url="https://finviz.com/screener.ashx?v=111&f=cap_smallover"
        ),
        output=OutputConfig(root_directory=tmp_path),
    )


def multi_settings_for(tmp_path: Path) -> Settings:
    return Settings(
        finviz=FinvizConfig(
            screens=[
                ScreenConfig(
                    id="stage-2",
                    name="Stage 2 Candidates",
                    url="https://finviz.com/screener.ashx?v=111&f=cap_smallover",
                ),
                ScreenConfig(
                    id="momentum",
                    name="Momentum Candidates",
                    url="https://finviz.com/screener.ashx?v=111&f=sh_price_o30",
                ),
            ]
        ),
        output=OutputConfig(root_directory=tmp_path),
    )


def now_utc() -> datetime:
    return datetime.now(UTC)
