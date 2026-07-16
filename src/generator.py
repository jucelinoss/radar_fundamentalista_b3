"""
Dashboard generator for the Radar Fundamentalista B3.

Reads data from SQLite (via database.py), computes sector aggregations
and top picks, then renders the Jinja2 template to produce dashboard.html.
"""
import json
import logging
import os
from datetime import date, datetime
from typing import Any

import database

# Importações v3: dados macro e scorecard de Renda Fixa
try:
    import macro_fetcher
    import tesouro_analyzer
    _V3_ENABLED = True
except ImportError:
    _V3_ENABLED = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SRC_DIR: str = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT: str = os.path.dirname(SRC_DIR)
TEMPLATES_DIR: str = os.path.join(SRC_DIR, "templates")
CONFIG_DIR: str = os.path.join(PROJECT_ROOT, "config")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger: logging.Logger = logging.getLogger("generator")


def load_indices() -> dict[str, list[str]]:
    """Load stock index memberships from config/indices.json."""
    path: str = os.path.join(CONFIG_DIR, "indices.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load indices.json: {e}")
    return {}


def load_ticker_mappings() -> dict[str, Any]:
    """Load ticker rename/delist mappings."""
    path: str = os.path.join(PROJECT_ROOT, "data", "ticker_mappings.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load ticker_mappings.json: {e}")
    return {}


def _build_reverse_mappings(mappings: dict[str, Any]) -> dict[str, str]:
    """Build reverse mapping: new_clean_ticker -> old_clean_ticker for index lookup."""
    result: dict[str, str] = {}
    for old_tick, new_tick in mappings.items():
        if old_tick.startswith("_") or not new_tick:
            continue
        if not isinstance(new_tick, str):
            continue
        result[new_tick.replace(".SA", "")] = old_tick.replace(".SA", "")
    return result


def _clean_ticker_display(stocks: list[dict[str, Any]], fiis: list[dict[str, Any]],
                          fiagros: list[dict[str, Any]], index_membership: dict[str, str],
                          stock_indices: dict[str, list[str]]) -> None:
    """Remove .SA suffix and assign index badges."""
    for s in stocks:
        if s.get("ticker"):
            s["ticker"] = s["ticker"].replace(".SA", "")
        lookup: str = index_membership.get(s.get("ticker", ""), s.get("ticker", ""))
        s["indices"] = stock_indices.get(lookup, [])

    for group in (fiis, fiagros):
        for asset in group:
            if asset.get("ticker"):
                asset["ticker"] = asset["ticker"].replace(".SA", "")


def _compute_sector_summaries(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate stocks by sector: count, avg score, avg DY, avg P/E."""
    sectors_data: dict[str, dict[str, Any]] = {}
    for s in stocks:
        sector: str = s.get("sector", "Outros")
        if sector not in sectors_data:
            sectors_data[sector] = {
                "name": sector, "count": 0,
                "total_score": 0, "total_dy": 0,
                "total_pe": 0, "valid_pe_count": 0,
            }
        d: dict[str, Any] = sectors_data[sector]
        d["count"] += 1
        d["total_score"] += s.get("score", 0) or 0
        d["total_dy"] += s.get("dividend_yield") or 0
        pe: float | None = s.get("pe_ratio")
        if pe and pe > 0:
            d["total_pe"] += pe
            d["valid_pe_count"] += 1

    summary: list[dict[str, Any]] = []
    for sname, sinfo in sectors_data.items():
        avg_score: float = round(sinfo["total_score"] / sinfo["count"], 2)
        avg_dy: float = round((sinfo["total_dy"] / sinfo["count"]) * 100, 2)
        avg_pe: float | None = (
            round(sinfo["total_pe"] / sinfo["valid_pe_count"], 2)
            if sinfo["valid_pe_count"] > 0 else None
        )
        summary.append({
            "name": sname, "count": sinfo["count"],
            "avg_score": avg_score, "avg_dy": avg_dy, "avg_pe": avg_pe,
        })
    summary.sort(key=lambda x: x["avg_score"], reverse=True)
    return summary


def _merge_tesouro_history(
    official_history: list[dict[str, Any]],
    persisted_history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Combine histórico oficial e cache sem descartar observações antigas.

    O cache contém snapshots reais coletados em execuções anteriores. A fonte
    oficial prevalece somente quando ambas possuem a mesma data, pois é a
    observação mais completa daquele pregão.
    """
    merged: dict[str, dict[str, Any]] = {}
    for point in persisted_history:
        date = point.get("date")
        if date:
            merged[date] = dict(point)
    for point in official_history:
        date = point.get("date")
        if date:
            merged.setdefault(date, {}).update(point)
    return [merged[date] for date in sorted(merged)]


def _build_tesouro_history_meta(
    history: list[dict[str, Any]],
    bond: dict[str, Any],
    fetched_at: str,
) -> dict[str, Any]:
    """Expõe a defasagem entre série histórica e cotação corrente sem misturá-las."""
    last_point = history[-1] if history else {}
    last_history_date = last_point.get("date")
    current_quote_date = bond.get("market_date") or fetched_at[:10] or None
    current_source = bond.get("data_source", "unavailable")
    meta: dict[str, Any] = {
        "last_history_date": last_history_date,
        "last_history_source": last_point.get("source", "legacy_cache") if last_point else None,
        "current_quote_date": current_quote_date,
        "current_quote_source": current_source,
        "gap_days": None,
        "freshness": "history_unavailable",
    }
    if not last_history_date:
        return meta

    if bond.get("is_demo"):
        meta["freshness"] = "current_quote_demo"
        return meta

    try:
        last_date = date.fromisoformat(str(last_history_date)[:10])
        quote_date = date.fromisoformat(str(current_quote_date)[:10])
        gap_days = max((quote_date - last_date).days, 0)
        meta["gap_days"] = gap_days
    except (TypeError, ValueError):
        meta["freshness"] = "date_unavailable"
        return meta

    if gap_days == 0:
        meta["freshness"] = "current"
    elif gap_days <= 4:
        meta["freshness"] = "informative_gap"
    elif gap_days <= 10:
        meta["freshness"] = "pending_update"
    else:
        meta["freshness"] = "stale"
    return meta


def _compute_top_picks(stocks: list[dict[str, Any]], fiis: list[dict[str, Any]],
                       fiagros: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Select top 5 assets per category."""
    top_stocks: list[dict[str, Any]] = sorted(stocks, key=lambda x: x["score"], reverse=True)[:5]

    valid_fiis: list[dict[str, Any]] = [f for f in fiis if f.get("pb_ratio") and f.get("dividend_yield")]
    top_fiis: list[dict[str, Any]] = sorted(valid_fiis, key=lambda x: x["score"], reverse=True)[:5]

    valid_fiagros: list[dict[str, Any]] = [f for f in fiagros if f.get("pb_ratio") and f.get("dividend_yield")]
    top_fiagros: list[dict[str, Any]] = sorted(
        valid_fiagros,
        key=lambda x: x["score"],
        reverse=True
    )[:5]

    return top_stocks, top_fiis, top_fiagros


def _summarize(asset: dict[str, Any], extra_fields: list[str] | None = None) -> dict[str, Any]:
    """Retorna campos mínimos para o card do Painel Home (Top Picks)."""
    fields = ["ticker", "name", "score", "dividend_yield"]
    if extra_fields:
        fields += extra_fields
    return {k: asset.get(k) for k in fields}


def _enrich_stock_status(stock: dict[str, Any]) -> dict[str, Any]:
    """Add diagnostic status fields for each metric on a stock.
    
    Status values:
      'ok'   → value is valid and present
      'na'   → not applicable (e.g., P/L when EPS <= 0)
      'nd'   → no data (API should have returned but didn't)
      'zero' → value is truly zero (e.g., DY when company doesn't pay dividends)
    """
    s = dict(stock)
    eps = s.get("eps")
    price = s.get("price")
    bv = s.get("book_value")
    pe = s.get("pe_ratio")
    dy = s.get("dividend_yield")
    roe = s.get("roe")
    gp = s.get("graham_price")
    bp = s.get("bazin_price")

    # --- P/L status ---
    if pe is not None and pe > 0:
        s["pe_status"] = "ok"
    elif eps is not None and eps <= 0:
        s["pe_status"] = "na"   # EPS <= 0 → P/L nao se aplica
    elif eps is not None and eps > 0 and pe is None:
        s["pe_status"] = "nd"   # EPS positivo mas API nao retornou P/L
    else:
        s["pe_status"] = "nd"

    # --- P/VP status ---
    pb = s.get("pb_ratio")
    if pb is not None and pb > 0:
        s["pb_status"] = "ok"
    elif pb is not None and pb <= 0:
        s["pb_status"] = "na"   # P/VP negativo (PL negativo)
    else:
        s["pb_status"] = "nd"

    # --- DY status ---
    if dy is not None and dy > 0:
        s["dy_status"] = "ok"
    elif dy is not None and dy == 0:
        if eps is not None and eps < 0:
            s["dy_status"] = "na"   # prejuizo, sem dividendos
        else:
            s["dy_status"] = "zero"  # empresa nao distribui
    else:
        s["dy_status"] = "nd"

    # --- ROE status ---
    if roe is not None:
        s["roe_status"] = "ok"
    else:
        if eps is not None and eps < 0:
            s["roe_status"] = "na"   # prejuizo, ROE nao se aplica
        else:
            s["roe_status"] = "nd"

    # --- Graham price status ---
    if gp is not None and gp > 0:
        s["graham_status"] = "ok"
    elif eps is not None and eps <= 0:
        s["graham_status"] = "na"   # LPA <= 0
    elif bv is not None and bv <= 0:
        s["graham_status"] = "na"   # VPA <= 0
    elif eps is None or bv is None:
        s["graham_status"] = "nd"
    else:
        s["graham_status"] = "ok"

    # --- Bazin price status ---
    if bp is not None and bp > 0:
        s["bazin_status"] = "ok"
    elif dy is None or dy == 0:
        if eps is not None and eps < 0:
            s["bazin_status"] = "na"   # prejuizo
        else:
            s["bazin_status"] = "zero"  # nao distribui
    else:
        s["bazin_status"] = "nd"

    return s


def _enrich_fii_status(asset: dict[str, Any], asset_type: str) -> dict[str, Any]:
    """Add diagnostic status fields for FIIs and FIAGROs."""
    a = dict(asset)

    # P/VP status
    pb = a.get("pb_ratio")
    if pb is not None:
        a["pb_status"] = "ok"
    else:
        a["pb_status"] = "nd"

    # DY status
    dy = a.get("dividend_yield")
    if dy is not None and dy > 0:
        a["dy_status"] = "ok"
    elif dy is not None and dy == 0:
        a["dy_status"] = "zero"
    else:
        a["dy_status"] = "nd"

    # Dividend rate status
    dr = a.get("dividend_rate")
    if dr is not None and dr > 0:
        a["rate_status"] = "ok"
    elif dr is not None and dr == 0:
        a["rate_status"] = "zero"
    else:
        a["rate_status"] = "nd"

    return a



def generate_dashboard() -> None:
    """Main generator: read DB, compute aggregates, save JSON data."""
    logger.info("Generating dashboard JSON...")

    STOCK_INDICES: dict[str, list[str]] = load_indices()
    mappings: dict[str, Any] = load_ticker_mappings()
    mappings_clean: dict[str, str] = _build_reverse_mappings(mappings)

    stocks: list[dict[str, Any]] = database.get_all_stocks()
    fiis: list[dict[str, Any]] = database.get_all_fiis()
    fiagros: list[dict[str, Any]] = database.get_all_fiagros()
    logger.info(f"  Loaded {len(stocks)} stocks, {len(fiis)} FIIs, {len(fiagros)} FIAGROs")

    _clean_ticker_display(stocks, fiis, fiagros, mappings_clean, STOCK_INDICES)

    # Enrich each asset with diagnostic status fields
    stocks = [_enrich_stock_status(s) for s in stocks]
    fiis = [_enrich_fii_status(f, "fii") for f in fiis]
    fiagros = [_enrich_fii_status(f, "fiagro") for f in fiagros]

    unique_sectors: list[str] = sorted({
        s.get("sector") for s in stocks if s.get("sector")
    })

    # Use v2.5 score for sorting if available, fallback to legacy score
    for s in stocks:
        score_v2 = s.get("score_v2")
        s["score"] = score_v2 if score_v2 is not None else (s.get("score") or 0)
        s["score_breakdown"] = json.loads(s.get("score_breakdown") or "[]") if s.get("score_breakdown") else []
    for f in fiis:
        score_v2 = f.get("score_v2")
        f["score"] = score_v2 if score_v2 is not None else (f.get("score") or 0)
        f["score_breakdown"] = json.loads(f.get("score_breakdown") or "[]") if f.get("score_breakdown") else []
    for g in fiagros:
        score_v2 = g.get("score_v2")
        g["score"] = score_v2 if score_v2 is not None else (g.get("score") or 0)
        g["score_breakdown"] = json.loads(g.get("score_breakdown") or "[]") if g.get("score_breakdown") else []

    sectors_summary: list[dict[str, Any]] = _compute_sector_summaries(stocks)
    top_stocks, top_fiis, top_fiagros = _compute_top_picks(stocks, fiis, fiagros)

    # ---------------------------------------------------------------------------
    # v3: Macro State + Tesouro Direto
    # ---------------------------------------------------------------------------
    macro_state_payload: dict[str, Any] = {}
    tesouro_direto_payload: list[dict[str, Any]] = []

    if _V3_ENABLED:
        try:
            logger.info("  [v3] Carregando macro_state...")
            ms = macro_fetcher.fetch_macro_state()

            # Monta payload macro compacto (sem lista completa de bonds — fica no TD abaixo)
            macro_state_payload = {
                "selic": ms.get("CURRENT_SELIC"),
                "selic_meta": ms.get("SELIC_META"),
                "focus_selic": ms.get("FOCUS_SELIC", []),
                "focus_ipca": ms.get("FOCUS_IPCA", []),
                "focus_cambio": ms.get("FOCUS_CAMBIO", []),
                "focus_pib": ms.get("FOCUS_PIB", []),
                "focus_selic_next_year": ms.get("FOCUS_SELIC_NEXT_YEAR"),
                "focus_ipca_trend": ms.get("FOCUS_IPCA_TREND", "estavel"),
                "focus_ipca_weekly": ms.get("FOCUS_IPCA_WEEKLY_OBSERVATIONS", []),
                "ettj_curve": ms.get("ETTJ_CURVE", {}),
                "fetched_at": ms.get("fetched_at"),
                "SELIC_HISTORY": ms.get("SELIC_HISTORY", []),
                "IPCA_HISTORY": ms.get("IPCA_HISTORY", []),
                "IPCA_YTD_HISTORY": ms.get("IPCA_YTD_HISTORY", []),
                "CAMBIO_HISTORY": ms.get("CAMBIO_HISTORY", []),
                "data_sources": {
                    "focus": ms.get("FOCUS_DATA_SOURCE", "unavailable"),
                    "tesouro_direto": (
                        ms.get("TESOURO_DIRETO_BONDS", [{}])[0].get("data_source", "unavailable")
                        if ms.get("TESOURO_DIRETO_BONDS") else "unavailable"
                    ),
                    "ettj": "estimated_from_selic_and_focus",
                },
            }

            # Pontua os títulos do Tesouro Direto
            bonds = ms.get("TESOURO_DIRETO_BONDS", [])
            if bonds:
                logger.info(f"  [v3] Pontuando {len(bonds)} títulos do Tesouro Direto...")
                tesouro_direto_payload = tesouro_analyzer.score_all_bonds(bonds)
                macro_fetcher.record_tesouro_scores(tesouro_direto_payload, ms.get("fetched_at", ""))
                for bond in tesouro_direto_payload:
                    official_history = bond.get("history", [])
                    persisted_history = macro_fetcher.get_tesouro_history(bond.get("name", ""))
                    merged = {
                        point["date"]: point
                        for point in _merge_tesouro_history(official_history, persisted_history)
                    }
                    market_date = bond.get("market_date")
                    if market_date in merged:
                        merged[market_date]["score"] = bond.get("score")

                    # Recalcula toda a série com dados observados até cada data.
                    bond_type = bond.get("type", "")
                    maturity_date_str = bond.get("maturity_date", "")
                    maturity_dt: datetime | None = None
                    if maturity_date_str:
                        try:
                            maturity_dt = datetime.strptime(maturity_date_str, "%Y-%m-%d")
                        except ValueError:
                            pass
                    historical_points = [merged[key] for key in sorted(merged)]
                    for index, point in enumerate(historical_points):
                        if point.get("buy_yield") is None:
                            continue
                        try:
                            hist_dt = datetime.strptime(point["date"], "%Y-%m-%d")
                            hist_days = (maturity_dt - hist_dt).days if maturity_dt else bond.get("days_to_maturity", 0)
                            temp_bond = {
                                "name": bond.get("name"),
                                "type": bond_type,
                                "days_to_maturity": max(hist_days, 1),
                                "buy_yield": point["buy_yield"],
                                "history": historical_points[:index + 1],
                            }
                            point["score"] = tesouro_analyzer.score_bond(temp_bond).get("score", 0)
                        except Exception:
                            point["score"] = 0
                    bond["history"] = [merged[key] for key in sorted(merged)]
                    bond["history_meta"] = _build_tesouro_history_meta(
                        bond["history"], bond, ms.get("fetched_at", "")
                    )
                logger.info(f"  [v3] Tesouro Direto: {len(tesouro_direto_payload)} títulos pontuados.")
            else:
                logger.warning("  [v3] Nenhum título do Tesouro Direto encontrado na macro_state.")

        except Exception as exc:
            logger.warning(f"  [v3] Erro ao processar dados macro/TD: {exc}. Continuando sem dados v3.")

    # ---------------------------------------------------------------------------
    # Top 5 para o Painel Home (derivados dos rankings já ordenados)
    # ---------------------------------------------------------------------------
    home_top_stocks = [_summarize(s, ["sector", "pb_ratio", "dy_medio_3y"]) for s in top_stocks[:5]]
    home_top_fiis   = [_summarize(f, ["pb_ratio"]) for f in top_fiis[:5]]
    home_top_fiagros = [_summarize(g, ["pb_ratio"]) for g in top_fiagros[:5]]
    home_top_td = [
        {k: b.get(k) for k in ["name", "type", "buy_yield", "score", "badge", "days_to_maturity", "maturity_date"]}
        for b in tesouro_direto_payload[:5]
    ] if tesouro_direto_payload else []

    now: datetime = datetime.now()
    timestamp_str: str = now.strftime("%d/%m/%Y %H:%M:%S")

    data_payload = {
        "stocks": stocks,
        "fiis": fiis,
        "fiagros": fiagros,
        "sectors_summary": sectors_summary,
        "top_stocks": top_stocks,
        "top_fiis": top_fiis,
        "top_fiagros": top_fiagros,
        "unique_sectors": unique_sectors,
        "timestamp": timestamp_str,
        # v3: dados macro e renda fixa
        "macro_state": macro_state_payload,
        "tesouro_direto": tesouro_direto_payload,
        # v3: top 5 para o Painel Home
        "home": {
            "top_stocks": home_top_stocks,
            "top_fiis": home_top_fiis,
            "top_fiagros": home_top_fiagros,
            "top_tesouro": home_top_td,
        },
    }

    output_path: str = os.path.join(PROJECT_ROOT, "data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data_payload, f, ensure_ascii=False, indent=2)

    logger.info(f"JSON data generated: {output_path} ({len(stocks) + len(fiis) + len(fiagros)} ativos)")

    _copy_pwa_assets(PROJECT_ROOT)
    _copy_pages_config(PROJECT_ROOT)


def _copy_pwa_assets(dest: str) -> None:
    """Copy PWA files (manifest, SW, icons) to the destination directory."""
    pwa_src: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "pwa")
    icon_src: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons")

    for file in ("manifest.json", "service-worker.js"):
        src: str = os.path.join(pwa_src, file)
        dst: str = os.path.join(dest, file)
        if os.path.exists(src):
            with open(src, "r", encoding="utf-8") as f:
                content: str = f.read()
            with open(dst, "w", encoding="utf-8") as f:
                f.write(content)

    # Copy icons directory (read before write to avoid self-truncation)
    icon_dst: str = os.path.join(dest, "icons")
    os.makedirs(icon_dst, exist_ok=True)
    if os.path.exists(icon_src):
        for f_name in os.listdir(icon_src):
            src_path: str = os.path.join(icon_src, f_name)
            dst_path: str = os.path.join(icon_dst, f_name)
            if os.path.isfile(src_path) and src_path != dst_path:
                with open(src_path, "rb") as fin:
                    data: bytes = fin.read()
                with open(dst_path, "wb") as fout:
                    fout.write(data)

    logger.info(f"PWA assets copied to {dest}")


def _copy_pages_config(dest: str) -> None:
    """Copy GitHub Pages config files (_headers, _redirects)."""
    src_dir: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    for file in ("_headers",):
        src: str = os.path.join(src_dir, file)
        dst: str = os.path.join(dest, file)
        if os.path.exists(src):
            with open(src, "r", encoding="utf-8") as f:
                content: str = f.read()
            with open(dst, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Pages config copied: {file}")


# ---------------------------------------------------------------------------
# CLI entry point (also used by pipeline.py and server.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    today_str: str = datetime.now().strftime("%Y-%m-%d")
    needs_refresh: bool = False

    try:
        last_update: str | None = database.get_last_update_timestamp()
        if not last_update:
            needs_refresh = True
            logger.info("Database is empty - will ingest first")
        else:
            last_date: str = last_update[:10]
            if last_date != today_str:
                needs_refresh = True
                logger.info(f"Data stale (last: {last_date}, today: {today_str}) - refreshing")
    except Exception as e:
        logger.warning(f"Could not check DB staleness: {e}")
        needs_refresh = True

    if needs_refresh:
        logger.info("Running auto-ingestion before generating dashboard...")
        import ingestion
        result: dict[str, Any] = ingestion.run_full_ingestion()
        logger.info(f"Ingestion result: {result}")

    generate_dashboard()
