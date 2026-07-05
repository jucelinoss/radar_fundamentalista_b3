#!/usr/bin/env python3
"""
Data Exporter — B3 Fundamentalist Screener

Generates CSV and JSON exports of all screened assets and top picks
for use in external analysis (AI, spreadsheets, portfolio tools).

Usage:
    python src/exporter.py                     # Export both CSV + JSON to data/
    python src/exporter.py --format csv        # Only CSV
    python src/exporter.py --format json       # Only JSON
    python src/exporter.py --top-picks         # Only top picks
    python src/exporter.py --output-dir /path  # Custom output directory

Output files:
    data/export_ativos.csv       — All assets in tabular format
    data/export_ativos.json      — All assets in structured JSON
    data/export_top_picks.json   — Top 10 stocks, FIIs, and FIAGROs
"""
import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime

# Ensure src/ in path
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import database

logger = logging.getLogger("exporter")

# ---------------------------------------------------------------------------
# Percentage formatter
# ---------------------------------------------------------------------------

def pct(value, decimals=2):
    """Format a decimal ratio as a percentage string (e.g., 0.1234 → '12.34%')."""
    if value is None:
        return ""
    try:
        return f"{round(float(value) * 100, decimals)}%"
    except (ValueError, TypeError):
        return ""


def fmt_currency(value):
    """Format a number as BRL currency string."""
    if value is None:
        return ""
    try:
        return f"R$ {float(value):.2f}"
    except (ValueError, TypeError):
        return ""


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_all_assets():
    """Load all assets from the database, grouped by type."""
    return {
        "stocks": database.get_all_stocks(),
        "fiis": database.get_all_fiis(),
        "fiagros": database.get_all_fiagros(),
    }


# ---------------------------------------------------------------------------
# CSV Export
# ---------------------------------------------------------------------------

def export_csv(output_dir=None):
    """Export all assets as CSV files (one per type + a combined file)."""
    if output_dir is None:
        output_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(output_dir, exist_ok=True)

    assets = load_all_assets()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    exported = []

    # ── Stocks CSV ──────────────────────────────────────────────────
    stock_fields = [
        ("ticker", "Ticker"),
        ("name", "Nome"),
        ("sector", "Setor"),
        ("price", "Preço"),
        ("pe_ratio", "P/L"),
        ("pb_ratio", "P/VP"),
        ("dividend_yield", "Dividend Yield"),
        ("roe", "ROE"),
        ("eps", "LPA"),
        ("book_value", "VPA"),
        ("graham_price", "Preço Justo Graham"),
        ("bazin_price", "Preço Teto Bazin"),
        ("score", "Score (0-5)"),
    ]

    stock_path = os.path.join(output_dir, "export_stocks.csv")
    with open(stock_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([h for _, h in stock_fields])
        writer.writerow(["# Exportado em:", timestamp, "", "", "", "", "", "", "", "", "", "", ""])
        for s in assets["stocks"]:
            writer.writerow([
                s.get("ticker", "").replace(".SA", ""),
                s.get("name", ""),
                s.get("sector", ""),
                fmt_currency(s.get("price")),
                round(s["pe_ratio"], 2) if s.get("pe_ratio") else "",
                round(s["pb_ratio"], 2) if s.get("pb_ratio") else "",
                pct(s.get("dividend_yield")),
                pct(s.get("roe")),
                round(s["eps"], 2) if s.get("eps") else "",
                round(s["book_value"], 2) if s.get("book_value") else "",
                fmt_currency(s.get("graham_price")),
                fmt_currency(s.get("bazin_price")),
                round(s["score"], 1) if s.get("score") is not None else "",
            ])
    exported.append(("stocks", stock_path, len(assets["stocks"])))
    logger.info(f"  ✅ Stocks CSV: {stock_path} ({len(assets['stocks'])} ativos)")

    # ── FIIs CSV ────────────────────────────────────────────────────
    fii_fields = [
        ("ticker", "Ticker"),
        ("name", "Nome"),
        ("price", "Preço"),
        ("pb_ratio", "P/VP"),
        ("dividend_yield", "Dividend Yield"),
        ("dividend_rate", "Dividendo Mensal Est."),
        ("score", "Score (0-5)"),
    ]

    fii_path = os.path.join(output_dir, "export_fiis.csv")
    with open(fii_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([h for _, h in fii_fields])
        for fii in assets["fiis"]:
            writer.writerow([
                fii.get("ticker", "").replace(".SA", ""),
                fii.get("name", ""),
                fmt_currency(fii.get("price")),
                round(fii["pb_ratio"], 2) if fii.get("pb_ratio") else "",
                pct(fii.get("dividend_yield")),
                fmt_currency(fii.get("dividend_rate")),
                round(fii["score"], 1) if fii.get("score") is not None else "",
            ])
    exported.append(("fiis", fii_path, len(assets["fiis"])))
    logger.info(f"  ✅ FIIs CSV: {fii_path} ({len(assets['fiis'])} ativos)")

    # ── FIAGROs CSV ─────────────────────────────────────────────────
    fiagro_path = os.path.join(output_dir, "export_fiagros.csv")
    with open(fiagro_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([h for _, h in fii_fields])
        for a in assets["fiagros"]:
            writer.writerow([
                a.get("ticker", "").replace(".SA", ""),
                a.get("name", ""),
                fmt_currency(a.get("price")),
                round(a["pb_ratio"], 2) if a.get("pb_ratio") else "",
                pct(a.get("dividend_yield")),
                fmt_currency(a.get("dividend_rate")),
                round(a["score"], 1) if a.get("score") is not None else "",
            ])
    exported.append(("fiagros", fiagro_path, len(assets["fiagros"])))
    logger.info(f"  ✅ FIAGROs CSV: {fiagro_path} ({len(assets['fiagros'])} ativos)")

    return exported


# ---------------------------------------------------------------------------
# JSON Export
# ---------------------------------------------------------------------------

def export_json(output_dir=None):
    """Export all assets as a single structured JSON file."""
    if output_dir is None:
        output_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(output_dir, exist_ok=True)

    assets = load_all_assets()

    # Clean tickers (remove .SA suffix)
    for group in assets.values():
        for item in group:
            if item.get("ticker"):
                item["ticker"] = item["ticker"].replace(".SA", "")

    output = {
        "meta": {
            "exported_at": datetime.now().isoformat(),
            "source": "Screener Fundamentalista B3",
            "version": "2.0",
            "description": "Dados fundamentalistas de ativos da B3 - pronto para analise com IA",
        },
        "summary": {
            "total_stocks": len(assets["stocks"]),
            "total_fiis": len(assets["fiis"]),
            "total_fiagros": len(assets["fiagros"]),
            "total_assets": sum(len(v) for v in assets.values()),
        },
        "stocks": assets["stocks"],
        "fiis": assets["fiis"],
        "fiagros": assets["fiagros"],
    }

    path = os.path.join(output_dir, "export_ativos.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"  ✅ JSON export: {path} ({output['summary']['total_assets']} ativos)")
    return path


# ---------------------------------------------------------------------------
# Top Picks Export
# ---------------------------------------------------------------------------

def export_top_picks(output_dir=None):
    """Export top-rated assets for portfolio analysis with AI."""
    if output_dir is None:
        output_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(output_dir, exist_ok=True)

    assets = load_all_assets()

    # Top stocks by score (top 10)
    stocks_sorted = sorted(assets["stocks"], key=lambda x: x["score"] or 0, reverse=True)
    top_stocks = []
    for s in stocks_sorted[:10]:
        top_stocks.append({
            "ticker": s.get("ticker", "").replace(".SA", ""),
            "name": s.get("name", ""),
            "sector": s.get("sector", ""),
            "price": s.get("price"),
            "pe_ratio": round(s["pe_ratio"], 2) if s.get("pe_ratio") else None,
            "pb_ratio": round(s["pb_ratio"], 2) if s.get("pb_ratio") else None,
            "dividend_yield_pct": round(s["dividend_yield"] * 100, 2) if s.get("dividend_yield") else None,
            "roe_pct": round(s["roe"] * 100, 2) if s.get("roe") else None,
            "graham_price": s.get("graham_price"),
            "bazin_price": s.get("bazin_price"),
            "score": round(s["score"], 1) if s.get("score") is not None else None,
            "upside_graham_pct": round((s["graham_price"] / s["price"] - 1) * 100, 1)
                if s.get("graham_price") and s.get("price") and s["graham_price"] > 0 else None,
        })

    # Top FIIs by score (top 10)
    fiis_sorted = sorted(assets["fiis"], key=lambda x: x["score"] or 0, reverse=True)
    top_fiis = []
    for f in fiis_sorted[:10]:
        top_fiis.append({
            "ticker": f.get("ticker", "").replace(".SA", ""),
            "name": f.get("name", ""),
            "price": f.get("price"),
            "pb_ratio": round(f["pb_ratio"], 2) if f.get("pb_ratio") else None,
            "dividend_yield_pct": round(f["dividend_yield"] * 100, 2) if f.get("dividend_yield") else None,
            "dividend_rate": f.get("dividend_rate"),
            "score": round(f["score"], 1) if f.get("score") is not None else None,
        })

    # Top FIAGROs by score (top 10)
    fiagros_sorted = sorted(assets["fiagros"], key=lambda x: x["score"] or 0, reverse=True)
    top_fiagros = []
    for a in fiagros_sorted[:10]:
        top_fiagros.append({
            "ticker": a.get("ticker", "").replace(".SA", ""),
            "name": a.get("name", ""),
            "price": a.get("price"),
            "pb_ratio": round(a["pb_ratio"], 2) if a.get("pb_ratio") else None,
            "dividend_yield_pct": round(a["dividend_yield"] * 100, 2) if a.get("dividend_yield") else None,
            "dividend_rate": a.get("dividend_rate"),
            "score": round(a["score"], 1) if a.get("score") is not None else None,
        })

    output = {
        "meta": {
            "exported_at": datetime.now().isoformat(),
            "source": "Screener Fundamentalista B3 - Top Picks",
            "description": "Melhores ativos por score fundamentalista. Pronto para alimentar IA com sua carteira.",
            "suggested_prompt": (
                "Analise minha carteira de investimentos comparando com estes top picks. "
                "Para cada ativo da minha carteira, sugira se devo manter, aumentar, reduzir ou vender, "
                "considerando os scores fundamentalistas, DY, P/L, P/VP, ROE e margem de segurança de Graham."
            ),
        },
        "top_stocks": top_stocks,
        "top_fiis": top_fiis,
        "top_fiagros": top_fiagros,
    }

    path = os.path.join(output_dir, "export_top_picks.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"  ✅ Top picks JSON: {path}")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Export B3 Screener data for AI/portfolio analysis",
    )
    parser.add_argument("--format", choices=["csv", "json", "all"], default="all",
                        help="Export format (default: all)")
    parser.add_argument("--top-picks", action="store_true",
                        help="Export top picks summary")
    parser.add_argument("--output-dir", default=None,
                        help="Output directory (default: data/)")
    args = parser.parse_args()

    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler(sys.stdout))

    logger.info("📤 EXPORTING SCREENER DATA")
    logger.info("=" * 50)

    do_csv = args.format in ("csv", "all")
    do_json = args.format in ("json", "all")

    if do_csv:
        logger.info("Exporting CSV...")
        export_csv(args.output_dir)

    if do_json:
        logger.info("Exporting JSON...")
        export_json(args.output_dir)

    if args.top_picks or (do_json and not do_csv):
        logger.info("Exporting top picks...")
        export_top_picks(args.output_dir)

    logger.info("=" * 50)
    logger.info("✅ Export complete!")


if __name__ == "__main__":
    main()
