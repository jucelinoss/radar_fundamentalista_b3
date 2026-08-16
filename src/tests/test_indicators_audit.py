"""
Automated Indicator Audit & Market Alignment Tests (Investidor 10 / CVM Standard)

Validates that Dividend Yield (DY) and P/VP across all asset classes (Stocks, FIIs, FIAGROs)
meet realistic fundamental market criteria and do NOT suffer from:
1. Un-annualized monthly yield truncation (e.g. 1.37% instead of 16.79% LTM).
2. Distorted or negative P/VP ratios for active real estate/agro funds.
3. Scorecard breakdown misalignment (e.g. 0.0 pts for healthy 10-18% dividend yield).

Run with:
    python -m pytest src/tests/test_indicators_audit.py -v
"""
import os
import sqlite3
import pytest

SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(os.path.dirname(SRC_DIR), "data", "investments.db")


@pytest.fixture(scope="module")
def db():
    """Connection to canonical database."""
    if not os.path.exists(DB_PATH):
        pytest.fail(f"Database not found at {DB_PATH}.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _fetch_table(db, table_name: str) -> list[dict]:
    cursor = db.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# ======================================================================
# CVM Regulatory Data Integrity (Primary Source of Truth)
# ======================================================================

class TestCVMDataConsistency:
    """Validates that database indicators directly match official CVM reports (dados.cvm.gov.br)."""

    def test_fii_vpa_matches_cvm(self, db):
        """Stored book_value for FIIs must match the official CVM VPA per share."""
        import json
        cvm_vpa_path = os.path.join(os.path.dirname(SRC_DIR), "data", "fii_vpa.json")
        if not os.path.exists(cvm_vpa_path):
            pytest.skip("CVM FII VPA cache não encontrado")
        with open(cvm_vpa_path, "r", encoding="utf-8") as f:
            cvm_vpas = json.load(f)

        cursor = db.cursor()
        cursor.execute("SELECT ticker, book_value, price, pb_ratio FROM fiis")
        mismatches = []
        for r in cursor.fetchall():
            clean = r["ticker"].replace(".SA", "")
            if clean in cvm_vpas and r["book_value"] is not None:
                cvm_val = cvm_vpas[clean]
                # Verifica tolerância de arredondamento de 1 centavo
                if abs(r["book_value"] - cvm_val) > 0.05:
                    mismatches.append((clean, r["book_value"], cvm_val))
        assert len(mismatches) == 0, (
            f"{len(mismatches)} FIIs com VPA divergente da CVM oficial:\n"
            + "\n".join(f"  {t}: DB={db_v} vs CVM={cvm_v}" for t, db_v, cvm_v in mismatches[:10])
        )

    def test_fiagro_vpa_matches_cvm(self, db):
        """Stored book_value for FIAGROs must match the official CVM VPA per share."""
        import json
        cvm_vpa_path = os.path.join(os.path.dirname(SRC_DIR), "data", "fiagro_vpa.json")
        if not os.path.exists(cvm_vpa_path):
            pytest.skip("CVM FIAGRO VPA cache não encontrado")
        with open(cvm_vpa_path, "r", encoding="utf-8") as f:
            cvm_vpas = json.load(f)

        cursor = db.cursor()
        cursor.execute("SELECT ticker, book_value, price, pb_ratio FROM fiagros")
        mismatches = []
        for r in cursor.fetchall():
            clean = r["ticker"].replace(".SA", "")
            if clean in cvm_vpas and r["book_value"] is not None:
                cvm_val = cvm_vpas[clean]
                if abs(r["book_value"] - cvm_val) > 0.05:
                    mismatches.append((clean, r["book_value"], cvm_val))
        assert len(mismatches) == 0, (
            f"{len(mismatches)} FIAGROs com VPA divergente da CVM oficial:\n"
            + "\n".join(f"  {t}: DB={db_v} vs CVM={cvm_v}" for t, db_v, cvm_v in mismatches[:10])
        )


# ======================================================================
# FIAGROs — Market Alignment & Indicator Audit
# ======================================================================

class TestFiagroIndicatorsAudit:
    """Validates FIAGRO metrics against CVM and Investidor 10 trailing 12M standard."""

    def test_no_unannualized_monthly_dy(self, db):
        """
        Critical regression check:
        FIAGROs paying monthly dividends must NEVER have an un-annualized DY (0.5% - 4.5%).
        If an asset is paying, its annualized DY in Brazil is >= 5.0% (typically 11% - 18%).
        """
        fiagros = _fetch_table(db, "fiagros")
        unannualized = [
            f for f in fiagros
            if f.get("dividend_yield") is not None and 0.005 <= f["dividend_yield"] < 0.05
        ]
        assert len(unannualized) == 0, (
            f"Encontrados {len(unannualized)} FIAGROs com DY mensal não-anualizado (< 5%):\n"
            + "\n".join(f"  {f['ticker']}: DY={f['dividend_yield']*100:.2f}% (Price: R$ {f.get('price')})" for f in unannualized)
        )

    def test_rura11_dividend_yield_alignment(self, db):
        """RURA11 must reflect the ~15-17% LTM yield reported on Investidor 10, not 1.37%."""
        cursor = db.cursor()
        cursor.execute("SELECT ticker, price, dividend_yield, score_v2, score_breakdown FROM fiagros WHERE ticker LIKE '%RURA%'")
        rura = cursor.fetchone()
        assert rura is not None, "RURA11 não encontrado no banco de FIAGROs"
        assert rura["dividend_yield"] >= 0.12, f"RURA11 DY muito baixo: {rura['dividend_yield']*100:.2f}%"
        assert rura["score_v2"] >= 6.0, f"RURA11 score anormalmente baixo: {rura['score_v2']}"

    def test_fiagro_pvp_reasonable_bounds(self, db):
        """Active FIAGROs must have P/VP within reasonable market discount/premium bounds."""
        fiagros = _fetch_table(db, "fiagros")
        for f in fiagros:
            pvp = f.get("pb_ratio")
            if pvp is not None:
                assert pvp > 0, f"FIAGRO {f['ticker']} com P/VP negativo ou zero: {pvp}"
                assert pvp <= 3.0, f"FIAGRO {f['ticker']} com P/VP excessivo: {pvp}"


# ======================================================================
# FIIs — Market Alignment & Indicator Audit
# ======================================================================

class TestFiiIndicatorsAudit:
    """Validates FII metrics against CVM and Investidor 10 trailing 12M standard."""

    def test_no_unannualized_monthly_dy(self, db):
        """
        FIIs with active distributions must have annualized 12M DY,
        never a truncated single month yield (< 5% for paying funds).
        """
        fiis = _fetch_table(db, "fiis")
        # Exclude funds with 0 distributions (e.g. undergoing liquidation or pure development)
        unannualized = [
            f for f in fiis
            if f.get("dividend_yield") is not None and 0.005 <= f["dividend_yield"] < 0.05
        ]
        assert len(unannualized) == 0, (
            f"Encontrados {len(unannualized)} FIIs com DY mensal não-anualizado (< 5%):\n"
            + "\n".join(f"  {f['ticker']}: DY={f['dividend_yield']*100:.2f}%" for f in unannualized)
        )

    def test_benchmark_fiis_alignment(self, db):
        """Benchmark FIIs (MXRF11, HGLG11, KNIP11, CPTS11) must have realistic market DY (7% - 16%)."""
        cursor = db.cursor()
        benchmarks = ["MXRF11", "HGLG11", "KNIP11", "CPTS11"]
        for ticker in benchmarks:
            cursor.execute("SELECT ticker, price, pb_ratio, dividend_yield, score_v2 FROM fiis WHERE ticker LIKE ?", (f"%{ticker}%",))
            row = cursor.fetchone()
            assert row is not None, f"FII de referência {ticker} não encontrado"
            assert 0.06 <= row["dividend_yield"] <= 0.20, (
                f"{ticker} DY fora do esperado de mercado: {row['dividend_yield']*100:.2f}%"
            )
            assert 0.60 <= row["pb_ratio"] <= 1.40, (
                f"{ticker} P/VP fora do esperado de mercado: {row['pb_ratio']:.2f}"
            )


# ======================================================================
# Stocks — Market Alignment & Indicator Audit
# ======================================================================

class TestStockIndicatorsAudit:
    """Validates Stock metrics against B3 and Investidor 10 fundamental criteria."""

    def test_stock_prices_and_pe_ratios(self, db):
        """Stock prices must be positive; profitable stocks must have P/E between 0.5 and 200."""
        stocks = _fetch_table(db, "stocks")
        for s in stocks:
            price = s.get("price")
            assert price is not None and price > 0, f"Ação {s['ticker']} com preço inválido: {price}"
            pe = s.get("pe_ratio")
            if pe is not None and pe > 0:
                assert 0.5 <= pe <= 200.0, f"Ação {s['ticker']} com P/L fora da realidade: {pe}"

    def test_stock_dividend_yields(self, db):
        """Stock DY must be within 0% - 30%."""
        stocks = _fetch_table(db, "stocks")
        for s in stocks:
            dy = s.get("dividend_yield")
            if dy is not None:
                assert 0.0 <= dy <= 0.30, f"Ação {s['ticker']} com DY fora dos limites: {dy*100:.2f}%"


# ======================================================================
# Score Breakdown Consistency
# ======================================================================

class TestScoreBreakdownIntegrity:
    """Ensures no asset with healthy metrics receives 0.0 on DY or P/VP criteria."""

    def test_fiagro_score_breakdown_not_zero_on_healthy_dy(self, db):
        """FIAGROs in the sweet spot (10% to 18% DY) must receive strong score (>= 1.5/4.0) on DY criterion."""
        import json
        fiagros = _fetch_table(db, "fiagros")
        for f in fiagros:
            dy = f.get("dividend_yield")
            breakdown_str = f.get("score_breakdown")
            if dy and 0.10 <= dy <= 0.18 and breakdown_str:
                breakdown = json.loads(breakdown_str)
                dy_item = next((item for item in breakdown if "Yield" in item["label"]), None)
                if dy_item:
                    assert dy_item["score"] >= 1.5, (
                        f"FIAGRO {f['ticker']} com DY={dy*100:.2f}% recebeu nota DY muito baixa: {dy_item['score']}/4.0"
                    )
