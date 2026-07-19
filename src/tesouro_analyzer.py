#!/usr/bin/env python3
"""Score de oportunidade do Tesouro Direto, comparável apenas por grupo."""
from __future__ import annotations

from typing import Any

SCORE_DECIMALS = 2
SCORE_METHOD = "tesouro-opportunity-v2"
_PLANNING_TYPES = {"Educa+", "RendA+"}
_COUPON_MARKER = "Juros Semestrais"


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _as_decimal(rate: float) -> float:
    return rate / 100.0 if abs(rate) > 1.0 else rate


def _is_coupon_bond(bond: dict[str, Any]) -> bool:
    return _COUPON_MARKER.lower() in str(bond.get("name", "")).lower()


def _duration_band(bond: dict[str, Any]) -> str:
    days = max(int(bond.get("days_to_maturity") or 0), 0)
    effective_days = days * (0.65 if _is_coupon_bond(bond) else 1.0)
    if effective_days <= 365 * 3:
        return "até 3 anos"
    if effective_days <= 365 * 7:
        return "3–7 anos"
    return "mais de 7 anos"


def bond_group(bond: dict[str, Any]) -> str:
    """Grupo econômico homogêneo: indexador, fluxo e faixa de duração."""
    title_type = str(bond.get("type", "Tesouro"))
    if title_type in _PLANNING_TYPES:
        return title_type
    if title_type in {"IPCA+", "Prefixado"}:
        flow = "com cupom" if _is_coupon_bond(bond) else "sem cupom"
        return f"{title_type} {flow} · {_duration_band(bond)}"
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


def _expected_ipca(bond: dict[str, Any], macro_state: dict[str, Any] | None) -> float | None:
    projections = (macro_state or {}).get("FOCUS_IPCA", [])
    available = [_as_decimal(float(value)) for value in projections if value is not None]
    if not available:
        return None
    index = min(max(int(bond.get("days_to_maturity") or 1) - 1, 0) // 365, len(available) - 1)
    return available[index]


def calculate_real_rate(bond: dict[str, Any], expected_ipca: float | None = None) -> float | None:
    """Taxa real contratada (IPCA+) ou estimada (Prefixado)."""
    rate = bond.get("buy_yield")
    if rate is None:
        return None
    rate = _as_decimal(float(rate))
    if bond.get("type") in {"IPCA+", "Educa+", "RendA+"}:
        return rate
    if bond.get("type") == "Prefixado" and expected_ipca is not None:
        inflation = _as_decimal(float(expected_ipca))
        return (1 + rate) / (1 + inflation) - 1
    return None


def score_real_rate(bond: dict[str, Any], expected_ipca: float | None = None) -> float:
    """Compatibilidade: nota de taxa real em escala legada de 0–2."""
    real_rate = calculate_real_rate(bond, expected_ipca)
    if real_rate is None:
        return 0.0
    return round(_clamp((real_rate - 0.04) / 0.04 * 2, 0.0, 2.0), SCORE_DECIMALS)


def score_mtm_capture(bond: dict[str, Any], focus_selic_next: float | None, current_selic: float | None) -> float:
    """Compatibilidade: potencial de MTM em 0–2 para títulos de taxa fixa/real."""
    if bond.get("type") not in {"IPCA+", "Prefixado", "Educa+", "RendA+"}:
        return 0.0
    if focus_selic_next is None or current_selic is None:
        return 0.0
    delta = _as_decimal(float(focus_selic_next)) - _as_decimal(float(current_selic))
    if delta >= 0:
        return 0.0
    duration_factor = _clamp((float(bond.get("days_to_maturity") or 0) / 3650) * (0.65 if _is_coupon_bond(bond) else 1), 0, 1)
    return round(2 * duration_factor * _clamp(abs(delta) / 0.03, 0, 1), SCORE_DECIMALS)


def score_duration_risk(bond: dict[str, Any], ipca_trend: str) -> float:
    """Compatibilidade: estabilidade de preço em 0–2, não usada como oportunidade."""
    return {"Baixo": 2.0, "Moderado": 1.3, "Elevado": 0.7}.get(risk_profile(bond), 0.7)


def score_cambio_hedge(bond: dict[str, Any], focus_cambio_next: float | None) -> float:
    """Compatibilidade para consumidores antigos; câmbio não entra no score v2."""
    return 1.0 if bond.get("type") in {"IPCA+", "Educa+", "RendA+"} else 0.0


def score_tax_efficiency(bond: dict[str, Any]) -> float:
    """Ajuste pequeno (máx. 0,5) para IR na manutenção até o vencimento."""
    days = int(bond.get("days_to_maturity") or 0)
    if days > 720:
        return 0.5
    if days > 360:
        return 0.38
    if days > 180:
        return 0.25
    return 0.12


def risk_profile(bond: dict[str, Any]) -> str:
    """Risco de oscilação antes do vencimento; não é a faixa do score."""
    if bond.get("type") in {"Selic", "Reserva"}:
        return "Baixo"
    effective_days = float(bond.get("days_to_maturity") or 0) * (0.65 if _is_coupon_bond(bond) else 1.0)
    if effective_days <= 365 * 3:
        return "Baixo"
    if effective_days <= 365 * 7:
        return "Moderado"
    return "Elevado"


def _rate_score(bond: dict[str, Any], macro_state: dict[str, Any] | None) -> tuple[float, str, str, str]:
    """Critério principal de entrada, específico para cada indexador."""
    rate = bond.get("buy_yield")
    if rate is None:
        return 0.0, "Taxa indisponível", "Sem cotação de compra.", "Aguarda uma cotação oficial."
    rate = _as_decimal(float(rate))
    title_type = bond.get("type")
    if title_type in {"Selic", "Reserva"}:
        # LFT: a taxa é ágio/deságio em pontos percentuais sobre a Selic.
        score = _clamp((rate + 0.0015) / 0.003 * 6.0, 0.0, 6.0)
        sign = "+" if rate >= 0 else ""
        return round(score, SCORE_DECIMALS), "Ágio/deságio sobre a Selic", f"Selic {sign}{rate * 100:.4f}%.", "Deságio positivo aumenta o retorno sobre a Selic; ágio negativo o reduz."
    real_rate = calculate_real_rate(bond, _expected_ipca(bond, macro_state))
    if real_rate is None:
        return 0.0, "Taxa real esperada", "Focus IPCA indisponível.", "Prefixados dependem do IPCA projetado para estimar a taxa real."
    score = _clamp((real_rate - 0.04) / 0.04 * 4.0, 0.0, 4.0)
    label = "Taxa real contratada" if title_type in {"IPCA+", "Educa+", "RendA+"} else "Taxa real esperada"
    return round(score, SCORE_DECIMALS), label, f"{real_rate * 100:.2f}% a.a.", "IPCA+ usa a taxa real contratada; Prefixado desconta a projeção Focus de inflação."


def _peer_values(bond: dict[str, Any], universe: list[dict[str, Any]]) -> tuple[list[float], str]:
    exact_group = bond_group(bond)
    values = [float(item["buy_yield"]) for item in universe if item.get("buy_yield") is not None and bond_group(item) == exact_group]
    if len(values) >= 2:
        return values, exact_group
    # Se a faixa estiver escassa, preserva indexador e fluxo; nunca mistura cupom.
    title_type = bond.get("type")
    if title_type in {"IPCA+", "Prefixado"}:
        flow = _is_coupon_bond(bond)
        values = [float(item["buy_yield"]) for item in universe if item.get("buy_yield") is not None and item.get("type") == title_type and _is_coupon_bond(item) == flow]
        return values, f"{title_type} {'com cupom' if flow else 'sem cupom'} (amostra ampliada)"
    values = [float(item["buy_yield"]) for item in universe if item.get("buy_yield") is not None and item.get("type") == title_type]
    return values, exact_group


def _mtm_score(bond: dict[str, Any], macro_state: dict[str, Any] | None) -> float:
    if bond.get("type") not in {"IPCA+", "Prefixado", "Educa+", "RendA+"}:
        return 0.0
    macro = macro_state or {}
    current = macro.get("CURRENT_SELIC")
    next_year = macro.get("FOCUS_SELIC_NEXT_YEAR")
    if current is None or next_year is None:
        return 0.0
    delta = _as_decimal(float(next_year)) - _as_decimal(float(current))
    if delta >= 0:
        return 0.0
    duration_factor = _clamp((float(bond.get("days_to_maturity") or 0) / 3650) * (0.65 if _is_coupon_bond(bond) else 1), 0, 1)
    return round(2 * duration_factor * _clamp(abs(delta) / 0.03, 0, 1), SCORE_DECIMALS)


def score_bond(bond: dict[str, Any], universe: list[dict[str, Any]] | dict[str, Any] | None = None, macro_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Calcula score v2; um score baixo representa entrada menos atraente, nunca risco alto."""
    if isinstance(universe, dict) and macro_state is None:
        macro_state = universe
        universe = []
    comparable_bonds = universe if isinstance(universe, list) else []
    historical_rates = _yield_values(bond)
    historical_percentile = round(_percentile(bond.get("buy_yield"), historical_rates) * 100)
    rate_score, rate_label, rate_desc, rate_tip = _rate_score(bond, macro_state)
    history_max = 2.5
    history_score = round(_percentile(bond.get("buy_yield"), historical_rates) * history_max, SCORE_DECIMALS)
    peer_values, peer_group = _peer_values(bond, comparable_bonds)
    peer_score = round(_percentile(bond.get("buy_yield"), peer_values) * 1.0, SCORE_DECIMALS)
    mtm_score = _mtm_score(bond, macro_state)
    tax_score = score_tax_efficiency(bond)
    is_selic = bond.get("type") in {"Selic", "Reserva"}
    components = [rate_score, history_score, peer_score, tax_score] if is_selic else [rate_score, history_score, mtm_score, peer_score, tax_score]
    total = round(sum(components), SCORE_DECIMALS)
    group = bond_group(bond)
    days = bond.get("days_to_maturity", "?")
    breakdown = [
        {"label": rate_label, "score": rate_score, "max": 6.0 if is_selic else 4.0, "desc": rate_desc, "tip": rate_tip},
        {"label": "Taxa vs. histórico", "score": history_score, "max": history_max, "desc": f"Percentil {historical_percentile} em {len(historical_rates)} observações.", "tip": "Taxas maiores que o histórico do mesmo título tornam a nova entrada relativamente mais atrativa."},
        {"label": "Taxa vs. pares", "score": peer_score, "max": 1.0, "desc": f"Comparação em {peer_group}.", "tip": "Compara apenas títulos do mesmo indexador e fluxo; a faixa de prazo é preservada sempre que houver amostra suficiente."},
    ]
    if not is_selic:
        breakdown.append({"label": "Potencial de marcação a mercado", "score": mtm_score, "max": 2.0, "desc": f"Prazo efetivo de {days} dias; cupom reduz a duration estimada.", "tip": "Indicador técnico condicionado à queda esperada da Selic; não é previsão nem promessa de ganho."})
    breakdown.append({"label": "IR até o vencimento", "score": tax_score, "max": 0.5, "desc": f"{days} dias até o vencimento.", "tip": "Peso limitado: imposto é relevante, mas não deve dominar a atratividade do título."})
    result = dict(bond)
    result.update({
        "group": group,
        "risk_profile": risk_profile(bond),
        "historical_yield_percentile": historical_percentile,
        "historical_yield_observations": len(historical_rates),
        "score": total,
        "score_method": SCORE_METHOD,
        "score_breakdown": breakdown,
        "badge": _classify_badge(total),
    })
    return result


def _classify_badge(score: float) -> str:
    if score >= 8.0:
        return "premium"
    if score >= 6.0:
        return "bom"
    if score >= 4.0:
        return "regular"
    return "baixa_oportunidade"


def score_all_bonds(bonds: list[dict[str, Any]], macro_state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    scored = [score_bond(bond, bonds, macro_state) for bond in bonds]
    opportunities = sorted((bond for bond in scored if not _is_planning_bond(bond)), key=lambda bond: bond.get("score", 0.0), reverse=True)
    planning = sorted((bond for bond in scored if _is_planning_bond(bond)), key=lambda bond: bond.get("score", 0.0), reverse=True)
    for rank, bond in enumerate(opportunities, 1):
        bond["general_rank"] = rank
    for rank, bond in enumerate(planning, 1):
        bond["general_rank"] = None
        bond["planning_rank"] = rank
    positions: dict[str, int] = {}
    for bond in opportunities + planning:
        group = bond["group"]
        positions[group] = positions.get(group, 0) + 1
        bond["group_rank"] = positions[group]
    return opportunities + planning
