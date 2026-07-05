"""
Test utilities for Radar Fundamentalista B3.

Provides helper functions that reduce boilerplate in test files:
  - setup_mock_brapi_stock()    — patch requests.get for stock data
  - setup_mock_brapi_fii()      — patch requests.get for FII data
  - setup_mock_brapi_history()  — patch requests.get for history data
  - make_mock_yfinance()        — patch yfinance.Ticker for info
  - make_mock_yfinance_history()— patch yfinance.Ticker for history
"""
import json
from typing import Any

from conftest import MockResponse


# ---------------------------------------------------------------------------
# brapi.dev mock helpers
# ---------------------------------------------------------------------------

def setup_mock_brapi_stock(
    mocker,
    quote: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
    fin: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    symbol: str = "TEST",
) -> Any:
    """Patch ``requests.get`` to simulate brapi.dev stock-info endpoints.

    Each endpoint (quote, statistics, financial-data, profile) returns a
    ``MockResponse`` wrapping the provided payload.  Endpoints without a
    payload return an empty result set, allowing partial-data scenarios.

    Returns the ``mock_get`` instance for additional assertions (e.g.
    ``call_count``).
    """
    mock_get = mocker.patch("requests.get")

    def side_effect(url: str, **kwargs) -> MockResponse:
        if "quote" in url and quote is not None:
            return MockResponse({"results": [{"symbol": symbol, "data": quote}]})
        elif "statistics" in url and stats is not None:
            return MockResponse({"results": [{"symbol": symbol, "data": stats}]})
        elif "financial-data" in url and fin is not None:
            return MockResponse({"results": [{"symbol": symbol, "data": fin}]})
        elif "profile" in url and profile is not None:
            return MockResponse({"results": [{"symbol": symbol, "data": profile}]})
        return MockResponse({"results": []})

    mock_get.side_effect = side_effect
    return mock_get


def setup_mock_brapi_fii(
    mocker,
    payload: dict[str, Any],
) -> Any:
    """Patch ``requests.get`` to simulate a brapi.dev FII indicators response."""
    mock_get = mocker.patch("requests.get")
    mock_get.return_value = MockResponse(payload)
    return mock_get


def setup_mock_brapi_history(
    mocker,
    payload: dict[str, Any],
    symbol: str = "TEST",
) -> Any:
    """Patch ``requests.get`` to simulate a brapi.dev history response."""
    mock_get = mocker.patch("requests.get")
    mock_get.return_value = MockResponse({
        "results": [{"symbol": symbol, "data": payload}],
    })
    return mock_get


# ---------------------------------------------------------------------------
# yfinance mock helpers
# ---------------------------------------------------------------------------

def make_mock_yfinance(mocker, info: dict[str, Any] | None = None) -> Any:
    """Patch ``yfinance.Ticker`` to return a mock with the given *info* dict.

    The returned mock can be further configured (e.g. ``mock.history``).
    """
    mock_ticker = mocker.MagicMock()
    mock_ticker.info = info or {}
    mocker.patch("yfinance.Ticker", return_value=mock_ticker)
    return mock_ticker


def make_mock_yfinance_history(
    mocker,
    df: Any,  # pandas DataFrame
) -> Any:
    """Patch ``yfinance.Ticker`` to return a DataFrame from ``.history()``.

    Usage::

        import pandas as pd
        dates = pd.date_range("2025-01-01", periods=10, freq="D")
        df = pd.DataFrame({"Close": [float(i) for i in range(10)]}, index=dates)
        make_mock_yfinance_history(mocker, df)
    """
    mock_ticker = mocker.MagicMock()
    mock_ticker.history.return_value = df
    mocker.patch("yfinance.Ticker", return_value=mock_ticker)
    return mock_ticker
