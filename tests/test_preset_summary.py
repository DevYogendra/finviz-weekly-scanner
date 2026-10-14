from __future__ import annotations

from finviz_scanner.preset_summary import summarize_preset


def test_filters_view_and_sort_are_described_without_source_url() -> None:
    summary = summarize_preset(
        "https://finviz.com/screener.ashx?v=111&f=cap_smallover,sh_price_o30"
        "&o=-marketcap&private=secret"
    )
    assert summary == {
        "filters": [
            {"label": "Market capitalization", "value": "Over $300 million", "recognized": True},
            {"label": "Share price", "value": "Over $30", "recognized": True},
        ],
        "view": "Overview",
        "sort": "Market capitalization · descending",
    }
    assert "secret" not in str(summary)
    assert "https://" not in str(summary)


def test_unknown_settings_are_explicit_and_all_filter_groups_are_kept() -> None:
    summary = summarize_preset(
        "https://finviz.com/screener.ashx?v=unknown&f=,new_filter,&f=sh_price_o30&o=new_sort"
    )
    assert summary["filters"] == [
        {"label": "Unrecognized filter", "value": "new_filter", "recognized": False},
        {"label": "Share price", "value": "Over $30", "recognized": True},
    ]
    assert summary["view"] == "Unrecognized view: unknown"
    assert summary["sort"] == "Unrecognized sort: new_sort"


def test_no_filters_and_unspecified_view_sort() -> None:
    assert summarize_preset("https://finviz.com/screener.ashx") == {
        "filters": [],
        "view": "Finviz default",
        "sort": "Finviz default",
    }
