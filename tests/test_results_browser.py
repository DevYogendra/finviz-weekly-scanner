"""Offline browser behavior tests against a loopback server and synthetic scan data."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.sync_api import Error, Page, expect, sync_playwright

from finviz_scanner.storage.sqlite import SQLiteStore
from tests.test_results import save_run, symbol


@pytest.fixture
def results_page(results_server: tuple[str, SQLiteStore]) -> Iterator[Page]:
    url, _ = results_server
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Error:
            pytest.skip("Offline UI tests require installed Playwright Chromium.")
        context = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()
        page.goto(url)
        expect(page.locator("#watchlist-preview")).to_have_value("NASDAQ:BBB,NASDAQ:AAA")
        try:
            yield page
        finally:
            context.close()
            browser.close()


def test_selection_filters_sort_and_screen_switch(results_page: Page) -> None:
    page = results_page
    page.get_by_role("checkbox", name="Select AAA", exact=True).uncheck()
    page.locator("#results-search").fill("AAA")
    expect(page.locator("#watchlist-preview")).to_have_value("NASDAQ:BBB")
    page.locator("#select-visible").click()
    expect(page.locator("#watchlist-preview")).to_have_value("NASDAQ:BBB,NASDAQ:AAA")
    page.locator("#results-search").fill("")
    page.get_by_role("button", name="Ticker", exact=True).click()
    expect(page.locator("#results-body tr").first).to_contain_text("AAA")
    expect(page.locator("#watchlist-preview")).to_have_value("NASDAQ:BBB,NASDAQ:AAA")
    page.get_by_role("checkbox", name="Select AAA", exact=True).uncheck()
    page.locator("#screen-selector").select_option("momentum")
    expect(page.locator("#watchlist-preview")).to_have_value("NASDAQ:DDD")
    page.locator("#screen-selector").select_option("stage-2")
    expect(page.locator("#watchlist-preview")).to_have_value("NASDAQ:BBB")
    page.locator('[data-result-tab="removals"]').click()
    expect(page.locator("#results-body")).to_contain_text("CCC")
    expect(page.locator("#results-body input")).to_have_count(0)
    expect(page.locator("#select-visible")).to_be_disabled()
    expect(page.locator("#watchlist-preview")).to_have_value("NASDAQ:BBB")
    page.locator("#clear-selection").click()
    expect(page.locator("#copy-selected")).to_be_disabled()
    expect(page.locator("#download-selected")).to_be_disabled()


def test_preset_summary_follows_selected_screen(results_page: Page) -> None:
    page = results_page
    expect(page.locator("#preset-title")).to_have_text("Stage 2 Candidates · preset settings")
    expect(page.locator("#preset-options")).to_contain_text("Over $300 million")
    expect(page.locator("#preset-count")).to_have_text("1 filter")
    expect(page.locator("#preset-context")).to_contain_text("View: Overview")
    page.locator("#screen-selector").select_option("momentum")
    expect(page.locator("#preset-title")).to_have_text("Momentum Candidates · preset settings")
    expect(page.locator("#preset-options")).to_contain_text("Over $30")
    expect(page.locator("#preset-options")).not_to_contain_text("Market capitalization")


def test_missing_results_workspace_has_actionable_error(results_page: Page) -> None:
    page = results_page
    page.route("**/results.js", lambda route: route.fulfill(status=404, body="Not found"))
    page.reload()
    expect(page.locator("#current-state")).to_have_text("Dashboard needs reopening")
    expect(page.locator("#results-error")).to_be_visible()
    expect(page.locator("#results-error")).to_contain_text("Reopen the dashboard using web.bat")


def test_clipboard_download_and_failure(results_page: Page) -> None:
    page = results_page
    page.locator("#copy-selected").click()
    expect(page.locator("#export-feedback")).to_have_text("Watchlist copied.")
    assert page.evaluate("navigator.clipboard.readText()") == "NASDAQ:BBB,NASDAQ:AAA"
    with page.expect_download() as event:
        page.locator("#download-selected").click()
    download = event.value
    assert download.suggested_filename == "stage-2-selected.txt"
    assert download.path().read_text(encoding="utf-8") == "NASDAQ:BBB,NASDAQ:AAA"
    page.evaluate(
        "() => { navigator.clipboard.writeText = async () => {throw new Error('Denied');}; }"
    )
    page.locator("#copy-selected").click()
    expect(page.locator("#export-feedback")).to_contain_text("Clipboard unavailable")
    expect(page.locator("#watchlist-preview")).to_be_focused()
    assert page.locator("#watchlist-preview").evaluate(
        "element => element.selectionEnd - element.selectionStart"
    ) == len("NASDAQ:BBB,NASDAQ:AAA")


def test_new_success_requires_update_and_integrity_failure_disables_export(
    results_page: Page, results_server: tuple[str, SQLiteStore]
) -> None:
    page = results_page
    _, store = results_server
    page.get_by_role("checkbox", name="Select AAA", exact=True).uncheck()
    save_run(store, "newest", (symbol("EEE"), symbol("FFF", 2)), screen_id="stage-2", day=3)
    expect(page.locator("#update-results")).to_be_visible(timeout=10000)
    expect(page.locator("#watchlist-preview")).to_have_value("NASDAQ:BBB")
    page.locator("#update-results").click()
    expect(page.locator("#watchlist-preview")).to_have_value("NASDAQ:EEE,NASDAQ:FFF")
    save_run(store, "incomplete", (symbol("GGG"),), screen_id="stage-2", day=4, count=2)
    expect(page.locator("#results-error")).to_contain_text("incomplete", timeout=10000)
    expect(page.locator("#copy-selected")).to_be_disabled()
    expect(page.locator("#download-selected")).to_be_disabled()


def test_keyboard_selection_and_mobile_columns(results_page: Page) -> None:
    page = results_page
    page.set_viewport_size({"width": 390, "height": 844})
    checkbox = page.get_by_role("checkbox", name="Select AAA", exact=True)
    checkbox.focus()
    page.keyboard.press("Space")
    expect(checkbox).not_to_be_checked()
    expect(page.locator("#watchlist-preview")).to_have_value("NASDAQ:BBB")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    expect(page.get_by_role("button", name="Company", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Exchange", exact=True)).to_be_visible()
    page.locator("#copy-selected").focus()
    page.keyboard.press("Enter")
    expect(page.locator("#export-feedback")).to_have_text("Watchlist copied.")
