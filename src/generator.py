"""
Dashboard generator for the Radar Fundamentalista B3.

Reads data from SQLite (via database.py), computes sector aggregations
and top picks, then renders the Jinja2 template to produce dashboard.html.
"""
import json
import logging
import os
from datetime import datetime
from typing import Any

import database

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


def _compute_top_picks(stocks: list[dict[str, Any]], fiis: list[dict[str, Any]],
                       fiagros: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Select top 5 assets per category."""
    top_stocks: list[dict[str, Any]] = sorted(stocks, key=lambda x: x["score"], reverse=True)[:5]

    valid_fiis: list[dict[str, Any]] = [f for f in fiis if f.get("pb_ratio") and f.get("dividend_yield")]
    top_fiis: list[dict[str, Any]] = sorted(valid_fiis, key=lambda x: (x["pb_ratio"], -x["dividend_yield"]))[:5]

    valid_fiagros: list[dict[str, Any]] = [f for f in fiagros if f.get("pb_ratio") and f.get("dividend_yield")]
    top_fiagros: list[dict[str, Any]] = sorted(
        valid_fiagros,
        key=lambda x: (-x["dividend_yield"], x.get("pb_ratio") or 999.0)
    )[:5]

    return top_stocks, top_fiis, top_fiagros





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

    sectors_summary: list[dict[str, Any]] = _compute_sector_summaries(stocks)
    top_stocks, top_fiis, top_fiagros = _compute_top_picks(stocks, fiis, fiagros)

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
