from __future__ import annotations

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError

from finviz_scanner.browser.readiness import (
    CURRENT_STRICT_SELECTOR,
    CURRENT_STRUCTURAL_SELECTOR,
    LEGACY_QUOTE_LINK_SELECTOR,
    classify_finviz_html,
    dismiss_elite_dialog,
    is_transient_navigation_error,
    save_failure_diagnostics,
    wait_for_finviz_ready,
    wait_for_next_page_ready,
)
from finviz_scanner.errors import CaptchaError, ExtractionError
from finviz_scanner.extraction.finviz_dom import (
    BROAD_BOXOVER_SELECTOR,
    ELITE_DIALOG_CLOSE_SELECTOR,
    ELITE_DIALOG_OPEN_SELECTOR,
    extract_rows_from_html,
    extract_ticker_candidates,
    page_select_options,
    parse_displayed_count,
    parse_screener_total,
)

CURRENT_FIXTURE = Path("tests/fixtures/finviz_current_failure_page.html")


class FakeLocator:
    def __init__(self, count: int, text: str = "AAPL") -> None:
        self._count = count
        self._text = text
        self.first = self

    def count(self) -> int:
        return self._count

    def wait_for(self, *, state: str, timeout: int) -> None:
        _ = (state, timeout)

    def text_content(self) -> str:
        return self._text


class FakePage:
    def __init__(
        self,
        html_sequence: list[str],
        *,
        url: str = "https://finviz.com/screener",
    ) -> None:
        self._html_sequence = html_sequence
        self._index = 0
        self.url = url
        self.wait_count = 0
        self.screenshots: list[Path] = []

    def content(self) -> str:
        html = self._html_sequence[min(self._index, len(self._html_sequence) - 1)]
        if self._index < len(self._html_sequence) - 1:
            self._index += 1
        return html

    def _peek_content(self) -> str:
        return self._html_sequence[min(self._index, len(self._html_sequence) - 1)]

    def wait_for_timeout(self, _milliseconds: int) -> None:
        self.wait_count += 1

    def locator(self, selector: str) -> FakeLocator:
        html = self._peek_content()
        if selector == CURRENT_STRICT_SELECTOR:
            count = html.count('href="stock?t=')
        elif selector == CURRENT_STRUCTURAL_SELECTOR:
            count = html.count('class="tab-link"')
        elif selector == LEGACY_QUOTE_LINK_SELECTOR:
            count = html.count("quote.ashx?t=")
        else:
            count = 0
        ticker = "AAPL"
        if "AAA" in html:
            ticker = "AAA"
        elif "UUU" in html:
            ticker = "UUU"
        elif "BBB" in html:
            ticker = "BBB"
        elif "MSFT" in html:
            ticker = "MSFT"
        return FakeLocator(count, ticker)

    def title(self) -> str:
        return "Finviz Screener"

    def screenshot(self, *, path: str, full_page: bool) -> None:
        _ = full_page
        screenshot_path = Path(path)
        screenshot_path.write_bytes(b"fake")
        self.screenshots.append(screenshot_path)


class TransientContentPage(FakePage):
    def __init__(self, content_results: list[str | PlaywrightError]) -> None:
        super().__init__([])
        self._content_results = content_results
        self.content_calls = 0
        self.load_state_waits = 0

    def content(self) -> str:
        self.content_calls += 1
        result = self._content_results.pop(0) if self._content_results else ready_html("AAA")
        if isinstance(result, PlaywrightError):
            raise result
        return result

    def wait_for_load_state(self, state: str, *, timeout: int) -> None:
        _ = (state, timeout)
        self.load_state_waits += 1

    def locator(self, _selector: str) -> FakeLocator:
        return FakeLocator(0)


class PersistentTransientContentPage(TransientContentPage):
    def __init__(self) -> None:
        super().__init__([])

    def content(self) -> str:
        self.content_calls += 1
        raise transient_error()


class LocatorReadyPage(FakePage):
    def __init__(self) -> None:
        super().__init__([])
        self.content_calls = 0

    def content(self) -> str:
        self.content_calls += 1
        raise transient_error()

    def locator(self, selector: str) -> FakeLocator:
        count = 1 if selector == CURRENT_STRICT_SELECTOR else 0
        return FakeLocator(count)


def ready_html(
    ticker: str = "AAA",
    *,
    total: int = 44,
    page_text: str = "Page 1/3",
    old_selector: bool = False,
) -> str:
    table_class = "old-table-class" if old_selector else "screener_table"
    return f"""
    <html>
      <head><title>Finviz Screener</title></head>
      <body>
        <span>#1 / {total} Total</span>
        <span>{page_text}</span>
        <table class="{table_class}">
          <tr>
            <td>1</td>
            <td><a href="quote.ashx?t={ticker}">{ticker}</a></td>
            <td>{ticker} Corp</td>
          </tr>
        </table>
      </body>
    </html>
    """


def transient_error() -> PlaywrightError:
    return PlaywrightError(
        "Page.content: Unable to retrieve content because the page is navigating "
        "and changing the content."
    )


def test_page_with_44_results_and_quote_links_is_ready() -> None:
    state = classify_finviz_html(ready_html())
    assert state.ready
    assert state.ticker_count == 1
    assert state.displayed_total == 44
    assert state.current_page == 1
    assert state.total_pages == 3


def test_uploaded_current_markup_page_is_ready_and_extracts_20_unique_tickers() -> None:
    html = CURRENT_FIXTURE.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    assert len(soup.select(CURRENT_STRICT_SELECTOR)) == 20
    assert len(soup.select(CURRENT_STRUCTURAL_SELECTOR)) == 20
    assert len(soup.select(LEGACY_QUOTE_LINK_SELECTOR)) == 0
    assert len(soup.select(BROAD_BOXOVER_SELECTOR)) == 40
    rows = extract_rows_from_html(html, page_number=1, source_url="https://finviz.com/screener")
    assert len(rows) == 20
    assert len({row.ticker for row in rows}) == 20
    assert [row.ticker for row in rows[:3]] == ["AAPL", "TSM", "LLY"]
    for candidate in extract_ticker_candidates(html):
        assert candidate.ticker == candidate.text


def test_uploaded_page_metadata_parses_screener_total_and_page_select() -> None:
    html = CURRENT_FIXTURE.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one("#screener-total") is not None
    assert parse_screener_total(html) == (1, 44)
    assert parse_displayed_count(html) == 44
    assert soup.select_one("#pageSelect") is not None
    assert page_select_options(html) == (
        ("1", "Page 1 / 3"),
        ("21", "Page 2 / 3"),
        ("41", "Page 3 / 3"),
    )


def test_uploaded_page_elite_dialog_selectors_are_present() -> None:
    html = CURRENT_FIXTURE.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    assert len(soup.select(ELITE_DIALOG_OPEN_SELECTOR)) == 1
    assert len(soup.select(ELITE_DIALOG_CLOSE_SELECTOR)) == 1


def test_background_network_activity_does_not_prevent_readiness() -> None:
    page = FakePage([ready_html()])
    state = wait_for_finviz_ready(page, timeout_ms=100, stage="test")
    assert state.ready
    assert page.wait_count == 0


def test_transient_content_navigation_error_then_success() -> None:
    page = TransientContentPage([transient_error(), ready_html("AAPL")])
    state = wait_for_finviz_ready(page, timeout_ms=1_000, stage="initial")
    assert state.ready
    assert page.content_calls == 2
    assert page.load_state_waits == 1


def test_several_transient_content_errors_then_success() -> None:
    page = TransientContentPage([transient_error(), transient_error(), ready_html("MSFT")])
    state = wait_for_finviz_ready(page, timeout_ms=1_000, stage="initial")
    assert state.ready
    assert page.content_calls == 3


def test_persistent_transient_navigation_times_out_as_extraction_error() -> None:
    page = PersistentTransientContentPage()
    with pytest.raises(ExtractionError, match=r"initial.*unstable or navigating"):
        wait_for_finviz_ready(page, timeout_ms=1, stage="initial")


def test_non_transient_playwright_error_is_actionable_extraction_error() -> None:
    page = TransientContentPage([PlaywrightError("browser has been closed")])
    with pytest.raises(ExtractionError, match="Unable to inspect Finviz page during initial"):
        wait_for_finviz_ready(page, timeout_ms=1_000, stage="initial")


def test_locator_based_readiness_avoids_unstable_page_content() -> None:
    page = LocatorReadyPage()
    state = wait_for_finviz_ready(page, timeout_ms=1_000, stage="initial")
    assert state.ready
    assert state.ticker_count == 1
    assert page.content_calls == 0


def test_transient_navigation_error_classifier_is_narrow() -> None:
    assert is_transient_navigation_error(transient_error())
    assert is_transient_navigation_error(PlaywrightError("Execution context was destroyed"))
    assert is_transient_navigation_error(PlaywrightError("Cannot find context with specified id"))
    assert not is_transient_navigation_error(PlaywrightError("browser has been closed"))


def test_quote_links_succeed_even_if_generic_navigation_timed_out() -> None:
    page = FakePage([ready_html("BBB")])
    state = wait_for_finviz_ready(page, timeout_ms=100, stage="navigation_timeout_probe")
    assert state.first_ticker == "BBB"


def test_old_table_selector_does_not_prevent_extraction() -> None:
    html = ready_html("CCC", old_selector=True)
    rows = extract_rows_from_html(html, page_number=1, source_url="https://finviz.com/screener")
    assert [row.ticker for row in rows] == ["CCC"]


def test_legacy_quote_link_fallback_still_extracts() -> None:
    html = (
        '<html><body>Total: 1<table><tr><td><a href="quote.ashx?t=AAPL">'
        "AAPL</a></td></tr></table></body></html>"
    )
    rows = extract_rows_from_html(html, page_number=1, source_url="https://finviz.com/screener")
    assert [row.ticker for row in rows] == ["AAPL"]


@pytest.mark.parametrize(
    ("href", "text", "data_ticker", "expected"),
    [
        ("stock?t=AAPL", "AAPL", "AAPL", ("AAPL",)),
        ("/stock?t=AAPL&ty=c&p=d&b=1", "AAPL", "AAPL", ("AAPL",)),
        ("quote.ashx?t=MSFT", "MSFT", None, ("MSFT",)),
        ("/quote.ashx?t=MSFT", "MSFT", None, ("MSFT",)),
        ("stock?x=AAPL", "AAPL", "AAPL", ()),
        ("stock?t=MSFT", "AAPL", "AAPL", ()),
        ("stock?t=AAPL", "AAPL", "MSFT", ()),
    ],
)
def test_ticker_url_variants_and_conflicts(
    href: str,
    text: str,
    data_ticker: str | None,
    expected: tuple[str, ...],
) -> None:
    if data_ticker is None:
        html = f'<html><body>Total: 1<a href="{href}">{text}</a></body></html>'
    else:
        html = (
            f'<html><body>Total: 1<td data-boxover-ticker="{data_ticker}">'
            f'<a class="tab-link" href="{href}">{text}</a></td></body></html>'
        )
    assert tuple(candidate.ticker for candidate in extract_ticker_candidates(html)) == expected


def test_duplicate_candidates_are_logged_and_deduped(caplog: pytest.LogCaptureFixture) -> None:
    html = """
    <html><body>Total: 1
      <td data-boxover-ticker="AAPL"><a class="tab-link" href="stock?t=AAPL">AAPL</a></td>
      <td data-boxover-ticker="AAPL"><a class="tab-link" href="stock?t=AAPL">AAPL</a></td>
      <td data-boxover-ticker="MSFT"><a class="tab-link" href="stock?t=MSFT">MSFT</a></td>
    </body></html>
    """
    with caplog.at_level("WARNING"):
        rows = extract_rows_from_html(html, page_number=1, source_url="https://finviz.com/screener")
    assert [row.ticker for row in rows] == ["AAPL", "MSFT"]
    assert "duplicate_ticker_candidate" in caplog.text


def test_captcha_page_is_rejected() -> None:
    with pytest.raises(CaptchaError):
        classify_finviz_html("<html>captcha unusual traffic challenge</html>")


def test_cloudflare_security_verification_page_is_rejected() -> None:
    with pytest.raises(CaptchaError):
        classify_finviz_html(
            "<html><title>Just a moment...</title>security verification not a bot</html>"
        )


def test_no_results_page_is_handled_explicitly() -> None:
    state = classify_finviz_html("<html><body>#0 / 0 Total Page 1/1</body></html>")
    assert state.ready
    assert state.no_results
    with pytest.raises(ExtractionError, match="zero results"):
        wait_for_finviz_ready(
            FakePage(["<html><body>#0 / 0 Total Page 1/1</body></html>"]),
            timeout_ms=10,
            stage="test",
        )


def test_diagnostic_artifacts_are_created_on_failure(tmp_path: Path) -> None:
    page = FakePage(["<html><body>#1 / 44 Total</body></html>"])
    save_failure_diagnostics(
        page,
        tmp_path,
        http_status=200,
        stage="readiness",
        timeout_ms=45_000,
    )
    assert (tmp_path / "failure-page.html").exists()
    assert (tmp_path / "failure-page.png").exists()
    metadata = json.loads((tmp_path / "failure-metadata.json").read_text(encoding="utf-8"))
    assert metadata["final_url"] == "https://finviz.com/screener"
    assert metadata["http_status"] == 200
    assert metadata["browser_timeout_stage"] == "readiness"
    assert metadata["matching_selector_counts"][CURRENT_STRICT_SELECTOR] == 0


def test_diagnostics_are_best_effort_when_page_content_is_navigating(tmp_path: Path) -> None:
    page = TransientContentPage([transient_error()])
    save_failure_diagnostics(
        page,
        tmp_path,
        http_status=None,
        stage="readiness",
        timeout_ms=45_000,
    )
    assert not (tmp_path / "failure-page.html").exists()
    assert (tmp_path / "failure-page.png").exists()
    metadata = json.loads((tmp_path / "failure-metadata.json").read_text(encoding="utf-8"))
    assert metadata["browser_timeout_stage"] == "readiness"
    assert metadata["ticker_link_count"] == 0


def test_pagination_waits_for_changed_result_content() -> None:
    page = FakePage(
        [
            ready_html("UUU", page_text="Page 2/3"),
        ]
    )
    state = wait_for_next_page_ready(
        page,
        previous_first_ticker="AAA",
        previous_page_indicator=(1, 3),
        timeout_ms=1_000,
    )
    assert state.first_ticker == "UUU"
    assert state.ready


def test_displayed_count_parser_accepts_hash_range_format() -> None:
    assert parse_displayed_count(ready_html()) == 44


class DialogCloseButton:
    def __init__(self, page: DialogPage) -> None:
        self.page = page

    def click(self, *, timeout: int) -> None:
        _ = timeout
        self.page.dialog_open = False


class DialogLocator:
    def __init__(self, page: DialogPage) -> None:
        self.page = page

    def count(self) -> int:
        return 1 if self.page.dialog_open else 0

    def locator(self, selector: str) -> DialogCloseButton:
        assert selector == ELITE_DIALOG_CLOSE_SELECTOR
        return DialogCloseButton(self.page)

    def get_attribute(self, name: str) -> str | None:
        assert name == "open"
        return "" if self.page.dialog_open else None


class DialogKeyboard:
    def __init__(self, page: DialogPage) -> None:
        self.page = page

    def press(self, key: str) -> None:
        if key == "Escape":
            self.page.dialog_open = False


class DialogPage:
    def __init__(self) -> None:
        self.dialog_open = True
        self.keyboard = DialogKeyboard(self)

    def locator(self, selector: str) -> DialogLocator:
        assert selector == ELITE_DIALOG_OPEN_SELECTOR
        return DialogLocator(self)

    def wait_for_timeout(self, _milliseconds: int) -> None:
        return


def test_elite_dialog_dismissal_helper_closes_dialog() -> None:
    page = DialogPage()
    assert dismiss_elite_dialog(page) == "closed"
    assert not page.dialog_open
