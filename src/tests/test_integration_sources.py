"""
Integration tests for sources.py — make REAL calls to brapi.dev.

These tests require internet access and are skipped by default.
Run with:  python -m pytest src/tests/test_integration_sources.py -v --run-network

All tests use PUBLIC test tickers (no BRAPI token required).
"""
import json

import pytest

network = pytest.mark.network


# ======================================================================
# Live brapi.dev connectivity tests
# ======================================================================

class TestBrapiLiveConnectivity:
    """Make real calls to brapi.dev for publicly accessible tickers.

    These work WITHOUT a token (public test tickers).
    """

    @network
    def test_brapi_live_stock_quote(self):
        """PETR4 should return quote data without token."""
        from sources import BrapiClient

        brapi = BrapiClient(token=None)
        info = brapi.fetch_stock_info("PETR4.SA")

        assert info is not None, "brapi.dev returned None for PETR4"
        assert info.get("longName"), "No longName for PETR4"
        assert info.get("currentPrice") is not None, "No price for PETR4"
        if info.get("currentPrice") is not None:
            assert info["currentPrice"] > 0, f"Price should be > 0, got {info['currentPrice']}"

    @network
    def test_brapi_live_stock_statistics(self):
        """PETR4 statistics should include P/E, P/B, DY, EPS, BV."""
        from sources import BrapiClient

        brapi = BrapiClient(token=None)
        info = brapi.fetch_stock_info("PETR4.SA")

        fundamentals = [
            ("trailingPE", info.get("trailingPE")),
            ("priceToBook", info.get("priceToBook")),
            ("dividendYield", info.get("dividendYield")),
            ("trailingEps", info.get("trailingEps")),
            ("bookValue", info.get("bookValue")),
        ]
        present = [name for name, val in fundamentals if val is not None]
        assert len(present) >= 3, (
            f"PETR4 missing most fundamentals via brapi.dev. "
            f"Found only: {present}"
        )

    @network
    def test_brapi_live_fii(self):
        """MXRF11 should return FII indicator data without token."""
        from sources import BrapiClient

        brapi = BrapiClient(token=None)
        info = brapi.fetch_fii_info("MXRF11.SA")

        assert info is not None, "brapi.dev returned None for MXRF11"
        if info.get("currentPrice") is not None:
            assert info["currentPrice"] > 0, f"Price should be > 0, got {info['currentPrice']}"

    @network
    def test_brapi_live_history(self):
        """PETR4 history should contain date/price points."""
        from sources import BrapiClient

        brapi = BrapiClient(token=None)
        history = brapi.fetch_history("PETR4.SA", period="1y", max_points=60)

        assert isinstance(history, list), "History should be a list"
        if len(history) > 0:
            assert "date" in history[0], "Missing date in history point"
            assert "price" in history[0], "Missing price in history point"
            assert history[0]["price"] > 0, "Price should be positive"

    @network
    def test_live_fetch_asset_info_fallback(self):
        """Unified fetch_asset_info should work without token."""
        from sources import fetch_asset_info

        config = {"brapi": {"token": ""}, "pipeline": {}}
        info = fetch_asset_info("ITUB4.SA", "stock", config)

        assert info is not None
        assert info.get("longName") or info.get("shortName"), "No name for ITUB4"
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price is not None:
            assert price > 0, f"Price should be > 0, got {price}"

    @network
    def test_live_fetch_history_fallback(self):
        """Without token, history should still work via fallback."""
        from sources import fetch_history

        config = {"brapi": {"token": ""}, "pipeline": {}}
        hist_json = fetch_history("PETR4.SA", config, period="1y", max_points=30)
        data = json.loads(hist_json)

        if len(data) > 0:
            assert data[0]["price"] > 0
