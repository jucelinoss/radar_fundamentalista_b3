"""
Unit tests for the analyzer module (Graham, Bazin, scorecard calculations).

Run with:  python -m pytest src/tests/test_analyzer.py -v
Or:        python -m pytest src/tests/ -v
"""
import sys
import os
import math

# Ensure src/ is in path
SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from analyzer import (
    calculate_graham_price,
    calculate_bazin_price,
    normalize_dividend_yield,
    calculate_stock_score,
    calculate_fii_score,
    analyze_stock,
    analyze_fii,
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
        """All 5 FII criteria met."""
        score = calculate_fii_score(
            price=100.0, pb_ratio=0.95, dividend_yield=0.12, dividend_rate=1.0
        )
        assert score == 5, f"Expected 5, got {score}"

    def test_low_pb_ratio(self):
        """P/B below 0.85 → no ideal range point but may still pass limit."""
        score = calculate_fii_score(
            price=100.0, pb_ratio=0.70, dividend_yield=0.12, dividend_rate=1.0
        )
        # P/B ideal (0.85-1.05)? No → -1
        # P/B ≤ 1.15? Yes → +1
        # DY ≥ 8%? Yes → +1
        # DY ≥ 10%? Yes → +1
        # Rate > 0? Yes → +1
        assert score == 4

    def test_high_pb_ratio(self):
        """P/B above 1.15 → only DY and rate count."""
        score = calculate_fii_score(
            price=100.0, pb_ratio=1.50, dividend_yield=0.12, dividend_rate=1.0
        )
        # P/B ideal? No. P/B ≤ 1.15? No.
        # DY ≥ 8%? Yes. DY ≥ 10%? Yes. Rate > 0? Yes.
        assert score == 3

    def test_no_dividend(self):
        """Zero dividend rate → no rate point, no yield points."""
        score = calculate_fii_score(
            price=100.0, pb_ratio=0.95, dividend_yield=0.0, dividend_rate=0.0
        )
        # P/B ideal ✓, P/B limit ✓, DY 0 ✗, DY excellent ✗, Rate ✗
        assert score == 2

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
        # Score: P/B ideal ✓, P/B limit ✓, DY ≥ 8% ✓, DY ≥ 10% ✗ (9.5%), Rate >0 ✓ → 4
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
