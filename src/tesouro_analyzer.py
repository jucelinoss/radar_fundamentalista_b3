#!/usr/bin/env python3
"""
tesouro_analyzer.py — Radar Fundamentalista B3 v3.0

Scorecard Contínuo 0-10 para títulos do Tesouro Direto.
5 critérios × 2.0 pontos cada = máximo de 10.0 pontos.

Critérios:
  1. Prêmio Real Esperado      (2.0) — taxa real contratada ou estimada
  2. Captura Marcação Mercado  (2.0) — queda projetada de Selic (Focus)
  3. Risco Duration/Volatil.   (2.0) — sensibilidade à aceleração do IPCA
  4. Elasticidade Cambial      (2.0) — proteção via IPCA+ em câmbio estressado
  5. Eficiência Tributária     (2.0) — IR regressivo por prazo de vencimento

Todos os critérios retornam 0.0–2.0 (float) para agregação simples.
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Constantes dos critérios
# ---------------------------------------------------------------------------

# Critério 1 — Prêmio real contratado ou esperado
REAL_RATE_BASE = 0.060    # 6.0% a.a. → pontuação base de 1.0
REAL_RATE_MAX = 0.075     # 7.5% a.a. → pontuação máxima de 2.0

# Critério 2 — Captura Marcação a Mercado
# Quanto maior a queda projetada da Selic, maior o bônus
MTM_SELIC_MIN_DELTA = 0.0    # Delta = 0 → 0.0 pts bônus
MTM_SELIC_MAX_DELTA = -0.030  # Delta ≤ -3pp → 2.0 pts bônus

# Critério 3 — Risco Duration
DURATION_SHORT_MAX_DAYS = 365    # ≤ 1 ano → considerado "curto prazo"
DURATION_LONG_MIN_DAYS = 1826    # ≥ 5 anos → considerado "longo prazo"

# Critério 5 — Eficiência Tributária (IR regressivo)
TAX_SHORT_DAYS = 180     # até 180 dias: 22.5% IR
TAX_MEDIUM_DAYS = 360    # até 360 dias: 20.0% IR
TAX_LONG_MIN_DAYS = 720  # acima de 720 dias: 15.0% IR (alíquota mínima)

SCORE_DECIMALS = 2
_PLANNING_TYPES = {"Educa+", "RendA+"}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Critério 1 — Prêmio Real de Inflação
# ---------------------------------------------------------------------------
def _as_decimal(rate: float) -> float:
    return rate / 100.0 if rate > 1.0 else rate


def calculate_real_rate(
    bond: dict[str, Any],
    expected_ipca: float | None = None,
) -> float | None:
    """Retorna a taxa real contratada (IPCA+) ou esperada (Prefixado)."""
    rate = bond.get("buy_yield")
    if rate is None:
        return None

    nominal_or_real_rate = _as_decimal(float(rate))
    if bond.get("type") == "IPCA+":
        return nominal_or_real_rate
    if bond.get("type") == "Prefixado" and expected_ipca is not None:
        inflation_rate = _as_decimal(float(expected_ipca))
        if inflation_rate <= -1.0:
            return None
        return (1.0 + nominal_or_real_rate) / (1.0 + inflation_rate) - 1.0
    return None


def score_real_rate(
    bond: dict[str, Any],
    expected_ipca: float | None = None,
) -> float:
    """
    Pontua a taxa real contratada dos títulos IPCA+ e a taxa real esperada
    dos Prefixados, descontando a inflação projetada pelo Focus.

    Escala:
      - < 6.0% a.a.  → 0.0 pts
      - = 6.0% a.a.  → 1.0 pts
      - = 7.5% a.a.  → 2.0 pts (teto)
      - > 7.5% a.a.  → 2.0 pts (cap)
    """
    real_rate = calculate_real_rate(bond, expected_ipca)
    if real_rate is None:
        return 0.0
    if real_rate < REAL_RATE_BASE:
        return 0.0

    proportion = (real_rate - REAL_RATE_BASE) / (REAL_RATE_MAX - REAL_RATE_BASE)
    return round(_clamp(1.0 + proportion * 1.0, 0.0, 2.0), SCORE_DECIMALS)


def _select_expected_ipca(
    bond: dict[str, Any],
    focus_ipca: list[float | None],
) -> float | None:
    """Seleciona a projeção Focus mais próxima do horizonte do título."""
    available = [value for value in focus_ipca if value is not None]
    if not available:
        return None
    days = max(int(bond.get("days_to_maturity") or 0), 1)
    projection_index = min((days - 1) // 365, len(available) - 1)
    return available[projection_index]


# ---------------------------------------------------------------------------
# Critério 2 — Captura de Marcação a Mercado via Focus
# ---------------------------------------------------------------------------
_MTM_ELIGIBLE_TYPES = {"IPCA+", "Prefixado"}


def score_mtm_capture(
    bond: dict[str, Any],
    focus_selic_next: float | None,
    current_selic: float | None,
) -> float:
    """
    Bônus de marcação a mercado para Prefixados e IPCA+ Longos (≥ 5 anos).
    Quanto maior a queda projetada da Selic, maior o potencial de ganho de capital.

    Escala:
      - ΔSelic ≥ 0   → 0.0 pts (sem queda ou alta de juros)
      - ΔSelic = -3pp → 2.0 pts (queda máxima de referência)
    """
    if bond.get("type") not in _MTM_ELIGIBLE_TYPES:
        return 0.0

    # Só títulos longos se beneficiam do MTM
    days = bond.get("days_to_maturity")
    if days is None or days < DURATION_LONG_MIN_DAYS:
        return 0.0

    if focus_selic_next is None or current_selic is None:
        return 0.0

    delta = focus_selic_next - current_selic  # negativo = queda de juros projetada

    if delta >= MTM_SELIC_MIN_DELTA:
        return 0.0

    # Normaliza o delta inverso (quanto mais negativo, maior o bônus)
    proportion = min(abs(delta) / abs(MTM_SELIC_MAX_DELTA), 1.0)
    return round(_clamp(proportion * 2.0, 0.0, 2.0), SCORE_DECIMALS)


# ---------------------------------------------------------------------------
# Critério 3 — Risco de Duration / Volatilidade
# ---------------------------------------------------------------------------
def score_duration_risk(
    bond: dict[str, Any],
    ipca_trend: str,
) -> float:
    """
    Avalia o risco de duration em função da tendência inflacionária do Focus.

    - Tesouro Selic (pós-fixado): sempre protegido → 2.0 pts
    - Títulos Longos (≥ 5 anos) com IPCA acelerando → penalidade
    - Títulos Curtos (≤ 1 ano) → menos sensíveis → pontuação boa

    Escala:
      - Selic: sempre 2.0 pts
      - IPCA trend = "alta" + longo (≥5a): 0.0 pts
      - IPCA trend = "alta" + médio (1-5a): 0.5 pts
      - IPCA trend = "alta" + curto (≤1a): 1.5 pts
      - IPCA trend = "estavel": short=2.0, médio=1.5, longo=1.0
      - IPCA trend = "baixa": short=2.0, médio=2.0, longo=2.0
    """
    bond_type = bond.get("type", "")
    days = bond.get("days_to_maturity") or 0

    # Selic é sempre protegido contra inflação
    if bond_type == "Selic":
        return 2.0

    if ipca_trend == "baixa":
        # Queda de inflação beneficia todos os vencimentos
        return 2.0

    # Categoriza prazo
    if days <= DURATION_SHORT_MAX_DAYS:
        prazo = "curto"
    elif days >= DURATION_LONG_MIN_DAYS:
        prazo = "longo"
    else:
        prazo = "medio"

    if ipca_trend == "alta":
        scores = {"curto": 1.5, "medio": 0.5, "longo": 0.0}
    else:  # estavel
        scores = {"curto": 2.0, "medio": 1.5, "longo": 1.0}

    return round(scores.get(prazo, 1.0), SCORE_DECIMALS)


# ---------------------------------------------------------------------------
# Critério 4 — Elasticidade Cambial
# ---------------------------------------------------------------------------
_CAMBIO_STRESS_THRESHOLD = 5.50  # R$/USD — câmbio "estressado"
_CAMBIO_HEDGE_TYPES = {"IPCA+", "IGP-M+"}  # ativos com proteção implícita contra câmbio


def score_cambio_hedge(
    bond: dict[str, Any],
    focus_cambio_next: float | None,
) -> float:
    """
    Bonifica títulos indexados à inflação (IPCA+, IGP-M+) quando o câmbio
    projetado pelo Focus sinaliza desvalorização do Real.

    Escala:
      - IPCA+ com câmbio > R$5.50: 2.0 pts (proteção máxima)
      - IPCA+ com câmbio normal (≤ 5.50): 1.0 pts
      - Prefixado: 0.5 pts (exposto à inflação cambial)
      - Selic: 1.5 pts (pós-fixado, semi-protegido via BC)
      - Outros: 0.5 pts
    """
    bond_type = bond.get("type", "")

    if focus_cambio_next is None:
        # Sem dados Focus, pontuação neutra por tipo
        defaults = {"IPCA+": 1.0, "Selic": 1.5, "Prefixado": 0.5, "IGP-M+": 1.0}
        return round(defaults.get(bond_type, 0.5), SCORE_DECIMALS)

    cambio_stressed = focus_cambio_next > _CAMBIO_STRESS_THRESHOLD

    if bond_type in _CAMBIO_HEDGE_TYPES:
        return 2.0 if cambio_stressed else 1.0
    elif bond_type == "Selic":
        return 1.5  # pós-fixado: BC tende a subir juros com câmbio estressado
    elif bond_type == "Prefixado":
        return 0.0 if cambio_stressed else 1.0  # pior cenário: câmbio infla e corrói taxa real
    else:
        return 0.5


# ---------------------------------------------------------------------------
# Critério 5 — Eficiência Tributária
# ---------------------------------------------------------------------------
def score_tax_efficiency(bond: dict[str, Any]) -> float:
    """
    Pontuação baseada na alíquota de IR regressiva aplicada ao título.

    Tabela regressiva de IR para renda fixa:
      - ≤ 180 dias:   22.5% IR → 0.5 pts
      - 181–360 dias: 20.0% IR → 1.0 pts
      - 361–720 dias: 17.5% IR → 1.5 pts
      - > 720 dias:   15.0% IR → 2.0 pts
    """
    days = bond.get("days_to_maturity")
    if days is None or days <= 0:
        return 0.5  # desconhecido → conservador

    if days > TAX_LONG_MIN_DAYS:
        return 2.0
    elif days > TAX_MEDIUM_DAYS:
        return 1.5
    elif days > TAX_SHORT_DAYS:
        return 1.0
    else:
        return 0.5


# ---------------------------------------------------------------------------
# Scorecard completo por título
# ---------------------------------------------------------------------------
def bond_group(bond: dict[str, Any]) -> str:
    """Agrupa títulos comparáveis por indexador e fluxo de pagamento."""
    title_type = bond.get("type", "Tesouro")
    has_coupon = "Juros Semestrais" in bond.get("name", "")
    if title_type in {"IPCA+", "Prefixado"}:
        return f"{title_type} {'com cupom' if has_coupon else 'sem cupom'}"
    return title_type


def _is_planning_bond(bond: dict[str, Any]) -> bool:
    return bond.get("type") in _PLANNING_TYPES


def _yield_values(bond: dict[str, Any]) -> list[float]:
    return [
        float(point["buy_yield"])
        for point in bond.get("history", [])
        if point.get("buy_yield") is not None
    ]


def _percentile(value: float | None, values: list[float]) -> float:
    if value is None or not values:
        return 0.5
    return sum(item <= value for item in values) / len(values)


def _score_historical_yield(bond: dict[str, Any]) -> float:
    return round(_percentile(bond.get("buy_yield"), _yield_values(bond)) * 4.0, SCORE_DECIMALS)


def _score_peer_yield(bond: dict[str, Any], universe: list[dict[str, Any]]) -> float:
    peers = [
        float(item["buy_yield"])
        for item in universe
        if bond_group(item) == bond_group(bond) and item.get("buy_yield") is not None
    ]
    return round(_percentile(bond.get("buy_yield"), peers) * 2.0, SCORE_DECIMALS)


def _score_mtm_opportunity(bond: dict[str, Any]) -> float:
    duration_factor = _clamp(float(bond.get("days_to_maturity") or 0) / 3650.0, 0.0, 1.0)
    historical_position = _percentile(bond.get("buy_yield"), _yield_values(bond))
    return round(2.0 * duration_factor * historical_position, SCORE_DECIMALS)


def score_bond(
    bond: dict[str, Any],
    universe: list[dict[str, Any]] | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calcula a atratividade diária a partir de dados observados do Tesouro."""
    comparable_bonds = universe if isinstance(universe, list) else []
    historical_rates = _yield_values(bond)
    historical_percentile = round(_percentile(bond.get("buy_yield"), historical_rates) * 100)
    historical_yield = _score_historical_yield(bond)
    peer_yield = _score_peer_yield(bond, comparable_bonds)
    mtm_opportunity = _score_mtm_opportunity(bond)
    tax_efficiency = score_tax_efficiency(bond)
    total = round(historical_yield + peer_yield + mtm_opportunity + tax_efficiency, SCORE_DECIMALS)
    days = bond.get("days_to_maturity", "?")
    group = bond_group(bond)

    result = dict(bond)
    result.update({
        "group": group,
        "historical_yield_percentile": historical_percentile,
        "historical_yield_observations": len(historical_rates),
        "score": total,
        "score_breakdown": [
            {
                "label": "Taxa vs. Histórico",
                "score": historical_yield,
                "max": 4.0,
                "desc": f"Percentil {historical_percentile}: taxa igual ou maior que {historical_percentile}% das {len(historical_rates)} observações.",
                "tip": "Taxas maiores que o histórico recente elevam a atratividade para uma nova compra.",
            },
            {
                "label": "Taxa vs. Pares",
                "score": peer_yield,
                "max": 2.0,
                "desc": f"Comparação dentro do grupo {group}.",
                "tip": "Compara somente títulos do mesmo indexador e mesmo fluxo de pagamentos.",
            },
            {
                "label": "Potencial de Marcação a Mercado",
                "score": mtm_opportunity,
                "max": 2.0,
                "desc": f"Sensibilidade pelo prazo de {days} dias e taxa historicamente atrativa.",
                "tip": "É potencial técnico, não previsão de juros nem promessa de ganho em venda antecipada.",
            },
            {
                "label": "IR se mantido até o vencimento",
                "score": tax_efficiency,
                "max": 2.0,
                "desc": f"{days} dias até o vencimento.",
                "tip": "A alíquota depende do prazo efetivo entre compra e resgate; esta referência assume manutenção até o vencimento.",
            },
        ],
        "badge": _classify_badge(total),
    })
    return result


def _classify_badge(score: float) -> str:
    """Classifica o badge de qualidade do título pelo score."""
    if score >= 8.0:
        return "premium"
    elif score >= 6.0:
        return "bom"
    elif score >= 4.0:
        return "regular"
    else:
        return "alto_risco"


# ---------------------------------------------------------------------------
# Função de conveniência: pontua lista completa
# ---------------------------------------------------------------------------
def score_all_bonds(
    bonds: list[dict[str, Any]],
    macro_state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Pontua todos os títulos da lista e retorna ordenado por score desc.
    """
    scored = [score_bond(b, bonds) for b in bonds]
    opportunities = sorted(
        (bond for bond in scored if not _is_planning_bond(bond)),
        key=lambda bond: bond.get("score", 0.0),
        reverse=True,
    )
    planning = sorted(
        (bond for bond in scored if _is_planning_bond(bond)),
        key=lambda bond: bond.get("score", 0.0),
        reverse=True,
    )
    for general_rank, bond in enumerate(opportunities, start=1):
        bond["general_rank"] = general_rank
    for planning_rank, bond in enumerate(planning, start=1):
        bond["general_rank"] = None
        bond["planning_rank"] = planning_rank
    scored = opportunities + planning
    group_positions: dict[str, int] = {}
    for bond in scored:
        group = bond["group"]
        group_positions[group] = group_positions.get(group, 0) + 1
        bond["group_rank"] = group_positions[group]
    return scored
