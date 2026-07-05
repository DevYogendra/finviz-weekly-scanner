from __future__ import annotations

import pytest

from finviz_scanner.errors import ExtractionError
from finviz_scanner.extraction.finviz_dom import extract_pages
from finviz_scanner.models import PageCapture
from tests.helpers import TICKERS_44, html_page, pages_for


def test_repeated_page_loop_is_detected() -> None:
    duplicate_html = html_page(TICKERS_44[:20])
    pages = (
        PageCapture(1, "https://finviz.com/screener.ashx&r=1", duplicate_html),
        PageCapture(2, "https://finviz.com/screener.ashx&r=21", duplicate_html),
    )
    with pytest.raises(ExtractionError, match="Repeated page loop"):
        extract_pages(pages)


def test_partial_page_load_is_rejected_by_count_validation() -> None:
    from finviz_scanner.validation import validate_extraction

    result = extract_pages(pages_for(TICKERS_44[:40], total=44))
    with pytest.raises(Exception, match="Displayed count 44"):
        validate_extraction(result)
