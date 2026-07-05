"""Playwright collection of Finviz result pages."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from finviz_scanner.browser.readiness import (
    dismiss_elite_dialog,
    ensure_finviz_url,
    save_failure_diagnostics,
    wait_for_finviz_ready,
    wait_for_next_page_ready,
)
from finviz_scanner.errors import CaptchaError, ExtractionError
from finviz_scanner.extraction.finviz_dom import (
    extract_rows_from_html,
    page_select_options,
    page_signature,
    parse_displayed_count,
    parse_page_indicator,
)
from finviz_scanner.models import PageCapture
from finviz_scanner.utils import ensure_directory

logger = logging.getLogger(__name__)


class FinvizBrowserCollector:
    def __init__(
        self,
        *,
        output_dir: Path,
        headed: bool = False,
        max_pages: int = 50,
        readiness_timeout_ms: int = 45_000,
    ) -> None:
        self.output_dir = output_dir
        self.headed = headed
        self.max_pages = max_pages
        self.readiness_timeout_ms = readiness_timeout_ms

    def collect(self, url: str) -> tuple[PageCapture, ...]:
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - exercised by doctor when missing.
            raise ExtractionError("Playwright is not installed.") from exc

        screenshot_dir = ensure_directory(self.output_dir / "screenshots")
        html_dir = ensure_directory(self.output_dir / "html")
        pages: list[PageCapture] = []
        signatures: set[tuple[str, ...]] = set()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not self.headed)
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            http_status: int | None = None
            try:
                logger.info("navigation_started", extra={"url": url})
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                    http_status = response.status if response is not None else None
                    logger.info("domcontentloaded", extra={"url": page.url})
                except PlaywrightTimeoutError as exc:
                    try:
                        wait_for_finviz_ready(
                            page,
                            timeout_ms=1_000,
                            stage="navigation_timeout_probe",
                        )
                    except Exception:
                        save_failure_diagnostics(
                            page,
                            self.output_dir,
                            http_status=http_status,
                            stage="navigation",
                            timeout_ms=60_000,
                        )
                        raise ExtractionError(
                            "Navigation timed out before document creation."
                        ) from exc
                    logger.info("domcontentloaded", extra={"url": page.url})
                ensure_finviz_url(page.url)
                logger.info(
                    "navigation_status",
                    extra={
                        "http_status": http_status,
                        "final_url": page.url,
                        "page_title": page.title(),
                    },
                )
                wait_for_finviz_ready(
                    page,
                    timeout_ms=self.readiness_timeout_ms,
                    stage="initial",
                )
                option_values = _page_option_values(page)
                if option_values:
                    pages.extend(
                        self._collect_select_pages(
                            page,
                            option_values[: self.max_pages],
                            signatures,
                            screenshot_dir,
                            html_dir,
                        )
                    )
                else:
                    pages.extend(
                        self._collect_legacy_next_pages(
                            page,
                            signatures,
                            screenshot_dir,
                            html_dir,
                        )
                    )
            except PlaywrightTimeoutError as exc:
                save_failure_diagnostics(
                    page,
                    self.output_dir,
                    http_status=http_status,
                    stage="playwright_timeout",
                    timeout_ms=self.readiness_timeout_ms,
                )
                raise ExtractionError(
                    "Finviz document loaded but results were not detected."
                ) from exc
            except (CaptchaError, ExtractionError) as exc:
                save_failure_diagnostics(
                    page,
                    self.output_dir,
                    http_status=http_status,
                    stage="readiness",
                    timeout_ms=self.readiness_timeout_ms,
                )
                raise exc
            except PlaywrightError as exc:
                save_failure_diagnostics(
                    page,
                    self.output_dir,
                    http_status=http_status,
                    stage="playwright_operational_error",
                    timeout_ms=self.readiness_timeout_ms,
                )
                raise ExtractionError(
                    f"Playwright failed while collecting the Finviz screen: {exc}"
                ) from exc
            finally:
                browser.close()
        if not pages:
            raise CaptchaError("No pages were collected.")
        return tuple(pages)

    def _capture_current_page(
        self,
        page: Any,
        *,
        page_number: int,
        signatures: set[tuple[str, ...]],
        screenshot_dir: Path,
        html_dir: Path,
    ) -> tuple[PageCapture, tuple[str, ...], tuple[int | None, int | None]]:
        html = page.content()
        displayed_total = parse_displayed_count(html)
        page_indicator = parse_page_indicator(html)
        logger.info(
            "page_ready",
            extra={
                "displayed_total": displayed_total,
                "current_page": page_indicator[0] if page_indicator else None,
                "total_pages": page_indicator[1] if page_indicator else None,
            },
        )
        rows = extract_rows_from_html(
            html,
            page_number=page_number,
            source_url=page.url,
        )
        signature = page_signature(rows)
        if signature in signatures:
            raise ExtractionError(f"Repeated page loop detected at page {page_number}.")
        signatures.add(signature)
        screenshot = screenshot_dir / f"page-{page_number:02d}.png"
        page.screenshot(path=str(screenshot), full_page=True)
        html_path = html_dir / f"page-{page_number:02d}.html"
        html_path.write_text(html, encoding="utf-8")
        return (
            PageCapture(page_number, page.url, html, screenshot),
            signature,
            (
                page_indicator[0] if page_indicator else None,
                page_indicator[1] if page_indicator else None,
            ),
        )

    def _collect_select_pages(
        self,
        page: Any,
        option_values: list[str],
        signatures: set[tuple[str, ...]],
        screenshot_dir: Path,
        html_dir: Path,
    ) -> list[PageCapture]:
        captures: list[PageCapture] = []
        previous_signature: tuple[str, ...] | None = None
        previous_indicator: tuple[int | None, int | None] = (None, None)
        for page_index, option_value in enumerate(option_values, start=1):
            if page_index > 1:
                dismiss_elite_dialog(page)
                _select_page_option(page, option_value)
                wait_for_next_page_ready(
                    page,
                    previous_first_ticker=previous_signature[0] if previous_signature else None,
                    previous_page_indicator=previous_indicator,
                    timeout_ms=self.readiness_timeout_ms,
                )
            capture, previous_signature, previous_indicator = self._capture_current_page(
                page,
                page_number=page_index,
                signatures=signatures,
                screenshot_dir=screenshot_dir,
                html_dir=html_dir,
            )
            captures.append(capture)
        return captures

    def _collect_legacy_next_pages(
        self,
        page: Any,
        signatures: set[tuple[str, ...]],
        screenshot_dir: Path,
        html_dir: Path,
    ) -> list[PageCapture]:
        captures: list[PageCapture] = []
        for page_number in range(1, self.max_pages + 1):
            capture, signature, page_indicator = self._capture_current_page(
                page,
                page_number=page_number,
                signatures=signatures,
                screenshot_dir=screenshot_dir,
                html_dir=html_dir,
            )
            captures.append(capture)
            dismiss_elite_dialog(page)
            if not _click_next(page):
                break
            wait_for_next_page_ready(
                page,
                previous_first_ticker=signature[0] if signature else None,
                previous_page_indicator=page_indicator,
                timeout_ms=self.readiness_timeout_ms,
            )
        return captures


def _click_next(page: Any) -> bool:
    next_link = page.locator("a", has_text="Next").last
    if next_link.count() == 0:
        return False
    classes = next_link.get_attribute("class") or ""
    if "disabled" in classes.lower():
        return False
    next_link.click()
    return True


def _page_option_values(page: Any) -> list[str]:
    html_options = [value for value, _label in page_select_options(page.content()) if value]
    if html_options:
        return html_options
    locator = page.locator("#pageSelect option")
    try:
        values = locator.evaluate_all("(options) => options.map((option) => option.value)")
    except Exception:
        return []
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value)]


def _select_page_option(page: Any, option_value: str) -> None:
    page_select = page.locator("#pageSelect")
    try:
        current_value = str(page_select.input_value())
    except Exception:
        current_value = ""
    if current_value == option_value:
        return
    page_select.select_option(value=option_value)
    page.wait_for_function(
        """
        ([selector, expected]) => {
            const select = document.querySelector(selector);
            return select && select.value === expected;
        }
        """,
        arg=["#pageSelect", option_value],
        timeout=15_000,
    )
