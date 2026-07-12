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
    _calc_dy_medio_3y,
    _calc_dividend_consistency,
    SECTOR_MAP,
    # v2.5 continuous scoring
    calculate_stock_score_continuous,
    calculate_fii_score_continuous,
    calculate_fiagro_score_continuous,
    _score_dy_stock,
    _score_pe_stock,
    _score_pb_stock,
    _score_roe_stock,
    _score_graham_stock,
    _score_pb_fii_ideal,
    _score_pb_fii_limite,
    _score_dy_fii,
    _score_yield_cap,
    _score_dividend_consistency,
    # v2.5.1 — 4 criteria × 2.5 pts
    _score_pb_fii_unified,
    _score_dy_fii_v2,
    _score_yield_cap_v2,
    _score_dividend_consistency_v2,
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
        # VPA não está no info → fallback p/ price / pb_ratio = 105 / 0.95
        assert result["book_value"] == 110.53
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
    """Build a mock yfinance Ticker whose .actions returns a dividend DataFrame
    with a **timezone-aware** index (America/Sao_Paulo), matching real yfinance."""
    import pandas as pd
    from datetime import datetime, timedelta
    import pytz
    tz = pytz.timezone('America/Sao_Paulo')
    idx = pd.date_range(end=datetime.now(tz) - timedelta(days=days_ago),
                        periods=3, freq='ME', tz=tz)
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
# Timezone-aware Tests (catch the yfinance timezone bug)
# ======================================================================

class TestTimezoneAwareYield:
    """Tests that verify get_true_yield, _calc_dy_medio_3y and
    _calc_dividend_consistency work with timezone-aware indices (the
    real yfinance behavior). Without the fix, these would TypeError."""

    # ── get_true_yield ──

    def test_get_true_yield_tzaware_works(self):
        """get_true_yield must not crash with tz-aware index."""
        info = {}
        mock_ticker = _make_mock_ticker(total_dividends=6.0, days_ago=30)
        result = get_true_yield(info, yf_ticker=mock_ticker, price=100.0)
        assert result == 0.06, f"Expected 0.06, got {result}"

    def test_get_true_yield_tzaware_without_dividends(self):
        """get_true_yield falls back when tz-aware index has no Dividends column."""
        import pandas as pd
        from datetime import datetime, timedelta
        import pytz
        tz = pytz.timezone('America/Sao_Paulo')
        idx = pd.date_range(end=datetime.now(tz) - timedelta(days=30), periods=3, freq='ME', tz=tz)
        df = pd.DataFrame({'Stock Splits': [1.0] * 3}, index=idx)  # no Dividends column
        mock = type('MockTicker', (), {'actions': df})()
        info = {'dividendYield': 0.05}
        result = get_true_yield(info, yf_ticker=mock, price=100.0)
        assert result == 0.05, f"Expected 0.05 (fallback), got {result}"

    # ── _calc_dy_medio_3y ──

    def test_dy_medio_3y_tzaware_works(self):
        """_calc_dy_medio_3y must not crash with tz-aware index."""
        mock_ticker = _make_mock_ticker(total_dividends=9.0, days_ago=30)
        result = _calc_dy_medio_3y(mock_ticker, price=100.0)
        # 9.0 / 100.0 = 0.09 (cumulative 3-year)
        assert result == 0.09, f"Expected 0.09, got {result}"

    def test_dy_medio_3y_tzaware_empty_returns_none(self):
        """_calc_dy_medio_3y returns None when no dividends in window."""
        # Dividends 1200 days ago — safely outside 3y window (1095d)
        mock_ticker = _make_mock_ticker(total_dividends=6.0, days_ago=1200)
        result = _calc_dy_medio_3y(mock_ticker, price=100.0)
        assert result is None, f"Expected None (no divs in window), got {result}"

    def test_dy_medio_3y_tzaware_none_ticker(self):
        """_calc_dy_medio_3y returns None when ticker is None."""
        result = _calc_dy_medio_3y(None, price=100.0)
        assert result is None

    # ── _calc_dividend_consistency ──

    def test_dividend_consistency_tzaware_works(self):
        """_calc_dividend_consistency must not crash with tz-aware index."""
        import pandas as pd
        from datetime import datetime, timedelta
        import pytz
        tz = pytz.timezone('America/Sao_Paulo')
        # Create dividends: recent 6 months = 10, previous 6 months = 8
        now = datetime.now(tz)
        idx_recent = pd.date_range(end=now - timedelta(days=30), periods=3, freq='ME', tz=tz)
        idx_prev = pd.date_range(end=now - timedelta(days=200), periods=3, freq='ME', tz=tz)
        # Use union() instead of deprecated append() — works cross-platform with tz-aware indices
        all_idx = idx_prev.union(idx_recent)
        # Map values to sorted union order
        prev_set = set(idx_prev)
        all_divs = [8.0/3 if d in prev_set else 10.0/3 for d in all_idx]
        df = pd.DataFrame({'Dividends': all_divs}, index=all_idx)
        mock = type('MockTicker', (), {'actions': df})()
        result = _calc_dividend_consistency(mock)
        # 10/8 = 1.25
        assert result is not None, "Expected a value, got None"
        assert abs(result - 1.25) < 0.01, f"Expected ~1.25, got {result}"

    def test_dividend_consistency_tzaware_no_prev_divs(self):
        """_calc_dividend_consistency returns None when no previous dividends."""
        import pandas as pd
        from datetime import datetime, timedelta
        import pytz
        tz = pytz.timezone('America/Sao_Paulo')
        now = datetime.now(tz)
        # Only recent dividends (last 3 months), no previous
        idx = pd.date_range(end=now - timedelta(days=15), periods=3, freq='ME', tz=tz)
        df = pd.DataFrame({'Dividends': [2.0, 2.0, 2.0]}, index=idx)
        mock = type('MockTicker', (), {'actions': df})()
        result = _calc_dividend_consistency(mock)
        assert result is None


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
        # VPA não está no info → fallback p/ price / pb_ratio = 90 / 0.95
        assert result["book_value"] == 94.74
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
# v2.5 Continuous Stock Score Tests
# ======================================================================

class TestStockScoreContinuous:
    """Tests for the new 0-10 continuous stock scoring."""

    def test_dy_below_threshold(self):
        """DY < 6% → 0.0 pts no critério."""
        s = _score_dy_stock(0.05)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_dy_at_threshold(self):
        """DY = 6% → 1.0 pt (base)."""
        s = _score_dy_stock(0.06)
        assert s == 1.0, f"Expected 1.0, got {s}"

    def test_dy_mid_range(self):
        """DY = 10.5% → 1.5 pts (1.0 + 0.045 * 11.111 = 1.5)."""
        s = _score_dy_stock(0.105)
        assert s == 1.5, f"Expected 1.5, got {s}"

    def test_dy_max(self):
        """DY = 15% → 2.0 pts."""
        s = _score_dy_stock(0.15)
        assert s == 2.0, f"Expected 2.0, got {s}"

    def test_dy_above_max(self):
        """DY > 15% → capped at 2.0 pts."""
        s = _score_dy_stock(0.20)
        assert s == 2.0, f"Expected 2.0, got {s}"

    def test_dy_none(self):
        """DY None → 0.0."""
        s = _score_dy_stock(None)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_pe_at_limit(self):
        """P/E = 15 → 1.0 pt (base)."""
        s = _score_pe_stock(15.0)
        assert s == 1.0, f"Expected 1.0, got {s}"

    def test_pe_mid(self):
        """P/E = 5 → 1.666... ≈ 1.67 pts."""
        s = _score_pe_stock(5.0)
        assert abs(s - 1.67) < 0.01, f"Expected ~1.67, got {s}"

    def test_pe_low(self):
        """P/E = 1 → ~1.93 pts."""
        s = _score_pe_stock(1.0)
        assert abs(s - 1.93) < 0.01, f"Expected ~1.93, got {s}"

    def test_pe_above_max(self):
        """P/E > 15 → 0.0 pts."""
        s = _score_pe_stock(20.0)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_pe_negative(self):
        """P/E <= 0 → 0.0 pts."""
        s = _score_pe_stock(-5.0)
        assert s == 0.0, f"Expected 0.0, got {s}"
        s2 = _score_pe_stock(0.0)
        assert s2 == 0.0, f"Expected 0.0, got {s2}"

    def test_pe_none(self):
        """P/E None → 0.0."""
        s = _score_pe_stock(None)
        assert s == 0.0

    def test_pb_at_floor(self):
        """P/VP = 0.50 → 2.0 pts (max discount)."""
        s = _score_pb_stock(0.50)
        assert s == 2.0, f"Expected 2.0, got {s}"

    def test_pb_at_fair(self):
        """P/VP = 1.00 → 1.0 pt."""
        s = _score_pb_stock(1.00)
        assert s == 1.0, f"Expected 1.0, got {s}"

    def test_pb_at_ceiling(self):
        """P/VP = 1.50 → 0.0 pts (max allowed)."""
        s = _score_pb_stock(1.50)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_pb_below_floor(self):
        """P/VP < 0.50 → 0.0 pts (MGLU Proteção)."""
        s = _score_pb_stock(0.30)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_pb_above_ceiling(self):
        """P/VP > 1.50 → 0.0 pts."""
        s = _score_pb_stock(1.80)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_pb_asymmetric(self):
        """P/VP assimétrico: 0.75 → 1.5 pts, 1.25 → 0.5 pts."""
        s_low = _score_pb_stock(0.75)
        s_high = _score_pb_stock(1.25)
        assert s_low == 1.5, f"Expected 1.5, got {s_low}"
        assert s_high == 0.5, f"Expected 0.5, got {s_high}"

    def test_pb_none(self):
        """P/VP None → 0.0."""
        s = _score_pb_stock(None)
        assert s == 0.0

    def test_roe_at_threshold(self):
        """ROE = 10% → 1.0 pt."""
        s = _score_roe_stock(0.10)
        assert s == 1.0, f"Expected 1.0, got {s}"

    def test_roe_mid(self):
        """ROE = 20% → 1.5 pts."""
        s = _score_roe_stock(0.20)
        assert s == 1.5, f"Expected 1.5, got {s}"

    def test_roe_max(self):
        """ROE = 30% → 2.0 pts."""
        s = _score_roe_stock(0.30)
        assert s == 2.0, f"Expected 2.0, got {s}"

    def test_roe_above_max(self):
        """ROE > 30% → capped at 2.0."""
        s = _score_roe_stock(0.50)
        assert s == 2.0, f"Expected 2.0, got {s}"

    def test_roe_below_threshold(self):
        """ROE < 10% → 0.0."""
        s = _score_roe_stock(0.05)
        assert s == 0.0

    def test_roe_none(self):
        """ROE None → 0.0."""
        s = _score_roe_stock(None)
        assert s == 0.0

    def test_graham_at_price(self):
        """price = graham_price → 0.0 pts (no margin of safety).
        Document says: 'Se price >= graham_price → 0.0 pontos'."""
        s = _score_graham_stock(100.0, 100.0)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_graham_25_discount(self):
        """price = 0.75 * graham → 1.33 pts."""
        s = _score_graham_stock(75.0, 100.0)
        assert abs(s - 1.33) < 0.01, f"Expected ~1.33, got {s}"

    def test_graham_50_discount(self):
        """price = 0.50 * graham → 2.0 pts (max)."""
        s = _score_graham_stock(50.0, 100.0)
        assert s == 2.0, f"Expected 2.0, got {s}"

    def test_graham_no_discount(self):
        """price > graham_price → 0.0 pts."""
        s = _score_graham_stock(120.0, 100.0)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_graham_none_price(self):
        """price None → 0.0."""
        s = _score_graham_stock(None, 100.0)
        assert s == 0.0

    def test_graham_none_graham(self):
        """graham_price None → 0.0."""
        s = _score_graham_stock(100.0, None)
        assert s == 0.0

    def test_graham_peg_tech(self):
        """Tech sector with PEG=0.5 → use PEG path."""
        s = _score_graham_stock(100.0, 50.0, peg_ratio=0.5, sector='Technology')
        # PEG path: 1.0 + (1.0 - 0.5)/1.0 * 1.0 = 1.5
        assert s == 1.5, f"Expected 1.5, got {s}"

    def test_graham_peg_comm(self):
        """Communication Services with PEG=0.8 → use PEG path."""
        s = _score_graham_stock(100.0, 50.0, peg_ratio=0.8, sector='Communication Services')
        assert abs(s - 1.2) < 0.01, f"Expected ~1.2, got {s}"

    def test_graham_peg_non_tech(self):
        """Non-tech ignores PEG → graham path."""
        s = _score_graham_stock(80.0, 100.0, peg_ratio=0.5, sector='Financial Services')
        # Graham path: price=80 < 100 → 1.0 + (100-80)/80 = 1.25
        assert abs(s - 1.25) < 0.01, f"Expected ~1.25, got {s}"

    def test_total_perfect_score(self):
        """All criteria at max → 10.0 pts."""
        score = calculate_stock_score_continuous(
            dy_medio_3y=0.15, pe_medio_5y=0.01, pb_ratio=0.50,
            roe=0.30, price=50.0, graham_price=100.0
        )
        # DY=2.0 + PE=1.99 + PB=2.0 + ROE=2.0 + Graham=2.0 = 9.99 ≈ 10.0
        assert score == 10.0, f"Expected 10.0, got {score}"

    def test_total_zero_score(self):
        """No criteria met → 0.0 pts."""
        score = calculate_stock_score_continuous(
            dy_medio_3y=0.05, pe_medio_5y=20.0, pb_ratio=2.0,
            roe=0.05, price=100.0, graham_price=50.0
        )
        assert score == 0.0, f"Expected 0.0, got {score}"

    def test_total_mid_score(self):
        """Mid-range values."""
        score = calculate_stock_score_continuous(
            dy_medio_3y=0.09, pe_medio_5y=10.0, pb_ratio=1.0,
            roe=0.15, price=80.0, graham_price=100.0
        )
        # DY: (0.09-0.06)*11.111+1 = 1.33
        # PE: (15-10)/15+1 = 1.33
        # PB: 2*(1.5-1.0) = 1.0
        # ROE: (0.15-0.10)*5+1 = 1.25
        # Graham: (100-80)/80+1 = 1.25
        # Total ≈ 6.16
        assert 6.0 < score < 6.5, f"Expected ~6.16, got {score}"


# ======================================================================
# v2.5 Continuous FII Score Tests
# ======================================================================

class TestFiiScoreContinuous:
    """Tests for the new 0-10 continuous FII scoring."""

    def test_pb_ideal_discount(self):
        """P/VP = 0.70 (max discount in ideal range) → 2.0 pts."""
        s = _score_pb_fii_ideal(0.70)
        assert s == 2.0, f"Expected 2.0, got {s}"

    def test_pb_ideal_mid(self):
        """P/VP = 0.875 → ~1.0 pt."""
        s = _score_pb_fii_ideal(0.875)
        assert abs(s - 1.0) < 0.01, f"Expected ~1.0, got {s}"

    def test_pb_ideal_at_ceiling(self):
        """P/VP = 1.05 → 0.0 pts."""
        s = _score_pb_fii_ideal(1.05)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_pb_ideal_below_floor(self):
        """P/VP = 0.60 (< 0.70) → 0.0 pts."""
        s = _score_pb_fii_ideal(0.60)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_pb_ideal_none(self):
        """P/VP None → 0.0."""
        s = _score_pb_fii_ideal(None)
        assert s == 0.0

    def test_pb_limite_distress_low(self):
        """P/VP = 0.60 → 0.0 pts (edge of distress zone)."""
        s = _score_pb_fii_limite(0.60)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_pb_limite_distress_mid(self):
        """P/VP = 0.65 → 1.0 pt."""
        s = _score_pb_fii_limite(0.65)
        assert s == 1.0, f"Expected 1.0, got {s}"

    def test_pb_limite_distress_high(self):
        """P/VP = 0.699 → ~1.98 pts (near ideal floor)."""
        s = _score_pb_fii_limite(0.699)
        assert s > 1.9, f"Expected >1.9, got {s}"

    def test_pb_limite_premium_low(self):
        """P/VP = 1.06 → ~1.8 pts."""
        s = _score_pb_fii_limite(1.06)
        assert abs(s - 1.8) < 0.1, f"Expected ~1.8, got {s}"

    def test_pb_limite_premium_high(self):
        """P/VP = 1.15 → 0.0 pts."""
        s = _score_pb_fii_limite(1.15)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_pb_limite_ideal_zone(self):
        """P/VP = 0.80 (in ideal zone) → 0.0 pts (not in edge zone)."""
        s = _score_pb_fii_limite(0.80)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_pb_limite_none(self):
        """P/VP None → 0.0."""
        s = _score_pb_fii_limite(None)
        assert s == 0.0

    def test_dy_below_min(self):
        """DY < 8% → 0.0 pts."""
        s = _score_dy_fii(0.07, is_fiagro=False)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_dy_at_min_fii(self):
        """DY = 8% → 1.0 pt."""
        s = _score_dy_fii(0.08, is_fiagro=False)
        assert s == 1.0, f"Expected 1.0, got {s}"

    def test_dy_mid_fii(self):
        """DY = 11% → ~1.46 pts."""
        s = _score_dy_fii(0.11, is_fiagro=False)
        assert abs(s - 1.46) < 0.01, f"Expected ~1.46, got {s}"

    def test_dy_at_cap_fii(self):
        """DY = 14.5% (cap) → 2.0 pts."""
        s = _score_dy_fii(0.145, is_fiagro=False)
        assert abs(s - 2.0) < 0.01, f"Expected ~2.0, got {s}"

    def test_dy_below_min_fiagro(self):
        """FIAGRO DY < 10% → 0.0 pts."""
        s = _score_dy_fii(0.09, is_fiagro=True)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_dy_at_min_fiagro(self):
        """FIAGRO DY = 10% → 1.0 pt."""
        s = _score_dy_fii(0.10, is_fiagro=True)
        assert s == 1.0, f"Expected 1.0, got {s}"

    def test_dy_at_cap_fiagro(self):
        """FIAGRO DY = 16.5% (cap) → 2.0 pts."""
        s = _score_dy_fii(0.165, is_fiagro=True)
        assert abs(s - 2.0) < 0.01, f"Expected ~2.0, got {s}"

    def test_yield_cap_below(self):
        """DY = 5% → ~1.31 pts (very sustainable)."""
        s = _score_yield_cap(0.05, is_fiagro=False)
        assert abs(s - 1.31) < 0.01, f"Expected ~1.31, got {s}"

    def test_yield_cap_at_limit(self):
        """DY at exact cap → 0.0 pts."""
        s = _score_yield_cap(0.145, is_fiagro=False)
        assert abs(s) < 0.01, f"Expected ~0.0, got {s}"

    def test_yield_cap_exceeded(self):
        """DY > 14.5% → 0.0 pts."""
        s = _score_yield_cap(0.16, is_fiagro=False)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_yield_cap_fiagro_exceeded(self):
        """FIAGRO DY > 16.5% → 0.0 pts."""
        s = _score_yield_cap(0.18, is_fiagro=True)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_yield_cap_none(self):
        """DY None → 0.0."""
        s = _score_yield_cap(None)
        assert s == 0.0

    def test_consistency_perfect(self):
        """100% retention → 2.0 pts."""
        s = _score_dividend_consistency(1.0)
        assert s == 2.0, f"Expected 2.0, got {s}"

    def test_consistency_at_target(self):
        """95% retention → 2.0 pts."""
        s = _score_dividend_consistency(0.95)
        assert s == 2.0, f"Expected 2.0, got {s}"

    def test_consistency_below_target(self):
        """80% retention → ~1.68 pts."""
        s = _score_dividend_consistency(0.80)
        assert abs(s - 1.68) < 0.01, f"Expected ~1.68, got {s}"

    def test_consistency_zero(self):
        """0% retention → 0.0 pts."""
        s = _score_dividend_consistency(0.0)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_consistency_none(self):
        """No data → 1.0 pts (neutral)."""
        s = _score_dividend_consistency(None)
        assert s == 1.0, f"Expected 1.0 (neutral), got {s}"

    def test_total_perfect_fii(self):
        """Perfect FII → 8.28 pts (4 criteria × 2.5)."""
        score = calculate_fii_score_continuous(
            pb_ratio=0.70, dividend_yield=0.10, dividend_consistency=1.0
        )
        # v2.5.1: 4 criteria × 2.5
        # s1 (unified pb):  2.5
        # s2 (dy min v2):   1.64 (1.3077 * 1.25)
        # s3 (yield cap v2): 1.64 (2.5 * (1 - 0.10/0.29))
        # s4 (consist v2):  2.5
        # Total: ~8.28
        assert 8.0 < score < 8.6, f"Expected ~8.28, got {score}"

    def test_total_perfect_fiagro(self):
        """Perfect FIAGRO → ~8.23 pts (4 criteria × 2.5)."""
        score = calculate_fiagro_score_continuous(
            pb_ratio=0.70, dividend_yield=0.12, dividend_consistency=1.0
        )
        # s1 (unified pb):   2.5
        # s2 (dy min v2):    1.63 (1.3077 * 1.25)
        # s3 (yield cap v2): 1.59 (2.5 * (1 - 0.12/0.33))
        # s4 (consist v2):   2.5
        # Total: ~8.23
        assert 8.0 < score < 8.6, f"Expected ~8.23, got {score}"


# ======================================================================
# v2.5.1 Continuous FII/FIAGRO Score Tests (4 criteria × 2.5 pts)
# ======================================================================

class TestFiiScoreContinuousV2:
    """Tests for the new v2.5.1 4×2.5 scoring functions."""

    # _score_pb_fii_unified -------------------------------------------------
    def test_pb_unified_ideal_discount(self):
        """P/VP = 0.70 (max ideal) → 2.5 pts."""
        s = _score_pb_fii_unified(0.70)
        assert s == 2.5, f"Expected 2.5, got {s}"

    def test_pb_unified_ideal_mid(self):
        """P/VP = 0.875 → 1.25 pts."""
        s = _score_pb_fii_unified(0.875)
        assert s == 1.25, f"Expected 1.25, got {s}"

    def test_pb_unified_ideal_ceiling(self):
        """P/VP = 1.05 → 0.0 pts."""
        s = _score_pb_fii_unified(1.05)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_pb_unified_below_floor(self):
        """P/VP = 0.60 (< 0.70) → 0.0 from ideal, takes limite=0.0 → 0.0."""
        s = _score_pb_fii_unified(0.60)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_pb_unified_distress_zone(self):
        """P/VP = 0.65 (distress) → limite gives 1.0 × 1.25 = 1.25."""
        s = _score_pb_fii_unified(0.65)
        assert s == 1.25, f"Expected 1.25, got {s}"

    def test_pb_unified_premium_zone(self):
        """P/VP = 1.10 (premium) → limite gives 1.0 × 1.25 = 1.25."""
        s = _score_pb_fii_unified(1.10)
        assert s == 1.25, f"Expected 1.25, got {s}"

    def test_pb_unified_at_limit_ceiling(self):
        """P/VP = 1.15 → 0.0 pts."""
        s = _score_pb_fii_unified(1.15)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_pb_unified_none(self):
        """P/VP None → 0.0."""
        s = _score_pb_fii_unified(None)
        assert s == 0.0, f"Expected 0.0, got {s}"

    # _score_dy_fii_v2 ------------------------------------------------------
    def test_dy_v2_below_min_fii(self):
        """FII DY < 8% → 0.0 pts."""
        s = _score_dy_fii_v2(0.07, is_fiagro=False)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_dy_v2_at_min_fii(self):
        """FII DY = 8% → 1.25 pts."""
        s = _score_dy_fii_v2(0.08, is_fiagro=False)
        assert s == 1.25, f"Expected 1.25, got {s}"

    def test_dy_v2_mid_fii(self):
        """FII DY = 10% → ~1.64 pts."""
        s = _score_dy_fii_v2(0.10, is_fiagro=False)
        assert abs(s - 1.64) < 0.01, f"Expected ~1.64, got {s}"

    def test_dy_v2_cap_fii(self):
        """FII DY = 14.5% (cap) → 2.5 pts."""
        s = _score_dy_fii_v2(0.145, is_fiagro=False)
        assert s == 2.5, f"Expected 2.5, got {s}"

    def test_dy_v2_above_cap_fii(self):
        """FII DY > cap → capped at 2.5."""
        s = _score_dy_fii_v2(0.15, is_fiagro=False)
        assert s == 2.5, f"Expected 2.5, got {s}"

    def test_dy_v2_below_min_fiagro(self):
        """FIAGRO DY < 10% → 0.0 pts."""
        s = _score_dy_fii_v2(0.09, is_fiagro=True)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_dy_v2_at_min_fiagro(self):
        """FIAGRO DY = 10% → 1.25 pts."""
        s = _score_dy_fii_v2(0.10, is_fiagro=True)
        assert s == 1.25, f"Expected 1.25, got {s}"

    def test_dy_v2_cap_fiagro(self):
        """FIAGRO DY = 16.5% (cap) → 2.5 pts."""
        s = _score_dy_fii_v2(0.165, is_fiagro=True)
        assert s == 2.5, f"Expected 2.5, got {s}"

    def test_dy_v2_none(self):
        """DY None → 0.0."""
        s = _score_dy_fii_v2(None)
        assert s == 0.0

    # _score_yield_cap_v2 ---------------------------------------------------
    def test_yield_cap_v2_zero_dy(self):
        """DY = 0% → 2.5 pts (zero risk)."""
        s = _score_yield_cap_v2(0.0, is_fiagro=False)
        assert s == 2.5, f"Expected 2.5, got {s}"

    def test_yield_cap_v2_at_nominal_cap(self):
        """DY at nominal cap (14.5% FII) → 1.25 pts (mid)."""
        s = _score_yield_cap_v2(0.145, is_fiagro=False)
        assert s == 1.25, f"Expected 1.25, got {s}"

    def test_yield_cap_v2_at_double_cap(self):
        """DY at 2× cap (29% FII) → 0.0 pts (zera)."""
        s = _score_yield_cap_v2(0.29, is_fiagro=False)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_yield_cap_v2_above_double_cap(self):
        """DY > 2× cap → 0.0 pts."""
        s = _score_yield_cap_v2(0.30, is_fiagro=False)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_yield_cap_v2_fiagro_at_nominal(self):
        """FIAGRO DY at 16.5% (nominal cap) → 1.25 pts (0.5 × 2.5)."""
        s = _score_yield_cap_v2(0.165, is_fiagro=True)
        assert s == 1.25, f"Expected 1.25, got {s}"

    def test_yield_cap_v2_fiagro_double(self):
        """FIAGRO DY at 2× cap (33%) → 0.0 pts."""
        s = _score_yield_cap_v2(0.33, is_fiagro=True)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_yield_cap_v2_none(self):
        """DY None → 0.0."""
        s = _score_yield_cap_v2(None)
        assert s == 0.0

    # _score_dividend_consistency_v2 ----------------------------------------
    def test_consistency_v2_perfect(self):
        """100% retention → 2.5 pts."""
        s = _score_dividend_consistency_v2(1.0)
        assert s == 2.5, f"Expected 2.5, got {s}"

    def test_consistency_v2_at_target(self):
        """95% retention → 2.5 pts."""
        s = _score_dividend_consistency_v2(0.95)
        assert s == 2.5, f"Expected 2.5, got {s}"

    def test_consistency_v2_below_target(self):
        """80% retention → ~2.11 pts."""
        s = _score_dividend_consistency_v2(0.80)
        assert abs(s - 2.11) < 0.01, f"Expected ~2.11, got {s}"

    def test_consistency_v2_zero(self):
        """0% retention → 0.0 pts."""
        s = _score_dividend_consistency_v2(0.0)
        assert s == 0.0, f"Expected 0.0, got {s}"

    def test_consistency_v2_none(self):
        """No data → 1.5 pts (neutro mais generoso)."""
        s = _score_dividend_consistency_v2(None)
        assert s == 1.5, f"Expected 1.5 (neutro), got {s}"

    # Total scores ----------------------------------------------------------
    def test_total_perfect_fii_v2(self):
        """Perfect FII v2.5.1 → 8.28 pts."""
        score = calculate_fii_score_continuous(
            pb_ratio=0.70, dividend_yield=0.10, dividend_consistency=1.0
        )
        assert 8.0 < score < 8.6, f"Expected ~8.28, got {score}"

    def test_total_perfect_fiagro_v2(self):
        """Perfect FIAGRO v2.5.1 → 8.23 pts."""
        score = calculate_fiagro_score_continuous(
            pb_ratio=0.70, dividend_yield=0.12, dividend_consistency=1.0
        )
        assert 8.0 < score < 8.6, f"Expected ~8.23, got {score}"

    def test_total_zero_fii_v2(self):
        """Zero FII → ~2.5 pts (yield cap still gives pts for 0 risk)."""
        score = calculate_fii_score_continuous(
            pb_ratio=2.0, dividend_yield=0.0, dividend_consistency=0.0
        )
        assert 2.0 < score < 3.0, f"Expected ~2.5, got {score}"


# ======================================================================
# v2.5 analyze_stock with continuous score
# ======================================================================

class TestAnalyzeStockV2:
    """Test that analyze_stock returns v2.5 fields."""

    def test_v2_fields_present(self):
        """Should include dy_medio_3y, pe_medio_5y, net_debt_ebitda, score_v2."""
        info = {
            "currentPrice": 45.50,
            "trailingEps": 4.20,
            "bookValue": 25.00,
            "trailingPE": 10.83,
            "priceToBook": 1.82,
            "dividendYield": 5.8,
            "dividendRate": 2.64,
            "returnOnEquity": 0.168,
            "longName": "Empresa Teste SA",
            "sector": "Financial Services",
        }
        result = analyze_stock("TEST3.SA", info)
        assert "score_v2" in result, "Missing score_v2"
        assert "dy_medio_3y" in result, "Missing dy_medio_3y"
        assert "pe_medio_5y" in result, "Missing pe_medio_5y"
        assert "net_debt_ebitda" in result, "Missing net_debt_ebitda"
        # Without _yf_ticker, should fallback to current values
        assert result["dy_medio_3y"] == 0.058  # fallback to current DY
        assert result["pe_medio_5y"] == 10.83   # fallback to current P/E
        assert isinstance(result["score_v2"], float)
        assert 0 <= result["score_v2"] <= 10.0

    def test_v2_legacy_score_present(self):
        """Should still return legacy score."""
        result = analyze_stock("TEST3.SA", {"currentPrice": 10.0, "longName": "Test"})
        assert "score" in result
        assert isinstance(result["score"], int)


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
