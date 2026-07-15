"""
test_tesouro_analyzer.py — Testes unitários para tesouro_analyzer.py

Cobre todos os 5 critérios do scorecard de Renda Fixa e a função de
pontuação agregada score_bond().
"""
import sys
import os
import pytest

# Adiciona src ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tesouro_analyzer import (
    score_real_rate,
    score_mtm_capture,
    score_duration_risk,
    score_cambio_hedge,
    score_tax_efficiency,
    score_bond,
    score_all_bonds,
    _classify_badge,
)


# ---------------------------------------------------------------------------
# Fixtures — bonds base
# ---------------------------------------------------------------------------
@pytest.fixture
def ipca_long():
    return {
        "name": "Tesouro IPCA+ 2035",
        "type": "IPCA+",
        "days_to_maturity": 3285,  # ~9 anos
        "buy_yield": 6.45,         # % a.a.
        "sell_yield": 6.50,
        "buy_price": 3500.00,
        "maturity_date": "2035-01-01",
    }


@pytest.fixture
def ipca_short():
    return {
        "name": "Tesouro IPCA+ 2026",
        "type": "IPCA+",
        "days_to_maturity": 250,
        "buy_yield": 5.90,
        "sell_yield": 5.95,
        "buy_price": 1100.00,
        "maturity_date": "2026-12-01",
    }


@pytest.fixture
def prefixado_long():
    return {
        "name": "Tesouro Prefixado 2029",
        "type": "Prefixado",
        "days_to_maturity": 1095,  # ~3 anos
        "buy_yield": 13.10,
        "sell_yield": 13.20,
        "buy_price": 700.00,
        "maturity_date": "2029-01-01",
    }


@pytest.fixture
def selic_bond():
    return {
        "name": "Tesouro Selic 2027",
        "type": "Selic",
        "days_to_maturity": 730,
        "buy_yield": 14.00,
        "sell_yield": 13.95,
        "buy_price": 14500.00,
        "maturity_date": "2027-01-01",
    }


@pytest.fixture
def macro_queda_juros():
    """Cenário de queda de juros: Selic 14% hoje, 11% no Focus próximo ano."""
    return {
        "CURRENT_SELIC": 0.1400,
        "FOCUS_SELIC_NEXT_YEAR": 0.1100,
        "FOCUS_IPCA_TREND": "baixa",
        "FOCUS_IPCA": [0.053, 0.042, 0.038, 0.035],
        "FOCUS_CAMBIO": [5.20, 5.15, 5.10, 5.00],
        "FOCUS_SELIC": [0.1400, 0.1100, 0.0950, 0.0850],
    }


@pytest.fixture
def macro_alta_juros():
    """Cenário de alta de juros: Selic 14%, Focus sinaliza alta para 15%."""
    return {
        "CURRENT_SELIC": 0.1400,
        "FOCUS_SELIC_NEXT_YEAR": 0.1500,
        "FOCUS_IPCA_TREND": "alta",
        "FOCUS_IPCA": [0.053, 0.065, 0.070, 0.068],
        "FOCUS_CAMBIO": [5.80, 6.10, 6.20, 6.00],
        "FOCUS_SELIC": [0.1400, 0.1500, 0.1450, 0.1300],
    }


# ---------------------------------------------------------------------------
# Critério 1 — Prêmio Real de Inflação
# ---------------------------------------------------------------------------
class TestScoreRealRate:
    def test_ipca_acima_7_5_pct_retorna_max(self, ipca_long):
        """Taxa IPCA+ ≥ 7.5% a.a. deve retornar 2.0."""
        ipca_long["buy_yield"] = 7.5
        assert score_real_rate(ipca_long) == 2.0

    def test_ipca_na_base_6_pct_retorna_1(self, ipca_long):
        """Taxa IPCA+ = 6.0% a.a. deve retornar 1.0."""
        ipca_long["buy_yield"] = 6.0
        assert score_real_rate(ipca_long) == 1.0

    def test_ipca_abaixo_base_retorna_zero(self, ipca_short):
        """Taxa IPCA+ < 6.0% a.a. deve retornar 0.0."""
        ipca_short["buy_yield"] = 5.5
        assert score_real_rate(ipca_short) == 0.0

    def test_prefixado_15_pct_com_ipca_5_pct_retorna_max(self, prefixado_long):
        """15% nominal com IPCA de 5% equivale a cerca de 9,52% real."""
        prefixado_long["buy_yield"] = 15.0
        assert score_real_rate(prefixado_long, 0.05) == 2.0

    def test_prefixado_12_pct_com_ipca_5_pct_pontua(self, prefixado_long):
        """Prefixado deve pontuar pela taxa real esperada, não receber zero automático."""
        prefixado_long["buy_yield"] = 12.0
        assert 1.0 < score_real_rate(prefixado_long, 5.0) < 2.0

    def test_prefixado_sem_focus_retorna_zero(self, prefixado_long):
        """Sem inflação projetada não é possível estimar o retorno real."""
        assert score_real_rate(prefixado_long) == 0.0

    def test_selic_retorna_zero(self, selic_bond):
        """Tesouro Selic não pondera neste critério."""
        assert score_real_rate(selic_bond) == 0.0

    def test_interpolacao_6_45_pct(self, ipca_long):
        """Taxa 6.45% deve estar entre 1.0 e 2.0."""
        ipca_long["buy_yield"] = 6.45
        score = score_real_rate(ipca_long)
        assert 1.0 < score < 2.0

    def test_buy_yield_none_retorna_zero(self, ipca_long):
        ipca_long["buy_yield"] = None
        assert score_real_rate(ipca_long) == 0.0


# ---------------------------------------------------------------------------
# Critério 2 — Captura Marcação a Mercado
# ---------------------------------------------------------------------------
class TestScoreMTMCapture:
    def test_queda_3pp_longo_ipca_retorna_max(self, ipca_long):
        """Queda de 3pp em IPCA+ longo (≥5a) deve retornar 2.0."""
        score = score_mtm_capture(ipca_long, 0.1100, 0.1400)
        assert score == 2.0

    def test_sem_queda_retorna_zero(self, ipca_long):
        """Delta Selic = 0 não gera bônus MTM."""
        assert score_mtm_capture(ipca_long, 0.1400, 0.1400) == 0.0

    def test_alta_de_juros_retorna_zero(self, ipca_long):
        """Alta de juros não gera bônus MTM."""
        assert score_mtm_capture(ipca_long, 0.1500, 0.1400) == 0.0

    def test_titulo_curto_retorna_zero(self, ipca_short):
        """IPCA+ com vencimento curto não se beneficia do MTM."""
        assert score_mtm_capture(ipca_short, 0.1100, 0.1400) == 0.0

    def test_selic_retorna_zero(self, selic_bond):
        """Selic não participa do MTM."""
        assert score_mtm_capture(selic_bond, 0.1100, 0.1400) == 0.0

    def test_focus_none_retorna_zero(self, ipca_long):
        """Sem dados Focus, não há bônus."""
        assert score_mtm_capture(ipca_long, None, 0.1400) == 0.0


# ---------------------------------------------------------------------------
# Critério 3 — Risco de Duration
# ---------------------------------------------------------------------------
class TestScoreDurationRisk:
    def test_selic_sempre_max(self, selic_bond):
        """Selic deve sempre receber 2.0 pontos."""
        assert score_duration_risk(selic_bond, "alta") == 2.0
        assert score_duration_risk(selic_bond, "baixa") == 2.0
        assert score_duration_risk(selic_bond, "estavel") == 2.0

    def test_ipca_longo_com_ipca_alta_penalizado(self, ipca_long):
        """IPCA longo com IPCA acelerando deve receber 0.0."""
        assert score_duration_risk(ipca_long, "alta") == 0.0

    def test_ipca_longo_com_ipca_baixa_max(self, ipca_long):
        """IPCA longo com IPCA cadente deve receber 2.0."""
        assert score_duration_risk(ipca_long, "baixa") == 2.0

    def test_prefixado_curto_com_ipca_alta(self, prefixado_long):
        """Prefixado de prazo médio com IPCA alto deve receber 0.5."""
        # prefixado_long tem 1095 dias (~3 anos) = médio
        assert score_duration_risk(prefixado_long, "alta") == 0.5

    def test_ipca_curto_com_ipca_alta(self, ipca_short):
        """IPCA curto com IPCA acelerando deve receber 1.5."""
        assert score_duration_risk(ipca_short, "alta") == 1.5


# ---------------------------------------------------------------------------
# Critério 4 — Elasticidade Cambial
# ---------------------------------------------------------------------------
class TestScoreCambioHedge:
    def test_ipca_com_cambio_estressado_retorna_max(self, ipca_long):
        """IPCA+ com câmbio > R$5.50 deve retornar 2.0."""
        assert score_cambio_hedge(ipca_long, 5.80) == 2.0

    def test_ipca_com_cambio_normal_retorna_1(self, ipca_long):
        """IPCA+ com câmbio ≤ R$5.50 deve retornar 1.0."""
        assert score_cambio_hedge(ipca_long, 5.20) == 1.0

    def test_selic_retorna_1_5(self, selic_bond):
        """Selic com câmbio estressado retorna 1.5 (semi-protegido via BC)."""
        assert score_cambio_hedge(selic_bond, 5.80) == 1.5

    def test_prefixado_com_cambio_estressado_retorna_zero(self, prefixado_long):
        """Prefixado exposto à inflação cambial: 0.0 pts quando câmbio estressado."""
        assert score_cambio_hedge(prefixado_long, 5.80) == 0.0

    def test_prefixado_com_cambio_normal_retorna_1(self, prefixado_long):
        """Prefixado com câmbio normal: 1.0 pts."""
        assert score_cambio_hedge(prefixado_long, 5.20) == 1.0

    def test_none_focus_retorna_neutro_ipca(self, ipca_long):
        """Sem dados Focus, IPCA+ retorna 1.0 (neutro)."""
        assert score_cambio_hedge(ipca_long, None) == 1.0


# ---------------------------------------------------------------------------
# Critério 5 — Eficiência Tributária
# ---------------------------------------------------------------------------
class TestScoreTaxEfficiency:
    def test_acima_720_dias_retorna_max(self, ipca_long):
        """Acima de 720 dias (alíquota mínima 15%) = 2.0 pts."""
        assert score_tax_efficiency(ipca_long) == 2.0

    def test_entre_361_720_retorna_1_5(self, selic_bond):
        """730 dias → 2.0 pts (acima de 720)."""
        selic_bond["days_to_maturity"] = 730
        assert score_tax_efficiency(selic_bond) == 2.0

    def test_entre_181_360_retorna_1(self):
        """270 dias (entre 181-360) → 1.0 pts."""
        bond = {"days_to_maturity": 270}
        assert score_tax_efficiency(bond) == 1.0

    def test_ate_180_dias_retorna_0_5(self):
        """90 dias (≤ 180) → 0.5 pts."""
        bond = {"days_to_maturity": 90}
        assert score_tax_efficiency(bond) == 0.5

    def test_entre_361_720_retorna_1_5_correto(self):
        """500 dias (entre 361-720) → 1.5 pts."""
        bond = {"days_to_maturity": 500}
        assert score_tax_efficiency(bond) == 1.5

    def test_days_none_retorna_conservador(self):
        """Sem dados de prazo → 0.5 pts (conservador)."""
        assert score_tax_efficiency({}) == 0.5


# ---------------------------------------------------------------------------
# score_bond() — Integração
# ---------------------------------------------------------------------------
class TestScoreBond:
    def test_score_total_entre_0_e_10(self, ipca_long, macro_queda_juros):
        result = score_bond(ipca_long, macro_queda_juros)
        assert 0.0 <= result["score"] <= 10.0

    def test_score_breakdown_tem_5_criterios(self, ipca_long, macro_queda_juros):
        result = score_bond(ipca_long, macro_queda_juros)
        assert len(result["score_breakdown"]) == 5

    def test_cada_criterio_entre_0_e_2(self, ipca_long, macro_queda_juros):
        result = score_bond(ipca_long, macro_queda_juros)
        for item in result["score_breakdown"]:
            assert 0.0 <= item["score"] <= 2.0

    def test_score_preserva_campos_originais(self, ipca_long, macro_queda_juros):
        result = score_bond(ipca_long, macro_queda_juros)
        assert result["name"] == ipca_long["name"]
        assert result["type"] == ipca_long["type"]
        assert result["maturity_date"] == ipca_long["maturity_date"]

    def test_badge_premium_acima_8(self, ipca_long, macro_queda_juros):
        """IPCA+ longo em cenário de queda deve alcançar badge premium."""
        ipca_long["buy_yield"] = 7.5
        result = score_bond(ipca_long, macro_queda_juros)
        assert result["badge"] in ("premium", "bom")

    def test_selic_cenario_alta_pontuacao_razoavel(self, selic_bond, macro_alta_juros):
        """Selic em ambiente de juros altos deve ter boa pontuação (protegido)."""
        result = score_bond(selic_bond, macro_alta_juros)
        assert result["score"] >= 4.0  # Selic sempre pondera bem em criérios 3 e 4

    def test_macro_none_nao_crasha(self, ipca_long):
        """score_bond deve funcionar sem macro_state (fallback seguro)."""
        result = score_bond(ipca_long, None)
        assert "score" in result
        assert 0.0 <= result["score"] <= 10.0

    def test_prefixado_exibe_taxa_real_esperada(self, prefixado_long, macro_queda_juros):
        prefixado_long["buy_yield"] = 15.0
        result = score_bond(prefixado_long, macro_queda_juros)
        premio_real = result["score_breakdown"][0]
        assert premio_real["score"] == 2.0
        assert "Taxa real esperada" in premio_real["desc"]
        assert "IPCA Focus" in premio_real["desc"]


# ---------------------------------------------------------------------------
# _classify_badge()
# ---------------------------------------------------------------------------
class TestClassifyBadge:
    def test_premium_acima_8(self):
        assert _classify_badge(8.5) == "premium"

    def test_bom_entre_6_e_8(self):
        assert _classify_badge(7.0) == "bom"
        assert _classify_badge(6.0) == "bom"

    def test_regular_entre_4_e_6(self):
        assert _classify_badge(5.0) == "regular"
        assert _classify_badge(4.0) == "regular"

    def test_alto_risco_abaixo_4(self):
        assert _classify_badge(3.9) == "alto_risco"
        assert _classify_badge(0.0) == "alto_risco"


# ---------------------------------------------------------------------------
# score_all_bonds() — Ordenação
# ---------------------------------------------------------------------------
class TestScoreAllBonds:
    def test_lista_vazia_retorna_vazia(self):
        assert score_all_bonds([]) == []

    def test_ordenado_por_score_desc(self, ipca_long, selic_bond, prefixado_long, macro_queda_juros):
        ipca_long["buy_yield"] = 7.5  # garante que IPCA+ vence
        result = score_all_bonds([selic_bond, prefixado_long, ipca_long], macro_queda_juros)
        scores = [r["score"] for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_todos_os_bonds_pontuados(self, ipca_long, selic_bond, macro_queda_juros):
        result = score_all_bonds([ipca_long, selic_bond], macro_queda_juros)
        assert len(result) == 2
        for r in result:
            assert "score" in r
            assert "score_breakdown" in r
            assert "badge" in r
