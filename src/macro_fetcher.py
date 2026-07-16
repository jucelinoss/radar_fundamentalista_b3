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
import csv
import io
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SRC_DIR)
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
MACRO_STATE_FILE = os.path.join(_DATA_DIR, "macro_state.json")
TESOURO_HISTORY_FILE = os.path.join(_DATA_DIR, "tesouro_history.json")
TESOURO_HISTORY_RETENTION_DAYS = 365 * 5

# ---------------------------------------------------------------------------
# Configuração BCB
# ---------------------------------------------------------------------------
BCB_SGS_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados/ultimos/{n}?formato=json"
BCB_SGS_PERIOD = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados?formato=json"
BCB_FOCUS_BASE = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"
TESOURO_DIRETO_URLS = [
    # Endpoint clássico (protegido por Cloudflare — retorna 403 para bots)
    "https://www.tesourodireto.com.br/tesouro-direto/json/br/com/b3/tesourodireto/model/dto/TesouroDiretoDTO.json",
    "https://www.tesourodireto.com.br/json/br/com/b3/tesourodireto/model/dto/TesouroDiretoDTO.json",
    # Endpoint alternativo (redireciona para login Microsoft — 200 mas HTML, não JSON)
    "https://sistemas.tesouro.gov.br/tesouro-direto/rest/v1/bonds",
]
TESOURO_TRANSPARENTE_CSV_URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
    "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv"
)
# CDN Excel com preços históricos de PU (formato .xls, requer xlrd para ler)
#   LFT = Tesouro Selic, LTN = Prefixado, NTN-B = IPCA+, NTN-C = IGP-M+
# Ex: https://cdn.tesouro.gov.br/.../sistd/2026/LFT_2026.xls
# Todos retornam 200, mas são .xls binário (não .xlsx). openpyxl NÃO lê .xls.
TESOURO_CDN_XLS = (
    "https://cdn.tesouro.gov.br/sistemas-internos/apex/producao/sistemas/sistd/{year}/{type}_{year}.xls"
)

SESSION = requests.Session()
SESSION.headers.update({
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.tesourodireto.com.br/",
    "Origin": "https://www.tesourodireto.com.br",
})

DEFAULT_TIMEOUT = 5  # segundos (reduzido para fallback rápido quando APIs falham)
TTL_HOURS = 24
TESOURO_FALLBACK_TTL_HOURS = 1
TESOURO_CSV_RETRY_ATTEMPTS = 3
TESOURO_CSV_RETRY_BACKOFF_SECONDS = 1
MACRO_STATE_SCHEMA_VERSION = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get(url: str, params: dict | None = None) -> dict | list | None:
    """HTTP GET com timeout e tratamento de erro unificado."""
    try:
        encoded_params = urlencode(params, quote_via=quote) if params else None
        resp = SESSION.get(url, params=encoded_params, timeout=DEFAULT_TIMEOUT)
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
        cache_ttl = ttl_hours
        bonds = macro_state.get("TESOURO_DIRETO_BONDS", [])
        if bonds and all(bond.get("is_demo") for bond in bonds):
            cache_ttl = min(cache_ttl, TESOURO_FALLBACK_TTL_HOURS)
        return (datetime.now(timezone.utc) - fetched) > timedelta(hours=cache_ttl)
    except Exception:
        return True


def _load_cached() -> dict | None:
    """Carrega macro_state.json se existir e não estiver stale."""
    if not os.path.exists(MACRO_STATE_FILE):
        return None
    try:
        with open(MACRO_STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        if state.get("schema_version") != MACRO_STATE_SCHEMA_VERSION:
            return None
        if not _is_stale(state):
            logger.info("[macro_fetcher] Usando cache existente (dentro do TTL).")
            return state
    except Exception:
        pass
    return None


def _load_cache_ignore_stale() -> dict | None:
    """Carrega macro_state.json ignorando TTL (usado como fallback quando API falha)."""
    if not os.path.exists(MACRO_STATE_FILE):
        return None
    try:
        with open(MACRO_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _save(state: dict) -> None:
    """Persiste macro_state no disco."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(MACRO_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    logger.info(f"[macro_fetcher] macro_state.json salvo em {MACRO_STATE_FILE}")


def _normalize_rate(value: float | None) -> float | None:
    """Normaliza taxas para decimal (8,08% e 0,0808 viram 0,0808)."""
    if value is None:
        return None
    return value / 100.0 if abs(value) > 1.0 else value


def _load_tesouro_history() -> dict[str, list[dict[str, Any]]]:
    if not os.path.exists(TESOURO_HISTORY_FILE):
        return {}
    try:
        with open(TESOURO_HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        logger.warning("[macro_fetcher] Histórico do Tesouro inválido; iniciando nova série.")
        return {}


def _save_tesouro_history(history: dict[str, list[dict[str, Any]]]) -> None:
    with open(TESOURO_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _retain_recent_tesouro_points(points: list[dict[str, Any]], reference_date: str) -> list[dict[str, Any]]:
    cutoff = datetime.strptime(reference_date, "%Y-%m-%d") - timedelta(days=TESOURO_HISTORY_RETENTION_DAYS)
    retained = []
    for point in points:
        try:
            if datetime.strptime(point.get("date", ""), "%Y-%m-%d") >= cutoff:
                retained.append(point)
        except ValueError:
            logger.warning("[macro_fetcher] Descartando ponto histórico do Tesouro com data inválida.")
    return retained


def record_tesouro_snapshot(bonds: list[dict[str, Any]], fetched_at: str) -> None:
    """Persiste uma observação diária real para os gráficos do Tesouro."""
    history = _load_tesouro_history()
    for bond in bonds:
        if bond.get("is_demo"):
            continue
        name = bond.get("name")
        if not name:
            continue
        date = bond.get("market_date") or fetched_at[:10]
        points = history.setdefault(name, [])
        point = {
            "date": date,
            "buy_yield": bond.get("buy_yield"),
            "buy_price": bond.get("buy_price"),
            "source": bond.get("data_source", "tesouro_direto_snapshot"),
        }
        existing = next((item for item in points if item.get("date") == date), None)
        if existing:
            existing.update(point)
        else:
            points.append(point)
        points.sort(key=lambda item: item.get("date", ""))
        history[name] = _retain_recent_tesouro_points(points, date)
    _save_tesouro_history(history)


def record_tesouro_scores(scored_bonds: list[dict[str, Any]], fetched_at: str) -> None:
    """Acrescenta o score calculado à observação diária já persistida."""
    history = _load_tesouro_history()
    changed = False
    for bond in scored_bonds:
        name = bond.get("name", "")
        if not name or bond.get("is_demo"):
            continue
        date = bond.get("market_date") or fetched_at[:10]
        points = history.setdefault(name, [])
        existing = next((item for item in points if item.get("date") == date), None)
        if existing is None:
            existing = {
                "date": date,
                "buy_yield": bond.get("buy_yield"),
                "buy_price": bond.get("buy_price"),
                "source": bond.get("data_source", "tesouro_direto_snapshot"),
            }
            points.append(existing)
            points.sort(key=lambda item: item.get("date", ""))
        existing["score"] = bond.get("score")
        changed = True
    if changed:
        _save_tesouro_history(history)


def get_tesouro_history(name: str) -> list[dict[str, Any]]:
    """Retorna observações reais persistidas para um título."""
    return _load_tesouro_history().get(name, [])


# ---------------------------------------------------------------------------
# 1. Selic Over — BCB SGS Série 11
# ---------------------------------------------------------------------------
def fetch_selic() -> float | None:
    """
    Retorna a taxa Selic Over anualizada (% a.a. em decimal).

    A SGS série 11 retorna a taxa Selic Over DIÁRIA em % (ex: 0,05 para 0,05%).
    Anualizamos multiplicando por 252 dias úteis.
    Ex: 0,05% diário × 252 = 12,6% a.a. → 0,126 em decimal.
    """
    url = BCB_SGS_BASE.format(series=11, n=1)
    data = _get(url)
    if data and isinstance(data, list) and data:
        try:
            daily_pct = float(data[-1]["valor"])    # ex: 0,05 (% diário)
            daily_decimal = daily_pct / 100.0        # ex: 0,0005
            annualized = daily_decimal * 252          # ex: 0,126 (12,6% a.a.)
            return round(annualized, 6)
        except (KeyError, ValueError, TypeError):
            pass
    logger.warning("[macro_fetcher] Selic não obtida via SGS.")
    return None


# ---------------------------------------------------------------------------
# 1a-bis. Selic Meta (COPOM) — BCB SGS Série 432
# ---------------------------------------------------------------------------
def fetch_selic_meta() -> float | None:
    """
    Retorna a taxa Selic META definida pelo COPOM (% a.a. em decimal).

    SGS série 432 = 'Taxa de juros - Meta Selic definida pelo COPOM % a.a.'.
    O valor já vem anualizado (ex: 14,25 → 0.1425 em decimal).
    """
    url = BCB_SGS_BASE.format(series=432, n=1)
    data = _get(url)
    if data and isinstance(data, list) and data:
        try:
            pct = float(data[-1]["valor"])          # ex: 14.25 (% a.a.)
            return round(pct / 100.0, 6)             # ex: 0.1425
        except (KeyError, ValueError, TypeError):
            pass
    logger.warning("[macro_fetcher] Selic Meta não obtida via SGS 432.")
    return None


# ---------------------------------------------------------------------------
# 1a-ter. Histórico Selic Meta (5 anos) — BCB SGS Série 432
# ---------------------------------------------------------------------------
def fetch_selic_meta_history(years: int = 5) -> list[dict[str, Any]]:
    """
    Busca histórico da Selic META (COPOM) dos últimos N anos.

    SGS série 432 = 'Taxa de juros - Meta Selic definida pelo COPOM % a.a.'
    Os dados são esparsos (mudam apenas nas reuniões do COPOM, ~8x/ano).
    Cada valor já é anualizado (ex: 14.25 → 0.1425 em decimal).
    Retorna lista de {date, value} ordenada por data.
    """
    data = _fetch_sgs_period(432, years)
    if not data:
        logger.warning("[macro_fetcher] Histórico Selic Meta não obtido via SGS 432.")
        return []
    result: list[dict[str, Any]] = []
    for item in data:
        try:
            annual_pct = float(item["valor"])  # ex: 14.25 (% a.a.)
            result.append({"date": item["data"], "value": round(annual_pct / 100.0, 6)})
        except (KeyError, ValueError, TypeError):
            continue
    result.sort(key=lambda x: x["date"])
    logger.info(f"[macro_fetcher] Histórico Selic Meta: {len(result)} pontos (SGS 432)")
    return result


# ---------------------------------------------------------------------------
# 1b. Histórico Selic (5 anos) — BCB SGS Série 11 (mantido para fallback)
# ---------------------------------------------------------------------------
def _fetch_sgs_period(series: int, years: int) -> list[dict[str, Any]]:
    """Busca dados de uma série SGS por período (usa dataInicial/dataFinal).

    Constrói a URL manualmente porque _get() já inclui ?formato=json na base,
    e passar params como dict faria a requests duplicar a query string.
    """
    end_date = datetime.now()
    start_date = end_date.replace(year=end_date.year - years)
    query = urlencode({
        "dataInicial": start_date.strftime("%d/%m/%Y"),
        "dataFinal": end_date.strftime("%d/%m/%Y"),
    })
    url = BCB_SGS_PERIOD.format(series=series) + "&" + query
    try:
        resp = SESSION.get(url, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning(f"[macro_fetcher] Série SGS {series} não obtida via período: {exc}")
        return []


def fetch_selic_history(years: int = 5) -> list[dict[str, Any]]:
    """
    Busca histórico diário da Selic Over dos últimos N anos.
    Retorna lista de {date, value} com a taxa anualizada (decimal).
    """
    data = _fetch_sgs_period(11, years)
    if not data:
        return []
    result: list[dict[str, Any]] = []
    for item in data:
        try:
            daily_pct = float(item["valor"])
            daily_decimal = daily_pct / 100.0
            annualized = round(daily_decimal * 252, 6)
            result.append({"date": item["data"], "value": annualized})
        except (KeyError, ValueError, TypeError):
            continue
    return result


# ---------------------------------------------------------------------------
# 1c. Histórico IPCA (5 anos) — IBGE SIDRA (tabela 1737)
#     Retorna duas visões: acumulado no ano (v/69) + acumulado 12 meses (v/2265)
# ---------------------------------------------------------------------------
SIDRA_IPCA_URL = (
    "https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/69,2265/"
    "p/all/d/v69%202,v2265%202"
)

def fetch_ipca_sidra_history(years: int = 10) -> dict[str, list[dict[str, Any]]]:
    """
    Busca histórico mensal do IPCA via API SIDRA do IBGE (fonte oficial).

    Tabela 1737 = IPCA - Série histórica
      v/69   = IPCA - Variação acumulada no ano (%)
      v/2265 = IPCA - Variação acumulada em 12 meses (%)

    Args:
        years: quantos anos de histórico retornar (padrão 10).

    Retorna dict com:
      'IPCA_HISTORY':     acumulado 12 meses (compatível com gráfico Focus)
      'IPCA_YTD_HISTORY': acumulado no ano (YTD)
    Cada lista contém {date, value} com value em decimal (ex: 0.1006).
    """
    try:
        resp = SESSION.get(SIDRA_IPCA_URL, timeout=DEFAULT_TIMEOUT * 2)
        resp.raise_for_status()
        rows = resp.json()
    except Exception as exc:
        logger.warning(f"[macro_fetcher] SIDRA IPCA não obtido: {exc}")
        return {"IPCA_HISTORY": [], "IPCA_YTD_HISTORY": []}

    series_12m: list[dict[str, Any]] = []   # v/2265
    series_ytd: list[dict[str, Any]] = []    # v/69
    cutoff_year = datetime.now().year - years

    for row in rows[1:]:  # skip header
        try:
            var_code = row.get("D2C")
            month_code = row.get("D3C")  # YYYYMM
            value_str = row.get("V")
            if not var_code or not month_code or value_str is None:
                continue
            # Filtra por ano
            year_int = int(month_code[:4])
            if year_int < cutoff_year:
                continue
            # Parse date as 01/MM/YYYY
            month = month_code[4:6]
            date_str = f"01/{month}/{month_code[:4]}"
            val = round(float(value_str) / 100.0, 6)

            entry = {"date": date_str, "value": val}
            if var_code == "2265":
                series_12m.append(entry)
            elif var_code == "69":
                series_ytd.append(entry)
        except (KeyError, ValueError, TypeError):
            continue

    logger.info(
        f"[macro_fetcher] IPCA SIDRA: {len(series_12m)} pts (acum. 12m, {years}a), "
        f"{len(series_ytd)} pts (acum. ano, {years}a)"
    )
    return {
        "IPCA_HISTORY": series_12m,
        "IPCA_YTD_HISTORY": series_ytd,
    }


# Mantém fetch_ipca_history() como alias para SIDRA (compatibilidade)
def fetch_ipca_history(years: int = 5) -> list[dict[str, Any]]:
    """
    Alias: retorna apenas IPCA acumulado 12 meses via SIDRA (compatível com gráfico Focus).
    Equivalente a fetch_ipca_sidra_history()['IPCA_HISTORY'].
    """
    result = fetch_ipca_sidra_history()
    return result.get("IPCA_HISTORY", [])


# ---------------------------------------------------------------------------
# 1d. Histórico Câmbio (5 anos) — BCB SGS Série 1
# ---------------------------------------------------------------------------
def fetch_cambio_history(years: int = 5) -> list[dict[str, Any]]:
    """
    Busca histórico diário da taxa de câmbio PTAX venda (R$/US$).
    Série SGS 1 = Taxa de câmbio - livre - Dólar americano (venda) - diária.
    Retorna lista de {date, value}.
    """
    data = _fetch_sgs_period(1, years)
    if not data:
        logger.warning("[macro_fetcher] Histórico Câmbio não obtido.")
        return []
    result: list[dict[str, Any]] = []
    for item in data:
        try:
            result.append({"date": item["data"], "value": float(item["valor"])})
        except (KeyError, ValueError, TypeError):
            continue
    return result


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

    Tenta duas estratégias:
      1. API OData do BCB (Expectativas de Mercado)
      2. Fallback: SGS séries de expectativas
    """
    result: dict[str, Any] = {v: [] for v in _FOCUS_INDICATORS.values()}
    result["FOCUS_DATA_SOURCE"] = "unavailable"
    current_year = datetime.now().year
    years = [current_year, current_year + 1, current_year + 2, current_year + 3]

    # ── Estratégia 1: API OData do BCB ──
    for indicator_pt, key in _FOCUS_INDICATORS.items():
        yearly: dict[int, float | None] = {y: None for y in years}
        year_filter = " or ".join(f"DataReferencia eq '{year}'" for year in years)

        # Tenta com $format=json padrão
        params = {
            "$filter": (
                f"Indicador eq '{indicator_pt}' and baseCalculo eq 0 "
                f"and ({year_filter})"
            ),
            "$orderby": "Data desc",
            "$top": 200,
            "$format": "json",
            "$select": "Indicador,Data,DataReferencia,Mediana,numeroRespondentes,baseCalculo",
        }
        data = _get(BCB_FOCUS_BASE, params=params)

        # Se falhou, tenta sem $format (usa Accept header)
        if not data:
            params_no_fmt = dict(params)
            params_no_fmt.pop("$format", None)
            data = _get(BCB_FOCUS_BASE, params=params_no_fmt)

        if data and isinstance(data, dict):
            items = data.get("value", [])
            sorted_items = sorted(items, key=lambda x: x.get("Data", ""), reverse=True)
            if sorted_items:
                result["FOCUS_DATA_SOURCE"] = "bcb_expectativas_odata"
            for item in sorted_items:
                try:
                    yr = int(item["DataReferencia"])
                    if yr in yearly and yearly[yr] is None:
                        val = float(item["Mediana"])
                        if indicator_pt in ("IPCA", "Selic", "PIB Total"):
                            val = round(val / 100.0, 8)
                        yearly[yr] = val
                except (KeyError, ValueError, TypeError):
                    continue

            if indicator_pt == "IPCA":
                observations = _sample_focus_weekly(sorted_items, current_year)
                result["FOCUS_IPCA_WEEKLY"] = [point["value"] for point in observations]
                result["FOCUS_IPCA_WEEKLY_OBSERVATIONS"] = observations

        result[key] = [yearly[y] for y in years]
        logger.info(f"[macro_fetcher] Focus {indicator_pt}: {result[key]}")

    return result


def _sample_focus_weekly(items: list[dict[str, Any]], reference_year: int) -> list[dict[str, Any]]:
    """Seleciona hoje, 1, 2, 3 e 4 semanas atrás na série diária do Focus."""
    daily: list[tuple[datetime, float]] = []
    seen_dates: set[str] = set()
    for item in items:
        try:
            if int(item["DataReferencia"]) != reference_year:
                continue
            date_text = str(item["Data"])[:10]
            if date_text in seen_dates:
                continue
            seen_dates.add(date_text)
            daily.append((datetime.fromisoformat(date_text), round(float(item["Mediana"]) / 100.0, 8)))
        except (KeyError, ValueError, TypeError):
            continue

    daily.sort(key=lambda point: point[0], reverse=True)
    if not daily:
        return []

    latest_date = daily[0][0]
    sampled: list[dict[str, Any]] = []
    used_dates: set[str] = set()
    for weeks_ago in (0, 1, 2, 3, 4):
        target = latest_date - timedelta(days=weeks_ago * 7)
        match = next((point for point in daily if point[0] <= target), None)
        if not match:
            continue
        date_text = match[0].date().isoformat()
        if date_text in used_dates:
            continue
        used_dates.add(date_text)
        sampled.append({"date": date_text, "value": match[1], "weeks_ago": weeks_ago})
    return sampled


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
    Tenta múltiplos endpoints conhecidos em sequência.
    Retorna lista de dicionários com campos normalizados.
    """
    csv_bonds = _fetch_tesouro_transparente_csv()
    if csv_bonds:
        logger.info(
            f"[macro_fetcher] Tesouro Transparente: {len(csv_bonds)} títulos "
            "com histórico oficial."
        )
        return csv_bonds

    data = None
    source = "tesouro_direto_api"
    for url in TESOURO_DIRETO_URLS:
        data = _get(url)
        if data:
            logger.info(f"[macro_fetcher] Tesouro Direto: dados obtidos via {url}")
            break
    bonds: list[dict[str, Any]] = []

    if not data:
        logger.warning("[macro_fetcher] Tesouro Direto: API offline, usando dados de demonstração.")
        bonds = _get_demo_bonds()
        for bond in bonds:
            bond["data_source"] = "demo_fallback"
            bond["is_demo"] = True
        logger.info(f"[macro_fetcher] Tesouro Direto: {len(bonds)} títulos de demonstração.")
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
            buy_yield = _normalize_rate(_to_float(bd.get("anulInvstmtRate")))
            sell_yield = _normalize_rate(_to_float(bd.get("anulRedRate")))
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
                "data_source": source,
                "is_demo": False,
            })
    except Exception as exc:
        logger.warning(f"[macro_fetcher] Erro ao parsear Tesouro Direto: {exc}")

    logger.info(f"[macro_fetcher] Tesouro Direto: {len(bonds)} títulos encontrados.")
    return bonds


def _fetch_tesouro_transparente_csv() -> list[dict[str, Any]]:
    """Baixa e interpreta o histórico diário oficial do Tesouro Transparente."""
    for attempt in range(1, TESOURO_CSV_RETRY_ATTEMPTS + 1):
        try:
            response = SESSION.get(TESOURO_TRANSPARENTE_CSV_URL, timeout=45)
            response.raise_for_status()
            return _parse_tesouro_csv(response.content.decode("latin-1"))
        except Exception as exc:
            logger.warning(
                "[macro_fetcher] Falha no CSV do Tesouro Transparente "
                f"(tentativa {attempt}/{TESOURO_CSV_RETRY_ATTEMPTS}) → {exc}"
            )
            if attempt < TESOURO_CSV_RETRY_ATTEMPTS:
                time.sleep(TESOURO_CSV_RETRY_BACKOFF_SECONDS * attempt)
    return []


def _parse_tesouro_csv(content: str) -> list[dict[str, Any]]:
    """Converte o CSV oficial em títulos atuais enriquecidos com histórico."""
    rows: list[dict[str, Any]] = []
    for raw in csv.DictReader(io.StringIO(content), delimiter=";"):
        try:
            base_date = datetime.strptime(raw["Data Base"], "%d/%m/%Y").date()
            maturity = datetime.strptime(raw["Data Vencimento"], "%d/%m/%Y").date()
            title_type = raw["Tipo Titulo"].strip()
            buy_yield = _normalize_rate(_to_float_br(raw.get("Taxa Compra Manha")))
            sell_yield = _normalize_rate(_to_float_br(raw.get("Taxa Venda Manha")))
            buy_price = _to_float_br(raw.get("PU Compra Manha"))
            sell_price = _to_float_br(raw.get("PU Venda Manha"))
        except (KeyError, ValueError, TypeError):
            continue
        if not title_type or buy_yield is None or buy_price is None:
            continue
        rows.append({
            "title_type": title_type,
            "base_date": base_date,
            "maturity": maturity,
            "buy_yield": buy_yield,
            "sell_yield": sell_yield,
            "buy_price": buy_price,
            "sell_price": sell_price,
        })

    if not rows:
        return []

    latest_date = max(row["base_date"] for row in rows)
    cutoff = latest_date - timedelta(days=5 * 366)
    history_by_key: dict[tuple[str, Any], list[dict[str, Any]]] = {}
    for row in rows:
        if row["base_date"] < cutoff:
            continue
        key = (row["title_type"], row["maturity"])
        history_by_key.setdefault(key, []).append({
            "date": row["base_date"].isoformat(),
            "buy_yield": row["buy_yield"],
            "buy_price": row["buy_price"],
            "source": "tesouro_transparente_csv",
        })

    bonds: list[dict[str, Any]] = []
    for row in rows:
        if row["base_date"] != latest_date:
            continue
        key = (row["title_type"], row["maturity"])
        history = sorted(history_by_key.get(key, []), key=lambda point: point["date"])
        bonds.append({
            "name": f"{row['title_type']} {row['maturity'].year}",
            "type": _classify_bond_type(row["title_type"]),
            "maturity_date": row["maturity"].isoformat(),
            "days_to_maturity": (row["maturity"] - datetime.now().date()).days,
            "buy_yield": row["buy_yield"],
            "sell_yield": row["sell_yield"],
            "buy_price": row["buy_price"],
            "sell_price": row["sell_price"],
            "min_investment": round(row["buy_price"] * 0.01, 2),
            "history": history,
            "market_date": latest_date.isoformat(),
            "data_source": "tesouro_transparente_csv",
            "is_demo": False,
        })
    return bonds


def _get_demo_bonds() -> list[dict[str, Any]]:
    """
    Retorna lista completa de títulos do Tesouro Direto com taxas e PU realistas
    (capturados do site oficial em julho/2026).
    Usado quando a API oficial está offline.
    """
    now = datetime.now()

    def _d(mat_tuple: tuple[int, int, int]) -> int:
        """Dias até o vencimento."""
        return (datetime(*mat_tuple) - now).days

    return [
        # ═══════ Tesouro Reserva ═══════
        {"name": "Tesouro Reserva 2036", "type": "Reserva",
         "maturity_date": "2036-01-01", "days_to_maturity": _d((2036, 1, 1)),
         "buy_yield": 0.1478, "sell_yield": 0.1476,
         "buy_price": 10735.0, "sell_price": 10730.0, "min_investment": 1.0},

        # ═══════ Tesouro Selic ═══════
        {"name": "Tesouro Selic 2031", "type": "Selic",
         "maturity_date": "2031-03-01", "days_to_maturity": _d((2031, 3, 1)),
         "buy_yield": 0.1475, "sell_yield": 0.1474,
         "buy_price": 19349.60, "sell_price": 19340.0, "min_investment": 193.49},

        # ═══════ Tesouro Prefixado ═══════
        {"name": "Tesouro Prefixado 2029", "type": "Prefixado",
         "maturity_date": "2029-01-01", "days_to_maturity": _d((2029, 1, 1)),
         "buy_yield": 0.1398, "sell_yield": 0.1370,
         "buy_price": 725.49, "sell_price": 720.0, "min_investment": 7.25},
        {"name": "Tesouro Prefixado 2032", "type": "Prefixado",
         "maturity_date": "2032-01-01", "days_to_maturity": _d((2032, 1, 1)),
         "buy_yield": 0.1426, "sell_yield": 0.1400,
         "buy_price": 484.20, "sell_price": 480.0, "min_investment": 4.84},
        {"name": "Tesouro Prefixado com Juros Semestrais 2037", "type": "Prefixado",
         "maturity_date": "2037-01-01", "days_to_maturity": _d((2037, 1, 1)),
         "buy_yield": 0.1427, "sell_yield": 0.1400,
         "buy_price": 786.67, "sell_price": 782.0, "min_investment": 7.86},

        # ═══════ Tesouro IPCA+ ═══════
        {"name": "Tesouro IPCA+ 2032", "type": "IPCA+",
         "maturity_date": "2032-08-15", "days_to_maturity": _d((2032, 8, 15)),
         "buy_yield": 0.0808, "sell_yield": 0.0815,
         "buy_price": 2959.36, "sell_price": 2950.0, "min_investment": 29.59},
        {"name": "Tesouro IPCA+ com Juros Semestrais 2037", "type": "IPCA+",
         "maturity_date": "2037-05-15", "days_to_maturity": _d((2037, 5, 15)),
         "buy_yield": 0.0784, "sell_yield": 0.0790,
         "buy_price": 4186.17, "sell_price": 4175.0, "min_investment": 41.86},
        {"name": "Tesouro IPCA+ 2040", "type": "IPCA+",
         "maturity_date": "2040-08-15", "days_to_maturity": _d((2040, 8, 15)),
         "buy_yield": 0.0753, "sell_yield": 0.0760,
         "buy_price": 1713.02, "sell_price": 1708.0, "min_investment": 17.13},
        {"name": "Tesouro IPCA+ com Juros Semestrais 2045", "type": "IPCA+",
         "maturity_date": "2045-05-15", "days_to_maturity": _d((2045, 5, 15)),
         "buy_yield": 0.0751, "sell_yield": 0.0758,
         "buy_price": 4103.16, "sell_price": 4092.0, "min_investment": 41.03},
        {"name": "Tesouro IPCA+ 2050", "type": "IPCA+",
         "maturity_date": "2050-08-15", "days_to_maturity": _d((2050, 8, 15)),
         "buy_yield": 0.0723, "sell_yield": 0.0730,
         "buy_price": 890.77, "sell_price": 887.0, "min_investment": 8.90},
        {"name": "Tesouro IPCA+ com Juros Semestrais 2060", "type": "IPCA+",
         "maturity_date": "2060-08-15", "days_to_maturity": _d((2060, 8, 15)),
         "buy_yield": 0.0738, "sell_yield": 0.0745,
         "buy_price": 4078.69, "sell_price": 4067.0, "min_investment": 40.78},

        # ═══════ Tesouro RendA+ (Aposentadoria Extra) ═══════
        {"name": "Tesouro RendA+ Aposentadoria Extra 2030", "type": "RendA+",
         "maturity_date": "2049-12-15", "days_to_maturity": _d((2049, 12, 15)),
         "buy_yield": 0.0760, "sell_yield": 0.0768,
         "buy_price": 1938.93, "sell_price": 1932.0, "min_investment": 19.38},
        {"name": "Tesouro RendA+ Aposentadoria Extra 2035", "type": "RendA+",
         "maturity_date": "2054-12-15", "days_to_maturity": _d((2054, 12, 15)),
         "buy_yield": 0.0741, "sell_yield": 0.0750,
         "buy_price": 1386.05, "sell_price": 1380.0, "min_investment": 13.86},
        {"name": "Tesouro RendA+ Aposentadoria Extra 2040", "type": "RendA+",
         "maturity_date": "2059-12-15", "days_to_maturity": _d((2059, 12, 15)),
         "buy_yield": 0.0725, "sell_yield": 0.0733,
         "buy_price": 1002.56, "sell_price": 998.0, "min_investment": 10.02},
        {"name": "Tesouro RendA+ Aposentadoria Extra 2045", "type": "RendA+",
         "maturity_date": "2064-12-15", "days_to_maturity": _d((2064, 12, 15)),
         "buy_yield": 0.0717, "sell_yield": 0.0725,
         "buy_price": 722.03, "sell_price": 718.0, "min_investment": 7.22},
        {"name": "Tesouro RendA+ Aposentadoria Extra 2050", "type": "RendA+",
         "maturity_date": "2069-12-15", "days_to_maturity": _d((2069, 12, 15)),
         "buy_yield": 0.0712, "sell_yield": 0.0720,
         "buy_price": 519.27, "sell_price": 516.0, "min_investment": 5.19},
        {"name": "Tesouro RendA+ Aposentadoria Extra 2055", "type": "RendA+",
         "maturity_date": "2074-12-15", "days_to_maturity": _d((2074, 12, 15)),
         "buy_yield": 0.0710, "sell_yield": 0.0718,
         "buy_price": 371.41, "sell_price": 369.0, "min_investment": 3.71},
        {"name": "Tesouro RendA+ Aposentadoria Extra 2060", "type": "RendA+",
         "maturity_date": "2079-12-15", "days_to_maturity": _d((2079, 12, 15)),
         "buy_yield": 0.0710, "sell_yield": 0.0718,
         "buy_price": 264.10, "sell_price": 262.0, "min_investment": 2.64},
        {"name": "Tesouro RendA+ Aposentadoria Extra 2065", "type": "RendA+",
         "maturity_date": "2084-12-15", "days_to_maturity": _d((2084, 12, 15)),
         "buy_yield": 0.0710, "sell_yield": 0.0718,
         "buy_price": 187.81, "sell_price": 186.0, "min_investment": 1.87},

        # ═══════ Tesouro Educa+ ═══════
        {"name": "Tesouro Educa+ 2027", "type": "Educa+",
         "maturity_date": "2031-12-15", "days_to_maturity": _d((2031, 12, 15)),
         "buy_yield": 0.0827, "sell_yield": 0.0835,
         "buy_price": 3774.26, "sell_price": 3765.0, "min_investment": 37.74},
        {"name": "Tesouro Educa+ 2028", "type": "Educa+",
         "maturity_date": "2032-12-15", "days_to_maturity": _d((2032, 12, 15)),
         "buy_yield": 0.0821, "sell_yield": 0.0829,
         "buy_price": 3494.88, "sell_price": 3485.0, "min_investment": 34.94},
        {"name": "Tesouro Educa+ 2029", "type": "Educa+",
         "maturity_date": "2033-12-15", "days_to_maturity": _d((2033, 12, 15)),
         "buy_yield": 0.0813, "sell_yield": 0.0821,
         "buy_price": 3242.70, "sell_price": 3234.0, "min_investment": 32.42},
        {"name": "Tesouro Educa+ 2030", "type": "Educa+",
         "maturity_date": "2034-12-15", "days_to_maturity": _d((2034, 12, 15)),
         "buy_yield": 0.0807, "sell_yield": 0.0815,
         "buy_price": 3009.33, "sell_price": 3000.0, "min_investment": 30.09},
        {"name": "Tesouro Educa+ 2031", "type": "Educa+",
         "maturity_date": "2035-12-15", "days_to_maturity": _d((2035, 12, 15)),
         "buy_yield": 0.0801, "sell_yield": 0.0809,
         "buy_price": 2796.00, "sell_price": 2788.0, "min_investment": 27.96},
        {"name": "Tesouro Educa+ 2032", "type": "Educa+",
         "maturity_date": "2036-12-15", "days_to_maturity": _d((2036, 12, 15)),
         "buy_yield": 0.0794, "sell_yield": 0.0802,
         "buy_price": 2602.74, "sell_price": 2595.0, "min_investment": 26.02},
        {"name": "Tesouro Educa+ 2033", "type": "Educa+",
         "maturity_date": "2037-12-15", "days_to_maturity": _d((2037, 12, 15)),
         "buy_yield": 0.0787, "sell_yield": 0.0795,
         "buy_price": 2426.17, "sell_price": 2419.0, "min_investment": 24.26},
        {"name": "Tesouro Educa+ 2034", "type": "Educa+",
         "maturity_date": "2038-12-15", "days_to_maturity": _d((2038, 12, 15)),
         "buy_yield": 0.0781, "sell_yield": 0.0789,
         "buy_price": 2262.87, "sell_price": 2256.0, "min_investment": 22.62},
        {"name": "Tesouro Educa+ 2035", "type": "Educa+",
         "maturity_date": "2039-12-15", "days_to_maturity": _d((2039, 12, 15)),
         "buy_yield": 0.0774, "sell_yield": 0.0782,
         "buy_price": 2114.98, "sell_price": 2108.0, "min_investment": 21.14},
        {"name": "Tesouro Educa+ 2036", "type": "Educa+",
         "maturity_date": "2040-12-15", "days_to_maturity": _d((2040, 12, 15)),
         "buy_yield": 0.0767, "sell_yield": 0.0775,
         "buy_price": 1978.83, "sell_price": 1972.0, "min_investment": 19.78},
        {"name": "Tesouro Educa+ 2037", "type": "Educa+",
         "maturity_date": "2041-12-15", "days_to_maturity": _d((2041, 12, 15)),
         "buy_yield": 0.0760, "sell_yield": 0.0768,
         "buy_price": 1853.79, "sell_price": 1848.0, "min_investment": 18.53},
        {"name": "Tesouro Educa+ 2038", "type": "Educa+",
         "maturity_date": "2042-12-15", "days_to_maturity": _d((2042, 12, 15)),
         "buy_yield": 0.0754, "sell_yield": 0.0762,
         "buy_price": 1736.71, "sell_price": 1731.0, "min_investment": 17.36},
        {"name": "Tesouro Educa+ 2039", "type": "Educa+",
         "maturity_date": "2043-12-15", "days_to_maturity": _d((2043, 12, 15)),
         "buy_yield": 0.0748, "sell_yield": 0.0756,
         "buy_price": 1628.69, "sell_price": 1623.0, "min_investment": 16.28},
        {"name": "Tesouro Educa+ 2040", "type": "Educa+",
         "maturity_date": "2044-12-15", "days_to_maturity": _d((2044, 12, 15)),
         "buy_yield": 0.0743, "sell_yield": 0.0751,
         "buy_price": 1526.98, "sell_price": 1521.0, "min_investment": 15.26},
        {"name": "Tesouro Educa+ 2041", "type": "Educa+",
         "maturity_date": "2045-12-15", "days_to_maturity": _d((2045, 12, 15)),
         "buy_yield": 0.0738, "sell_yield": 0.0746,
         "buy_price": 1433.07, "sell_price": 1428.0, "min_investment": 14.33},
        {"name": "Tesouro Educa+ 2042", "type": "Educa+",
         "maturity_date": "2046-12-15", "days_to_maturity": _d((2046, 12, 15)),
         "buy_yield": 0.0734, "sell_yield": 0.0742,
         "buy_price": 1344.05, "sell_price": 1339.0, "min_investment": 13.44},
        {"name": "Tesouro Educa+ 2043", "type": "Educa+",
         "maturity_date": "2047-12-15", "days_to_maturity": _d((2047, 12, 15)),
         "buy_yield": 0.0731, "sell_yield": 0.0739,
         "buy_price": 1259.41, "sell_price": 1254.0, "min_investment": 12.59},
        {"name": "Tesouro Educa+ 2044", "type": "Educa+",
         "maturity_date": "2048-12-15", "days_to_maturity": _d((2048, 12, 15)),
         "buy_yield": 0.0729, "sell_yield": 0.0737,
         "buy_price": 1178.58, "sell_price": 1174.0, "min_investment": 11.78},
    ]


def _to_float(val: Any) -> float | None:
    """Conversão segura para float."""
    if val is None:
        return None
    try:
        f = float(val)
        return f if not (f != f) else None  # NaN check
    except (ValueError, TypeError):
        return None


def _to_float_br(val: Any) -> float | None:
    """Converte número do CSV brasileiro, com vírgula decimal."""
    if val is None:
        return None
    text = str(val).strip()
    if not text:
        return None
    return _to_float(text.replace(".", "").replace(",", "."))


def _classify_bond_type(name: str) -> str:
    """Classifica o tipo do título pelo nome."""
    name_lower = name.lower()
    if "reserva" in name_lower:
        return "Reserva"
    elif "educa" in name_lower:
        return "Educa+"
    elif "renda" in name_lower:
        return "RendA+"
    elif "ipca" in name_lower:
        return "IPCA+"
    elif "prefixado" in name_lower or "pre" in name_lower:
        return "Prefixado"
    elif "selic" in name_lower:
        return "Selic"
    elif "igpm" in name_lower or "igp-m" in name_lower:
        return "IGP-M+"
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

    # 1. Selic (efetiva Over) + Selic Meta (COPOM)
    current_selic = fetch_selic()
    selic_meta = fetch_selic_meta()
    logger.info(f"[macro_fetcher] Selic atual: {current_selic}, Meta COPOM: {selic_meta}")

    # 2. Focus
    focus = fetch_focus()

    # Derivados úteis
    focus_selic_list = focus.get("FOCUS_SELIC", [])
    focus_selic_next = focus_selic_list[1] if len(focus_selic_list) > 1 else None

    focus_ipca_list = focus.get("FOCUS_IPCA", [])
    focus_ipca_trend = _calc_ipca_trend(focus.get("FOCUS_IPCA_WEEKLY", []))

    # 3. ETTJ
    ettj = fetch_ettj(current_selic, focus_selic_next)

    # 4. Tesouro Direto
    tesouro_bonds = fetch_tesouro_direto()

    # Uma indisponibilidade transitória não deve apagar a última série oficial.
    # Mantém os títulos reais do cache anterior até que a fonte responda novamente.
    old_cache = _load_cache_ignore_stale()
    old_tesouro_bonds = (old_cache or {}).get("TESOURO_DIRETO_BONDS", [])
    if (
        tesouro_bonds
        and all(bond.get("is_demo") for bond in tesouro_bonds)
        and old_tesouro_bonds
        and any(not bond.get("is_demo") for bond in old_tesouro_bonds)
    ):
        logger.warning(
            "[macro_fetcher] Tesouro indisponível; preservando a última série oficial em cache."
        )
        tesouro_bonds = old_tesouro_bonds

    # ── Preenche defaults realistas para dados macro (cenário atual BR) ──
    # Selic Over efetiva: ~13,24% a.a. · Selic Meta COPOM: ~14,25% a.a.
    if current_selic is None or current_selic < 0.01:
        current_selic = 0.1324
        logger.info(f"[macro_fetcher] Usando Selic Over default: {current_selic}")
    if selic_meta is None or selic_meta < 0.01:
        # Fallback: usa a própria Selic Over * 1.08 (aproximação meta ~+0,8pp)
        selic_meta = round(min(current_selic * 1.08, current_selic + 0.015), 4)
        logger.info(f"[macro_fetcher] Usando Selic Meta estimada: {selic_meta}")

    # Nunca inventa expectativas: em falha da API, mantém lacunas explícitas.
    focus_selic_list = _pad_focus_list(focus_selic_list)
    focus_ipca_list = _pad_focus_list(focus_ipca_list)
    focus_cambio_list = _pad_focus_list(focus.get("FOCUS_CAMBIO", []))
    focus_pib_list = _pad_focus_list(focus.get("FOCUS_PIB", []))

    if focus_selic_next is None and len(focus_selic_list) > 1:
        focus_selic_next = focus_selic_list[1]

    # Recalcula ETTJ com Selic corrigida se necessário
    if ettj.get("1y") is None or ettj["1y"] < 0.01:
        ettj = fetch_ettj(current_selic, focus_selic_next)

    # ── Histórico 5 anos (Selic Meta, IPCA, Câmbio PTAX) ──
    selic_history = fetch_selic_meta_history(5)
    # IPCA: duas visões via SIDRA (IBGE) — acum. 12 meses + acum. no ano
    ipca_sidra = fetch_ipca_sidra_history()
    ipca_history = ipca_sidra.get("IPCA_HISTORY", [])
    ipca_ytd_history = ipca_sidra.get("IPCA_YTD_HISTORY", [])
    cambio_history = fetch_cambio_history(5)
    logger.info(
        f"[macro_fetcher] Histórico: Selic Meta {len(selic_history)} pts (SGS 432), "
        f"IPCA 12m {len(ipca_history)} pts / YTD {len(ipca_ytd_history)} pts (SIDRA), "
        f"Câmbio {len(cambio_history)} pts (SGS 1)"
    )

    # Fallback: se API falhou, usa último cache válido (nunca dados sintéticos)
    if not selic_history or not ipca_history or not cambio_history:
        if old_cache:
            logger.info("[macro_fetcher] Fallback: usando último cache disponível para séries vazias.")
            if not selic_history:
                selic_history = old_cache.get("SELIC_HISTORY", [])
            if not ipca_history:
                ipca_history = old_cache.get("IPCA_HISTORY", [])
            if not ipca_ytd_history:
                ipca_ytd_history = old_cache.get("IPCA_YTD_HISTORY", [])
            if not cambio_history:
                cambio_history = old_cache.get("CAMBIO_HISTORY", [])
        else:
            logger.warning("[macro_fetcher] Fallback indisponível: sem cache anterior.")

    fetched_at = datetime.now(timezone.utc).isoformat()
    state: dict[str, Any] = {
        "schema_version": MACRO_STATE_SCHEMA_VERSION,
        "fetched_at": fetched_at,
        "CURRENT_SELIC": current_selic,
        "SELIC_META": selic_meta,
        "FOCUS_SELIC": focus_selic_list,
        "FOCUS_IPCA": focus_ipca_list,
        "FOCUS_CAMBIO": focus_cambio_list,
        "FOCUS_PIB": focus_pib_list,
        "FOCUS_SELIC_NEXT_YEAR": focus_selic_next,
        "FOCUS_IPCA_TREND": focus_ipca_trend,
        "FOCUS_IPCA_WEEKLY": focus.get("FOCUS_IPCA_WEEKLY", []),
        "FOCUS_IPCA_WEEKLY_OBSERVATIONS": focus.get("FOCUS_IPCA_WEEKLY_OBSERVATIONS", []),
        "FOCUS_DATA_SOURCE": focus.get("FOCUS_DATA_SOURCE", "unavailable"),
        "ETTJ_CURVE": ettj,
        "TESOURO_DIRETO_BONDS": tesouro_bonds,
        "SELIC_HISTORY": selic_history,
        "IPCA_HISTORY": ipca_history,
        "IPCA_YTD_HISTORY": ipca_ytd_history,
        "CAMBIO_HISTORY": cambio_history,
    }

    _save(state)
    record_tesouro_snapshot(tesouro_bonds, fetched_at)
    logger.info("[macro_fetcher] Estado macro atualizado com sucesso.")
    return state


def _demo_selic_history() -> list[dict[str, Any]]:
    """Dados sintéticos realistas de Selic (últimos 5 anos) para fallback."""
    from random import uniform, seed
    seed(42)
    values: list[dict[str, Any]] = []
    # Targets anuais com drift mensal para simular dados reais
    targets = {
        2021: [0.025, 0.030, 0.040, 0.050, 0.055, 0.060, 0.065, 0.070, 0.075, 0.080, 0.085, 0.090],
        2022: [0.095, 0.100, 0.105, 0.110, 0.115, 0.120, 0.125, 0.130, 0.135, 0.138, 0.140, 0.140],
        2023: [0.140, 0.140, 0.140, 0.138, 0.138, 0.138, 0.135, 0.135, 0.135, 0.135, 0.133, 0.133],
        2024: [0.133, 0.130, 0.128, 0.125, 0.125, 0.123, 0.120, 0.118, 0.118, 0.118, 0.118, 0.118],
        2025: [0.118, 0.118, 0.120, 0.122, 0.125, 0.128, 0.130, 0.132, 0.135, 0.138, 0.142, 0.145],
        2026: [0.147, 0.148, 0.148, 0.148, 0.147, 0.147, 0.147],
    }
    for year, monthly_targets in targets.items():
        for month_idx, target in enumerate(monthly_targets, 1):
            v = target + uniform(-0.003, 0.003)
            values.append({"date": f"{month_idx:02d}/01/{year}", "value": round(v, 4)})
    return values[-252*5:]


def _demo_ipca_history() -> list[dict[str, Any]]:
    """Dados sintéticos realistas de IPCA mensal (últimos 5 anos) para fallback."""
    from random import uniform, seed
    seed(43)
    values: list[dict[str, Any]] = []
    base_monthly = [
        0.0025, 0.0050, 0.0060, 0.0055, 0.0045, 0.0040,
        0.0030, 0.0020, 0.0030, 0.0040, 0.0050, 0.0050,
    ]
    for year in range(2021, 2027):
        for month_idx, bm in enumerate(base_monthly, 1):
            v = bm + uniform(-0.001, 0.001)
            values.append({"date": f"{month_idx:02d}/01/{year}", "value": round(v, 4)})
    return values[-60:]


def _demo_cambio_history() -> list[dict[str, Any]]:
    """Dados sintéticos realistas de Câmbio (R$/US$) para fallback."""
    from random import uniform, seed
    seed(44)
    values: list[dict[str, Any]] = []
    base = 5.20
    for year in range(2021, 2027):
        drift = 0.0
        if year == 2021: drift = -0.3
        elif year == 2022: drift = 0.5
        elif year == 2023: drift = -0.2
        elif year == 2024: drift = 0.3
        elif year == 2025: drift = 0.2
        elif year == 2026: drift = 0.3
        for _ in range(252):
            v = base + drift + uniform(-0.10, 0.10)
            values.append({"date": f"01/01/{year}", "value": round(v, 2)})
    return values[-252*5:]


def _pad_focus_list(lst: list[float | None]) -> list[float | None]:
    """Garante quatro anos sem substituir lacunas por projeções sintéticas."""
    return (list(lst) + [None] * 4)[:4]


def _calc_ipca_trend(focus_ipca_weekly: list[float | None]) -> str:
    """
    Determina a tendência do IPCA pelas últimas quatro divulgações semanais
    do Focus para o ano corrente.
    """
    valid = [value for value in focus_ipca_weekly if value is not None]
    if len(valid) < 2:
        return "estavel"
    delta = valid[0] - valid[-1]
    if delta > 0.0001:    # +0,01pp ou mais → alta
        return "alta"
    elif delta < -0.0001:  # -0,01pp ou mais → baixa
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
