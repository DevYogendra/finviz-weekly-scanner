"""Offline, display-safe descriptions of configured Finviz screen settings."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

# Verified against Finviz's filter labels. Never infer an unknown filter's meaning.
FILTER_LABELS: dict[str, tuple[str, str]] = {
    "cap_smallover": ("Market capitalization", "Over $300 million"),
    "sh_avgvol_o2000": ("Average daily volume", "Over 2 million shares"),
    "sh_price_o30": ("Share price", "Over $30"),
    "ta_averagetruerange_o2": ("Average true range (ATR)", "Over $2"),
    "ta_highlow52w_b0to10h": ("52-week high", "Price is 0-10% below the high"),
    "ta_perf_13w20o": ("Quarter performance", "Over +20%"),
    "ta_sma20_sa50": ("20-day moving average", "Above the 50-day moving average"),
    "ta_sma200_pa": ("Share price vs. 200-day average", "Above the 200-day moving average"),
    "ta_sma50_sa200": ("50-day moving average", "Above the 200-day moving average"),
}
VIEW_LABELS = {
    "111": "Overview",
    "121": "Valuation",
    "161": "Financial",
    "131": "Ownership",
    "141": "Performance",
    "171": "Technical",
}
SORT_LABELS = {
    "ticker": "Ticker",
    "company": "Company",
    "marketcap": "Market capitalization",
    "price": "Share price",
    "volume": "Volume",
    "change": "Price change",
}


def summarize_preset(url: str) -> dict[str, object]:
    """Describe URL filters without returning the source URL or unrelated parameters."""
    parameters = parse_qs(urlparse(url).query)
    filters = []
    for group in parameters.get("f", []):
        for code in group.split(","):
            code = code.strip()
            if not code:
                continue
            known = code in FILTER_LABELS
            label, value = FILTER_LABELS.get(code, ("Unrecognized filter", code))
            filters.append({"label": label, "value": value, "recognized": known})
    view_code = parameters.get("v", [""])[0]
    order = parameters.get("o", [""])[0]
    sort_code = order.removeprefix("-")
    sort_label = SORT_LABELS.get(sort_code)
    sort = (
        f"{sort_label} · {'descending' if order.startswith('-') else 'ascending'}"
        if sort_label
        else f"Unrecognized sort: {order}"
        if order
        else "Finviz default"
    )
    return {
        "filters": filters,
        "view": VIEW_LABELS.get(view_code, f"Unrecognized view: {view_code}")
        if view_code
        else "Finviz default",
        "sort": sort,
    }
