"""
Dashboard generator for the B3 Fundamentalist Screener.

Reads data from SQLite (via database.py), computes sector aggregations
and top picks, then renders the Jinja2 template to produce dashboard.html.
"""
import json
import logging
import os
import sys
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

import database

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
TEMPLATES_DIR = os.path.join(SRC_DIR, "templates")
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("generator")
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(_handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def load_indices():
    """Load stock index memberships from config/indices.json."""
    path = os.path.join(CONFIG_DIR, "indices.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load indices.json: {e}")
    return {}


def load_ticker_mappings():
    """Load ticker rename/delist mappings."""
    path = os.path.join(PROJECT_ROOT, "data", "ticker_mappings.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load ticker_mappings.json: {e}")
    return {}


def generate_dashboard():
    """Main generator: read DB, compute aggregates, render template, write HTML."""
    logger.info("Generating dashboard...")

    STOCK_INDICES = load_indices()
    mappings = load_ticker_mappings()

    # Build reverse mapping: new_clean_ticker → old_clean_ticker (for index lookup)
    # Skip metadata keys (strings starting with _) and null values
    mappings_clean = {}
    for old_tick, new_tick in mappings.items():
        if old_tick.startswith("_") or not new_tick:
            continue
        if not isinstance(new_tick, str):
            continue
        old_c = old_tick.replace(".SA", "")
        new_c = new_tick.replace(".SA", "")
        mappings_clean[new_c] = old_c

    # Fetch data from DB
    stocks = database.get_all_stocks()
    fiis = database.get_all_fiis()
    fiagros = database.get_all_fiagros()

    logger.info(f"  Loaded {len(stocks)} stocks, {len(fiis)} FIIs, {len(fiagros)} FIAGROs")

    # Clean ticker display and assign index badges
    for s in stocks:
        if s.get("ticker"):
            s["ticker"] = s["ticker"].replace(".SA", "")
        ticker_clean = s.get("ticker", "")
        lookup = mappings_clean.get(ticker_clean, ticker_clean)
        s["indices"] = STOCK_INDICES.get(lookup, [])

    for f in fiis:
        if f.get("ticker"):
            f["ticker"] = f["ticker"].replace(".SA", "")

    for a in fiagros:
        if a.get("ticker"):
            a["ticker"] = a["ticker"].replace(".SA", "")

    # Unique sectors for dropdown filter
    unique_sectors = sorted({
        s.get("sector") for s in stocks if s.get("sector")
    })

    # ── Sector summaries ──────────────────────────────────────────────
    sectors_data = {}
    for s in stocks:
        sector = s.get("sector", "Outros")
        if sector not in sectors_data:
            sectors_data[sector] = {
                "name": sector, "count": 0,
                "total_score": 0, "total_dy": 0,
                "total_pe": 0, "valid_pe_count": 0,
            }
        sectors_data[sector]["count"] += 1
        sectors_data[sector]["total_score"] += s.get("score", 0) or 0
        dy = s.get("dividend_yield") or 0
        sectors_data[sector]["total_dy"] += dy
        pe = s.get("pe_ratio")
        if pe and pe > 0:
            sectors_data[sector]["total_pe"] += pe
            sectors_data[sector]["valid_pe_count"] += 1

    sectors_summary = []
    for sname, sinfo in sectors_data.items():
        avg_score = round(sinfo["total_score"] / sinfo["count"], 2)
        avg_dy = round((sinfo["total_dy"] / sinfo["count"]) * 100, 2)
        avg_pe = (
            round(sinfo["total_pe"] / sinfo["valid_pe_count"], 2)
            if sinfo["valid_pe_count"] > 0 else None
        )
        sectors_summary.append({
            "name": sname, "count": sinfo["count"],
            "avg_score": avg_score, "avg_dy": avg_dy, "avg_pe": avg_pe,
        })
    sectors_summary.sort(key=lambda x: x["avg_score"], reverse=True)

    # ── Top picks ─────────────────────────────────────────────────────
    top_stocks = sorted(stocks, key=lambda x: x["score"], reverse=True)[:5]

    valid_fiis = [f for f in fiis if f.get("pb_ratio") and f.get("dividend_yield")]
    top_fiis = sorted(valid_fiis, key=lambda x: (x["pb_ratio"], -x["dividend_yield"]))[:5]

    valid_fiagros = [f for f in fiagros if f.get("dividend_yield")]
    top_fiagros = sorted(
        valid_fiagros,
        key=lambda x: (-x["dividend_yield"], x.get("pb_ratio") or 999.0)
    )[:5]

    # ── Render ────────────────────────────────────────────────────────
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("dashboard_template.html")

    now = datetime.now()
    timestamp_str = now.strftime("%d/%m/%Y %H:%M:%S")

    html_output = template.render(
        stocks=stocks,
        fiis=fiis,
        fiagros=fiagros,
        sectors_summary=sectors_summary,
        top_stocks=top_stocks,
        top_fiis=top_fiis,
        top_fiagros=top_fiagros,
        unique_sectors=unique_sectors,
        timestamp=timestamp_str,
    )

    output_path = os.path.join(PROJECT_ROOT, "dashboard.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_output)

    logger.info(f"Dashboard generated: {output_path} "
                f"({len(html_output)} bytes, {len(stocks) + len(fiis) + len(fiagros)} ativos)")


# ---------------------------------------------------------------------------
# CLI entry point (also used by pipeline.py and server.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Check if data is stale; if needed, run ingestion + generate
    today_str = datetime.now().strftime("%Y-%m-%d")
    needs_refresh = False

    try:
        last_update = database.get_last_update_timestamp()
        if not last_update:
            needs_refresh = True
            logger.info("Database is empty — will ingest first")
        else:
            last_date = last_update[:10]
            if last_date != today_str:
                needs_refresh = True
                logger.info(f"Data stale (last: {last_date}, today: {today_str}) — refreshing")
    except Exception as e:
        logger.warning(f"Could not check DB staleness: {e}")
        needs_refresh = True

    if needs_refresh:
        logger.info("Running auto-ingestion before generating dashboard...")
        import ingestion
        result = ingestion.run_full_ingestion()
        logger.info(f"Ingestion result: {result}")

    generate_dashboard()
