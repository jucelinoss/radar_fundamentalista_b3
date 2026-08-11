"""Exporta a comparação histórica entre score de produção e experimento de um FII."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", nargs="?", default="BCRI11")
    parser.add_argument("--data", type=Path, default=PROJECT_ROOT / "data.json")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "data" / "fii_score_experiment.db")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "reports")
    return parser.parse_args()


def production_history(data_path: Path, ticker: str) -> dict[str, dict]:
    data = json.loads(data_path.read_text(encoding="utf-8"))
    asset = next(item for item in data["fiis"] if item["ticker"] == ticker)
    return {point["date"][:7]: point for point in json.loads(asset["history_json"])}


def comparison_rows(db_path: Path, production: dict[str, dict], ticker: str) -> list[dict]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        experimental = connection.execute("""
            SELECT date, experimental_score, income_score, risk_proxy_score, valuation_score,
                   trailing_yield, six_month_change, monthly_volatility, income_alert
            FROM experimental_score_history
            WHERE ticker = ?
            ORDER BY date
        """, (ticker,)).fetchall()
    rows = []
    for point in experimental:
        historic = production.get(point["date"][:7], {})
        rows.append({
            "data": point["date"],
            "preco": historic.get("price"),
            "p_vp": historic.get("pb"),
            "dy_producao": historic.get("dy"),
            "score_producao": historic.get("score"),
            "score_experimental": point["experimental_score"],
            "renda_experimental": point["income_score"],
            "risco_renda": point["risk_proxy_score"],
            "valuation_experimental": point["valuation_score"],
            "dy_12m_experimental": point["trailing_yield"],
            "variacao_renda_6m": point["six_month_change"],
            "volatilidade_mensal": point["monthly_volatility"],
            "alerta_queda_renda": "sim" if point["income_alert"] else "não",
        })
    return rows


def format_number(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def format_percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, ticker: str, rows: list[dict]) -> None:
    lines = [
        f"# {ticker}: produção vs. score experimental",
        "",
        "A metodologia experimental pondera renda sustentável (5), risco observável da renda (3) e valuation contínuo (2).",
        "O alerta é acionado quando a renda dos últimos seis meses cai 15% ou mais contra os seis meses anteriores.",
        "",
        "| Data | Preço | P/VP | DY produção | Score produção | Score experimental | Renda (5) | Risco renda (3) | Valuation (2) | DY 12m exp. | Δ renda 6m | Volatilidade | Alerta |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {data} | R$ {preco} | {p_vp} | {dy} | {producao} | {experimental} | {renda} | {risco} | {valuation} | {dy_exp} | {variacao} | {volatilidade} | {alerta} |".format(
                data=row["data"], preco=format_number(row["preco"]), p_vp=format_number(row["p_vp"]),
                dy=format_percent(row["dy_producao"] / 100 if row["dy_producao"] is not None else None),
                producao=format_number(row["score_producao"]), experimental=format_number(row["score_experimental"]),
                renda=format_number(row["renda_experimental"]), risco=format_number(row["risco_renda"]),
                valuation=format_number(row["valuation_experimental"]), dy_exp=format_percent(row["dy_12m_experimental"]),
                variacao=format_percent(row["variacao_renda_6m"]), volatilidade=format_percent(row["volatilidade_mensal"]),
                alerta=row["alerta_queda_renda"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    ticker = args.ticker.upper()
    rows = comparison_rows(args.db, production_history(args.data, ticker), ticker)
    if not rows:
        raise SystemExit(f"Sem histórico experimental para {ticker}. Execute run_fii_score_experiment.py primeiro.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.output_dir / f"{ticker.lower()}_score_comparison"
    write_csv(prefix.with_suffix(".csv"), rows)
    write_markdown(prefix.with_suffix(".md"), ticker, rows)
    print(f"Tabela gerada: {prefix.with_suffix('.csv')} e {prefix.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
