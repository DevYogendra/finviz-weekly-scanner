from __future__ import annotations

import pytest

from finviz_scanner.errors import ValidationError
from finviz_scanner.extraction.finviz_dom import extract_pages
from finviz_scanner.validation import validate_extraction
from tests.helpers import TICKERS_44, pages_for


def test_displayed_count_mismatch_is_rejected() -> None:
    result = extract_pages(pages_for(TICKERS_44, total=45))
    with pytest.raises(ValidationError):
        validate_extraction(result)
