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


class CollectorFakePage:
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.url = "https://finviz.com/screener"

    def goto(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
        raise self.error

    def content(self) -> str:
        return "<html><body>#1 / 44 Total</body></html>"

    def title(self) -> str:
        return "Finviz"

    def locator(self, _selector: str) -> CollectorFakeLocator:
        return CollectorFakeLocator(0)

    def screenshot(self, *, path: str, full_page: bool) -> None:
        _ = full_page
        Path(path).write_bytes(b"fake")

    def evaluate(self, _script: str) -> list[dict[str, str]]:
        return []


class CollectorFakeBrowser:
    def __init__(self, error: BaseException) -> None:
        self.error = error

    def new_page(self, *, viewport: dict[str, int]) -> CollectorFakePage:
        _ = viewport
        return CollectorFakePage(self.error)

    def close(self) -> None:
        return


class CollectorFakeChromium:
    def __init__(self, error: BaseException) -> None:
        self.error = error

    def launch(self, *, headless: bool) -> CollectorFakeBrowser:
        _ = headless
        return CollectorFakeBrowser(self.error)


class CollectorFakePlaywright:
    def __init__(self, error: BaseException) -> None:
        self.chromium = CollectorFakeChromium(error)

    def __enter__(self) -> CollectorFakePlaywright:
        return self

    def __exit__(self, *_args: object) -> None:
        return


def install_fake_playwright(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
    import playwright.sync_api

    monkeypatch.setattr(
        playwright.sync_api,
        "sync_playwright",
        lambda: CollectorFakePlaywright(error),
    )


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
