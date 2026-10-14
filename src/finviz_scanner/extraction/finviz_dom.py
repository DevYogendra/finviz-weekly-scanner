"""DOM extraction for sanitized and live Finviz pages."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from finviz_scanner.errors import CaptchaError, ExtractionError
from finviz_scanner.models import ExtractedRow, ExtractionResult, PageCapture
from finviz_scanner.utils import normalize_ticker

CURRENT_STRICT_TICKER_SELECTOR = 'td[data-boxover-ticker] a.tab-link[href^="stock?t="]'
CURRENT_STRUCTURAL_TICKER_SELECTOR = "td[data-boxover-ticker] a.tab-link"
LEGACY_TICKER_SELECTOR = 'a[href*="quote.ashx?t="]'
TICKER_SELECTOR_ORDER = (
    CURRENT_STRICT_TICKER_SELECTOR,
    CURRENT_STRUCTURAL_TICKER_SELECTOR,
    LEGACY_TICKER_SELECTOR,
)
BROAD_BOXOVER_SELECTOR = "td[data-boxover-ticker]"
SCREENER_TOTAL_SELECTOR = "#screener-total"
PAGE_SELECT_SELECTOR = "#pageSelect"
PAGE_SELECT_OPTION_SELECTOR = "#pageSelect option"
ELITE_DIALOG_OPEN_SELECTOR = 'dialog[data-testid="elite-features-dialog"][open]'
ELITE_DIALOG_CLOSE_SELECTOR = 'button[data-testid="elite-features-dialog-close"]'

COUNT_RE = re.compile(
    r"Total:\s*([0-9,]+)|#?\s*\d+\s*/\s*([0-9,]+)\s+Total|([0-9,]+)\s+Total",
    re.IGNORECASE,
)
SCREENER_TOTAL_RE = re.compile(r"#?\s*([0-9,]+)\s*/\s*([0-9,]+)\s*Total", re.IGNORECASE)
PAGE_RE = re.compile(r"Page\s+([0-9,]+)\s*/\s*([0-9,]+)", re.IGNORECASE)


def parse_displayed_count(html: str) -> int:
    screener_total = parse_screener_total(html)
    if screener_total is not None:
        return screener_total[1]
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    match = COUNT_RE.search(text)
    if match is None:
        raise ExtractionError("Could not locate Finviz displayed result count.")
    value = next(group for group in match.groups() if group)
    return int(value.replace(",", ""))


def parse_screener_total(html: str) -> tuple[int, int] | None:
    soup = BeautifulSoup(html, "html.parser")
    total_element = soup.select_one(SCREENER_TOTAL_SELECTOR)
    texts = [total_element.get_text(" ", strip=True)] if total_element else []
    texts.append(soup.get_text(" ", strip=True))
    for text in texts:
        match = SCREENER_TOTAL_RE.search(text)
        if match is not None:
            current = int(match.group(1).replace(",", ""))
            total = int(match.group(2).replace(",", ""))
            return current, total
    return None


def detect_blockers(html: str) -> None:
    lowered = BeautifulSoup(html, "html.parser").get_text(" ", strip=True).lower()
    if (
        "captcha" in lowered
        or "are you human" in lowered
        or "unusual traffic" in lowered
        or "challenge" in lowered
        or "rate limit" in lowered
        or "just a moment" in lowered
        or "security verification" in lowered
        or "not a bot" in lowered
    ):
        raise CaptchaError("Finviz displayed a CAPTCHA or human verification challenge.")
    if "access denied" in lowered or ("login" in lowered and "screener" not in lowered):
        raise CaptchaError("Finviz displayed an access or login challenge.")


def quote_link_tickers(html: str) -> tuple[str, ...]:
    return tuple(candidate.ticker for candidate in extract_ticker_candidates(html))


class TickerCandidate:
    def __init__(
        self,
        *,
        ticker: str,
        company_name: str | None,
        sector: str | None,
        industry: str | None,
        country: str | None,
        href: str,
        text: str,
        selector: str,
    ) -> None:
        self.ticker = ticker
        self.company_name = company_name
        self.sector = sector
        self.industry = industry
        self.country = country
        self.href = href
        self.text = text
        self.selector = selector


def extract_ticker_candidates(html: str) -> tuple[TickerCandidate, ...]:
    soup = BeautifulSoup(html, "html.parser")
    for selector in TICKER_SELECTOR_ORDER:
        anchors = soup.select(selector)
        if anchors:
            return _validated_candidates(anchors, selector)
    return ()


def selector_counts(html: str) -> dict[str, int]:
    soup = BeautifulSoup(html, "html.parser")
    selectors = (
        CURRENT_STRICT_TICKER_SELECTOR,
        CURRENT_STRUCTURAL_TICKER_SELECTOR,
        LEGACY_TICKER_SELECTOR,
        BROAD_BOXOVER_SELECTOR,
        SCREENER_TOTAL_SELECTOR,
        PAGE_SELECT_SELECTOR,
        PAGE_SELECT_OPTION_SELECTOR,
        ELITE_DIALOG_OPEN_SELECTOR,
    )
    return {selector: len(soup.select(selector)) for selector in selectors}


def parse_page_indicator(html: str) -> tuple[int, int] | None:
    soup = BeautifulSoup(html, "html.parser")
    selected_option = soup.select_one("#pageSelect option[selected]")
    if selected_option is None:
        selected_option = soup.select_one("#pageSelect option")
    if selected_option is not None:
        match = PAGE_RE.search(selected_option.get_text(" ", strip=True))
        if match is not None:
            return int(match.group(1).replace(",", "")), int(match.group(2).replace(",", ""))
    text = soup.get_text(" ", strip=True)
    match = PAGE_RE.search(text)
    if match is None:
        return None
    return int(match.group(1).replace(",", "")), int(match.group(2).replace(",", ""))


def page_select_options(html: str) -> tuple[tuple[str, str], ...]:
    soup = BeautifulSoup(html, "html.parser")
    options: list[tuple[str, str]] = []
    for option in soup.select(PAGE_SELECT_OPTION_SELECTOR):
        value = option.get("value", "")
        options.append((value if isinstance(value, str) else "", option.get_text(" ", strip=True)))
    return tuple(options)


def extract_rows_from_html(
    html: str,
    *,
    page_number: int,
    source_url: str,
) -> tuple[ExtractedRow, ...]:
    detect_blockers(html)
    soup = BeautifulSoup(html, "html.parser")
    rows: list[ExtractedRow] = []
    captured_at = datetime.now(UTC)
    candidates = extract_ticker_candidates(html)
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.ticker in seen:
            continue
        seen.add(candidate.ticker)
        anchor = _find_anchor_for_candidate(soup, candidate)
        tr = anchor.find_parent("tr") if anchor is not None else None
        cells = [cell.get_text(" ", strip=True) for cell in tr.find_all("td")] if tr else []
        rank = len(rows) + 1
        if cells and cells[0].isdigit():
            rank = int(cells[0])
        company = candidate.company_name
        if company is None:
            company = cells[2] if len(cells) > 2 and cells[2] != candidate.ticker else None
        rows.append(
            ExtractedRow(
                ticker=candidate.ticker,
                company_name=company,
                finviz_rank=rank,
                source_page=page_number,
                source_url=source_url,
                captured_at=captured_at,
                industry=candidate.industry,
                country=candidate.country,
            )
        )
    if not rows:
        raise ExtractionError(f"No ticker rows found on page {page_number}.")
    return tuple(rows)


def page_signature(rows: tuple[ExtractedRow, ...]) -> tuple[str, ...]:
    return tuple(row.ticker for row in rows)


def _validated_candidates(anchors: list[Tag], selector: str) -> tuple[TickerCandidate, ...]:
    candidates: list[TickerCandidate] = []
    seen: set[str] = set()
    for anchor in anchors:
        candidate = _candidate_from_anchor(anchor, selector)
        if candidate is None:
            continue
        if candidate.ticker in seen:
            import logging

            logging.getLogger(__name__).warning(
                "duplicate_ticker_candidate",
                extra={"ticker": candidate.ticker, "href": candidate.href, "selector": selector},
            )
            continue
        seen.add(candidate.ticker)
        candidates.append(candidate)
    return tuple(candidates)


def _candidate_from_anchor(anchor: Tag, selector: str) -> TickerCandidate | None:
    href = anchor.get("href")
    text = anchor.get_text(strip=True)
    if not isinstance(href, str) or not href or not text:
        _log_rejected_candidate("missing_href_or_text", text=text, href=str(href))
        return None
    cell = anchor.find_parent("td", attrs={"data-boxover-ticker": True})
    raw_values = {"text": text, "href": _ticker_from_href(href)}
    if cell is not None:
        boxover_ticker = cell.get("data-boxover-ticker")
        if isinstance(boxover_ticker, str) and boxover_ticker.strip():
            raw_values["data"] = boxover_ticker
    normalized: dict[str, str] = {}
    try:
        for source, value in raw_values.items():
            if value is None:
                _log_rejected_candidate("missing_ticker_representation", text=text, href=href)
                return None
            normalized[source] = normalize_ticker(value)
    except ValueError:
        _log_rejected_candidate("malformed_ticker_representation", text=text, href=href)
        return None
    if len(set(normalized.values())) != 1:
        _log_rejected_candidate("conflicting_ticker_representations", text=text, href=href)
        return None
    company = _tag_attr(cell, "data-boxover-company")
    return TickerCandidate(
        ticker=normalized["text"],
        company_name=company,
        sector=None,
        industry=_tag_attr(cell, "data-boxover-industry"),
        country=_tag_attr(cell, "data-boxover-country"),
        href=href,
        text=text,
        selector=selector,
    )


def _ticker_from_href(href: str) -> str | None:
    parsed = urlparse(urljoin("https://finviz.com/", href))
    values = parse_qs(parsed.query).get("t")
    return values[0] if values else None


def _tag_attr(tag: Tag | None, name: str) -> str | None:
    if tag is None:
        return None
    value = tag.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _find_anchor_for_candidate(soup: BeautifulSoup, candidate: TickerCandidate) -> Tag | None:
    for selector in TICKER_SELECTOR_ORDER:
        for anchor in soup.select(selector):
            text_matches = anchor.get_text(strip=True) == candidate.text
            href_matches = anchor.get("href") == candidate.href
            if text_matches and href_matches:
                return anchor
    return None


def _log_rejected_candidate(reason: str, *, text: str, href: str) -> None:
    import logging

    logging.getLogger(__name__).debug(
        "rejected_ticker_candidate",
        extra={"reason": reason, "text": text, "href": href},
    )


def extract_pages(pages: tuple[PageCapture, ...]) -> ExtractionResult:
    if not pages:
        raise ExtractionError("No pages were supplied for extraction.")
    detect_blockers(pages[0].html)
    displayed_count = parse_displayed_count(pages[0].html)
    signatures: set[tuple[str, ...]] = set()
    all_rows: list[ExtractedRow] = []
    duplicate_tickers: list[str] = []
    seen: set[str] = set()
    for page in pages:
        rows = extract_rows_from_html(page.html, page_number=page.page_number, source_url=page.url)
        signature = page_signature(rows)
        if signature in signatures:
            raise ExtractionError(f"Repeated page loop detected at page {page.page_number}.")
        signatures.add(signature)
        for row in rows:
            if row.ticker in seen:
                duplicate_tickers.append(row.ticker)
            seen.add(row.ticker)
            all_rows.append(row)
    return ExtractionResult(
        displayed_count=displayed_count,
        rows=tuple(all_rows),
        pages=pages,
        duplicate_tickers=tuple(sorted(set(duplicate_tickers))),
    )
