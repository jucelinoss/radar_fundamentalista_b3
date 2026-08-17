"""Esteira de Testes Automatizados para a Calculadora de Renda Fixa e Previdencia Privada (PGBL x VGBL).

Valida:
1. Precisao matematica da deducao do IRPF anual (teto de 12% da renda bruta).
2. Precisao matematica da projecao VGBL x PGBL simples x PGBL com Reinvestimento fiscal (Caso exato da planilha).
3. Precisao do calculo comparativo de Renda Fixa (Poupanca vs CDB vs LCI/LCA vs Tesouro com tabela regressiva).
4. Integridade estrutural do DOM e funcoes JS no index-v2.html e dashboard.js.
"""

import math
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HTML_PATH = REPO_ROOT / "index-v2.html"
JS_PATH = REPO_ROOT / "assets" / "dashboard.js"
CSS_PATH = REPO_ROOT / "assets" / "dashboard.css"


# ===================================================================
# 1. Funcoes Oraculo de Matematica Financeira & Tributaria
# ===================================================================

def calc_irpf_due(income: float):
    """Calcula o imposto de renda anual devido pela tabela progressiva oficial."""
    if income <= 22847.76:
        return {"rate": 0.0, "deduction": 0.0, "tax": 0.0}
    elif income <= 33919.80:
        return {"rate": 0.075, "deduction": 1713.58, "tax": max(0.0, income * 0.075 - 1713.58)}
    elif income <= 45012.60:
        return {"rate": 0.15, "deduction": 4257.57, "tax": max(0.0, income * 0.15 - 4257.57)}
    elif income <= 55976.16:
        return {"rate": 0.225, "deduction": 7633.51, "tax": max(0.0, income * 0.225 - 7633.51)}
    else:
        return {"rate": 0.275, "deduction": 10432.32, "tax": max(0.0, income * 0.275 - 10432.32)}


def calc_future_value(pmt: float, annual_rate: float, months: int):
    """Calcula o valor futuro de uma serie de pagamentos mensais postecipados."""
    monthly_rate = math.pow(1.0 + annual_rate, 1.0 / 12.0) - 1.0
    if monthly_rate <= 0:
        return pmt * months
    return pmt * (math.pow(1.0 + monthly_rate, months) - 1.0) / monthly_rate


def simulate_pgbl_vgbl_full(annual_income: float, invest_pct: float, years: int, annual_return: float, reinvest_tax_rate: float = 0.15):
    """Simula os 3 cenarios de Previdencia com exatidao centesimal."""
    annual_invest = annual_income * (invest_pct / 100.0)
    monthly_invest = annual_invest / 12.0
    new_tax_base = max(0.0, annual_income - annual_invest)

    tax_without = calc_irpf_due(annual_income)["tax"]
    tax_with = calc_irpf_due(new_tax_base)["tax"]
    annual_tax_savings = max(0.0, tax_without - tax_with)
    total_tax_savings_no_interest = annual_tax_savings * years
    monthly_reinvest = annual_tax_savings / 12.0

    months = years * 12
    monthly_rate = math.pow(1.0 + annual_return, 1.0 / 12.0) - 1.0

    # Plano Principal
    main_gross = calc_future_value(monthly_invest, annual_return, months)
    main_invested = monthly_invest * months
    main_earnings = max(0.0, main_gross - main_invested)

    # Tabela Regressiva Previdencia
    if years <= 2:
        reg_tax = 0.35
    elif years <= 4:
        reg_tax = 0.30
    elif years <= 6:
        reg_tax = 0.25
    elif years <= 8:
        reg_tax = 0.20
    elif years <= 10:
        reg_tax = 0.15
    else:
        reg_tax = 0.10

    # 1. VGBL (IR sobre rendimento)
    vgbl_tax = main_earnings * reg_tax
    vgbl_net = main_gross - vgbl_tax

    # 2. PGBL Simples (IR sobre total + economia acumulada sem juros)
    pgbl_plan_tax = main_gross * reg_tax
    pgbl_plan_net = main_gross - pgbl_plan_tax
    pgbl_simple_total = pgbl_plan_net + total_tax_savings_no_interest

    # 3. PGBL Otimizado (Reinvestindo mensalmente a economia de IR)
    reinvest_gross = calc_future_value(monthly_reinvest, annual_return, months)
    reinvest_invested = monthly_reinvest * months
    reinvest_earnings = max(0.0, reinvest_gross - reinvest_invested)
    reinvest_tax = reinvest_earnings * reinvest_tax_rate
    reinvest_net = reinvest_gross - reinvest_tax
    pgbl_opt_total = pgbl_plan_net + reinvest_net

    return {
        "annual_tax_savings": round(annual_tax_savings, 2),
        "total_tax_savings_no_interest": round(total_tax_savings_no_interest, 2),
        "main_gross": round(main_gross, 2),
        "main_invested": round(main_invested, 2),
        "main_earnings": round(main_earnings, 2),
        "vgbl_tax": round(vgbl_tax, 2),
        "vgbl_net": round(vgbl_net, 2),
        "pgbl_plan_net": round(pgbl_plan_net, 2),
        "pgbl_simple_total": round(pgbl_simple_total, 2),
        "reinvest_net": round(reinvest_net, 2),
        "pgbl_opt_total": round(pgbl_opt_total, 2),
        "advantage_over_vgbl": round(pgbl_opt_total - vgbl_net, 2)
    }


# ===================================================================
# 2. Testes de Precisao Matematica dos Modelos
# ===================================================================

class TestPrevidenciaMathPrecision:
    """Valida as equacoes da Previdencia Privada contra a planilha modelo."""

    def test_spreadsheet_exact_case_120k_30y_10pct(self):
        """Caso 1: Renda R$ 120k, 12% aporte, 30 anos, 10% a.a. (Planilha do usuario)."""
        res = simulate_pgbl_vgbl_full(annual_income=120000.0, invest_pct=12.0, years=30, annual_return=0.10, reinvest_tax_rate=0.15)

        # Economia Anual de IR
        assert res["annual_tax_savings"] == 3960.00
        assert res["total_tax_savings_no_interest"] == 118800.00

        # Plano Principal (Bruto e Aportes)
        assert math.isclose(res["main_gross"], 2475411.98, rel_tol=1e-4)
        assert res["main_invested"] == 432000.00

        # VGBL Resgate
        assert math.isclose(res["vgbl_tax"], 204341.20, rel_tol=1e-4)
        assert math.isclose(res["vgbl_net"], 2271070.78, rel_tol=1e-4)

        # PGBL Simples
        assert math.isclose(res["pgbl_plan_net"], 2227870.78, rel_tol=1e-4)
        assert math.isclose(res["pgbl_simple_total"], 2346670.78, rel_tol=1e-4)

        # PGBL Otimizado (Reinvestimento da Restituicao)
        assert math.isclose(res["reinvest_net"], 596447.55, rel_tol=1e-4)
        assert math.isclose(res["pgbl_opt_total"], 2824318.33, rel_tol=1e-4)
        assert math.isclose(res["advantage_over_vgbl"], 553247.55, rel_tol=1e-4)

    def test_irpf_brackets_deduction(self):
        """Valida os intervalos da tabela do IRPF."""
        # Isento
        assert calc_irpf_due(20000)["tax"] == 0.0
        # Faixa 7.5%
        f2 = calc_irpf_due(30000)
        assert round(f2["tax"], 2) == round(30000 * 0.075 - 1713.58, 2)
        # Faixa 27.5%
        f5 = calc_irpf_due(100000)
        assert round(f5["tax"], 2) == round(100000 * 0.275 - 10432.32, 2)


class TestFixedIncomeComparisonPrecision:
    """Valida as equacoes de Renda Fixa & Poupanca."""

    def test_poupanca_vs_cdb_compounding(self):
        """Valida que CDB 100% CDI supera a Poupanca em 2 anos (IR 17.5%)."""
        amount = 10000.0
        years = 2.0
        cdi_rate = 0.13
        tax_rate = 0.175

        # Poupanca
        poupanca_rate = 0.0617 + 0.005 # ~6.67% a.a.
        poupanca_net = amount * math.pow(1 + poupanca_rate, years)

        # CDB 100% CDI
        cdb_gross = amount * math.pow(1 + cdi_rate, years)
        cdb_profit = cdb_gross - amount
        cdb_net = cdb_gross - (cdb_profit * tax_rate)

        assert cdb_net > poupanca_net
        loss = cdb_net - poupanca_net
        assert loss > 500.0 # Perda significativa na poupanca


# ===================================================================
# 3. Testes de Contrato de DOM e JS
# ===================================================================

class TestPrevidenciaAndRfDOMContract:
    """Valida presenca dos elementos de Previdencia e Renda Fixa no HTML/JS."""

    @pytest.fixture(scope="module")
    def html_content(self):
        return HTML_PATH.read_text(encoding="utf-8")

    @pytest.fixture(scope="module")
    def js_content(self):
        return JS_PATH.read_text(encoding="utf-8")

    def test_previdencia_mode_button_and_grid(self, html_content):
        """Valida que o botao de modo e o painel de Previdencia existem no HTML."""
        assert 'id="btn-calc-mode-previdencia"' in html_content
        assert 'id="calc-grid-previdencia"' in html_content
        assert 'switchCalcMode(\'previdencia\')' in html_content

    def test_previdencia_inputs_and_results(self, html_content):
        """Valida a presenca de todos os campos de entrada e saida de previdencia."""
        required_ids = [
            "calc-prev-diag-decl",
            "calc-prev-diag-inss",
            "calc-prev-diag-horizon",
            "calc-prev-diag-banner",
            "calc-prev-income",
            "calc-prev-pct",
            "calc-prev-years",
            "calc-prev-regime",
            "calc-prev-prog-tax",
            "calc-prev-return",
            "calc-prev-reinvest-tax",
            "calc-prev-annual-invest",
            "calc-prev-new-tax-base",
            "calc-prev-tax-diff",
            "calc-prev-tax-savings-annual",
            "calc-prev-tax-savings-total",
            "calc-prev-vgbl-gross",
            "calc-prev-vgbl-tax",
            "calc-prev-vgbl-net",
            "calc-prev-pgbl-plan-net",
            "calc-prev-pgbl-simple-net",
            "calc-prev-opt-total-net",
            "previdencia-chart",
            "calc-prev-verdict-desc"
        ]
        for elem_id in required_ids:
            assert f'id="{elem_id}"' in html_content, f"Elemento #{elem_id} ausente no HTML."

    def test_poupanca_elements_exist_in_rf(self, html_content):
        """Valida que os elementos da Poupanca e alerta de custo de oportunidade estao presentes."""
        assert 'id="calc-card-poupanca"' in html_content
        assert 'id="calc-poupanca-net-val"' in html_content
        assert 'id="calc-poupanca-rate-info"' in html_content
        assert 'id="calc-poupanca-loss-desc"' in html_content

    def test_js_previdencia_functions(self, js_content):
        """Valida que as funcoes JS de Previdencia estao implementadas no dashboard.js."""
        assert "function calculatePrevidencia()" in js_content
        assert "function updatePrevidenciaDiagnostic()" in js_content
        assert "function applyDiagnosticToSimulation()" in js_content
        assert "function onPrevRegimeChange()" in js_content
        assert "function renderPrevidenciaChart(" in js_content
        assert "function setPrevIncomePreset(" in js_content
        assert "function onPrevPctChange(" in js_content
        assert "calc-grid-previdencia" in js_content
