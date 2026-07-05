#!/usr/bin/env python3
"""
Data Exporter — Radar Fundamentalista B3

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
from typing import Any

import database

PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logger: logging.Logger = logging.getLogger("exporter")

# ---------------------------------------------------------------------------
# Percentage formatter
# ---------------------------------------------------------------------------


def pct(value: float | int | None, decimals: int = 2) -> str:
    """Format a decimal ratio as a percentage string (e.g., 0.1234 → '12.34%')."""
    if value is None:
        return ""
    try:
        return f"{round(float(value) * 100, decimals)}%"
    except (ValueError, TypeError):
        return ""


def fmt_currency(value: float | int | None) -> str:
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


def load_all_assets() -> dict[str, list[dict[str, Any]]]:
    """Load all assets from the database, grouped by type."""
    return {
        "stocks": database.get_all_stocks(),
        "fiis": database.get_all_fiis(),
        "fiagros": database.get_all_fiagros(),
    }


# ---------------------------------------------------------------------------
# CSV Export
# ---------------------------------------------------------------------------


def _write_stock_csv(output_dir: str, stocks: list[dict[str, Any]], timestamp: str) -> str:
    """Write stocks CSV with full fundamentalist fields."""
    fields: list[tuple[str, str]] = [
        ("ticker", "Ticker"), ("name", "Nome"), ("sector", "Setor"),
        ("price", "Preço"), ("pe_ratio", "P/L"), ("pb_ratio", "P/VP"),
        ("dividend_yield", "Dividend Yield"), ("roe", "ROE"),
        ("eps", "LPA"), ("book_value", "VPA"),
        ("graham_price", "Preço Justo Graham"), ("bazin_price", "Preço Teto Bazin"),
        ("score", "Score (0-5)"),
    ]
    path: str = os.path.join(output_dir, "export_stocks.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([h for _, h in fields])
        writer.writerow(["# Exportado em:", timestamp] + [""] * (len(fields) - 2))
        for s in stocks:
            writer.writerow([
                s.get("ticker", "").replace(".SA", ""),
                s.get("name", ""), s.get("sector", ""),
                fmt_currency(s.get("price")),
                round(s["pe_ratio"], 2) if s.get("pe_ratio") else "",
                round(s["pb_ratio"], 2) if s.get("pb_ratio") else "",
                pct(s.get("dividend_yield")), pct(s.get("roe")),
                round(s["eps"], 2) if s.get("eps") else "",
                round(s["book_value"], 2) if s.get("book_value") else "",
                fmt_currency(s.get("graham_price")),
                fmt_currency(s.get("bazin_price")),
                round(s["score"], 1) if s.get("score") is not None else "",
            ])
    logger.info(f"  Stocks CSV: {path} ({len(stocks)} ativos)")
    return path


def _write_reit_csv(output_dir: str, assets: list[dict[str, Any]], asset_type: str, timestamp: str) -> str:
    """Write FII/FIAGRO CSV with REIT-specific fields."""
    fields: list[tuple[str, str]] = [
        ("ticker", "Ticker"), ("name", "Nome"), ("price", "Preço"),
        ("pb_ratio", "P/VP"), ("dividend_yield", "Dividend Yield"),
        ("dividend_rate", "Dividendo Mensal Est."), ("score", "Score (0-5)"),
    ]
    path: str = os.path.join(output_dir, f"export_{asset_type}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([h for _, h in fields])
        for item in assets:
            writer.writerow([
                item.get("ticker", "").replace(".SA", ""),
                item.get("name", ""),
                fmt_currency(item.get("price")),
                round(item["pb_ratio"], 2) if item.get("pb_ratio") else "",
                pct(item.get("dividend_yield")),
                fmt_currency(item.get("dividend_rate")),
                round(item["score"], 1) if item.get("score") is not None else "",
            ])
    logger.info(f"  {asset_type.upper()} CSV: {path} ({len(assets)} ativos)")
    return path


def export_csv(output_dir: str | None = None) -> list[tuple[str, str, int]]:
    """Export all assets as CSV files (one per type + a combined file)."""
    if output_dir is None:
        output_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(output_dir, exist_ok=True)

    assets: dict[str, list[dict[str, Any]]] = load_all_assets()
    timestamp: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    exported: list[tuple[str, str, int]] = [
        ("stocks", _write_stock_csv(output_dir, assets["stocks"], timestamp), len(assets["stocks"])),
        ("fiis", _write_reit_csv(output_dir, assets["fiis"], "fiis", timestamp), len(assets["fiis"])),
        ("fiagros", _write_reit_csv(output_dir, assets["fiagros"], "fiagros", timestamp), len(assets["fiagros"])),
    ]
    return exported


# ---------------------------------------------------------------------------
# JSON Export
# ---------------------------------------------------------------------------


def export_json(output_dir: str | None = None) -> str:
    """Export all assets as a single structured JSON file."""
    if output_dir is None:
        output_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(output_dir, exist_ok=True)

    assets: dict[str, list[dict[str, Any]]] = load_all_assets()

    # Clean tickers (remove .SA suffix)
    for group in assets.values():
        for item in group:
            if item.get("ticker"):
                item["ticker"] = item["ticker"].replace(".SA", "")

    output: dict[str, Any] = {
        "meta": {
            "exported_at": datetime.now().isoformat(),
            "source": "Radar Fundamentalista B3",
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

    path: str = os.path.join(output_dir, "export_ativos.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"  JSON export: {path} ({output['summary']['total_assets']} ativos)")
    return path


# ---------------------------------------------------------------------------
# Top Picks Export
# ---------------------------------------------------------------------------


def _build_top_picks_list(
    assets: list[dict[str, Any]],
    *extra_fields: str,
) -> list[dict[str, Any]]:
    """Build a top-10 list for a given asset type, sorted by score descending.

    Each entry includes common fields (ticker, name, price, pb_ratio, dividend_yield_pct, score)
    plus any extra fields specified.
    """
    sorted_assets: list[dict[str, Any]] = sorted(
        assets, key=lambda x: x.get("score") or 0, reverse=True
    )
    result: list[dict[str, Any]] = []
    for item in sorted_assets[:10]:
        entry: dict[str, Any] = {
            "ticker": item.get("ticker", "").replace(".SA", ""),
            "name": item.get("name", ""),
            "price": item.get("price"),
            "pb_ratio": round(item["pb_ratio"], 2) if item.get("pb_ratio") else None,
            "dividend_yield_pct": round(item["dividend_yield"] * 100, 2) if item.get("dividend_yield") else None,
            "score": round(item["score"], 1) if item.get("score") is not None else None,
        }
        for field in extra_fields:
            entry[field] = item.get(field)
        result.append(entry)
    return result


def export_top_picks(output_dir: str | None = None) -> str:
    """Export top-rated assets for portfolio analysis with AI."""
    if output_dir is None:
        output_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(output_dir, exist_ok=True)

    assets: dict[str, list[dict[str, Any]]] = load_all_assets()

    top_stocks: list[dict[str, Any]] = []
    for s in sorted(assets["stocks"], key=lambda x: x.get("score") or 0, reverse=True)[:10]:
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

    top_fiis: list[dict[str, Any]] = _build_top_picks_list(assets["fiis"], "dividend_rate")
    top_fiagros: list[dict[str, Any]] = _build_top_picks_list(assets["fiagros"], "dividend_rate")

    output: dict[str, Any] = {
        "meta": {
            "exported_at": datetime.now().isoformat(),
            "source": "Radar Fundamentalista B3 - Top Picks",
            "description": "Melhores ativos por score fundamentalista. Pronto para alimentar IA com sua carteira.",
            "suggested_prompt": (
                "Analise minha carteira de investimentos comparando com estes top picks. "
                "Para cada ativo da minha carteira, sugira se devo manter, aumentar, reduzir ou vender, "
                "considerando os scores fundamentalistas, DY, P/L, P/VP, ROE e margem de seguranca de Graham."
            ),
        },
        "top_stocks": top_stocks,
        "top_fiis": top_fiis,
        "top_fiagros": top_fiagros,
    }

    path: str = os.path.join(output_dir, "export_top_picks.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"  Top picks JSON: {path}")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Radar Fundamentalista B3 data for AI/portfolio analysis",
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

    logger.info("EXPORTANDO DADOS DO RADAR")
    logger.info("=" * 50)

    do_csv: bool = args.format in ("csv", "all")
    do_json: bool = args.format in ("json", "all")

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
    logger.info("Export complete!")


if __name__ == "__main__":
    main()
