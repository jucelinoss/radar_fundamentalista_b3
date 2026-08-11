"""Gera um banco isolado para validar o score experimental de FIIs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fii_score_experiment import load_fiis, run_experiment


def load_dividends(ticker: str):
    return yf.Ticker(f"{ticker}.SA").dividends


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=PROJECT_ROOT / "data.json")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "data" / "fii_score_experiment.db")
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "reports" / "fii_score_experiment.md")
    parser.add_argument("--baseline", default="BCRI11")
    parser.add_argument("--ticker", action="append", help="Restringe o experimento a um ticker; repetível.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    assets = load_fiis(args.data)
    if args.ticker:
        selected = {ticker.upper() for ticker in args.ticker}
        assets = [asset for asset in assets if asset["ticker"].upper() in selected]
    completed, failed = run_experiment(assets, args.db, args.report, load_dividends, args.baseline)
    print(f"Experimento concluído: {completed} FIIs analisados, {failed} sem série suficiente ou com erro.")
    print(f"Banco de teste: {args.db}")
    print(f"Relatório: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
