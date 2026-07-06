"""
Tests for the data source abstraction layer (src/sources.py).

Covers:
  - BrapiClient with mocked HTTP responses
  - YfinanceClient with mocked data
  - Unified fetch_asset_info() with fallback logic
  - Unified fetch_history() with fallback logic
  - Edge cases: empty responses, rate limiting, missing fields, errors

Run with:
  python -m pytest src/tests/test_sources.py -v --tb=short
"""
import json
import os

import pytest
from conftest import MockResponse, RateLimitedResponse
from utils import (
    make_mock_yfinance,
    make_mock_yfinance_history,
    setup_mock_brapi_fii,
    setup_mock_brapi_history,
    setup_mock_brapi_stock,
)

# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def sample_quote_payload():
    """Simulated brapi.dev stock quote response payload (data dict)."""
    return {
        "symbol": "PETR4",
        "longName": "Petróleo Brasileiro S.A. - Petrobras",
        "shortName": "PETROBRAS PN",
        "regularMarketPrice": 38.25,
        "regularMarketDayHigh": 38.45,
        "regularMarketDayLow": 37.90,
        "regularMarketChange": 0.29,
        "regularMarketChangePercent": 0.76,
        "regularMarketVolume": 10359300,
        "marketCap": 514933647834,
        "fiftyTwoWeekLow": 29.31,
        "fiftyTwoWeekHigh": 50.69,
    }


@pytest.fixture
def sample_statistics_payload():
    """Simulated brapi.dev statistics response payload (data dict)."""
    return {
        "trailingPE": 5.08,
        "priceToBook": 1.11,
        "dividendYield": 0.06,
        "trailingEps": 8.35,
        "bookValue": 34.54,
        "beta": 0.37,
        "profitMargins": 0.22,
        "marketCap": 492994040000,
    }


@pytest.fixture
def sample_financial_payload():
    """Simulated brapi.dev financial-data response payload (data dict)."""
    return {
        "returnOnEquity": 0.24,
        "returnOnAssets": 0.09,
        "totalRevenue": 498091000000,
        "ebitda": 230884000000,
    }


@pytest.fixture
def sample_profile_payload():
    """Simulated brapi.dev profile response payload (data dict)."""
    return {
        "sector": "Energy",
        "industry": "Oil & Gas",
    }


@pytest.fixture
def sample_history_payload():
    """Simulated brapi.dev historical data payload."""
    return {
        "usedInterval": "1d",
        "usedRange": "1y",
        "historicalDataPrice": [
            {"date": 1775000000, "open": 38.0, "high": 38.5, "low": 37.5, "close": 38.25, "volume": 10000000},
            {"date": 1772500000, "open": 37.5, "high": 38.0, "low": 37.0, "close": 37.80, "volume": 12000000},
            {"date": 1770000000, "open": 37.0, "high": 37.5, "low": 36.5, "close": 37.00, "volume": 15000000},
        ],
    }


@pytest.fixture
def sample_fii_payload():
    """Simulated brapi.dev FII indicators response."""
    return {
        "fiis": [{
            "symbol": "MXRF11",
            "asOfDate": "2026-05-01",
            "price": 9.76,
            "navPerShare": 9.37,
            "priceToNav": 1.04,
            "dividendYield12m": 0.122,
            "dividendYield1m": 0.0102,
            "totalInvestors": 1468513,
            "sharesOutstanding": 460269540,
            "name": "FII MAXI RENDA",
        }],
    }


@pytest.fixture
def minimal_config():
    """Minimal config for testing sources."""
    return {
        "brapi": {"token": ""},
        "pipeline": {
            "history_years": "5y",
            "history_sample_points": 60,
        },
    }


# ======================================================================
# BrapiClient Tests (mocked HTTP)
# ======================================================================

class TestBrapiClient:
    """Test BrapiClient with mocked requests."""

    # ------------------------------------------------------------------
    # fetch_stock_info
    # ------------------------------------------------------------------
    def test_fetch_stock_info_success(self, mocker, sample_quote_payload,
                                       sample_statistics_payload,
                                       sample_financial_payload,
                                       sample_profile_payload):
        """All 4 endpoints return valid data — should merge correctly."""
        from sources import BrapiClient

        mock_get = setup_mock_brapi_stock(
            mocker,
            quote=sample_quote_payload,
            stats=sample_statistics_payload,
            fin=sample_financial_payload,
            profile=sample_profile_payload,
            symbol="PETR4",
        )
        brapi = BrapiClient(token="test-token")
        info = brapi.fetch_stock_info("PETR4.SA")

        assert info is not None
        assert info.get("longName") == "Petróleo Brasileiro S.A. - Petrobras"
        assert info.get("currentPrice") == 38.25
        assert info.get("trailingPE") == 5.08
        assert info.get("priceToBook") == 1.11
        assert info.get("dividendYield") == 0.06
        assert info.get("trailingEps") == 8.35
        assert info.get("bookValue") == 34.54
        assert info.get("returnOnEquity") == 0.24
        assert info.get("sector") == "Energy"
        assert mock_get.call_count == 4  # quote + statistics + financial + profile

    def test_fetch_stock_info_quote_fails(self, mocker):
        """If quote endpoint returns empty, return {}."""
        from sources import BrapiClient

        mock_get = mocker.patch("requests.get")
        mock_get.return_value = MockResponse({"results": []})

        brapi = BrapiClient(token="test")
        info = brapi.fetch_stock_info("UNKN3.SA")
        assert info == {}

    def test_fetch_stock_info_http_error(self, mocker):
        """HTTP error should return {}."""
        from sources import BrapiClient

        mock_get = mocker.patch("requests.get")
        mock_get.side_effect = Exception("Connection error")

        brapi = BrapiClient(token=None)
        info = brapi.fetch_stock_info("FAIL.SA")
        assert info == {}

    def test_fetch_stock_info_rate_limited(self, mocker):
        """429 should raise BrapiRateLimitError."""
        from sources import BrapiClient, BrapiRateLimitError

        mock_get = mocker.patch("requests.get")
        mock_get.return_value = RateLimitedResponse()

        brapi = BrapiClient(token="test")
        with pytest.raises(BrapiRateLimitError):
            brapi.fetch_stock_info("PETR4.SA")

    def test_fetch_stock_info_partial_data(self, mocker, sample_quote_payload):
        """Only quote endpoint works — should still return partial info."""
        from sources import BrapiClient

        mock_get = setup_mock_brapi_stock(
            mocker,
            quote=sample_quote_payload,
            symbol="PETR4",
            # No stats/fin/profile → those endpoints return empty
        )
        brapi = BrapiClient(token="test")
        info = brapi.fetch_stock_info("PETR4.SA")

        assert info.get("currentPrice") == 38.25
        assert info.get("longName") == "Petróleo Brasileiro S.A. - Petrobras"
        # Statistics fields should be absent
        assert info.get("trailingPE") is None

    # ------------------------------------------------------------------
    # fetch_fii_info
    # ------------------------------------------------------------------
    def test_fetch_fii_info_success(self, mocker, sample_fii_payload):
        """FII indicators endpoint returns valid data."""
        from sources import BrapiClient

        setup_mock_brapi_fii(mocker, sample_fii_payload)
        brapi = BrapiClient(token="test")
        info = brapi.fetch_fii_info("MXRF11.SA")

        assert info is not None
        assert info.get("longName") == "FII MAXI RENDA"
        assert info.get("currentPrice") == 9.76
        assert info.get("priceToBook") == 1.04  # priceToNav → priceToBook
        assert info.get("dividendYield") == 0.122  # dividendYield12m
        assert info.get("bookValue") == 9.37  # navPerShare
        assert info.get("sector") == "Real Estate"
        # dividendRate should be estimated
        assert info.get("dividendRate") == round(9.76 * 0.122, 4)

    def test_fetch_fii_info_empty(self, mocker):
        """Empty FII indicators should return {}."""
        from sources import BrapiClient

        mock_get = mocker.patch("requests.get")
        mock_get.return_value = MockResponse({"fiis": []})

        brapi = BrapiClient(token="test")
        info = brapi.fetch_fii_info("EMPTY11.SA")
        assert info == {}

    # ------------------------------------------------------------------
    # fetch_history
    # ------------------------------------------------------------------
    def test_fetch_history_success(self, mocker, sample_history_payload):
        """Historical data should be converted to standard format."""
        from sources import BrapiClient

        setup_mock_brapi_history(mocker, sample_history_payload, symbol="PETR4")
        brapi = BrapiClient(token="test")
        history = brapi.fetch_history("PETR4.SA", period="1y", max_points=60)

        assert isinstance(history, list)
        assert len(history) == 3
        # Chronological order (reversed from API)
        assert history[0]["date"] < history[-1]["date"]
        assert "date" in history[0]
        assert "price" in history[0]
        assert history[0]["price"] > 0

    def test_fetch_history_empty(self, mocker):
        """Empty history should return []."""
        from sources import BrapiClient

        mock_get = mocker.patch("requests.get")
        mock_get.return_value = MockResponse({"results": [{"symbol": "PETR4", "data": {}}]})

        brapi = BrapiClient(token="test")
        history = brapi.fetch_history("PETR4.SA")
        assert history == []

    def test_fetch_history_rate_limited(self, mocker):
        """429 on history should raise BrapiRateLimitError."""
        from sources import BrapiClient, BrapiRateLimitError

        mock_get = mocker.patch("requests.get")
        mock_get.return_value = RateLimitedResponse()

        brapi = BrapiClient(token="test")
        with pytest.raises(BrapiRateLimitError):
            brapi.fetch_history("PETR4.SA")

    # ------------------------------------------------------------------
    # Normalize dividend yield
    # ------------------------------------------------------------------
    def test_normalize_dividend_yield(self):
        """normalize_dividend_yield should handle all input forms."""
        from sources import normalize_dividend_yield

        # brapi returns decimal (0.06)
        assert normalize_dividend_yield(0.06) == 0.06
        # yfinance sometimes returns percentage (6.0)
        assert normalize_dividend_yield(6.0) == 0.06
        # None should return 0.0
        assert normalize_dividend_yield(None) == 0.0
        # Already normalized
        assert normalize_dividend_yield(0.122) == 0.122


# ======================================================================
# YfinanceClient Tests (mocked)
# ======================================================================

class TestYfinanceClient:
    """Test YfinanceClient with mocked yfinance responses."""

    def test_fetch_stock_info_success(self, mocker):
        """yfinance returns valid stock info."""
        from sources import YfinanceClient

        make_mock_yfinance(mocker, {
            "longName": "Petrobras PN",
            "currentPrice": 38.25,
            "trailingPE": 5.08,
            "priceToBook": 1.11,
            "dividendYield": 0.06,
            "trailingEps": 8.35,
            "bookValue": 34.54,
            "returnOnEquity": 0.24,
            "sector": "Energy",
        })

        client = YfinanceClient()
        info = client.fetch_stock_info("PETR4.SA")

        assert info["longName"] == "Petrobras PN"
        assert info["currentPrice"] == 38.25
        assert info["trailingPE"] == 5.08

    def test_fetch_stock_info_empty(self, mocker):
        """yfinance returns empty info should return {}."""
        from sources import YfinanceClient

        make_mock_yfinance(mocker, info={})

        client = YfinanceClient()
        info = client.fetch_stock_info("BAD.SA")
        assert info == {}

    def test_fetch_stock_info_exception(self, mocker):
        """yfinance exception should return {}."""
        from sources import YfinanceClient

        mocker.patch("yfinance.Ticker", side_effect=Exception("Network error"))

        client = YfinanceClient()
        info = client.fetch_stock_info("FAIL.SA")
        assert info == {}

    def test_fetch_history_success(self, mocker):
        """yfinance history returns valid data."""
        from sources import YfinanceClient
        import pandas as pd

        dates = pd.date_range("2025-01-01", periods=100, freq="D")
        mock_df = pd.DataFrame({
            "Close": [float(i) for i in range(100)],
        }, index=dates)
        make_mock_yfinance_history(mocker, mock_df)

        client = YfinanceClient()
        history = client.fetch_history("PETR4.SA", period="1y", max_points=60)

        assert isinstance(history, list)
        assert len(history) > 0
        assert "date" in history[0]
        assert "price" in history[0]

    def test_fetch_history_empty(self, mocker):
        """Empty yfinance history returns []."""
        from sources import YfinanceClient
        import pandas as pd

        make_mock_yfinance_history(mocker, pd.DataFrame())

        client = YfinanceClient()
        history = client.fetch_history("PETR4.SA")
        assert history == []


# ======================================================================
# Unified fetch_asset_info Tests
# ======================================================================

class TestFetchAssetInfo:
    """Test the unified fetch_asset_info with fallback logic."""

    def test_primary_source_success(self, mocker, sample_quote_payload,
                                     sample_statistics_payload,
                                     sample_financial_payload,
                                     sample_profile_payload,
                                     minimal_config):
        """brapi.dev (primary) returns valid stock data — no fallback needed."""
        from sources import fetch_asset_info

        setup_mock_brapi_stock(
            mocker,
            quote=sample_quote_payload,
            stats=sample_statistics_payload,
            fin=sample_financial_payload,
            profile=sample_profile_payload,
            symbol="PETR4",
        )

        info = fetch_asset_info("PETR4.SA", "stock", minimal_config)

        assert info is not None
        assert info["longName"] == "Petróleo Brasileiro S.A. - Petrobras"
        assert info["currentPrice"] == 38.25
        assert info["trailingPE"] == 5.08
        assert info["returnOnEquity"] == 0.24

    def test_primary_fails_fallback_succeeds(self, mocker, minimal_config):
        """brapi.dev fails — yfinance fallback should work."""
        from sources import fetch_asset_info

        mock_get = mocker.patch("requests.get")
        mock_get.side_effect = Exception("brapi.dev network error")

        make_mock_yfinance(mocker, {
            "longName": "Petrobras PN",
            "currentPrice": 38.25,
            "trailingPE": 5.08,
            "priceToBook": 1.11,
            "dividendYield": 0.06,
            "trailingEps": 8.35,
            "bookValue": 34.54,
            "returnOnEquity": 0.24,
            "sector": "Energy",
        })

        info = fetch_asset_info("PETR4.SA", "stock", minimal_config)

        assert info is not None
        assert info["longName"] == "Petrobras PN"
        assert mock_get.called  # brapi was tried
        # Verify yfinance was called as fallback
        assert info["currentPrice"] == 38.25

    def test_both_sources_fail(self, mocker, minimal_config):
        """Both sources fail — should return {}."""
        from sources import fetch_asset_info

        mocker.patch("requests.get", side_effect=Exception("Network error"))
        make_mock_yfinance(mocker, info={})

        info = fetch_asset_info("BOGUS.SA", "stock", minimal_config)
        assert info == {}

    def test_primary_fii_success(self, mocker, minimal_config):
        """yfinance fetches FII data successfully (BRAPI is skipped for FIIs)."""
        from sources import fetch_asset_info

        make_mock_yfinance(mocker, {
            "longName": "MXRF11 Fundo Imobiliario",
            "currentPrice": 9.76,
            "priceToBook": 1.04,
            "dividendYield": 0.122,
            "dividendRate": 1.19,
            "lastDividendValue": 0.10,
        })

        info = fetch_asset_info("MXRF11.SA", "fii", minimal_config)

        assert info is not None
        assert info["longName"] == "MXRF11 Fundo Imobiliario"
        assert info["currentPrice"] == 9.76
        assert info["priceToBook"] == 1.04

    def test_fiagro_uses_fii_endpoint(self, mocker, minimal_config):
        """FIAGRO assets use the same yfinance path as FIIs."""
        from sources import fetch_asset_info

        make_mock_yfinance(mocker, {
            "longName": "KNCA11 Fundo Agro",
            "currentPrice": 9.76,
            "dividendYield": 0.122,
            "dividendRate": 1.19,
            "lastDividendValue": 0.10,
        })

        info = fetch_asset_info("KNCA11.SA", "fiagro", minimal_config)

        assert info is not None
        assert info["currentPrice"] == 9.76  # Same as mocked yfinance data

    def test_rate_limit_fallback(self, mocker, minimal_config):
        """Rate limited brapi should trigger yfinance fallback."""
        from sources import fetch_asset_info

        mock_get = mocker.patch("requests.get")
        mock_get.return_value = RateLimitedResponse()

        make_mock_yfinance(mocker, {
            "longName": "Petrobras PN",
            "currentPrice": 38.25,
            "trailingPE": 5.08,
        })

        info = fetch_asset_info("PETR4.SA", "stock", minimal_config)

        assert info is not None
        assert info["longName"] == "Petrobras PN"
        assert info["currentPrice"] == 38.25


# ======================================================================
# Unified fetch_history Tests
# ======================================================================

class TestFetchHistory:
    """Test the unified fetch_history with fallback logic."""

    def test_primary_history_success(self, mocker, sample_history_payload,
                                       minimal_config):
        """brapi.dev history returns valid data."""
        from sources import fetch_history

        setup_mock_brapi_history(mocker, sample_history_payload, symbol="PETR4")

        hist_json = fetch_history("PETR4.SA", minimal_config, period="1y", max_points=60)
        data = json.loads(hist_json)

        assert isinstance(data, list)
        assert len(data) == 3
        assert data[0]["price"] > 0

    def test_primary_fails_fallback_history(self, mocker, minimal_config):
        """brapi.dev history fails — yfinance fallback."""
        from sources import fetch_history
        import pandas as pd

        mock_get = mocker.patch("requests.get")
        mock_get.side_effect = Exception("brapi error")

        dates = pd.date_range("2025-01-01", periods=10, freq="D")
        mock_df = pd.DataFrame({"Close": [float(i) for i in range(10)]}, index=dates)
        make_mock_yfinance_history(mocker, mock_df)

        hist_json = fetch_history("PETR4.SA", minimal_config, period="1y", max_points=60)
        data = json.loads(hist_json)

        assert isinstance(data, list)
        assert len(data) > 0

    def test_both_history_fail(self, mocker, minimal_config):
        """Both sources fail for history — should return []."""
        from sources import fetch_history
        import pandas as pd

        mock_get = mocker.patch("requests.get")
        mock_get.side_effect = Exception("brapi error")

        make_mock_yfinance_history(mocker, pd.DataFrame())

        hist_json = fetch_history("FAIL.SA", minimal_config)
        assert hist_json == "[]"


# ======================================================================
# Cross-module Consistency
# ======================================================================

class TestSourceAnalyzerCompatibility:
    """Verify that sources.py output is compatible with analyzer.py."""

    def test_source_output_has_all_analyzer_keys(self, mocker,
                                                   sample_quote_payload,
                                                   sample_statistics_payload,
                                                   sample_financial_payload,
                                                   minimal_config):
        """Stock info from sources should have all keys that analyzer needs."""
        from sources import fetch_asset_info
        import analyzer

        setup_mock_brapi_stock(
            mocker,
            quote=sample_quote_payload,
            stats=sample_statistics_payload,
            fin=sample_financial_payload,
            profile={"sector": "Energy"},
            symbol="PETR4",
        )

        info = fetch_asset_info("PETR4.SA", "stock", minimal_config)

        # analyzer.analyze_stock expects these keys in the info dict
        required = ["currentPrice", "trailingEps", "bookValue",
                     "trailingPE", "priceToBook", "dividendYield",
                     "returnOnEquity", "longName", "sector"]
        present = [k for k in required if info.get(k) is not None]
        # At least 7 of 9 should be present
        assert len(present) >= 7, (
            f"Source output missing analyzer keys. "
            f"Found: {present}, Missing: {set(required) - set(present)}"
        )

        # Now actually run the analyzer
        result = analyzer.analyze_stock("PETR4.SA", info)
        assert result["ticker"] == "PETR4.SA"
        assert result["name"] is not None
        assert isinstance(result["score"], int)
        assert 0 <= result["score"] <= 5

    def test_fii_source_analyzer_compatible(self, mocker,
                                              sample_fii_payload,
                                              minimal_config):
        """FII info from sources should work with analyzer.analyze_fii."""
        from sources import fetch_asset_info
        import analyzer

        setup_mock_brapi_fii(mocker, sample_fii_payload)

        info = fetch_asset_info("MXRF11.SA", "fii", minimal_config)

        # analyzer needs: currentPrice, priceToBook, dividendYield, longName
        assert info.get("currentPrice") is not None, "FII source missing currentPrice"
        assert info.get("priceToBook") is not None, "FII source missing priceToBook"

        # Run analyzer
        result = analyzer.analyze_fii("MXRF11.SA", info)
        assert result["ticker"] == "MXRF11.SA"
        assert isinstance(result["score"], int)
        assert 0 <= result["score"] <= 5
