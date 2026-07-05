"""Finviz-specific page readiness and diagnostics."""

from __future__ import annotations

import json
import logging
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError

from finviz_scanner.errors import ExtractionError
from finviz_scanner.extraction.finviz_dom import (
    ELITE_DIALOG_CLOSE_SELECTOR,
    ELITE_DIALOG_OPEN_SELECTOR,
    PAGE_SELECT_OPTION_SELECTOR,
    PAGE_SELECT_SELECTOR,
    SCREENER_TOTAL_SELECTOR,
    detect_blockers,
    page_select_options,
    parse_displayed_count,
    parse_page_indicator,
    quote_link_tickers,
    selector_counts,
)
from finviz_scanner.utils import ensure_directory

CURRENT_STRICT_SELECTOR = 'td[data-boxover-ticker] > a.tab-link[href^="stock?t="]'
CURRENT_STRUCTURAL_SELECTOR = "td[data-boxover-ticker] > a.tab-link"
LEGACY_QUOTE_LINK_SELECTOR = 'a[href*="quote.ashx?t="]'
QUOTE_LINK_SELECTOR = CURRENT_STRICT_SELECTOR
RESULT_SELECTORS = (
    CURRENT_STRICT_SELECTOR,
    CURRENT_STRUCTURAL_SELECTOR,
    LEGACY_QUOTE_LINK_SELECTOR,
)
TRANSIENT_NAVIGATION_MESSAGES = (
    "page is navigating and changing the content",
    "execution context was destroyed",
    "cannot find context with specified id",
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FinvizReadiness:
    ready: bool
    no_results: bool
    ticker_count: int
    displayed_total: int | None
    current_page: int | None
    total_pages: int | None
    first_ticker: str | None


@dataclass(frozen=True, slots=True)
class FailureMetadata:
    final_url: str
    title: str
    http_status: int | None
    ticker_link_count: int
    matching_selector_counts: dict[str, int]
    selected_page_value: str | None
    page_option_values: tuple[str, ...]
    page_option_labels: tuple[str, ...]
    screener_total_text: str | None
    candidate_anchors: tuple[dict[str, str | None], ...]
    elite_dialog_open: bool
    readiness_selector: str | None
    browser_timeout_stage: str
    configured_timeout: int
    current_utc_timestamp: str


def classify_finviz_html(html: str) -> FinvizReadiness:
    detect_blockers(html)
    tickers = quote_link_tickers(html)
    try:
        displayed_total = parse_displayed_count(html)
    except ExtractionError:
        displayed_total = None
    page_indicator = parse_page_indicator(html)
    current_page = page_indicator[0] if page_indicator else None
    total_pages = page_indicator[1] if page_indicator else None
    if tickers:
        return FinvizReadiness(
            ready=True,
            no_results=False,
            ticker_count=len(tickers),
            displayed_total=displayed_total,
            current_page=current_page,
            total_pages=total_pages,
            first_ticker=tickers[0],
        )
    if displayed_total == 0:
        return FinvizReadiness(
            ready=True,
            no_results=True,
            ticker_count=0,
            displayed_total=0,
            current_page=current_page,
            total_pages=total_pages,
            first_ticker=None,
        )
    return FinvizReadiness(
        ready=False,
        no_results=False,
        ticker_count=0,
        displayed_total=displayed_total,
        current_page=current_page,
        total_pages=total_pages,
        first_ticker=None,
    )


def ensure_finviz_url(url: str) -> None:
    hostname = urlparse(url).hostname or ""
    if hostname not in {"finviz.com", "www.finviz.com"}:
        raise ExtractionError(f"Finviz returned an unexpected page: final URL is {url}")


def wait_for_finviz_ready(page: Any, *, timeout_ms: int, stage: str) -> FinvizReadiness:
    deadline = time.monotonic() + timeout_ms / 1000
    last_state: FinvizReadiness | None = None
    last_transient_error: PlaywrightError | None = None
    while time.monotonic() < deadline:
        selector = detect_result_selector(page)
        if selector is not None:
            state = _state_from_locator_ready(page, selector)
            _log_state(stage, page, state)
            return state
        try:
            html = page.content()
        except PlaywrightError as exc:
            if not is_transient_navigation_error(exc):
                raise ExtractionError(
                    f"Unable to inspect Finviz page during {stage} readiness: {exc}"
                ) from exc
            last_transient_error = exc
            logger.debug(
                "Finviz page was navigating during %s readiness; retrying",
                stage,
                exc_info=exc,
            )
            _wait_briefly_for_transient_navigation(page, deadline, stage)
            continue
        state = classify_finviz_html(html)
        last_state = state
        _log_state(stage, page, state)
        if state.ready:
            if state.no_results:
                raise ExtractionError("Finviz explicitly reported zero results.")
            return state
        page.wait_for_timeout(250)
    if last_transient_error is not None and last_state is None:
        raise ExtractionError(
            f"Finviz readiness timed out during {stage} while the page remained "
            f"unstable or navigating: {last_transient_error}"
        ) from last_transient_error
    if last_state and last_state.displayed_total is not None:
        raise ExtractionError("Finviz document loaded but results were not detected.")
    raise ExtractionError("Finviz document loaded but displayed total could not be parsed.")


def is_transient_navigation_error(exc: PlaywrightError) -> bool:
    message = str(exc).lower()
    return any(term in message for term in TRANSIENT_NAVIGATION_MESSAGES)


def detect_result_selector(page: Any) -> str | None:
    for selector in RESULT_SELECTORS:
        try:
            if page.locator(selector).count() > 0:
                return selector
        except PlaywrightError as exc:
            if is_transient_navigation_error(exc):
                return None
            raise
    return None


def _state_from_locator_ready(page: Any, selector: str) -> FinvizReadiness:
    locator = page.locator(selector)
    ticker_count = int(locator.count())
    first_ticker: str | None = None
    try:
        first_ticker = str(locator.first.text_content()).strip()
    except PlaywrightError as exc:
        if not is_transient_navigation_error(exc):
            raise ExtractionError(
                f"Unable to inspect Finviz ticker locator readiness: {exc}"
            ) from exc
    return FinvizReadiness(
        ready=True,
        no_results=False,
        ticker_count=ticker_count,
        displayed_total=None,
        current_page=None,
        total_pages=None,
        first_ticker=first_ticker,
    )


def _wait_briefly_for_transient_navigation(page: Any, deadline: float, stage: str) -> None:
    remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
    with suppress(PlaywrightError):
        page.wait_for_load_state("domcontentloaded", timeout=min(1_000, remaining_ms))
    remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
    try:
        page.wait_for_timeout(min(100, remaining_ms))
    except PlaywrightError as exc:
        if not is_transient_navigation_error(exc):
            raise ExtractionError(
                f"Unable to wait for Finviz readiness during {stage}: {exc}"
            ) from exc


def wait_for_next_page_ready(
    page: Any,
    *,
    previous_first_ticker: str | None,
    previous_page_indicator: tuple[int | None, int | None],
    timeout_ms: int,
) -> FinvizReadiness:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        state = wait_for_finviz_ready(page, timeout_ms=1_000, stage="pagination")
        page_indicator = (state.current_page, state.total_pages)
        if state.first_ticker != previous_first_ticker or page_indicator != previous_page_indicator:
            return state
        page.wait_for_timeout(250)
    raise ExtractionError("Pagination page did not become ready.")


def dismiss_elite_dialog(page: Any) -> str:
    dialog = page.locator(ELITE_DIALOG_OPEN_SELECTOR)
    try:
        if dialog.count() == 0:
            logger.info("elite_dialog_absent")
            return "absent"
    except Exception:
        logger.info("elite_dialog_absent")
        return "absent"
    try:
        close_button = dialog.locator(ELITE_DIALOG_CLOSE_SELECTOR)
        close_button.click(timeout=5_000)
        _wait_for_dialog_closed(dialog, page, timeout_ms=5_000)
    except Exception as exc:
        logger.info("elite_dialog_close_click_failed", extra={"error": str(exc)})
        try:
            page.keyboard.press("Escape")
            _wait_for_dialog_closed(dialog, page, timeout_ms=2_000)
        except Exception as escape_exc:
            logger.info("elite_dialog_escape_failed", extra={"error": str(escape_exc)})
    try:
        if page.locator(ELITE_DIALOG_OPEN_SELECTOR).count() == 0:
            logger.info("elite_dialog_closed")
            return "closed"
    except Exception:
        logger.info("elite_dialog_closed")
        return "closed"
    logger.warning("elite_dialog_still_open")
    return "open"


def save_failure_diagnostics(
    page: Any,
    output_dir: Path,
    *,
    http_status: int | None,
    stage: str,
    timeout_ms: int,
) -> None:
    ensure_directory(output_dir)
    html = _safe_page_content(page)
    if html is not None:
        (output_dir / "failure-page.html").write_text(html, encoding="utf-8")
    try:
        page.screenshot(path=str(output_dir / "failure-page.png"), full_page=True)
    except PlaywrightError:  # pragma: no cover - diagnostics must not mask original failure.
        logger.exception("failure_screenshot_failed")
    metadata = FailureMetadata(
        final_url=str(getattr(page, "url", "")),
        title=_safe_title(page),
        http_status=http_status,
        ticker_link_count=len(quote_link_tickers(html or "")),
        matching_selector_counts=_safe_selector_counts(page, html or ""),
        selected_page_value=_safe_selected_page_value(page),
        page_option_values=tuple(value for value, _label in page_select_options(html or "")),
        page_option_labels=tuple(label for _value, label in page_select_options(html or "")),
        screener_total_text=_safe_text(page, SCREENER_TOTAL_SELECTOR),
        candidate_anchors=_candidate_anchor_preview(page),
        elite_dialog_open=_safe_count(page, ELITE_DIALOG_OPEN_SELECTOR) > 0,
        readiness_selector=_readiness_selector(html or ""),
        browser_timeout_stage=stage,
        configured_timeout=timeout_ms,
        current_utc_timestamp=datetime.now(UTC).isoformat(),
    )
    (output_dir / "failure-metadata.json").write_text(
        json.dumps(asdict(metadata), indent=2),
        encoding="utf-8",
    )


def _log_state(stage: str, page: Any, state: FinvizReadiness) -> None:
    logger.info(
        "page_ready" if state.ready else "page_waiting",
        extra={
            "stage": stage,
            "final_url": getattr(page, "url", ""),
            "page_title": _safe_title(page),
            "ticker_locator_count": state.ticker_count,
            "displayed_total": state.displayed_total,
            "current_page": state.current_page,
            "total_pages": state.total_pages,
        },
    )


def _safe_title(page: Any) -> str:
    try:
        return str(page.title())
    except Exception:
        return ""


def _safe_page_content(page: Any) -> str | None:
    try:
        return str(page.content())
    except PlaywrightError:
        logger.exception("failure_content_capture_failed")
        return None


def _wait_for_dialog_closed(dialog: Any, page: Any, *, timeout_ms: int) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        try:
            if page.locator(ELITE_DIALOG_OPEN_SELECTOR).count() == 0:
                return
            if dialog.get_attribute("open") is None:
                return
        except Exception:
            return
        page.wait_for_timeout(100)


def _readiness_selector(html: str) -> str | None:
    counts = selector_counts(html)
    for selector in (
        CURRENT_STRICT_SELECTOR,
        CURRENT_STRUCTURAL_SELECTOR,
        LEGACY_QUOTE_LINK_SELECTOR,
    ):
        if counts.get(selector, 0) > 0:
            return selector
    return None


def _safe_selector_counts(page: Any, html: str) -> dict[str, int]:
    counts = selector_counts(html)
    for selector in (
        CURRENT_STRICT_SELECTOR,
        CURRENT_STRUCTURAL_SELECTOR,
        LEGACY_QUOTE_LINK_SELECTOR,
        "td[data-boxover-ticker]",
        SCREENER_TOTAL_SELECTOR,
        PAGE_SELECT_SELECTOR,
        PAGE_SELECT_OPTION_SELECTOR,
        ELITE_DIALOG_OPEN_SELECTOR,
    ):
        with suppress(Exception):
            counts[selector] = int(page.locator(selector).count())
    return counts


def _safe_count(page: Any, selector: str) -> int:
    try:
        return int(page.locator(selector).count())
    except Exception:
        return 0


def _safe_text(page: Any, selector: str) -> str | None:
    try:
        locator = page.locator(selector)
        if locator.count() == 0:
            return None
        return str(locator.first.text_content()).strip()
    except Exception:
        return None


def _safe_selected_page_value(page: Any) -> str | None:
    try:
        value = page.locator(PAGE_SELECT_SELECTOR).input_value()
        return str(value)
    except Exception:
        return None


def _candidate_anchor_preview(page: Any) -> tuple[dict[str, str | None], ...]:
    script = """
    () => Array.from(document.querySelectorAll(
        'td[data-boxover-ticker] > a.tab-link, a[href*="quote.ashx?t="]'
    ))
      .slice(0, 5)
      .map((anchor) => ({
        text: anchor.textContent ? anchor.textContent.trim() : null,
        href: anchor.getAttribute('href'),
        dataTicker:
          anchor.closest('td[data-boxover-ticker]')?.getAttribute('data-boxover-ticker') ?? null
      }))
    """
    try:
        values = page.evaluate(script)
    except Exception:
        return ()
    if not isinstance(values, list):
        return ()
    preview: list[dict[str, str | None]] = []
    for value in values:
        if isinstance(value, dict):
            preview.append(
                {
                    "text": _optional_str(value.get("text")),
                    "href": _optional_str(value.get("href")),
                    "dataTicker": _optional_str(value.get("dataTicker")),
                }
            )
    return tuple(preview)


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
