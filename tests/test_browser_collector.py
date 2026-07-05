from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Error as PlaywrightError

from finviz_scanner.browser.finviz_browser import FinvizBrowserCollector
from finviz_scanner.errors import ExtractionError


class FakeResponse:
    status = 200


class CollectorFakeLocator:
    first: CollectorFakeLocator
    last: CollectorFakeLocator

    def __init__(self, count: int = 0) -> None:
        self._count = count
        self.first = self
        self.last = self

    def count(self) -> int:
        return self._count

    def text_content(self) -> str:
        return "AAPL"

    def input_value(self) -> str:
        return "1"

    def evaluate_all(self, _script: str) -> list[str]:
        return []

    def select_option(self, *, value: str) -> None:
        _ = value


class CollectorFakePage:
    def __init__(self, error: BaseException | None = None, urls: list[str] | None = None) -> None:
        self.error = error
        self.urls = urls if urls is not None else []
        self.url = "https://finviz.com/screener"

    def goto(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
        if self.error is not None:
            raise self.error
        self.urls.append(str(_args[0]))
        return FakeResponse()

    def content(self) -> str:
        return (
            '<html><body><div id="screener-total">#1 / 1 Total</div>'
            '<a href="quote.ashx?t=AAPL">AAPL</a></body></html>'
        )

    def title(self) -> str:
        return "Finviz"

    def locator(self, _selector: str, **_kwargs: Any) -> CollectorFakeLocator:
        return CollectorFakeLocator(0)

    def screenshot(self, *, path: str, full_page: bool) -> None:
        _ = full_page
        Path(path).write_bytes(b"fake")

    def evaluate(self, _script: str) -> list[dict[str, str]]:
        return []


class CollectorFakeBrowser:
    def __init__(self, error: BaseException | None = None, urls: list[str] | None = None) -> None:
        self.error = error
        self.urls = urls if urls is not None else []
        self.context_count = 0

    def new_context(self, *, viewport: dict[str, int]) -> CollectorFakeBrowser:
        _ = viewport
        self.context_count += 1
        return self

    def new_page(self) -> CollectorFakePage:
        return CollectorFakePage(self.error, self.urls)

    def close(self) -> None:
        return


class CollectorFakeBrowserFactory:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.launch_count = 0
        self.browser = CollectorFakeBrowser(error)

    def launch(self, *, headless: bool) -> CollectorFakeBrowser:
        _ = headless
        self.launch_count += 1
        return self.browser

    def close(self) -> None:
        return


class CollectorFakeChromium:
    def __init__(self, factory: CollectorFakeBrowserFactory) -> None:
        self.factory = factory

    def launch(self, *, headless: bool) -> CollectorFakeBrowser:
        return self.factory.launch(headless=headless)


class CollectorFakePlaywright:
    def __init__(self, factory: CollectorFakeBrowserFactory) -> None:
        self.factory = factory
        self.chromium = CollectorFakeChromium(factory)

    def __enter__(self) -> CollectorFakePlaywright:
        return self

    def __exit__(self, *_args: object) -> None:
        return


def install_fake_playwright(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException | None = None,
) -> CollectorFakeBrowserFactory:
    import playwright.sync_api

    factory = CollectorFakeBrowserFactory(error)
    monkeypatch.setattr(
        playwright.sync_api,
        "sync_playwright",
        lambda: CollectorFakePlaywright(factory),
    )
    return factory


def test_collector_converts_operational_playwright_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_playwright(monkeypatch, PlaywrightError("browser has been closed"))
    collector = FinvizBrowserCollector(output_dir=tmp_path)
    with pytest.raises(ExtractionError, match="Playwright failed while collecting"):
        collector.collect("https://finviz.com/screener")


def test_collector_preserves_existing_extraction_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_playwright(monkeypatch, ExtractionError("configured extraction failure"))
    collector = FinvizBrowserCollector(output_dir=tmp_path)
    with pytest.raises(ExtractionError, match="configured extraction failure"):
        collector.collect("https://finviz.com/screener")


def test_collector_does_not_convert_programming_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_playwright(monkeypatch, TypeError("programming defect"))
    collector = FinvizBrowserCollector(output_dir=tmp_path)
    with pytest.raises(TypeError, match="programming defect"):
        collector.collect("https://finviz.com/screener")


def test_collect_many_uses_one_browser_context_for_multiple_screens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from finviz_scanner.models import FinvizScreenConfig

    factory = install_fake_playwright(monkeypatch)
    collector = FinvizBrowserCollector(output_dir=tmp_path)
    results = collector.collect_many(
        [
            FinvizScreenConfig("stage-2", "Stage 2", "https://finviz.com/screener?v=111"),
            FinvizScreenConfig("momentum", "Momentum", "https://finviz.com/screener?v=111&f=x"),
        ],
        delay_between_screens_ms=0,
    )
    assert factory.launch_count == 1
    assert factory.browser.context_count == 1
    assert factory.browser.urls == [
        "https://finviz.com/screener?v=111",
        "https://finviz.com/screener?v=111&f=x",
    ]
    assert [result.screen.id for result in results] == ["stage-2", "momentum"]
