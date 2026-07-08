"""
Unit tests for the analyzer module (Graham, Bazin, scorecard calculations).

Run with:  python -m pytest src/tests/test_analyzer.py -v
Or:        python -m pytest src/tests/ -v
"""
import math

from analyzer import (
    calculate_graham_price,
    calculate_bazin_price,
    normalize_dividend_yield,
    calculate_stock_score,
    calculate_fii_score,
    calculate_fiagro_score,
    analyze_stock,
    analyze_fii,
    analyze_fiagro,
    get_true_yield,
    SECTOR_MAP,
)


# ======================================================================
# Graham Price Tests
# ======================================================================

class TestGrahamPrice:
    def test_valid_inputs(self):
        """sqrt(22.5 * 5 * 20) = sqrt(2250) ≈ 47.43"""
        result = calculate_graham_price(5.0, 20.0)
        expected = round(math.sqrt(22.5 * 5.0 * 20.0), 2)
        assert result == expected, f"Expected {expected}, got {result}"

    def test_zero_eps(self):
        assert calculate_graham_price(0, 20) == 0.0

    def test_negative_eps(self):
        assert calculate_graham_price(-5, 20) == 0.0

    def test_none_inputs(self):
        assert calculate_graham_price(None, 20) is None
        assert calculate_graham_price(5, None) is None
        assert calculate_graham_price(None, None) is None

    def test_large_values(self):
        result = calculate_graham_price(100, 500)
        expected = round(math.sqrt(22.5 * 100 * 500), 2)
        assert result == expected


# ======================================================================
# Bazin Price Tests
# ======================================================================

class TestBazinPrice:
    def test_valid_dividend(self):
        """2.50 / 0.06 = 41.67"""
        assert calculate_bazin_price(2.50) == round(2.50 / 0.06, 2)

    def test_zero_dividend(self):
        assert calculate_bazin_price(0) == 0.0

    def test_none_dividend(self):
        assert calculate_bazin_price(None) == 0.0

    def test_small_dividend(self):
        assert calculate_bazin_price(0.01) == round(0.01 / 0.06, 2)


# ======================================================================
# Dividend Yield Normalization Tests
# ======================================================================

class TestNormalizeDividendYield:
    def test_percentage_format(self):
        """6.5% → 0.065"""
        assert normalize_dividend_yield(6.5) == 0.065

    def test_decimal_format(self):
        """Already decimal: 0.065 stays 0.065"""
        assert normalize_dividend_yield(0.065) == 0.065

    def test_none(self):
        assert normalize_dividend_yield(None) == 0.0

    def test_exact_one(self):
        """1.0 is ambiguous: the function only divides by 100 if dy > 1.0, so 1.0 stays 1.0"""
        assert normalize_dividend_yield(1.0) == 1.0

    def test_zero(self):
        assert normalize_dividend_yield(0) == 0.0

    def test_high_percentage(self):
        assert normalize_dividend_yield(12.5) == 0.125


# ======================================================================
# Stock Score Tests
# ======================================================================

class TestStockScore:
    def test_perfect_score(self):
        """All 5 criteria met."""
        score = calculate_stock_score(
            price=20.0, eps=5.0, book_value=20.0,
            pe_ratio=4.0, pb_ratio=0.8, dividend_yield=0.08,
            roe=0.15, graham_price=47.43, bazin_price=41.67
        )
        assert score == 5, f"Expected 5, got {score}"

    def test_zero_score(self):
        """No criteria met."""
        score = calculate_stock_score(
            price=100.0, eps=0.5, book_value=5.0,
            pe_ratio=50.0, pb_ratio=5.0, dividend_yield=0.01,
            roe=0.02, graham_price=0.0, bazin_price=0.0
        )
        assert score == 0, f"Expected 0, got {score}"

    def test_dy_threshold(self):
        """DY exactly at 6% threshold should pass."""
        score = calculate_stock_score(
            price=50, eps=5, book_value=20,
            pe_ratio=10, pb_ratio=1.0, dividend_yield=0.06,
            roe=0.10, graham_price=47.43, bazin_price=41.67
        )
        # DY >= 0.06 ✓, PE <= 15 ✓, PB <= 1.5 ✓, ROE >= 0.10 ✓
        # Graham check: 50 < 47.43? No
        assert score == 4

    def test_margin_of_safety(self):
        """Price below Graham price should add 1 point."""
        score = calculate_stock_score(
            price=30, eps=5, book_value=20,
            pe_ratio=6, pb_ratio=1.0, dividend_yield=0.06,
            roe=0.15, graham_price=47.43, bazin_price=41.67
        )
        # DY ✓, PE ✓, PB ✓, ROE ✓, Graham ✓ → 5
        assert score == 5

    def test_bazin_price_ignored_in_score(self):
        """Bazin price is informational, not part of score."""
        score = calculate_stock_score(
            price=10, eps=2, book_value=10,
            pe_ratio=5, pb_ratio=1.0, dividend_yield=0.07,
            roe=0.15, graham_price=21.21, bazin_price=0.0
        )
        # bazin_price = 0 should not affect score
        assert score == 5

    def test_dy_as_percentage_string(self):
        """DY passed as percentage (e.g. 9.48) should be normalized."""
        score = calculate_stock_score(
            price=20, eps=5, book_value=20,
            pe_ratio=4, pb_ratio=0.8, dividend_yield=9.48,  # 9.48%
            roe=0.15, graham_price=47.43, bazin_price=41.67
        )
        assert score == 5


# ======================================================================
# FII Score Tests
# ======================================================================

class TestFiiScore:
    def test_perfect_fii(self):
        """Max score is 5 (C2 base + C1 bonus + 3 DY/distribution criteria)."""
        score = calculate_fii_score(
            price=100.0, pb_ratio=0.95, dividend_yield=0.12, dividend_rate=1.0
        )
        # C2 (≤1.15): 0.95 ✓ +1
        # C1 (0.70-1.05): 0.95 ✓ +1
        # DY ≥ 8% ✓ +1, DY ≥ 10% ✓ +1, Rate > 0 ✓ +1
        assert score == 5, f"Expected 5, got {score}"

    def test_low_pb_at_lower_bound(self):
        """P/B at 0.70 passes both C2 (≤1.15) and C1 (0.70-1.05 inclusive)."""
        score = calculate_fii_score(
            price=100.0, pb_ratio=0.70, dividend_yield=0.12, dividend_rate=1.0
        )
        # C2: 0.70 <= 1.15 ✓ +1
        # C1: 0.70 <= 0.70 <= 1.05 ✓ +1
        # DY ≥ 8% ✓ +1, DY ≥ 10% ✓ +1, Rate > 0 ✓ +1
        assert score == 5, f"Expected 5, got {score}"

    def test_pb_below_ideal_range(self):
        """P/B below 0.70 → C2 passes (≤1.15), C1 fails (<0.70)."""
        score = calculate_fii_score(
            price=100.0, pb_ratio=0.50, dividend_yield=0.12, dividend_rate=1.0
        )
        # C2: 0.50 <= 1.15 ✓ +1
        # C1: 0.70 <= 0.50? No +0
        # DY ≥ 8% ✓ +1, DY ≥ 10% ✓ +1, Rate > 0 ✓ +1
        assert score == 4, f"Expected 4, got {score}"

    def test_pb_in_limit_zone_above_ideal(self):
        """P/B between 1.05 and 1.15 → C2 passes (≤1.15), C1 fails (>1.05)."""
        score = calculate_fii_score(
            price=100.0, pb_ratio=1.10, dividend_yield=0.12, dividend_rate=1.0
        )
        # C2: 1.10 <= 1.15 ✓ +1
        # C1: 0.70 <= 1.10 <= 1.05? No +0
        # DY ≥ 8% ✓ +1, DY ≥ 10% ✓ +1, Rate > 0 ✓ +1
        assert score == 4, f"Expected 4, got {score}"

    def test_high_pb_ratio(self):
        """P/B above 1.15 → only DY and rate count."""
        score = calculate_fii_score(
            price=100.0, pb_ratio=1.50, dividend_yield=0.12, dividend_rate=1.0
        )
        # C2 (1.50 > 1.15): No. C1: No.
        # DY ≥ 8% ✓ +1, DY ≥ 10% ✓ +1, Rate > 0 ✓ +1
        assert score == 3

    def test_no_dividend(self):
        """Zero dividend rate → no rate point, no yield points."""
        score = calculate_fii_score(
            price=100.0, pb_ratio=0.95, dividend_yield=0.0, dividend_rate=0.0
        )
        # C2 ✓ +1, C1 ✓ +1, DY 0 ✗, DY exc ✗, Rate ✗
        assert score == 2

    def test_historical_dividends(self):
        """historical_dividends_365d > 0 satisfies C5 even with zero rate."""
        score = calculate_fii_score(
            price=100.0, pb_ratio=0.95, dividend_yield=0.12, dividend_rate=0.0,
            historical_dividends_365d=5.0
        )
        # C2 ✓ +1, C1 ✓ +1, DY ≥ 8% ✓ +1, DY ≥ 10% ✓ +1, hist_divs > 0 ✓ +1
        assert score == 5

    def test_none_values(self):
        """None values should not crash and return 0."""
        score = calculate_fii_score(
            price=100.0, pb_ratio=None, dividend_yield=None, dividend_rate=None
        )
        assert score == 0

    def test_dy_as_percentage(self):
        """DY as percentage should be normalized. 10.5% = 0.105, meets all thresholds."""
        score = calculate_fii_score(
            price=100.0, pb_ratio=0.95, dividend_yield=10.5, dividend_rate=1.0
        )
        assert score == 5


# ======================================================================
# Sector Map Tests
# ======================================================================

class TestSectorMap:
    def test_all_keys_translated(self):
        """Every English sector has a Portuguese translation."""
        assert len(SECTOR_MAP) >= 10
        assert "Financial Services" in SECTOR_MAP
        assert SECTOR_MAP["Financial Services"] == "Serviços Financeiros"
        assert SECTOR_MAP["Utilities"] == "Utilidade Pública"
        assert SECTOR_MAP["Basic Materials"] == "Materiais Básicos"
        assert SECTOR_MAP["Real Estate"] == "Imobiliário"

    def test_fallback_unknown(self):
        """Unknown sector should be handled by caller, not tested here."""
        # Caller uses SECTOR_MAP.get(raw_sector, raw_sector)
        assert SECTOR_MAP.get("Unknown Sector", "Unknown Sector") == "Unknown Sector"


# ======================================================================
# Integration: analyze_stock with synthetic data
# ======================================================================

class TestAnalyzeStock:
    def test_basic_stock_analysis(self):
        """Test analyze_stock with a realistic info dict."""
        info = {
            "currentPrice": 45.50,
            "trailingEps": 4.20,
            "bookValue": 25.00,
            "trailingPE": 10.83,
            "priceToBook": 1.82,
            "dividendYield": 5.8,  # 5.8% → 0.058
            "dividendRate": 2.64,
            "returnOnEquity": 0.168,
            "longName": "Empresa Teste SA",
            "sector": "Financial Services",
        }
        result = analyze_stock("TEST3.SA", info)
        assert result["ticker"] == "TEST3.SA"
        assert result["name"] == "Empresa Teste SA"
        assert result["sector"] == "Serviços Financeiros"
        assert result["price"] == 45.50
        assert result["pe_ratio"] == 10.83
        assert result["pb_ratio"] == 1.82
        assert result["dividend_yield"] == 0.058  # normalized
        assert result["roe"] == 0.168
        assert result["eps"] == 4.20
        assert result["book_value"] == 25.00
        # Score: DY 5.8% < 6% ✗, PE 10.83 ✓, PB 1.82 > 1.5 ✗, ROE 16.8% ✓, Graham?
        # Graham: sqrt(22.5 * 4.20 * 25) = sqrt(2362.5) ≈ 48.60
        # 45.50 < 48.60 ✓
        # Expected: 3 (PE ✓, ROE ✓, Graham ✓)
        assert result["score"] == 3, f"Expected score 3, got {result['score']}"
        assert result["graham_price"] == round(math.sqrt(22.5 * 4.2 * 25), 2)
        assert result["bazin_price"] == round(2.64 / 0.06, 2)

    def test_stock_with_minimal_info(self):
        """Should handle missing fields gracefully."""
        info = {
            "currentPrice": 30.0,
            "longName": "Minimal Inc",
            "sector": "Technology",
        }
        result = analyze_stock("MINI3.SA", info)
        assert result["ticker"] == "MINI3.SA"
        assert result["price"] == 30.0
        assert result["score"] == 0  # No criteria met

    def test_stock_fallback_price(self):
        """Should fallback to regularMarketPrice if currentPrice missing.
        Should also fallback to shortName if longName missing."""
        info = {
            "regularMarketPrice": 25.0,
            "shortName": "Fallback Corp",
        }
        result = analyze_stock("FALL3.SA", info)
        assert result["price"] == 25.0
        assert result["name"] == "Fallback Corp"

    def test_dividend_derivation(self):
        """If dividendYield missing but dividendRate present, should derive."""
        info = {
            "currentPrice": 50.0,
            "dividendRate": 3.0,
            "longName": "Div Corp",
        }
        result = analyze_stock("DIV3.SA", info)
        # DY = 3.0 / 50.0 = 0.06
        assert result["dividend_yield"] == 0.06

    def test_dividend_rate_derivation(self):
        """If dividendRate missing but dividendYield present, should derive bazin_price."""
        info = {
            "currentPrice": 50.0,
            "dividendYield": 6.0,  # 6%
            "longName": "Yield Corp",
        }
        result = analyze_stock("YLD3.SA", info)
        # Rate = 0.06 * 50.0 = 3.0 → bazin = 3.0 / 0.06 = 50.0
        assert result["bazin_price"] == 50.0


# ======================================================================
# Integration: analyze_fii with synthetic data
# ======================================================================

class TestAnalyzeFii:
    def test_basic_fii_analysis(self):
        info = {
            "currentPrice": 105.00,
            "priceToBook": 0.95,
            "dividendYield": 9.5,  # 9.5%
            "dividendRate": 0.85,
            "longName": "Fundo Teste RD",
        }
        result = analyze_fii("TEST11.SA", info)
        assert result["ticker"] == "TEST11.SA"
        assert result["price"] == 105.00
        assert result["pb_ratio"] == 0.95
        assert result["dividend_yield"] == 0.095
        assert result["dividend_rate"] == 0.85
        # Score: C2 (≤1.15) ✓ +1, C1 (0.70-1.05) ✓ +1, DY ≥ 8% ✓ +1, DY ≥ 10% ✗ (9.5%) +0, Rate >0 ✓ +1 → 4
        assert result["score"] == 4, f"Expected 4, got {result['score']}"

    def test_fii_last_dividend_fallback(self):
        """Should use lastDividendValue * 12 if yield and rate are missing.
        Uses approx because floating point: 0.80*12 = 9.600000000000001."""
        info = {
            "currentPrice": 100.00,
            "lastDividendValue": 0.80,
            "shortName": "FII Last Div",
        }
        result = analyze_fii("LDIV11.SA", info)
        # rate = 0.80 * 12 ≈ 9.6, yield = rate / 100 ≈ 0.096
        assert round(result["dividend_rate"], 4) == 9.6
        assert round(result["dividend_yield"], 4) == 0.096


# ======================================================================
# FIAGRO Score Tests
# ======================================================================

class TestFiagroScore:
    def test_perfect_fiagro(self):
        """Max score is 5 (C2 base + C1 bonus + 3 DY/distribution, elevated DY)."""
        score = calculate_fiagro_score(
            price=100.0, pb_ratio=0.95, dividend_yield=0.15, dividend_rate=1.0
        )
        # C2 (≤1.15): 0.95 ✓ +1
        # C1 (0.70-1.05): 0.95 ✓ +1
        # DY ≥ 10% ✓ +1, DY ≥ 12% ✓ +1, Rate > 0 ✓ +1
        assert score == 5, f"Expected 5, got {score}"

    def test_fiagro_minimum_dy(self):
        """DY at 10% meets the 'good' threshold for FIAGROs."""
        score = calculate_fiagro_score(
            price=100.0, pb_ratio=0.95, dividend_yield=0.10, dividend_rate=1.0
        )
        # C2 ✓ +1, C1 ✓ +1, DY ≥ 10% ✓ +1, DY ≥ 12% ✗ +0, Rate > 0 ✓ +1
        assert score == 4, f"Expected 4, got {score}"

    def test_fiagro_dy_below_minimum(self):
        """DY at 9% passes FII thresholds but NOT FIAGRO thresholds."""
        score = calculate_fiagro_score(
            price=100.0, pb_ratio=0.95, dividend_yield=0.09, dividend_rate=1.0
        )
        # C2 ✓ +1, C1 ✓ +1, DY ≥ 10% ✗ +0, DY ≥ 12% ✗ +0, Rate > 0 ✓ +1
        assert score == 3, f"Expected 3, got {score}"

    def test_fiagro_dy_exactly_12_percent(self):
        """DY exactly at 12% meets both FIAGRO DY thresholds."""
        score = calculate_fiagro_score(
            price=100.0, pb_ratio=0.95, dividend_yield=0.12, dividend_rate=1.0
        )
        # C2 ✓ +1, C1 ✓ +1, DY ≥ 10% ✓ +1, DY ≥ 12% ✓ +1, Rate > 0 ✓ +1
        assert score == 5

    def test_fiagro_pb_below_ideal(self):
        """P/B below 0.70 → C2 passes (≤1.15), C1 fails (<0.70)."""
        score = calculate_fiagro_score(
            price=100.0, pb_ratio=0.50, dividend_yield=0.15, dividend_rate=1.0
        )
        # C2: 0.50 <= 1.15 ✓ +1
        # C1: 0.70 <= 0.50? No +0
        # DY ≥ 10% ✓ +1, DY ≥ 12% ✓ +1, Rate > 0 ✓ +1
        assert score == 4

    def test_fiagro_pb_in_limit_zone(self):
        """P/B in 1.05-1.15 → C2 passes (≤1.15), C1 fails (>1.05)."""
        score = calculate_fiagro_score(
            price=100.0, pb_ratio=1.10, dividend_yield=0.15, dividend_rate=1.0
        )
        # C2: 1.10 <= 1.15 ✓ +1
        # C1: 0.70 <= 1.10 <= 1.05? No +0
        # DY ✓, DY exc ✓, Rate ✓
        assert score == 4

    def test_fiagro_high_pb(self):
        """P/B above 1.15 → only DY and rate count."""
        score = calculate_fiagro_score(
            price=100.0, pb_ratio=1.50, dividend_yield=0.15, dividend_rate=1.0
        )
        assert score == 3

    def test_fiagro_no_dividend(self):
        """Zero dividend → only valuation points."""
        score = calculate_fiagro_score(
            price=100.0, pb_ratio=0.95, dividend_yield=0.0, dividend_rate=0.0
        )
        # C2 ✓ +1, C1 ✓ +1, DY 0 ✗, DY exc ✗, Rate ✗
        assert score == 2

    def test_fiagro_historical_dividends(self):
        """historical_dividends_365d satisfies C5 even with zero rate."""
        score = calculate_fiagro_score(
            price=100.0, pb_ratio=0.95, dividend_yield=0.15, dividend_rate=0.0,
            historical_dividends_365d=8.0
        )
        assert score == 5

    def test_fiagro_none_values(self):
        """None values should not crash."""
        score = calculate_fiagro_score(
            price=100.0, pb_ratio=None, dividend_yield=None, dividend_rate=None
        )
        assert score == 0

    def test_fiagro_dy_as_percentage(self):
        """DY as percentage (15%) should be normalized."""
        score = calculate_fiagro_score(
            price=100.0, pb_ratio=0.95, dividend_yield=15.0, dividend_rate=1.0
        )
        assert score == 5


# ======================================================================
# True Yield Tests
# ======================================================================

def _make_mock_ticker(total_dividends: float, days_ago: int = 180):
    """Build a mock yfinance Ticker whose .actions returns a dividend DataFrame."""
    import pandas as pd
    from datetime import datetime, timedelta
    idx = pd.date_range(end=datetime.now() - timedelta(days=days_ago),
                        periods=3, freq='ME')
    actions_df = pd.DataFrame({'Dividends': [total_dividends / 3] * 3}, index=idx)
    return type('MockTicker', (), {'actions': actions_df})()


class TestGetTrueYield:
    def test_with_recent_dividends(self):
        """Uses ticker.actions when available."""
        info = {}
        mock_ticker = _make_mock_ticker(total_dividends=6.0, days_ago=30)
        result = get_true_yield(info, yf_ticker=mock_ticker, price=100.0)
        # 6.0 / 100.0 = 0.06
        assert result == 0.06, f"Expected 0.06, got {result}"

    def test_fallback_to_info_dy(self):
        """Falls back to info['dividendYield'] when no yf_ticker."""
        info = {'dividendYield': 0.08}
        result = get_true_yield(info, yf_ticker=None, price=None)
        assert result == 0.08, f"Expected 0.08, got {result}"

    def test_fallback_with_percentage(self):
        """Falls back and normalizes percentage DY."""
        info = {'dividendYield': 9.5}  # 9.5%
        result = get_true_yield(info, yf_ticker=None, price=None)
        assert result == 0.095, f"Expected 0.095, got {result}"

    def test_no_data_returns_zero(self):
        """When no data at all, returns 0.0."""
        info = {}
        result = get_true_yield(info, yf_ticker=None, price=None)
        assert result == 0.0, f"Expected 0.0, got {result}"

    def test_zero_price_uses_fallback(self):
        """Zero price avoids division by zero, falls back."""
        info = {'dividendYield': 0.06}
        mock_ticker = _make_mock_ticker(total_dividends=6.0, days_ago=30)
        result = get_true_yield(info, yf_ticker=mock_ticker, price=0)
        assert result == 0.06


# ======================================================================
# Integration: analyze_fiagro with synthetic data
# ======================================================================

class TestAnalyzeFiagro:
    def test_basic_fiagro_analysis(self):
        info = {
            "currentPrice": 90.00,
            "priceToBook": 0.95,
            "dividendYield": 14.0,  # 14% — passes both FIAGRO DY thresholds
            "dividendRate": 1.20,
            "longName": "Fundo Agro Teste RD",
        }
        result = analyze_fiagro("AGRO11.SA", info)
        assert result["ticker"] == "AGRO11.SA"
        assert result["price"] == 90.00
        assert result["pb_ratio"] == 0.95
        assert result["dividend_yield"] == 0.14
        assert result["dividend_rate"] == 1.20
        # C2 ✓ +1, C1 ✓ +1, DY ≥ 10% ✓ +1, DY ≥ 12% ✓ +1, Rate > 0 ✓ +1
        assert result["score"] == 5, f"Expected 5, got {result['score']}"

    def test_fiagro_low_dy(self):
        """DY that passes FII thresholds but not FIAGRO thresholds."""
        info = {
            "currentPrice": 90.00,
            "priceToBook": 0.95,
            "dividendYield": 9.0,  # 9% — good for FII, NOT for FIAGRO
            "dividendRate": 0.70,
            "longName": "Agro Low DY",
        }
        result = analyze_fiagro("AGRO11.SA", info)
        # C2 ✓ +1, C1 ✓ +1, DY ≥ 10% ✗ +0, DY ≥ 12% ✗ +0, Rate > 0 ✓ +1
        assert result["score"] == 3, f"Expected 3, got {result['score']}"

    def test_fiagro_minimal_info(self):
        info = {
            "currentPrice": 80.00,
            "shortName": "Agro Minimal",
        }
        result = analyze_fiagro("AGRO11.SA", info)
        assert result["ticker"] == "AGRO11.SA"
        assert result["price"] == 80.00
        assert result["score"] == 0


# ======================================================================
# Stock PEG Ratio Tests (new criterion 5 alternative)
# ======================================================================

class TestStockPegScore:
    def test_tech_stock_with_good_peg(self):
        """Technology stock with PEG <= 1.0 passes C5 via PEG path."""
        score = calculate_stock_score(
            price=100.0, eps=5.0, book_value=20.0,
            pe_ratio=10.0, pb_ratio=1.0, dividend_yield=0.06,
            roe=0.12, graham_price=0.0, bazin_price=0.0,  # graham=0 → no margin
            peg_ratio=0.8, sector='Technology'
        )
        # DY ✓, PE ✓, PB ✓, ROE ✓, PEG ✓ (Graham bypassed)
        assert score == 5

    def test_tech_stock_bad_peg_falls_back_to_graham(self):
        """Tech stock with PEG > 1.0 falls back to Graham margin check."""
        score = calculate_stock_score(
            price=100.0, eps=5.0, book_value=20.0,
            pe_ratio=10.0, pb_ratio=1.0, dividend_yield=0.06,
            roe=0.12, graham_price=0.0, bazin_price=0.0,  # graham=0 → no margin
            peg_ratio=1.5, sector='Technology'
        )
        # DY ✓, PE ✓, PB ✓, ROE ✓, PEG ✗, Graham ✗ → 4
        assert score == 4

    def test_tech_stock_with_margin_of_safety(self):
        """Tech with PEG > 1.0 but price < Graham can still pass C5."""
        score = calculate_stock_score(
            price=30.0, eps=5.0, book_value=20.0,
            pe_ratio=6.0, pb_ratio=1.0, dividend_yield=0.06,
            roe=0.15, graham_price=47.43, bazin_price=41.67,
            peg_ratio=1.5, sector='Technology'
        )
        # DY ✓, PE ✓, PB ✓, ROE ✓, PEG ✗, Graham (30 < 47.43) ✓ → 5
        assert score == 5

    def test_communication_services_peg(self):
        """Communication Services also qualifies for PEG path."""
        score = calculate_stock_score(
            price=50.0, eps=3.0, book_value=15.0,
            pe_ratio=16.0, pb_ratio=1.2, dividend_yield=0.06,
            roe=0.10, graham_price=0.0, bazin_price=0.0,
            peg_ratio=0.9, sector='Communication Services'
        )
        # DY ✓, PE ✗ (16>15), PB ✓ (1.2 <= 1.5), ROE ✓, PEG ✓
        assert score == 4

    def test_non_tech_ignores_peg(self):
        """Non-tech sectors ignore PEG and use Graham only."""
        score = calculate_stock_score(
            price=100.0, eps=5.0, book_value=20.0,
            pe_ratio=10.0, pb_ratio=1.0, dividend_yield=0.06,
            roe=0.12, graham_price=0.0, bazin_price=0.0,
            peg_ratio=0.8, sector='Financial Services'
        )
        # DY ✓, PE ✓, PB ✓, ROE ✓, PEG ignored, Graham ✗ → 4
        assert score == 4


# ======================================================================
# Run
# ======================================================================
if __name__ == "__main__":
    # Simple manual runner if pytest not available
    import inspect

    tests_passed = 0
    tests_failed = 0
    for name, obj in list(globals().items()):
        if isinstance(obj, type) and name.startswith("Test"):
            for m_name, method in inspect.getmembers(obj, predicate=inspect.isfunction):
                if m_name.startswith("test_"):
                    try:
                        method(obj())
                        tests_passed += 1
                    except AssertionError as e:
                        print(f"FAIL {name}.{m_name}: {e}")
                        tests_failed += 1
                    except Exception as e:
                        print(f"ERROR {name}.{m_name}: {e}")
                        tests_failed += 1

    print(f"\n{'='*40}")
    print(f"  Tests: {tests_passed} passed, {tests_failed} failed")
    print(f"{'='*40}")
    sys.exit(tests_failed)
