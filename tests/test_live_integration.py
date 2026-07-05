from __future__ import annotations

import os

import pytest


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("FINVIZ_LIVE_TEST") != "1", reason="Live Finviz test is opt-in.")
def test_live_scan_is_opt_in() -> None:
    assert os.environ["FINVIZ_LIVE_TEST"] == "1"
