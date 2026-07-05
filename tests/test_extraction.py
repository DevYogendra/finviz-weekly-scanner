from __future__ import annotations

import pytest

from finviz_scanner.errors import CaptchaError, ExtractionError
from finviz_scanner.extraction.finviz_dom import extract_pages
from tests.helpers import TICKERS_44, pages_for


def test_44_results_across_three_pages_yields_unique_tickers() -> None:
    result = extract_pages(pages_for(TICKERS_44))
    assert result.displayed_count == 44
    assert result.unique_count == 44
    assert len(result.pages) == 3
    assert [len(page.html) > 0 for page in result.pages] == [True, True, True]


def test_twenty_twenty_four_pagination_shape() -> None:
    result = extract_pages(pages_for(TICKERS_44))
    page_counts = [sum(1 for row in result.rows if row.source_page == page) for page in (1, 2, 3)]
    assert page_counts == [20, 20, 4]


def test_duplicate_rows_are_deduplicated_for_unique_count() -> None:
    tickers = (*TICKERS_44, "AAA")
    result = extract_pages(pages_for(tickers, total=44))
    assert result.unique_count == 44
    assert result.duplicate_tickers == ("AAA",)


def test_captcha_is_rejected() -> None:
    with pytest.raises(ExtractionError):
        extract_pages(())


def test_captcha_html_is_rejected() -> None:
    from finviz_scanner.models import PageCapture

    page = PageCapture(1, "https://finviz.com/screener.ashx", "<html>captcha are you human</html>")
    with pytest.raises(CaptchaError):
        extract_pages((page,))
