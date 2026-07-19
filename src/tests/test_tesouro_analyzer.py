"""Contratos do score de oportunidade v2 do Tesouro Direto."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tesouro_analyzer import SCORE_METHOD, bond_group, risk_profile, score_all_bonds, score_bond, score_tax_efficiency


@pytest.fixture
def macro():
    return {
        "CURRENT_SELIC": 0.14,
        "FOCUS_SELIC_NEXT_YEAR": 0.11,
        "FOCUS_IPCA": [0.05, 0.045, 0.04, 0.04],
    }


def _bond(name, title_type, days, rate, history=None):
    return {
        "name": name,
        "type": title_type,
        "days_to_maturity": days,
        "buy_yield": rate,
        "buy_price": 1000.0,
        "history": history or [{"buy_yield": rate}],
    }


def test_selic_uses_spread_and_not_nominal_selic(macro):
    selic = _bond("Tesouro Selic 2031", "Selic", 1700, 0.000744, [
        {"buy_yield": -0.0002}, {"buy_yield": 0.0003}, {"buy_yield": 0.000744},
    ])
    result = score_bond(selic, [selic], macro)

    assert result["score_method"] == SCORE_METHOD
    assert result["risk_profile"] == "Baixo"
    assert result["score_breakdown"][0]["label"] == "Ágio/deságio sobre a Selic"
    assert "Selic +0.0744%" in result["score_breakdown"][0]["desc"]
    assert result["score_breakdown"][0]["max"] == 6.0
    assert result["badge"] != "alto_risco"


def test_low_selic_opportunity_is_not_labeled_as_risk(macro):
    selic = _bond("Tesouro Selic 2029", "Selic", 900, -0.0015)
    result = score_bond(selic, [selic], macro)

    assert result["risk_profile"] == "Baixo"
    assert result["badge"] != "alto_risco"


def test_coupon_and_non_coupon_are_separate_groups():
    plain = _bond("Tesouro IPCA+ 2035", "IPCA+", 3300, 0.07)
    coupon = _bond("Tesouro IPCA+ com Juros Semestrais 2035", "IPCA+", 3300, 0.07)

    assert "sem cupom" in bond_group(plain)
    assert "com cupom" in bond_group(coupon)
    assert bond_group(plain) != bond_group(coupon)


def test_duration_is_part_of_comparison_group():
    short = _bond("Tesouro Prefixado 2029", "Prefixado", 1000, 0.14)
    long = _bond("Tesouro Prefixado 2037", "Prefixado", 4000, 0.14)

    assert bond_group(short) != bond_group(long)


def test_coupon_reduces_effective_risk_profile():
    without_coupon = _bond("Tesouro Prefixado 2035", "Prefixado", 3000, 0.14)
    with_coupon = _bond("Tesouro Prefixado com Juros Semestrais 2035", "Prefixado", 3000, 0.14)

    assert risk_profile(with_coupon) == "Moderado"
    assert risk_profile(without_coupon) == "Elevado"


def test_prefixado_uses_focus_ipca_and_mtm(macro):
    prefix = _bond("Tesouro Prefixado 2032", "Prefixado", 2200, 0.145, [
        {"buy_yield": 0.12}, {"buy_yield": 0.13}, {"buy_yield": 0.145},
    ])
    result = score_bond(prefix, [prefix], macro)
    labels = [item["label"] for item in result["score_breakdown"]]

    assert "Taxa real esperada" in labels
    assert "Potencial de marcação a mercado" in labels
    assert 0 <= result["score"] <= 10


def test_ipca_uses_contracted_real_rate(macro):
    ipca = _bond("Tesouro IPCA+ 2040", "IPCA+", 5000, 0.075)
    result = score_bond(ipca, [ipca], macro)

    assert result["score_breakdown"][0]["label"] == "Taxa real contratada"


def test_tax_is_limited_to_half_point():
    assert score_tax_efficiency({"days_to_maturity": 100}) < 0.5
    assert score_tax_efficiency({"days_to_maturity": 1000}) == 0.5


def test_peers_never_mix_coupon_and_non_coupon(macro):
    plain = _bond("Tesouro IPCA+ 2035", "IPCA+", 3300, 0.07)
    coupon = _bond("Tesouro IPCA+ com Juros Semestrais 2035", "IPCA+", 3300, 0.09)
    result = score_bond(plain, [plain, coupon], macro)
    peer = next(item for item in result["score_breakdown"] if item["label"] == "Taxa vs. pares")

    assert "sem cupom" in peer["desc"]


def test_planning_titles_do_not_enter_general_ranking(macro):
    bonds = [
        _bond("Tesouro RendA+ Aposentadoria Extra 2035", "RendA+", 9000, 0.075),
        _bond("Tesouro IPCA+ 2035", "IPCA+", 3300, 0.07),
    ]
    scored = score_all_bonds(bonds, macro)

    planning = next(item for item in scored if item["type"] == "RendA+")
    assert planning["general_rank"] is None
    assert planning["planning_rank"] == 1
