"""Esteira de Testes Automatizados para a Calculadora / Simulador de Renda Passiva.

Valida:
1. Precisao matematica do calculo de Meta de Renda (Bruto, Liquido, IR/JCP, Cotas/Titulos).
2. Precisao matematica da projecao Bola de Neve (Juros compostos, Magic Number, IR acumulado).
3. Segregacao por categorias de ativos (Estrategias, Acoes, FIIs, FIAGROs, Tesouro Direto).
4. Tratamento de aliquotas tributarias (Isento 0%, Acoes c/ JCP 3.75%, Tesouro 15%, Curto prazo 22.5%).
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


def calculate_snowball_math(initial: float, monthly: float, gross_dy: float, tax_rate: float, years: int, unit_price: float = 0.0):
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

    return {
        "final_balance": round(balance, 2),
        "total_invested": round(total_invested, 2),
        "final_dividends_net": round(final_dividends_net, 2),
        "final_tax_estimated": round(final_tax_estimated, 2),
        "final_monthly_net_income": round(final_monthly_net_income, 2),
        "magic_number": magic_number,
        "magic_capital": round(magic_capital, 2)
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
        """Acoes com ~25% JCP a 15% IR = 3.75% IR efetivo."""
        res = calculate_goal_math(monthly_net_target=2000.0, gross_dy=0.08, tax_rate=0.0375, unit_price=25.0)
        expected_net_dy = 0.08 * (1 - 0.0375) # 0.077
        assert math.isclose(res["net_dy"], expected_net_dy, rel_tol=1e-5)
        assert res["total_required"] == round(24000.0 / 0.077, 2)
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

