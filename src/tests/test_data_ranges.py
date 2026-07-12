"""
Tests that validate all pipeline output indicators are within acceptable
ranges. Acts as a safety net to catch regressions — if a code change
produces absurd values (e.g. DY = 72% or 16930%), these tests will fail.

Run with:  python -m pytest src/tests/test_data_ranges.py -v
Or:        python -m pytest src/tests/ -v

These tests read from the SQLite database (investments.db) which is the
canonical source of truth after a full ingestion pipeline run.
They do NOT call any external APIs — deterministic and offline.
"""
import os
import sqlite3
import sys

import pytest

# Ensure src/ is in path
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

DB_PATH = os.path.join(os.path.dirname(SRC_DIR), "data", "investments.db")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db():
    """Provide a connection to the investments database."""
    if not os.path.exists(DB_PATH):
        pytest.fail(f"Database not found at {DB_PATH}. Run ingestion first.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _fetch_all(cursor, table: str) -> list[dict]:
    """Fetch all rows from a table as dicts."""
    cursor.execute(f"SELECT * FROM {table}")
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


@pytest.fixture(scope="module")
def stocks(db):
    return _fetch_all(db.cursor(), "stocks")


@pytest.fixture(scope="module")
def fiis(db):
    return _fetch_all(db.cursor(), "fiis")


@pytest.fixture(scope="module")
def fiagros(db):
    return _fetch_all(db.cursor(), "fiagros")


# ======================================================================
# Critical field presence — every asset must have these
# ======================================================================

@pytest.mark.parametrize("table,label", [
    ("stocks", "ações"), ("fiis", "FIIs"), ("fiagros", "FIAGROs")
])
def test_all_have_ticker_and_name(request, table, label):
    """Every asset must have a ticker and name."""
    cursor = request.getfixturevalue("db").cursor()
    cursor.execute(f"SELECT ticker, name FROM {table} WHERE ticker IS NULL OR name IS NULL")
    nulls = cursor.fetchall()
    assert len(nulls) == 0, f"{len(nulls)} {label} sem ticker ou nome"


# ======================================================================
# STOCKS — indicator range validation
# ======================================================================

class TestStockRanges:
    """Validates that stock indicators stay within acceptable ranges."""

    def test_price_positive(self, stocks):
        outliers = [s for s in stocks if s.get("price") is None or s["price"] <= 0]
        assert len(outliers) == 0, f"{len(outliers)} ações com preço inválido: {[s['ticker'] for s in outliers]}"

    def test_dividend_yield_range(self, stocks):
        """DY should be 0-30% for stocks. Values above indicate data distortion."""
        outliers = [s for s in stocks if s.get("dividend_yield") is not None
                    and (s["dividend_yield"] < 0 or s["dividend_yield"] > 0.30)]
        assert len(outliers) == 0, (
            f"{len(outliers)} ações com DY fora do range 0-30%:\n"
            + "\n".join(f"  {s['ticker']}: {s['dividend_yield']*100:.2f}%" for s in outliers)
        )

    def test_dy_medio_3y_range(self, stocks):
        """3-year cumulative DY should be 0-50%."""
        vals = [s.get("dy_medio_3y") for s in stocks if s.get("dy_medio_3y") is not None]
        outliers = [s for s in stocks if s.get("dy_medio_3y") is not None
                    and (s["dy_medio_3y"] < 0 or s["dy_medio_3y"] > 0.50)]
        assert len(outliers) == 0, (
            f"{len(outliers)} ações com dy_medio_3y fora do range 0-50%:\n"
            + "\n".join(f"  {s['ticker']}: {s['dy_medio_3y']*100:.2f}%" for s in outliers)
        )

    def test_pe_ratio_range(self, stocks):
        """P/E should be positive and under 200 (exclui empresas sem lucro)."""
        vals = [s.get("pe_ratio") for s in stocks if s.get("pe_ratio") is not None]
        outliers = [s for s in stocks if s.get("pe_ratio") is not None
                    and (s["pe_ratio"] <= 0 or s["pe_ratio"] > 200)]
        assert len(outliers) == 0, (
            f"{len(outliers)} ações com P/L fora do range 0-200:\n"
            + "\n".join(f"  {s['ticker']}: P/L={s['pe_ratio']:.2f}" for s in outliers)
        )

    def test_pb_ratio_range(self, stocks):
        """P/VP should be > -1 and < 20."""
        outliers = [s for s in stocks if s.get("pb_ratio") is not None
                    and (s["pb_ratio"] < -1 or s["pb_ratio"] > 20)]
        assert len(outliers) == 0, (
            f"{len(outliers)} ações com P/VP fora do range -1 a 20:\n"
            + "\n".join(f"  {s['ticker']}: P/VP={s['pb_ratio']:.4f}" for s in outliers)
        )

    def test_roe_range(self, stocks):
        """ROE should be between -100% and 100%."""
        outliers = [s for s in stocks if s.get("roe") is not None
                    and (s["roe"] < -1.0 or s["roe"] > 1.0)]
        assert len(outliers) == 0, (
            f"{len(outliers)} ações com ROE fora do range -100% a 100%:\n"
            + "\n".join(f"  {s['ticker']}: ROE={s['roe']*100:.2f}%" for s in outliers)
        )

    def test_scores_in_range(self, stocks):
        """All score variants must be 0-10."""
        for field in ("score", "score_v2"):
            outliers = [s for s in stocks if s.get(field) is not None
                        and (s[field] < 0 or s[field] > 10)]
            assert len(outliers) == 0, (
                f"{len(outliers)} ações com {field} fora do range 0-10:\n"
                + "\n".join(f"  {s['ticker']}: {field}={s[field]:.2f}" for s in outliers)
            )

    def test_graham_price_non_negative(self, stocks):
        """Graham price should be >= 0."""
        outliers = [s for s in stocks if s.get("graham_price") is not None and s["graham_price"] < 0]
        assert len(outliers) == 0, (
            f"{len(outliers)} ações com Graham price negativo:\n"
            + "\n".join(f"  {s['ticker']}: {s['graham_price']:.2f}" for s in outliers)
        )

    def test_bazin_price_non_negative(self, stocks):
        """Bazin price should be >= 0."""
        outliers = [s for s in stocks if s.get("bazin_price") is not None and s["bazin_price"] < 0]
        assert len(outliers) == 0, (
            f"{len(outliers)} ações com Bazin price negativo:\n"
            + "\n".join(f"  {s['ticker']}: {s['bazin_price']:.2f}" for s in outliers)
        )

    def test_eps_consistent_with_pe(self, stocks):
        """If EPS is positive and price is known, P/E should be broadly consistent
        (15% tolerance — Yahoo may return trailingPE from slightly different
        time windows than the stored EPS)."""
        mismatches = []
        for s in stocks:
            price = s.get("price")
            eps = s.get("eps")
            pe = s.get("pe_ratio")
            if price and eps and eps > 0 and pe:
                implied_pe = round(price / eps, 2)
                if abs(implied_pe - pe) / pe > 0.15:  # 15% tolerance for timing diff
                    mismatches.append((s["ticker"], pe, implied_pe))
        assert len(mismatches) == 0, (
            f"{len(mismatches)} ações com P/L muito diferente de price/EPS (>15%):\n"
            + "\n".join(f"  {t}: P/L={pe} vs price/eps={ipe} (dif={abs(pe-ipe)/pe*100:.1f}%)"
                        for t, pe, ipe in mismatches[:5])
        )


# ======================================================================
# FIIs — indicator range validation
# ======================================================================

class TestFiiRanges:
    """Validates that FII indicators stay within acceptable ranges."""

    def test_price_positive(self, fiis):
        outliers = [f for f in fiis if f.get("price") is None or f["price"] <= 0]
        assert len(outliers) == 0, f"{len(outliers)} FIIs com preço inválido: {[f['ticker'] for f in outliers]}"

    def test_dividend_yield_range(self, fiis):
        """FII DY should be 0-25%. Values above indicate data distortion."""
        outliers = [f for f in fiis if f.get("dividend_yield") is not None
                    and (f["dividend_yield"] < 0 or f["dividend_yield"] > 0.25)]
        assert len(outliers) == 0, (
            f"{len(outliers)} FIIs com DY fora do range 0-25%:\n"
            + "\n".join(f"  {f['ticker']}: {f['dividend_yield']*100:.2f}%" for f in outliers)
        )

    def test_pb_ratio_range(self, fiis):
        """FII P/VP should be 0-5."""
        outliers = [f for f in fiis if f.get("pb_ratio") is not None
                    and (f["pb_ratio"] < 0 or f["pb_ratio"] > 5)]
        assert len(outliers) == 0, (
            f"{len(outliers)} FIIs com P/VP fora do range 0-5:\n"
            + "\n".join(f"  {f['ticker']}: P/VP={f['pb_ratio']:.4f}" for f in outliers)
        )

    def test_dividend_rate_range(self, fiis):
        """FII dividend rate (R$/cota) should be 0-100."""
        outliers = [f for f in fiis if f.get("dividend_rate") is not None
                    and (f["dividend_rate"] < 0 or f["dividend_rate"] > 100)]
        assert len(outliers) == 0, (
            f"{len(outliers)} FIIs com dividend_rate fora do range R$ 0-100:\n"
            + "\n".join(f"  {f['ticker']}: R$ {f['dividend_rate']:.2f}" for f in outliers)
        )

    def test_scores_in_range(self, fiis):
        """All FII score variants must be 0-10."""
        for field in ("score", "score_v2"):
            outliers = [f for f in fiis if f.get(field) is not None
                        and (f[field] < 0 or f[field] > 10)]
            assert len(outliers) == 0, (
                f"{len(outliers)} FIIs com {field} fora do range 0-10:\n"
                + "\n".join(f"  {f['ticker']}: {field}={f[field]:.2f}" for f in outliers)
            )

    def test_book_value_positive(self, fiis):
        """FII book value should be > 0 when available."""
        outliers = [f for f in fiis if f.get("book_value") is not None and f["book_value"] <= 0]
        assert len(outliers) == 0, (
            f"{len(outliers)} FIIs com book_value <= 0:\n"
            + "\n".join(f"  {f['ticker']}: VPA={f['book_value']:.2f}" for f in outliers)
        )


# ======================================================================
# FIAGROs — indicator range validation
# ======================================================================

class TestFiagroRanges:
    """Validates that FIAGRO indicators stay within acceptable ranges."""

    def test_price_positive(self, fiagros):
        outliers = [f for f in fiagros if f.get("price") is None or f["price"] <= 0]
        assert len(outliers) == 0, f"{len(outliers)} FIAGROs com preço inválido: {[f['ticker'] for f in outliers]}"

    def test_dividend_yield_range(self, fiagros):
        """FIAGRO DY should be 0-30%."""
        outliers = [f for f in fiagros if f.get("dividend_yield") is not None
                    and (f["dividend_yield"] < 0 or f["dividend_yield"] > 0.30)]
        assert len(outliers) == 0, (
            f"{len(outliers)} FIAGROs com DY fora do range 0-30%:\n"
            + "\n".join(f"  {f['ticker']}: {f['dividend_yield']*100:.2f}%" for f in outliers)
        )

    def test_pb_ratio_range(self, fiagros):
        """FIAGRO P/VP should be 0-5."""
        outliers = [f for f in fiagros if f.get("pb_ratio") is not None
                    and (f["pb_ratio"] < 0 or f["pb_ratio"] > 5)]
        assert len(outliers) == 0, (
            f"{len(outliers)} FIAGROs com P/VP fora do range 0-5:\n"
            + "\n".join(f"  {f['ticker']}: P/VP={f['pb_ratio']:.4f}" for f in outliers)
        )

    def test_dividend_rate_range(self, fiagros):
        """FIAGRO dividend rate (R$/cota) should be 0-100."""
        outliers = [f for f in fiagros if f.get("dividend_rate") is not None
                    and (f["dividend_rate"] < 0 or f["dividend_rate"] > 100)]
        assert len(outliers) == 0, (
            f"{len(outliers)} FIAGROs com dividend_rate fora do range R$ 0-100:\n"
            + "\n".join(f"  {f['ticker']}: R$ {f['dividend_rate']:.2f}" for f in outliers)
        )

    def test_scores_in_range(self, fiagros):
        """All FIAGRO score variants must be 0-10."""
        for field in ("score", "score_v2"):
            outliers = [f for f in fiagros if f.get(field) is not None
                        and (f[field] < 0 or f[field] > 10)]
            assert len(outliers) == 0, (
                f"{len(outliers)} FIAGROs com {field} fora do range 0-10:\n"
                + "\n".join(f"  {f['ticker']}: {field}={f[field]:.2f}" for f in outliers)
            )


# ======================================================================
# Cross-asset consistency
# ======================================================================

class TestCrossAssetConsistency:
    """Validates consistency rules across all asset types."""

    def test_dividend_yield_not_extreme(self, stocks, fiis, fiagros):
        """No asset should have DY > 50% (clear data distortion)."""
        all_assets = []
        for s in stocks:
            all_assets.append(("stock", s["ticker"], s.get("dividend_yield", 0)))
        for f in fiis:
            all_assets.append(("fii", f["ticker"], f.get("dividend_yield", 0)))
        for f in fiagros:
            all_assets.append(("fiagro", f["ticker"], f.get("dividend_yield", 0)))

        extreme = [(t, tk, dy) for t, tk, dy in all_assets
                   if dy is not None and dy > 0.50]
        assert len(extreme) == 0, (
            f"{len(extreme)} ativos com DY > 50% (dados distorcidos):\n"
            + "\n".join(f"  [{tipo}] {tk}: {dy*100:.2f}%" for tipo, tk, dy in extreme)
        )

    def test_price_minimum(self, stocks, fiis, fiagros):
        """No asset should have a price <= 0."""
        all_assets = []
        for s in stocks:
            all_assets.append(("stock", s["ticker"], s.get("price")))
        for f in fiis:
            all_assets.append(("fii", f["ticker"], f.get("price")))
        for f in fiagros:
            all_assets.append(("fiagro", f["ticker"], f.get("price")))

        zero_priced = [(t, tk, p) for t, tk, p in all_assets
                       if p is None or p <= 0]
        assert len(zero_priced) == 0, (
            f"{len(zero_priced)} ativos com preço <= 0 ou nulo:\n"
            + "\n".join(f"  [{tipo}] {tk}: {p}" for tipo, tk, p in zero_priced)
        )


# ======================================================================
# Run
# ======================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
