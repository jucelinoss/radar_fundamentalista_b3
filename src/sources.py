"""
Data source abstraction layer: brapi.dev (primary) + yfinance (fallback).

Provides a unified interface for fetching asset data regardless of the underlying
source. The preferred source is brapi.dev (v2 API), which offers better coverage
and reliability for Brazilian assets. yfinance is used as a fallback when brapi.dev
is unavailable or returns incomplete data (particularly for niche assets like FIAGROs).

Usage:
    from sources import fetch_asset_info, fetch_history
    info = fetch_asset_info("PETR4.SA", config)
    history = fetch_history("PETR4.SA", period="5y", max_points=60, config=config)

Field mapping (brapi.dev → yfinance-compatible key names):
    Quote endpoint:
      regularMarketPrice    → currentPrice
      longName / shortName  → longName / shortName
    
    Statistics endpoint:
      trailingPE            → trailingPE  (P/L)
      priceToBook           → priceToBook (P/VP)
      dividendYield         → dividendYield
      trailingEps           → trailingEps (LPA)
      bookValue             → bookValue   (VPA)
    
    Financial Data endpoint:
      returnOnEquity        → returnOnEquity (ROE)
    
    FII Indicators endpoint:
      price                 → currentPrice
      priceToNav            → priceToBook (P/VP)
      dividendYield12m      → dividendYield
      navPerShare           → bookValue   (VPA)
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("sources")

# ---------------------------------------------------------------------------
# Token loading: .env file > config > empty
# ---------------------------------------------------------------------------
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_FILE = os.path.join(_ROOT, ".env")

def _load_brapi_token() -> str | None:
    """Load BRAPI token from env var > .env file, or return None."""
    # 1. Environment variable (used by GitHub Actions)
    env_token = os.environ.get("BRAPI_TOKEN")
    if env_token and env_token != "seu_token_aqui":
        return env_token
    # 2. .env file (used locally)
    if os.path.exists(_ENV_FILE):
        try:
            with open(_ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("BRAPI_TOKEN="):
                        val = line.split("=", 1)[1].strip().strip("\"'")
                        if val and val != "seu_token_aqui":
                            return val
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BRAPI_BASE = "https://brapi.dev/api/v2"

# Map yfinance period strings to brapi range strings
PERIOD_TO_RANGE = {
    "1d": "1d",
    "5d": "5d",
    "1mo": "1mo",
    "3mo": "3mo",
    "6mo": "6mo",
    "1y": "1y",
    "2y": "2y",
    "5y": "5y",
    "10y": "10y",
    "ytd": "ytd",
    "max": "max",
}


# ---------------------------------------------------------------------------
# brapi.dev client
# ---------------------------------------------------------------------------
class BrapiClient:
    """HTTP client for the brapi.dev v2 API."""

    def __init__(self, token: str | None = None) -> None:
        self.token: str | None = token

    @property
    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"User-Agent": "Radar-Fundamentalista-B3/2.0"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform a GET request to the brapi.dev API."""
        import requests as req
        url = f"{BRAPI_BASE}/{endpoint}"
        resp = req.get(url, headers=self._headers, params=params, timeout=20)
        if resp.status_code == 429:
            logger.warning(f"brapi.dev rate limited on {endpoint}")
            raise BrapiRateLimitError("Rate limited by brapi.dev")
        resp.raise_for_status()
        return resp.json()

    # -------------------------------------------------------------------
    # Stock info (quote + statistics + financial-data)
    # -------------------------------------------------------------------
    def fetch_stock_info(self, ticker: str) -> dict[str, Any]:
        """Fetch complete stock info from brapi.dev.

        Combines data from quote, statistics, financial-data, and profile
        endpoints into a single dict with yfinance-compatible keys.
        Returns {} on any failure.
        """
        symbol = ticker.replace(".SA", "")
        info = {}

        try:
            # 1. Quote endpoint → price, name
            quote_resp = self._get("stocks/quote", {"symbols": symbol})
            quote = self._unwrap_result(quote_resp)
            if quote:
                info.update(self._extract_quote(quote))

            # 2. Statistics endpoint → fundamentals (P/L, P/VP, DY, EPS, BV)
            stats_resp = self._get("stocks/statistics", {
                "symbols": symbol, "mode": "current"
            })
            stats = self._unwrap_result(stats_resp)
            if stats:
                info.update(self._extract_statistics(stats))

            # 3. Financial data endpoint → ROE
            fin_resp = self._get("stocks/financial-data", {
                "symbols": symbol, "mode": "current"
            })
            fin = self._unwrap_result(fin_resp)
            if fin:
                info.update(self._extract_financial(fin))

            # 4. Profile endpoint → sector
            try:
                profile_resp = self._get("stocks/profile", {"symbols": symbol})
                profile = self._unwrap_result(profile_resp)
                if profile:
                    info.update(self._extract_profile(profile))
            except Exception:
                pass  # Profile is optional

            # Validate we got meaningful data
            if not info.get("longName") and not info.get("shortName"):
                logger.debug(f"brapi.dev returned no name for {ticker}")
                return {}

            return info

        except BrapiRateLimitError:
            raise
        except Exception as e:
            logger.debug(f"brapi.dev fetch failed for {ticker}: {e}")
            return {}

    # -------------------------------------------------------------------
    # FII / FIAGRO info (indicators endpoint)
    # -------------------------------------------------------------------
    def fetch_fii_info(self, ticker: str) -> dict[str, Any]:
        """Fetch FII/FIAGRO info from brapi.dev's FII indicators endpoint.

        Returns {} on any failure.
        """
        symbol = ticker.replace(".SA", "")
        info = {}

        try:
            resp = self._get("fii/indicators", {"symbols": symbol})
            fiis = resp.get("fiis", [])
            if not fiis:
                return {}

            fii = fiis[0]
            info["symbol"] = fii.get("symbol")
            info["longName"] = fii.get("name") or fii.get("symbol")
            info["shortName"] = fii.get("name") or fii.get("symbol")
            info["currentPrice"] = fii.get("price")
            info["regularMarketPrice"] = fii.get("price")
            info["priceToBook"] = fii.get("priceToNav")  # P/VP for FIIs
            info["dividendYield"] = fii.get("dividendYield12m")
            info["bookValue"] = fii.get("navPerShare")
            info["sector"] = "Real Estate"
            info["marketCap"] = (
                fii.get("price") * fii.get("sharesOutstanding")
                if fii.get("price") and fii.get("sharesOutstanding")
                else None
            )

            # Estimate dividendRate from yield * price
            dy = info.get("dividendYield")
            price = info.get("currentPrice")
            if dy is not None and price is not None:
                info["dividendRate"] = round(dy * price, 4)

            return info

        except BrapiRateLimitError:
            raise
        except Exception as e:
            logger.debug(f"brapi.dev FII fetch failed for {ticker}: {e}")
            return {}

    # -------------------------------------------------------------------
    # Historical data
    # -------------------------------------------------------------------
    def fetch_history(self, ticker: str, period: str = "5y", max_points: int = 60) -> list[dict[str, Any]]:
        """Fetch OHLCV history from brapi.dev.

        Returns a list of {date, price} dicts sampled to max_points.
        Returns [] on failure.
        """
        symbol = ticker.replace(".SA", "")
        brapi_range = PERIOD_TO_RANGE.get(period, "5y")

        try:
            resp = self._get("stocks/historical", {
                "symbols": symbol,
                "range": brapi_range,
                "interval": "1d",
            })
            results = resp.get("results", [])
            if not results:
                return []

            hist_data = results[0].get("data", {}).get("historicalDataPrice", [])
            if not hist_data:
                return []

            # Convert to standard format
            history = []
            for entry in hist_data:
                ts = entry.get("date")
                if not ts:
                    continue
                # brapi returns unix timestamps in seconds
                date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                close_price = entry.get("close")
                if close_price is None:
                    continue
                history.append({
                    "date": date_str,
                    "price": round(float(close_price), 2),
                })

            # Reverse to chronological order (brapi returns newest-first)
            history.reverse()

            # Sample down to max_points
            if max_points and len(history) > max_points:
                step = max(1, len(history) // max_points)
                history = history[::step]

            return history

        except BrapiRateLimitError:
            raise
        except Exception as e:
            logger.debug(f"brapi.dev history fetch failed for {ticker}: {e}")
            return []

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------
    @staticmethod
    def _unwrap_result(response: dict[str, Any]) -> dict[str, Any] | None:
        """Extract the inner 'data' payload from a v2 API response.

        v2 format: {"results": [{"symbol": "...", "data": {...}}]}
        Returns the 'data' dict or None.
        """
        results = response.get("results", [])
        if not results:
            return None
        return results[0].get("data", {})

    @staticmethod
    def _extract_quote(quote: dict[str, Any]) -> dict[str, Any]:
        """Extract fields from the quote endpoint response."""
        return {
            "symbol": quote.get("symbol"),
            "longName": quote.get("longName") or quote.get("shortName"),
            "shortName": quote.get("shortName"),
            "currentPrice": quote.get("regularMarketPrice"),
            "regularMarketPrice": quote.get("regularMarketPrice"),
            "regularMarketDayHigh": quote.get("regularMarketDayHigh"),
            "regularMarketDayLow": quote.get("regularMarketDayLow"),
            "regularMarketChange": quote.get("regularMarketChange"),
            "regularMarketChangePercent": quote.get("regularMarketChangePercent"),
            "regularMarketVolume": quote.get("regularMarketVolume"),
            "marketCap": quote.get("marketCap"),
            "fiftyTwoWeekLow": quote.get("fiftyTwoWeekLow"),
            "fiftyTwoWeekHigh": quote.get("fiftyTwoWeekHigh"),
            "logourl": quote.get("logourl"),
        }

    @staticmethod
    def _extract_statistics(stats: dict[str, Any]) -> dict[str, Any]:
        """Extract fundamental fields from the statistics endpoint."""
        return {
            "trailingPE": stats.get("trailingPE"),
            "priceToBook": stats.get("priceToBook"),
            "dividendYield": stats.get("dividendYield"),
            "trailingEps": stats.get("trailingEps") or stats.get("earningsPerShare"),
            "bookValue": stats.get("bookValue"),
            "beta": stats.get("beta"),
            "profitMargins": stats.get("profitMargins"),
            "earningsQuarterlyGrowth": stats.get("earningsQuarterlyGrowth"),
            "marketCap": stats.get("marketCap") or stats.get("enterpriseValue"),
            "lastDividendDate": stats.get("lastDividendDate"),
        }

    @staticmethod
    def _extract_financial(fin: dict[str, Any]) -> dict[str, Any]:
        """Extract ROE from the financial-data endpoint."""
        return {
            "returnOnEquity": fin.get("returnOnEquity"),
            "returnOnAssets": fin.get("returnOnAssets"),
            "totalRevenue": fin.get("totalRevenue"),
            "ebitda": fin.get("ebitda"),
            "freeCashflow": fin.get("freeCashflow"),
            "debtToEquity": fin.get("debtToEquity"),
        }

    @staticmethod
    def _extract_profile(profile: dict[str, Any]) -> dict[str, Any]:
        """Extract sector/industry from the profile endpoint."""
        return {
            "sector": profile.get("sector"),
            "industry": profile.get("industry"),
        }


# ---------------------------------------------------------------------------
# yfinance client (fallback)
# ---------------------------------------------------------------------------
class YfinanceClient:
    """yfinance-based data source for fallback scenarios."""

    @staticmethod
    def fetch_stock_info(ticker: str) -> dict[str, Any]:
        """Fetch stock info from yfinance."""
        import yfinance as yf
        try:
            yf_ticker = yf.Ticker(ticker)
            info = yf_ticker.info
            if not info or ("longName" not in info and "shortName" not in info):
                return {}
            return info
        except Exception as e:
            logger.debug(f"yfinance failed for {ticker}: {e}")
            return {}

    @staticmethod
    def fetch_fii_info(ticker: str) -> dict[str, Any]:
        """Fetch FII info from yfinance (same as stock info)."""
        return YfinanceClient.fetch_stock_info(ticker)

    @staticmethod
    def fetch_history(ticker: str, period: str = "10y", max_points: int = 60) -> list[dict[str, Any]]:
        """Fetch history from yfinance and sample down."""
        import yfinance as yf
        try:
            yf_ticker = yf.Ticker(ticker)
            hist_df = yf_ticker.history(period=period)
            if hist_df.empty:
                return []
            step = max(1, len(hist_df) // max_points) if max_points else 1
            sampled = hist_df.iloc[::step]
            history = []
            for ts, row in sampled.iterrows():
                history.append({
                    "date": ts.strftime("%Y-%m-%d"),
                    "price": round(float(row["Close"]), 2),
                })
            return history
        except Exception as e:
            logger.debug(f"yfinance history failed for {ticker}: {e}")
            return []


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------
class BrapiRateLimitError(Exception):
    """Raised when brapi.dev returns HTTP 429 (rate limited)."""
    pass


class AllSourcesFailedError(Exception):
    """Raised when all data sources fail for a ticker."""
    pass


# ---------------------------------------------------------------------------
# Unified fetch functions (main public API)
# ---------------------------------------------------------------------------

def fetch_asset_info(ticker: str, asset_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """Fetch asset info from primary source (brapi.dev) with yfinance fallback.

    Args:
        ticker: Full ticker symbol (e.g. 'PETR4.SA')
        asset_type: 'stock', 'fii', or 'fiagro'
        config: Full pipeline config dict (load_config())

    Returns:
        dict with yfinance-compatible keys, or {} if all sources fail.
    """
    # Token: .env > config
    brapi_token = _load_brapi_token() or config.get("brapi", {}).get("token")
    brapi = BrapiClient(token=brapi_token)
    yfin = YfinanceClient()

    fetch_funcs = {
        "stock": (brapi.fetch_stock_info, yfin.fetch_stock_info),
        "fii": (brapi.fetch_fii_info, yfin.fetch_fii_info),
        "fiagro": (brapi.fetch_fii_info, yfin.fetch_fii_info),
    }

    primary, fallback = fetch_funcs.get(asset_type, (brapi.fetch_stock_info, yfin.fetch_stock_info))

    # Try primary source (brapi.dev)
    try:
        info = primary(ticker)
        if info and (info.get("longName") or info.get("shortName") or info.get("currentPrice")):
            if info.get("dividendYield") is not None or info.get("currentPrice") is not None:
                logger.debug(f"brapi.dev OK for {ticker}")
                return info
        logger.debug(f"brapi.dev returned incomplete data for {ticker}, trying fallback")
    except BrapiRateLimitError:
        logger.warning(f"brapi.dev rate limited, falling back to yfinance for {ticker}")
    except Exception as e:
        logger.debug(f"brapi.dev failed for {ticker}: {e}")

    # Fallback to yfinance
    try:
        info = fallback(ticker)
        if info and (info.get("longName") or info.get("shortName") or info.get("currentPrice")):
            logger.debug(f"yfinance fallback OK for {ticker}")
            return info
    except Exception as e:
        logger.debug(f"yfinance fallback also failed for {ticker}: {e}")

    logger.warning(f"All sources failed for {ticker}")
    return {}


def fetch_history(ticker: str, config: dict[str, Any], period: str = "10y", max_points: int = 60) -> str:
    """Fetch historical price data from brapi.dev with yfinance fallback.

    Args:
        ticker: Full ticker symbol (e.g. 'PETR4.SA')
        config: Full pipeline config dict
        period: yfinance-compatible period string ('1y', '5y', '10y', etc.)
        max_points: Maximum number of data points to return

    Returns:
        JSON string of [{"date": "2025-01-01", "price": 42.0}, ...]
    """
    # Token: .env > config
    brapi_token = _load_brapi_token() or config.get("brapi", {}).get("token")
    brapi = BrapiClient(token=brapi_token)
    yfin = YfinanceClient()

    # Try brapi first
    try:
        history = brapi.fetch_history(ticker, period=period, max_points=max_points)
        if history:
            logger.debug(f"brapi.dev history OK for {ticker} ({len(history)} points)")
            return json.dumps(history)
    except BrapiRateLimitError:
        logger.warning("brapi.dev rate limited, falling back to yfinance for history")
    except Exception as e:
        logger.debug(f"brapi.dev history failed for {ticker}: {e}")

    # Fallback to yfinance
    try:
        history = yfin.fetch_history(ticker, period=period, max_points=max_points)
        if history:
            logger.debug(f"yfinance history OK for {ticker} ({len(history)} points)")
            return json.dumps(history)
    except Exception as e:
        logger.debug(f"yfinance history fallback failed for {ticker}: {e}")

    logger.warning(f"All sources failed for history of {ticker}")
    return json.dumps([])


def normalize_dividend_yield(dy: float | None) -> float:
    """Normalize dividend yield to decimal form (same as analyzer.normalize_dividend_yield).

    brapi.dev returns DY as decimal (e.g. 0.06 for 6%) — same as normalized yfinance.
    But yfinance sometimes returns it as percentage (e.g. 6.0).
    This ensures consistent normalization regardless of source.
    """
    if dy is None:
        return 0.0
    if dy > 1.0:
        return round(dy / 100.0, 6)
    return round(dy, 6)
