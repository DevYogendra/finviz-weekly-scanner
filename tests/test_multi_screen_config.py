from __future__ import annotations

import pytest

from finviz_scanner.config import FinvizConfig, ScreenConfig

URL = "https://finviz.com/screener.ashx?v=111&f=cap_smallover"


def test_one_screen_configuration_resolves_domain_model() -> None:
    config = FinvizConfig(screens=[ScreenConfig(id="stage-2", name="Stage 2", url=URL)])
    screens = config.resolved_screens()
    assert screens[0].id == "stage-2"
    assert screens[0].enabled is True
    assert config.tradingview_filename_for(screens[0]) == "stage-2.txt"


def test_disabled_screen_defaults_to_disabled_state() -> None:
    config = FinvizConfig(
        screens=[ScreenConfig(id="momentum", name="Momentum", url=URL, enabled=False)]
    )
    assert config.resolved_screens()[0].enabled is False


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="screen IDs must be unique"):
        FinvizConfig(
            screens=[
                ScreenConfig(id="stage-2", name="Stage 2", url=URL),
                ScreenConfig(id="stage-2", name="Other", url=URL),
            ]
        )


def test_case_insensitive_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="Screen ID must match"):
        ScreenConfig(id="Stage-2", name="Stage 2", url=URL)


@pytest.mark.parametrize("screen_id", ["Stage 2", "../output", "stage/2", "C:\\stage2"])
def test_invalid_ids_are_rejected(screen_id: str) -> None:
    with pytest.raises(ValueError, match="Screen ID must match"):
        ScreenConfig(id=screen_id, name="Bad", url=URL)


def test_duplicate_output_filenames_are_rejected() -> None:
    with pytest.raises(ValueError, match="both resolve to output file"):
        FinvizConfig(
            screens=[
                ScreenConfig(id="stage-2", name="Stage 2", url=URL),
                ScreenConfig(
                    id="momentum",
                    name="Momentum",
                    url=URL,
                    tradingview_filename="stage-2.txt",
                ),
            ]
        )


def test_malformed_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        ScreenConfig(id="stage-2", name="Stage 2", url="http://finviz.com/screener")


def test_saved_screen_url_becomes_default_screen() -> None:
    config = FinvizConfig(saved_screen_url=URL)
    screen = config.resolved_screens()[0]
    assert screen.id == "default"
    assert screen.name == "Default Screen"
    assert screen.url == URL


def test_both_old_and_new_formats_are_rejected() -> None:
    with pytest.raises(ValueError, match=r"either finviz\.screens or finviz\.saved_screen_url"):
        FinvizConfig(
            saved_screen_url=URL,
            screens=[ScreenConfig(id="stage-2", name="Stage 2", url=URL)],
        )


def test_no_screens_configured_is_rejected() -> None:
    with pytest.raises(ValueError, match="At least one Finviz screen"):
        FinvizConfig()
