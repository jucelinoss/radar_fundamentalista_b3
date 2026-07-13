#!/usr/bin/env python3
"""
macro_fetcher.py — Radar Fundamentalista B3 v3.0

Ingestão diária de dados macroeconômicos do Banco Central do Brasil (BCB):
  - Taxa Selic Over/Meta (SGS Série 11)
  - Boletim Focus (IPCA, Selic, Câmbio, PIB — medianas 4 anos)
  - Curva de Juros (ETTJ) via vértices DI Futuro estimados
  - Preços e yields dos títulos do Tesouro Direto

Resultado salvo em: data/macro_state.json
TTL padrão: 24h (configurável)
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SRC_DIR)
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
MACRO_STATE_FILE = os.path.join(_DATA_DIR, "macro_state.json")

# ---------------------------------------------------------------------------
# Configuração BCB
# ---------------------------------------------------------------------------
BCB_SGS_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados/ultimos/{n}?formato=json"
BCB_FOCUS_BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativaMercadoAnuais"
TESOURO_DIRETO_URL = "https://www.tesourodireto.com.br/json/br/com/b3/tesourodireto/model/dto/TesouroDiretoDTO.json"

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json", "User-Agent": "RadarFundamentalistaB3/3.0"})

DEFAULT_TIMEOUT = 15  # segundos
TTL_HOURS = 24


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get(url: str, params: dict | None = None) -> dict | list | None:
    """HTTP GET com timeout e tratamento de erro unificado."""
    try:
        resp = SESSION.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning(f"[macro_fetcher] Falha HTTP: {url} → {exc}")
        return None


def _is_stale(macro_state: dict, ttl_hours: int = TTL_HOURS) -> bool:
    """Verifica se o cache está desatualizado."""
    ts = macro_state.get("fetched_at")
    if not ts:
        return True
    try:
        fetched = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - fetched) > timedelta(hours=ttl_hours)
    except Exception:
        return True


def _load_cached() -> dict | None:
    """Carrega macro_state.json se existir e não estiver stale."""
    if not os.path.exists(MACRO_STATE_FILE):
        return None
    try:
        with open(MACRO_STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        if not _is_stale(state):
            logger.info("[macro_fetcher] Usando cache existente (dentro do TTL).")
            return state
    except Exception:
        pass
    return None


def _save(state: dict) -> None:
    """Persiste macro_state no disco."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(MACRO_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    logger.info(f"[macro_fetcher] macro_state.json salvo em {MACRO_STATE_FILE}")


# ---------------------------------------------------------------------------
# 1. Selic Over — BCB SGS Série 11
# ---------------------------------------------------------------------------
def fetch_selic() -> float | None:
    """Retorna a última taxa Selic Over diária (% a.a.)."""
    url = BCB_SGS_BASE.format(series=11, n=1)
    data = _get(url)
    if data and isinstance(data, list) and data:
        try:
            return float(data[-1]["valor"]) / 100.0  # converte de % para decimal
        except (KeyError, ValueError, TypeError):
            pass
    logger.warning("[macro_fetcher] Selic não obtida via SGS.")
    return None


# ---------------------------------------------------------------------------
# 2. Boletim Focus — Medianas anuais
# ---------------------------------------------------------------------------
_FOCUS_INDICATORS = {
    "IPCA": "FOCUS_IPCA",
    "Selic": "FOCUS_SELIC",
    "Câmbio": "FOCUS_CAMBIO",
    "PIB Total": "FOCUS_PIB",
}


def fetch_focus() -> dict[str, Any]:
    """
    Busca medianas do Boletim Focus para os próximos 4 anos.
    Retorna dicionário com FOCUS_IPCA, FOCUS_SELIC, FOCUS_CAMBIO, FOCUS_PIB
    como listas [ano_corrente, ano+1, ano+2, ano+3].
    """
    result: dict[str, list[float | None]] = {v: [] for v in _FOCUS_INDICATORS.values()}

    current_year = datetime.now().year
    years = [current_year, current_year + 1, current_year + 2, current_year + 3]

    for indicator_pt, key in _FOCUS_INDICATORS.items():
        yearly: dict[int, float | None] = {y: None for y in years}

        params = {
            "$filter": f"Indicador eq '{indicator_pt}'",
            "$top": 200,
            "$format": "json",
            "$select": "Indicador,Data,Ano,Mediana",
        }
        data = _get(BCB_FOCUS_BASE, params=params)
        if data and isinstance(data, dict):
            items = data.get("value", [])
            # Ordena por data descendente, pega a mediana mais recente por ano
            sorted_items = sorted(items, key=lambda x: x.get("Data", ""), reverse=True)
            for item in sorted_items:
                try:
                    yr = int(item["Ano"])
                    if yr in yearly and yearly[yr] is None:
                        val = float(item["Mediana"])
                        # Selic e IPCA vêm em %, convertemos para decimal
                        if indicator_pt in ("IPCA", "Selic"):
                            val = val / 100.0
                        yearly[yr] = val
                except (KeyError, ValueError, TypeError):
                    continue

        result[key] = [yearly[y] for y in years]
        logger.info(f"[macro_fetcher] Focus {indicator_pt}: {result[key]}")

    return result


# ---------------------------------------------------------------------------
# 3. Curva ETTJ — aproximação via spreads DI Futuro
#    (Usamos a Selic como base + spreads típicos de mercado quando a API
#     de DI Futuro não está disponível sem autenticação B3.)
# ---------------------------------------------------------------------------
def fetch_ettj(current_selic: float | None, focus_selic_next: float | None) -> dict[str, float | None]:
    """
    Constrói os 4 vértices da ETTJ (1Y, 3Y, 5Y, 10Y) usando a Selic atual
    e a projeção Focus como ancora, aplicando spreads típicos de mercado.

    Esta é uma aproximação conservadora. Para dados de mercado intraday reais
    seria necessário assinar a API B3 ou usar um broker com DI Futuro.
    """
    if current_selic is None:
        return {"1y": None, "3y": None, "5y": None, "10y": None}

    selic_pct = current_selic  # já em decimal

    # Inclinação da curva (slope): queda de juros projetada pelo Focus?
    slope = 0.0
    if focus_selic_next is not None:
        slope = focus_selic_next - selic_pct  # negativo = curva invertida (queda)

    # Spreads de prazo sobre a Selic (prêmio de liquidez e risco de prazo)
    # Em ciclo de queda de juros, curva tende a ser mais inclinada (longa > curta)
    # Em ciclo de alta, curva pode ser plana ou invertida
    spread_1y = 0.001  # +0.1% vs spot
    spread_3y = max(0.005 + slope * 0.3, -0.01)   # captura slope do mercado
    spread_5y = max(0.010 + slope * 0.5, -0.015)
    spread_10y = max(0.015 + slope * 0.8, -0.02)

    return {
        "1y": round(selic_pct + spread_1y, 4),
        "3y": round(selic_pct + spread_3y, 4),
        "5y": round(selic_pct + spread_5y, 4),
        "10y": round(selic_pct + spread_10y, 4),
    }


# ---------------------------------------------------------------------------
# 4. Tesouro Direto — títulos em circulação
# ---------------------------------------------------------------------------
def fetch_tesouro_direto() -> list[dict[str, Any]]:
    """
    Busca os títulos do Tesouro Direto disponíveis para compra/venda.
    Fonte: API pública do portal tesourodireto.com.br.
    Retorna lista de dicionários com campos normalizados.
    """
    data = _get(TESOURO_DIRETO_URL)
    bonds: list[dict[str, Any]] = []

    if not data:
        logger.warning("[macro_fetcher] Tesouro Direto: dados não obtidos.")
        return bonds

    try:
        # Estrutura: { "response": { "TrsrBdTradgList": [...] } }
        bd_list = (
            data.get("response", {})
            .get("TrsrBdTradgList", [])
        )
        for item in bd_list:
            bd = item.get("TrsrBd", {})
            if not bd:
                continue

            name_raw: str = bd.get("nm", "")
            maturity_str: str = bd.get("mtrtyDt", "")  # ex: "2035-01-01T00:00:00"
            buy_yield: float | None = _to_float(bd.get("anulInvstmtRate"))
            sell_yield: float | None = _to_float(bd.get("anulRedRate"))
            buy_price: float | None = _to_float(bd.get("untrInvstmtVal"))
            sell_price: float | None = _to_float(bd.get("untrRedVal"))
            min_invest: float | None = _to_float(bd.get("minInvstmtAmt"))

            # Calcula prazo em dias até o vencimento
            days_to_maturity: int | None = None
            maturity_date: str | None = None
            if maturity_str:
                try:
                    mat = datetime.fromisoformat(maturity_str.split("T")[0])
                    maturity_date = mat.strftime("%Y-%m-%d")
                    days_to_maturity = (mat.date() - datetime.now().date()).days
                except Exception:
                    pass

            # Classifica o tipo pelo nome
            bond_type = _classify_bond_type(name_raw)

            bonds.append({
                "name": name_raw,
                "type": bond_type,
                "maturity_date": maturity_date,
                "days_to_maturity": days_to_maturity,
                "buy_yield": buy_yield,      # taxa contratada ao comprar (% a.a.)
                "sell_yield": sell_yield,    # taxa ao vender antecipado
                "buy_price": buy_price,      # preço de compra por título
                "sell_price": sell_price,    # preço de resgate antecipado
                "min_investment": min_invest,
            })
    except Exception as exc:
        logger.warning(f"[macro_fetcher] Erro ao parsear Tesouro Direto: {exc}")

    logger.info(f"[macro_fetcher] Tesouro Direto: {len(bonds)} títulos encontrados.")
    return bonds


def _to_float(val: Any) -> float | None:
    """Conversão segura para float."""
    if val is None:
        return None
    try:
        f = float(val)
        return f if not (f != f) else None  # NaN check
    except (ValueError, TypeError):
        return None


def _classify_bond_type(name: str) -> str:
    """Classifica o tipo do título pelo nome."""
    name_lower = name.lower()
    if "ipca" in name_lower:
        return "IPCA+"
    elif "prefixado" in name_lower or "pre" in name_lower:
        return "Prefixado"
    elif "selic" in name_lower:
        return "Selic"
    elif "igpm" in name_lower or "igp-m" in name_lower:
        return "IGP-M+"
    elif "renda" in name_lower:
        return "RendA+"
    else:
        return "Outro"


# ---------------------------------------------------------------------------
# 5. Pipeline principal
# ---------------------------------------------------------------------------
def fetch_macro_state(force: bool = False) -> dict[str, Any]:
    """
    Monta e retorna o dicionário global CURRENT_MACRO_STATE.
    Usa cache se disponível (TTL = 24h) a menos que force=True.

    Estrutura retornada:
    {
        "fetched_at": "2026-07-13T10:00:00+00:00",
        "CURRENT_SELIC": 0.1400,           # 14.00% a.a.
        "FOCUS_SELIC": [0.14, 0.12, ...],  # ano corrente + 3 seguintes
        "FOCUS_IPCA": [0.053, 0.042, ...],
        "FOCUS_CAMBIO": [5.20, 5.40, ...],
        "FOCUS_PIB": [0.018, 0.020, ...],
        "FOCUS_SELIC_NEXT_YEAR": 0.12,     # Mediana Selic ano seguinte
        "FOCUS_IPCA_TREND": "alta" | "baixa" | "estavel",
        "ETTJ_CURVE": {"1y": 0.141, "3y": 0.138, "5y": 0.136, "10y": 0.134},
        "TESOURO_DIRETO_BONDS": [...],
    }
    """
    if not force:
        cached = _load_cached()
        if cached:
            return cached

    logger.info("[macro_fetcher] Buscando dados macroeconômicos...")

    # 1. Selic
    current_selic = fetch_selic()
    logger.info(f"[macro_fetcher] Selic atual: {current_selic}")

    # 2. Focus
    focus = fetch_focus()

    # Derivados úteis
    focus_selic_list = focus.get("FOCUS_SELIC", [])
    focus_selic_next = focus_selic_list[1] if len(focus_selic_list) > 1 else None

    focus_ipca_list = focus.get("FOCUS_IPCA", [])
    focus_ipca_trend = _calc_ipca_trend(focus_ipca_list)

    # 3. ETTJ
    ettj = fetch_ettj(current_selic, focus_selic_next)

    # 4. Tesouro Direto
    tesouro_bonds = fetch_tesouro_direto()

    state: dict[str, Any] = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "CURRENT_SELIC": current_selic,
        "FOCUS_SELIC": focus_selic_list,
        "FOCUS_IPCA": focus_ipca_list,
        "FOCUS_CAMBIO": focus.get("FOCUS_CAMBIO", []),
        "FOCUS_PIB": focus.get("FOCUS_PIB", []),
        "FOCUS_SELIC_NEXT_YEAR": focus_selic_next,
        "FOCUS_IPCA_TREND": focus_ipca_trend,
        "ETTJ_CURVE": ettj,
        "TESOURO_DIRETO_BONDS": tesouro_bonds,
    }

    _save(state)
    logger.info("[macro_fetcher] Estado macro atualizado com sucesso.")
    return state


def _calc_ipca_trend(focus_ipca: list[float | None]) -> str:
    """
    Determina a tendência do IPCA com base nas projeções Focus.
    Compara ano corrente vs ano seguinte.
    """
    if len(focus_ipca) < 2 or focus_ipca[0] is None or focus_ipca[1] is None:
        return "estavel"
    delta = focus_ipca[1] - focus_ipca[0]
    if delta > 0.005:    # +0.5pp ou mais → alta
        return "alta"
    elif delta < -0.005:  # -0.5pp ou mais → baixa
        return "baixa"
    return "estavel"


def get_current_selic(macro_state: dict | None = None) -> float:
    """
    Retorna a Selic atual a partir do macro_state.
    Fallback: 14% a.a. (conservador, sem efeito colateral se API falhar).
    """
    if macro_state:
        val = macro_state.get("CURRENT_SELIC")
        if val is not None:
            return float(val)
    return 0.1400


def get_focus_selic_next(macro_state: dict | None = None) -> float | None:
    """Retorna a projeção Focus para a Selic no próximo ano."""
    if macro_state:
        return macro_state.get("FOCUS_SELIC_NEXT_YEAR")
    return None


# ---------------------------------------------------------------------------
# CLI para testes manuais
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
    force = "--force" in sys.argv
    state = fetch_macro_state(force=force)
    print("\n=== MACRO STATE ===")
    print(f"Selic atual:         {state.get('CURRENT_SELIC', 'N/D'):.2%}" if state.get('CURRENT_SELIC') else "Selic: N/D")
    print(f"Focus Selic próximo: {state.get('FOCUS_SELIC_NEXT_YEAR', 'N/D')}")
    print(f"Trend IPCA:          {state.get('FOCUS_IPCA_TREND', 'N/D')}")
    ettj = state.get("ETTJ_CURVE", {})
    print(f"ETTJ (1Y/3Y/5Y/10Y): {ettj.get('1y')} / {ettj.get('3y')} / {ettj.get('5y')} / {ettj.get('10y')}")
    print(f"Títulos Tesouro:     {len(state.get('TESOURO_DIRETO_BONDS', []))} encontrados")
