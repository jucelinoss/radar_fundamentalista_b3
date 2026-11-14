"""Esteira de Testes Automatizados para a Calculadora / Simulador de Renda Passiva.

Valida:
1. Precisao matematica do calculo de Meta de Renda (Bruto, Liquido, IR/JCP, Cotas/Titulos).
2. Precisao matematica da projecao Bola de Neve (Juros compostos, Magic Number, IR acumulado).
3. Segregacao por categorias de ativos (Estrategias, Acoes, FIIs, FIAGROs, Tesouro Direto).
4. Tratamento de aliquotas tributarias (Isento 0%, Acoes c/ JCP 4.375% estimado, Tesouro 15%, Curto prazo 22.5%).
5. Integridade estrutural do DOM e funcoes JS no index-v2.html e dashboard.js.
"""

import math
import re
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HTML_PATH = REPO_ROOT / "index-v2.html"
JS_PATH = REPO_ROOT / "assets" / "dashboard.js"
CSS_PATH = REPO_ROOT / "assets" / "dashboard.css"


# ===================================================================
# 1. Funcoes de Referencia Matematica (Python Oracle)
# ===================================================================

def calculate_goal_math(monthly_net_target: float, gross_dy: float, tax_rate: float, unit_price: float = 0.0):
    net_dy = gross_dy * (1.0 - tax_rate)
    annual_net_target = monthly_net_target * 12.0
    total_required = (annual_net_target / net_dy) if net_dy > 0 else 0.0
    annual_gross = (annual_net_target / (1.0 - tax_rate)) if (1.0 - tax_rate) > 0 else annual_net_target
    monthly_gross = annual_gross / 12.0
    annual_tax = annual_gross - annual_net_target
    daily_net = annual_net_target / 365.0
    units = math.ceil(total_required / unit_price) if unit_price > 0 else 0

    return {
        "total_required": round(total_required, 2),
        "annual_net": round(annual_net_target, 2),
        "annual_gross": round(annual_gross, 2),
        "monthly_gross": round(monthly_gross, 2),
        "annual_tax": round(annual_tax, 2),
        "daily_net": round(daily_net, 2),
        "units": units,
        "net_dy": round(net_dy, 6)
    }


def calculate_snowball_math(initial: float, monthly: float, gross_dy: float, tax_rate: float, years: int, unit_price: float = 0.0, annual_inflation: float = 0.045):
    net_dy = gross_dy * (1.0 - tax_rate)
    monthly_net_rate = math.pow(1.0 + net_dy, 1.0 / 12.0) - 1.0
    months = years * 12

    balance = initial
    total_invested = initial

    for _ in range(months):
        net_div = balance * monthly_net_rate
        balance = balance + net_div + monthly
        total_invested += monthly

    final_dividends_net = max(0.0, balance - total_invested)
    final_dividends_gross = (final_dividends_net / (1.0 - tax_rate)) if (1.0 - tax_rate) > 0 else final_dividends_net
    final_tax_estimated = final_dividends_gross - final_dividends_net
    final_monthly_net_income = balance * monthly_net_rate
    magic_number = math.ceil(1.0 / monthly_net_rate) if monthly_net_rate > 0 else 0
    magic_capital = magic_number * unit_price if unit_price > 0 else 0.0

    cum_inflation = math.pow(1.0 + annual_inflation, years)
    final_real_balance = balance / cum_inflation
    final_real_monthly_income = final_monthly_net_income / cum_inflation
    real_annual_rate = ((1.0 + net_dy) / (1.0 + annual_inflation)) - 1.0
    real_net_gain = final_real_balance - total_invested

    return {
        "final_balance": round(balance, 2),
        "total_invested": round(total_invested, 2),
        "final_dividends_net": round(final_dividends_net, 2),
        "final_tax_estimated": round(final_tax_estimated, 2),
        "final_monthly_net_income": round(final_monthly_net_income, 2),
        "magic_number": magic_number,
        "magic_capital": round(magic_capital, 2),
        "final_real_balance": round(final_real_balance, 2),
        "final_real_monthly_income": round(final_real_monthly_income, 2),
        "real_annual_rate": round(real_annual_rate, 6),
        "real_net_gain": round(real_net_gain, 2)
    }


def calculate_retrospective_math(
    amount: float,
    modality: str,
    reinvest: bool,
    annual_inflation: float,
    history_points: list,
    target_years: int,
    current_dy: float
):
    """Oraculo matematico para o simulador retrospectivo."""
    history_duration_years = 0.0
    if len(history_points) >= 2:
        # Assumindo pontos mensais ~ 12 pts por ano
        history_duration_years = (len(history_points) - 1) / 12.0

    # Retorno do 1o ano
    r1y = current_dy
    if len(history_points) >= 12:
        p0 = history_points[0].get("price", 1.0)
        p1 = history_points[min(12, len(history_points) - 1)].get("price", p0)
        ret_price_1y = (p1 - p0) / p0
        avg_dy_1y = sum(p.get("dy", 0.0) for p in history_points[:12]) / 12.0 / 100.0
        r1y = ret_price_1y + avg_dy_1y

    is_real = history_duration_years >= target_years * 0.9 and len(history_points) >= target_years * 6

    if is_real:
        start_idx = max(0, len(history_points) - 1 - (target_years * 12))
        p_start = history_points[start_idx].get("price", 1.0)
        p_end = history_points[-1].get("price", p_start)
        f_price = p_end / p_start
        period_slice = history_points[start_idx:]
        avg_dy = (sum(p.get("dy", 0.0) for p in period_slice) / len(period_slice)) / 100.0 if period_slice else current_dy
        if reinvest:
            cagr = math.pow(f_price, 1.0 / target_years) - 1.0 + avg_dy
            total_factor = math.pow(1.0 + cagr, target_years)
        else:
            total_factor = f_price + (avg_dy * target_years)
    else:
        obs_duration = history_duration_years
        p_start = max(0.0001, history_points[0].get("price", 1.0) if history_points else 1.0)
        p_end = max(0.0001, history_points[-1].get("price", p_start) if history_points else p_start)
        f_price = max(0.0001, p_end / p_start)
        avg_dy = (sum(p.get("dy", 0.0) for p in history_points) / len(history_points)) / 100.0 if history_points else current_dy
        if obs_duration >= 0.5:
            cagr_obs = math.pow(f_price, 1.0 / max(0.1, obs_duration)) - 1.0 + avg_dy
            base_obs = max(0.01, 1.0 + cagr_obs)
            f_obs = math.pow(base_obs, obs_duration)
        else:
            f_obs = 1.0
        missing_years = max(0.0, target_years - obs_duration)
        base_proj = max(0.01, 1.0 + r1y)
        f_proj = math.pow(base_proj, missing_years)
        total_factor = max(0.001, f_obs * f_proj)

    total_invested = amount if modality == "single" else amount * (target_years * 12)
    if modality == "single":
        balance_nom = amount * total_factor
    else:
        cagr_eq = math.pow(max(0.01, total_factor), 1.0 / target_years) - 1.0
        m_rate = math.pow(1.0 + cagr_eq, 1.0 / 12.0) - 1.0
        balance_nom = amount * ((math.pow(1.0 + m_rate, target_years * 12) - 1.0) / m_rate) if m_rate > 0 else total_invested

    cum_inf = math.pow(1.0 + annual_inflation, target_years)
    balance_real = balance_nom / cum_inf

    return {
        "is_real": is_real,
        "total_invested": round(total_invested, 2),
        "balance_nominal": round(balance_nom, 2),
        "balance_real": round(balance_real, 2),
        "nominal_return_pct": round(((balance_nom - total_invested) / total_invested) * 100.0, 2),
        "real_return_pct": round(((balance_real - total_invested) / total_invested) * 100.0, 2),
        "r1y": round(r1y, 4)
    }


# ===================================================================
# 2. Testes de Precisao Matematica do Simulador
# ===================================================================

class TestCalculatorMathPrecision:
    """Valida as equacoes financeiras de Meta de Renda e Bola de Neve."""

    def test_goal_exempt_asset(self):
        """Ativo Isento (ex: FII a 10% a.a., R$ 1.000/mes líquido)."""
        res = calculate_goal_math(monthly_net_target=1000.0, gross_dy=0.10, tax_rate=0.0, unit_price=100.0)
        assert res["total_required"] == 120000.00
        assert res["annual_net"] == 12000.00
        assert res["annual_tax"] == 0.00
        assert res["units"] == 1200

    def test_goal_tesouro_with_fifteen_percent_tax(self):
        """Tesouro Direto com 15% de IR (Renda Fixa > 2 anos)."""
        # Gross DY 11.5%, IR 15% -> Net DY = 9.775%
        res = calculate_goal_math(monthly_net_target=1000.0, gross_dy=0.115, tax_rate=0.15, unit_price=1000.0)
        assert res["net_dy"] == 0.09775
        assert res["total_required"] == 122762.15
        assert res["annual_gross"] == 14117.65
        assert res["annual_tax"] == 2117.65
        assert res["units"] == 123

    def test_goal_stock_with_jcp_effective_tax(self):
        """Estimativa de 25% dos proventos em JCP, tributado a 17.5% em 2026."""
        res = calculate_goal_math(monthly_net_target=2000.0, gross_dy=0.08, tax_rate=0.04375, unit_price=25.0)
        expected_net_dy = 0.08 * (1 - 0.04375)
        assert math.isclose(res["net_dy"], expected_net_dy, rel_tol=1e-5)
        assert res["total_required"] == round(24000.0 / expected_net_dy, 2)
        assert res["units"] == math.ceil(res["total_required"] / 25.0)

    def test_snowball_compounding_five_years(self):
        """Simulacao Bola de Neve por 5 anos com aportes mensais."""
        res = calculate_snowball_math(initial=5000.0, monthly=500.0, gross_dy=0.10, tax_rate=0.0, years=5, unit_price=100.0)
        assert res["total_invested"] == 35000.00 # 5000 + 500 * 60
        assert res["final_balance"] > 45000.00
        assert res["final_dividends_net"] > 10000.00
        assert res["magic_number"] == 126 # ceil(1 / ((1.10)^(1/12)-1))
        assert res["magic_capital"] == 12600.00

    def test_snowball_with_tesouro_tax(self):
        """Bola de Neve com 15% de IR sobre Renda Fixa."""
        res = calculate_snowball_math(initial=10000.0, monthly=1000.0, gross_dy=0.12, tax_rate=0.15, years=10, unit_price=1000.0)
        assert res["final_tax_estimated"] > 0.00
        assert res["total_invested"] == 130000.00 # 10000 + 1000 * 120
        assert res["final_balance"] > 200000.00

    def test_snowball_real_growth_ipca_adjustment(self):
        """Valida que o poder de compra real e a rentabilidade real líquida (Fisher) são calculados corretamente."""
        # 10% a.a. líquido, inflação de 4.5% a.a., por 5 anos
        res = calculate_snowball_math(initial=10000.0, monthly=500.0, gross_dy=0.10, tax_rate=0.0, years=5, annual_inflation=0.045)
        # Fisher: (1 + 0.10) / (1 + 0.045) - 1 = 1.10 / 1.045 - 1 = 0.0526315 (5.26% a.a. real)
        expected_real_rate = (1.10 / 1.045) - 1.0
        assert math.isclose(res["real_annual_rate"], expected_real_rate, rel_tol=1e-4)

        # Deflator acumulado em 5 anos: (1.045)^5 = 1.24618
        cum_inf = math.pow(1.045, 5)
        assert math.isclose(res["final_real_balance"], res["final_balance"] / cum_inf, rel_tol=1e-3)
        assert res["final_real_balance"] < res["final_balance"] # Poder real é menor que o saldo nominal
        assert res["real_net_gain"] == round(res["final_real_balance"] - res["total_invested"], 2)

    def test_retrospective_simulator_math_within_lifespan(self):
        """Valida simulação retrospectiva quando o histórico cobre o horizonte pedido (dados reais)."""
        # Cria histórico sintético de 36 meses (~3 anos)
        # Preço sobe de 10.0 para 13.0, com DY de 10% a cada ano
        pts = [{"date": f"2023-{m:02d}-01", "price": 10.0 + (m * 0.1), "dy": 10.0} for m in range(1, 37)]
        res = calculate_retrospective_math(
            amount=5000.0,
            modality="single",
            reinvest=True,
            annual_inflation=0.05,
            history_points=pts,
            target_years=2,
            current_dy=0.10
        )
        assert res["is_real"] is True
        assert res["total_invested"] == 5000.0
        assert res["balance_nominal"] > 5000.0
        assert res["balance_real"] < res["balance_nominal"]
        assert res["nominal_return_pct"] > res["real_return_pct"]

    def test_retrospective_simulator_math_synthetic_projection_1st_year(self):
        """Valida projeção sintética com retorno do 1º ano quando o horizonte excede o tempo de vida do ativo."""
        # Ativo só tem 12 meses (1 ano de vida na B3)
        pts = [{"date": f"2025-{m:02d}-01", "price": 10.0 + (m * 0.15), "dy": 12.0} for m in range(1, 13)]
        # Simula horizonte de 5 anos (1 ano observado + 4 anos projetados pelo retorno do 1º ano)
        res = calculate_retrospective_math(
            amount=5000.0,
            modality="single",
            reinvest=True,
            annual_inflation=0.05,
            history_points=pts,
            target_years=5,
            current_dy=0.12
        )
        assert res["is_real"] is False # Período excedente requer projeção
        assert res["r1y"] > 0.10 # Retorno observado do 1º ano
        assert res["balance_nominal"] > 5000.0
        # O saldo real é deflacionado por 5 anos de inflação a 5%
        assert math.isclose(res["balance_real"], res["balance_nominal"] / math.pow(1.05, 5), rel_tol=1e-3)

    def test_retrospective_simulator_math_negative_returns_and_nan_resilience(self):
        """Valida resiliência matemática contra retornos negativos e potências fracionárias (evitando NaN)."""
        # Ativo que caiu 70% em 9 meses (período fracionário < 1 ano)
        pts = [
            {"date": "2025-01-01", "price": 10.0, "dy": 5.0},
            {"date": "2025-05-01", "price": 6.0, "dy": 5.0},
            {"date": "2025-09-01", "price": 3.0, "dy": 5.0},
        ]
        res = calculate_retrospective_math(
            amount=5000.0,
            modality="single",
            reinvest=True,
            annual_inflation=0.06,
            history_points=pts,
            target_years=3,
            current_dy=0.05
        )
        assert res["balance_nominal"] > 0
        assert not math.isnan(res["balance_nominal"])
        assert not math.isnan(res["balance_real"])
        assert res["total_invested"] == 5000.0


# ===================================================================
# 3. Testes de Contrato de Estrutura e DOM da Calculadora
# ===================================================================

class TestCalculatorDOMContract:
    """Valida presenca dos elementos de categoria, ativos e impostos no HTML."""

    @pytest.fixture(scope="module")
    def html_content(self):
        return HTML_PATH.read_text(encoding="utf-8")

    @pytest.fixture(scope="module")
    def js_content(self):
        return JS_PATH.read_text(encoding="utf-8")

    @pytest.fixture(scope="module")
    def css_content(self):
        return CSS_PATH.read_text(encoding="utf-8")

    def test_category_selectors_exist(self, html_content):
        """Seletor de classe de ativo deve existir nos dois modos."""
        assert 'id="calc-goal-category"' in html_content
        assert 'id="calc-snow-category"' in html_content
        assert 'onchange="onGoalCategoryChange()"' in html_content
        assert 'onchange="onSnowCategoryChange()"' in html_content

    def test_tax_selectors_exist(self, html_content):
        """Seletor de tributacao e regime fiscal deve existir nos dois modos."""
        assert 'id="calc-goal-tax"' in html_content
        assert 'id="calc-snow-tax"' in html_content
        assert 'value="auto"' in html_content
        assert 'value="exempt"' in html_content
        assert 'value="stock_jcp"' in html_content
        assert 'value="fixed_15"' in html_content

    def test_result_fields_exist(self, html_content):
        """Todos os campos de resultado brutos e liquidos estao presentes no DOM."""
        required_ids = [
            "calc-goal-result-total",
            "calc-goal-result-net",
            "calc-goal-result-gross",
            "calc-goal-result-tax",
            "calc-goal-result-net-yield",
            "calc-goal-result-shares",
            "calc-goal-result-daily",
            "calc-snow-result-total",
            "calc-snow-result-invested",
            "calc-snow-result-dividends",
            "calc-snow-result-tax",
            "calc-snow-result-monthly-income",
            "calc-magic-number-title",
            "calc-magic-number-desc",
        ]
        for elem_id in required_ids:
            assert f'id="{elem_id}"' in html_content, f"Elemento #{elem_id} ausente no HTML."

    def test_js_catalog_and_filtering_functions(self, js_content):
        """Funcoes de catalogo, filtragem por categoria e IR devem estar no JS."""
        assert "function getCalculatorAssetCatalog()" in js_content
        assert "function filterCalculatorAssets(" in js_content
        assert "function onGoalCategoryChange()" in js_content
        assert "function onSnowCategoryChange()" in js_content
        assert "function _getEffectiveTaxRate(" in js_content
        assert "category: 'tesouro'" in js_content
        assert "category: 'stocks'" in js_content
        assert "category: 'fiis'" in js_content
        assert "category: 'fiagros'" in js_content
        assert "category: 'strategies'" in js_content

    def test_sector_and_indices_analysis_exist(self, html_content, js_content):
        """Valida que o painel de setor/indices e os modais de componentes existem e estao conectados."""
        assert 'id="panel-sectors"' in html_content
        assert 'id="view-sectors-container"' in html_content
        assert 'id="view-indices-container"' in html_content
        assert 'id="btn-view-sectors"' in html_content
        assert 'id="btn-view-indices"' in html_content
        assert 'id="indices-tbody"' in html_content
        assert 'id="sector-detail-modal"' in html_content
        assert 'id="sector-modal-name"' in html_content
        assert 'id="sector-modal-tbody"' in html_content
        assert 'id="sector-modal-stats"' in html_content
        assert 'openSectorDetailModal' in js_content
        assert 'openIndexDetailModal' in js_content
        assert 'renderIndicesSummaryTable' in js_content
        assert 'switchSectorIndexView' in js_content
        assert 'closeSectorDetailModal' in js_content

    def test_contextual_na_observations(self, js_content):
        """Valida que formatBreakdownDesc existe e trata os casos de N/A com contexto explicativo."""
        assert "function formatBreakdownDesc(" in js_content
        assert "Prejuízo recente" in js_content
        assert "Fórmula de Graham exige LPA > 0" in js_content
        assert "Sem distribuição de proventos" in js_content
        assert "Patrimônio Líquido negativo" in js_content

    def test_macro_forecaster_panel_and_logic_exist(self, html_content, js_content):
        """Valida que a aba e o modulo de Previsor Macro estao devidamente configurados com analise de divida publica e Tesouro."""
        assert 'id="panel-macro"' in html_content
        assert 'switchTab(\'macro\')' in html_content
        assert 'id="macro-sim-selic"' in html_content
        assert 'id="macro-sim-ipca"' in html_content
        assert 'id="macro-sim-fiscal"' in html_content
        assert 'id="macro-sim-debt"' in html_content
        assert 'id="macro-tesouro-table-tbody"' in html_content
        assert 'id="macro-tesouro-verdict-badge"' in html_content
        assert 'id="macro-asset-classes-grid"' in html_content
        assert 'id="macro-winners-list"' in html_content
        assert 'id="macro-vulnerable-list"' in html_content
        assert 'id="macro-playbook-content"' in html_content
        assert "function applyMacroScenario(" in js_content
        assert "function runMacroForecastSimulation()" in js_content
        assert "fiscal_crisis" in js_content
        assert "fiscal_consolidation" in js_content
        assert "Tesouro Selic (LFT)" in js_content
        assert "Tesouro IPCA+ Médio" in js_content
        assert "Tesouro IPCA+ Longo & RendA+" in js_content
        assert "Tesouro Prefixado" in js_content

    def test_macro_clickable_assets_and_modals(self, js_content, css_content):
        """Valida que ativos e titulos no Previsor Macro sao interativos e abrem modais."""
        assert ".macro-clickable-ticker" in css_content
        assert "openTdDetailFromHome('Tesouro Selic 2029')" in js_content
        assert "openTdDetailFromHome('Tesouro IPCA+ 2029')" in js_content
        assert "openTdDetailFromHome('Tesouro IPCA+ 2045')" in js_content
        assert "openTdDetailFromHome('Tesouro Prefixado 2027')" in js_content
        assert "openDetailModal('CYRE3', 'stock')" in js_content
        assert "openDetailModal('VALE3', 'stock')" in js_content
        assert "openDetailModal('HGLG11', 'fii')" in js_content
        assert "openDetailModal('KNCR11', 'fii')" in js_content
        assert "window.dashboardData || {}" in js_content

    def test_nav_tabs_order_and_compare_responsive_structure(self, html_content, js_content, css_content):
        """Valida que as abas seguem o fluxo logico e as tabelas possuem suporte responsivo completo."""
        tab_matches = re.findall(r"switchTab\('([a-z]+)'\)", html_content)
        expected_order = ['home', 'global', 'stocks', 'sectors', 'fiis', 'fiagros', 'rendafixa', 'compare', 'calculator', 'macro', 'glossary']
        assert tab_matches == expected_order, f"Ordem das abas incorreta: {tab_matches}"

        # Validacao de classes e estilizacao responsiva
        assert ".macro-tesouro-table" in css_content
        assert "class=\"macro-tesouro-table\"" in html_content
        assert "setComparePreset" in js_content
        assert "Métricas Universais de Retorno & Risco" in js_content
        assert "Valuation & Renda Variável" in js_content
        assert "Renda Fixa & Títulos Públicos" in js_content
        assert "top_stocks" in js_content
        assert "top_fiis" in js_content
        assert "top_tesouro" in js_content

    def test_focus_macro_history_lookback_controls(self, html_content, js_content):
        """Valida que o modal de detalhes macro possui controles de janela de 3, 5 e 10 anos."""
        assert 'id="focus-lookback-select"' in html_content
        assert 'id="focus-range-btn-3"' in html_content
        assert 'id="focus-range-btn-5"' in html_content
        assert 'id="focus-range-btn-10"' in html_content
        assert "setFocusLookback" in js_content
        assert "renderFocusModalContent" in js_content
        assert "currentFocusLookback = 5" in js_content

    def test_compare_asset_class_filtering(self, html_content, js_content):
        """Valida que o Comparador possui seletor por classe e filtragem estrita."""
        assert 'id="compare-class-filter"' in html_content
        assert 'onchange="onCompareClassFilterChange(this.value)"' in html_content
        assert "function onCompareClassFilterChange(" in js_content
        assert "currentCompareClassFilter" in js_content

    def test_compare_tesouro_lookup_and_preset(self, js_content):
        """Valida que a busca e presets do Tesouro no comparador utilizam data.tesouro_direto."""
        assert "data.tesouro_direto" in js_content
        assert "setComparePreset('top_tesouro')" in js_content or "type === 'top_tesouro'" in js_content
        assert "_class: 'tesouro'" in js_content

    def test_simulator_non_coupon_treasury_handling(self, html_content, js_content):
        """Valida que títulos do Tesouro sem cupom recebem tratamento de capitalização no PU em vez de Magic Number."""
        assert 'id="calc-snow-card-title"' in html_content
        assert 'id="calc-snow-magic-icon"' in html_content
        assert 'hasCoupon' in js_content
        assert 'isNonCouponTreasury' in js_content
        assert 'Título sem Cupom (Capitalização no PU)' in js_content

    def test_glossary_panel_and_concepts_exist(self, html_content, js_content, css_content):
        """Valida que o Glossario e Base de Conhecimento possuem estrutura completa no padrao MS Learn."""
        assert 'id="panel-glossary"' in html_content
        assert 'id="learn-search"' in html_content
        assert 'filterGlossary' in html_content
        assert 'setGlossaryCategory' in html_content
        assert 'function filterGlossary(' in js_content
        assert 'function setGlossaryCategory(' in js_content
        assert '.learn-container' in css_content
        assert '.learn-card' in css_content
        # Conceitos fundamentais
        assert 'PGBL' in html_content
        assert 'VGBL' in html_content
        assert 'Taxa Selic' in html_content
        assert 'IPCA' in html_content
        assert 'IGP-M' in html_content
        assert 'Câmbio & Dólar' in html_content
        assert 'FIIs' in html_content
        assert 'FIAGROs' in html_content
        assert 'Tesouro Direto' in html_content

    def test_calculator_snowball_inflation_and_real_growth_elements(self, html_content, js_content):
        """Valida que a calculadora Bola de Neve possui os elementos e scripts de inflação e poder de compra real."""
        # Inputs e presets no HTML
        assert 'id="calc-snow-inflation"' in html_content
        assert 'setSnowInflationPreset' in html_content
        # Métricas reais no HTML
        assert 'id="calc-snow-result-real-total"' in html_content
        assert 'id="calc-snow-result-real-gain"' in html_content
        assert 'id="calc-snow-result-real-rate"' in html_content
        assert 'id="calc-snow-result-real-monthly-income"' in html_content
        # Lógica em dashboard.js
        assert 'balanceReal' in js_content
        assert 'calc-snow-inflation' in js_content
        assert 'setSnowInflationPreset' in js_content
        assert 'Poder Real (IPCA)' in js_content

    def test_calculator_retrospective_simulator_elements_and_js_bindings(self, html_content, js_content):
        """Valida o modo de simulação retrospectiva ("Quanto teria hoje?") e seus bindings JS."""
        # Botão seletor e container de grid
        assert 'id="btn-calc-mode-retrospective"' in html_content
        assert 'id="calc-grid-retrospective"' in html_content
        # Controles de entrada
        assert 'id="calc-retro-category"' in html_content
        assert 'id="calc-retro-asset"' in html_content
        assert 'id="calc-retro-amount"' in html_content
        assert 'id="calc-retro-modality"' in html_content
        assert 'id="calc-retro-reinvest"' in html_content
        assert 'id="calc-retro-inflation"' in html_content
        assert 'id="calc-retro-table"' in html_content
        assert 'id="calc-retro-tbody"' in html_content
        assert 'id="retro-chart"' in html_content
        # Presets e funções
        assert 'addRetroAmountPreset' in html_content
        assert 'setRetroInflationPreset' in html_content
        assert 'onRetroCategoryChange' in html_content
        # Funções implementadas em dashboard.js
        assert 'function calculateRetrospective()' in js_content
        assert 'function renderRetroChart(' in js_content
        assert 'function addRetroAmountPreset(' in js_content
        assert 'function setRetroAmountPreset(' in js_content
        assert 'function setRetroInflationPreset(' in js_content
        assert 'function onRetroCategoryChange(' in js_content
        assert "mode === 'retrospective'" in js_content or "currentCalcMode === 'retrospective'" in js_content

    def test_calculator_incremental_presets_bindings(self, html_content, js_content):
        """Valida que todas as calculadoras possuem botões incrementais (+100, +X) e opção de Zerar."""
        # Funções incrementais em dashboard.js
        assert 'function addGoalPreset(' in js_content
        assert 'function addSnowMonthlyPreset(' in js_content
        assert 'function addRfAmountPreset(' in js_content
        assert 'function addRetroAmountPreset(' in js_content
        # Compatibilidade com set*Preset
        assert 'function setGoalPreset(' in js_content
        assert 'function setSnowMonthlyPreset(' in js_content
        assert 'function setRfAmountPreset(' in js_content
        assert 'function setRetroAmountPreset(' in js_content

        # Botões incrementais no HTML
        assert 'addGoalPreset(0)' in html_content
        assert 'addGoalPreset(100)' in html_content
        assert 'addSnowMonthlyPreset(0)' in html_content
        assert 'addSnowMonthlyPreset(100)' in html_content
        assert 'addRfAmountPreset(0)' in html_content
        assert 'addRfAmountPreset(100)' in html_content
        assert 'addRetroAmountPreset(0)' in html_content
        assert 'addRetroAmountPreset(100)' in html_content
        assert '+100' in html_content
        assert 'Zerar' in html_content

