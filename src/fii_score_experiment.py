"""Score experimental para validar estabilidade de renda de FIIs."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

INCOME_WEIGHT = 5.0
RISK_WEIGHT = 3.0
VALUATION_WEIGHT = 2.0
MINIMUM_YIELD = 0.08
TARGET_YIELD = 0.16
SIX_MONTH_DROP_ALERT = -0.15
VOLATILITY_LIMIT = 0.35


@dataclass(frozen=True)
class ScorePoint:
    date: str
    score: float
    income_score: float
    risk_proxy_score: float
    valuation_score: float
    trailing_yield: float | None
    six_month_change: float | None
    monthly_volatility: float | None
    income_alert: bool


def load_fiis(data_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    return list(payload.get("fiis", []))


def normalize_dividends(dividends: pd.Series) -> pd.Series:
    if dividends.empty:
        return pd.Series(dtype=float)
    series = pd.to_numeric(dividends, errors="coerce").dropna()
    series.index = pd.to_datetime(series.index, utc=True).tz_convert(None)
    return series.resample("MS").sum().astype(float)


def price_by_month(asset: dict[str, Any]) -> pd.Series:
    history = json.loads(asset.get("history_json") or "[]")
    values = {
        pd.Timestamp(point["date"]).to_period("M").to_timestamp(): float(point["price"])
        for point in history
        if point.get("date") and point.get("price")
    }
    if asset.get("price"):
        values[pd.Timestamp.now().to_period("M").to_timestamp()] = float(asset["price"])
    return pd.Series(values, dtype=float).sort_index()


def latest_price(prices: pd.Series, as_of: pd.Timestamp) -> float | None:
    observed = prices[prices.index <= as_of]
    return float(observed.iloc[-1]) if not observed.empty else None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def calculate_valuation_score(pb_ratio: float | None) -> float:
    if pb_ratio is None or not math.isfinite(pb_ratio) or pb_ratio <= 0:
        return 0.0
    return round(VALUATION_WEIGHT * clamp((1.20 - pb_ratio) / 0.50, 0.0, 1.0), 2)


def calculate_income_components(
    dividends: pd.Series, price: float | None, as_of: pd.Timestamp
) -> tuple[float, float, float | None, float | None, float | None, bool]:
    history = dividends[dividends.index <= as_of].tail(12)
    if len(history) < 12 or (history > 0).sum() < 10 or price is None or price <= 0:
        return 0.0, 0.0, None, None, None, False

    trailing_yield = float(history.sum() / price)
    yield_score = 2.0 * clamp((trailing_yield - MINIMUM_YIELD) / (TARGET_YIELD - MINIMUM_YIELD), 0.0, 1.0)
    mean_income = float(history.mean())
    volatility = float(history.std(ddof=0) / mean_income) if mean_income > 0 else 1.0
    stability_score = 1.5 * clamp(1.0 - volatility / VOLATILITY_LIMIT, 0.0, 1.0)
    recent_income = float(history.iloc[-6:].sum())
    previous_income = float(history.iloc[:6].sum())
    six_month_change = recent_income / previous_income - 1.0 if previous_income > 0 else None
    trend_score = 1.5 * clamp(((six_month_change or -1.0) - SIX_MONTH_DROP_ALERT) / 0.30, 0.0, 1.0)
    income_score = round(yield_score + stability_score + trend_score, 2)
    risk_proxy_score = round(
        1.5 * float((history > 0).sum() / 12)
        + 1.5 * clamp(1.0 - max(0.0, -(six_month_change or 0.0)) / 0.30, 0.0, 1.0),
        2,
    )
    return income_score, risk_proxy_score, trailing_yield, six_month_change, volatility, bool(
        six_month_change is not None and six_month_change <= SIX_MONTH_DROP_ALERT
    )


def calculate_history(asset: dict[str, Any], dividends: pd.Series) -> list[ScorePoint]:
    prices = price_by_month(asset)
    book_value = asset.get("book_value")
    if not book_value:
        return []
    points: list[ScorePoint] = []
    for as_of in dividends.index:
        price = latest_price(prices, as_of)
        income, risk, trailing_yield, change, volatility, alert = calculate_income_components(dividends, price, as_of)
        if trailing_yield is None:
            continue
        valuation = calculate_valuation_score(price / float(book_value)) if price else 0.0
        points.append(ScorePoint(
            date=as_of.date().isoformat(), score=round(income + risk + valuation, 2),
            income_score=income, risk_proxy_score=risk, valuation_score=valuation,
            trailing_yield=trailing_yield, six_month_change=change,
            monthly_volatility=volatility, income_alert=alert,
        ))
    return points


def calculate_current(asset: dict[str, Any], history: list[ScorePoint]) -> ScorePoint | None:
    if not history:
        return None
    latest = history[-1]
    price = float(asset["price"]) if asset.get("price") else None
    book_value = float(asset["book_value"]) if asset.get("book_value") else None
    valuation = calculate_valuation_score(price / book_value) if price and book_value else 0.0
    return ScorePoint(
        date=datetime.now(UTC).date().isoformat(), score=round(latest.income_score + latest.risk_proxy_score + valuation, 2),
        income_score=latest.income_score, risk_proxy_score=latest.risk_proxy_score,
        valuation_score=valuation, trailing_yield=latest.trailing_yield,
        six_month_change=latest.six_month_change, monthly_volatility=latest.monthly_volatility,
        income_alert=latest.income_alert,
    )


def create_database(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.executescript("""
        DROP TABLE IF EXISTS experimental_asset_scores;
        DROP TABLE IF EXISTS experimental_score_history;
        CREATE TABLE experimental_asset_scores (
            ticker TEXT PRIMARY KEY, name TEXT NOT NULL, production_score REAL,
            experimental_score REAL, income_score REAL, risk_proxy_score REAL,
            valuation_score REAL, trailing_yield REAL, six_month_change REAL,
            monthly_volatility REAL, income_alert INTEGER NOT NULL, status TEXT NOT NULL
        );
        CREATE TABLE experimental_score_history (
            ticker TEXT NOT NULL, date TEXT NOT NULL, experimental_score REAL NOT NULL,
            income_score REAL NOT NULL, risk_proxy_score REAL NOT NULL, valuation_score REAL NOT NULL,
            production_score REAL, trailing_yield REAL, six_month_change REAL, monthly_volatility REAL,
            income_alert INTEGER NOT NULL, PRIMARY KEY (ticker, date)
        );
    """)
    return connection


def save_asset_scores(
    connection: sqlite3.Connection, asset: dict[str, Any], current: ScorePoint | None, history: Iterable[ScorePoint], status: str
) -> None:
    current_values = current or ScorePoint("", 0, 0, 0, 0, None, None, None, False)
    connection.execute("""
        INSERT INTO experimental_asset_scores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        asset["ticker"], asset.get("name", asset["ticker"]), asset.get("score_v2", asset.get("score")),
        current_values.score, current_values.income_score, current_values.risk_proxy_score,
        current_values.valuation_score, current_values.trailing_yield, current_values.six_month_change,
        current_values.monthly_volatility, int(current_values.income_alert), status,
    ))
    connection.executemany("""
        INSERT INTO experimental_score_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (asset["ticker"], point.date, point.score, point.income_score, point.risk_proxy_score,
         point.valuation_score, production_score_at(asset, point.date), point.trailing_yield,
         point.six_month_change, point.monthly_volatility, int(point.income_alert))
        for point in history
    ])


def production_score_at(asset: dict[str, Any], date: str) -> float | None:
    month = pd.Timestamp(date).to_period("M")
    for point in json.loads(asset.get("history_json") or "[]"):
        if point.get("date") and pd.Timestamp(point["date"]).to_period("M") == month:
            score = point.get("score")
            return float(score) if score is not None else None
    return None


def build_report(connection: sqlite3.Connection, report_path: Path, baseline: str) -> None:
    assets = pd.read_sql_query("SELECT * FROM experimental_asset_scores WHERE status = 'ok'", connection)
    history = pd.read_sql_query("SELECT * FROM experimental_score_history", connection)
    baseline_history = history[history["ticker"] == baseline].copy()
    lines = ["# Validação experimental de score de FIIs", "", "## Metodologia", "", "- Renda sustentável: 5,0 pontos.", "- Risco observável da renda: 3,0 pontos.", "- Valuation (P/VP contínuo): 2,0 pontos.", "- Alerta: queda de renda de 15% ou mais entre dois blocos consecutivos de 6 meses.", ""]
    lines += ["## Cobertura", "", f"- FIIs analisados: {len(assets)}.", f"- Séries históricas: {len(history)} pontos.", ""]
    if not history.empty:
        ordered_history = history.sort_values(["ticker", "date"])
        experimental_max = ordered_history.groupby("ticker")["experimental_score"].apply(lambda values: values.diff().abs().max()).dropna()
        production_scores = pd.to_numeric(ordered_history["production_score"], errors="coerce")
        production_max = production_scores.groupby(ordered_history["ticker"]).apply(lambda values: values.diff().abs().max()).dropna()
        lines += [
            "## Oscilação da carteira",
            "",
            f"- Mediana da maior variação mensal experimental por FII: {experimental_max.median():.2f} ponto(s).",
            f"- Mediana da maior variação mensal de produção por FII: {production_max.median():.2f} ponto(s).",
            "",
        ]
    if not baseline_history.empty:
        changes = baseline_history["experimental_score"].diff().abs().dropna()
        production = pd.to_numeric(baseline_history["production_score"], errors="coerce").dropna()
        production_changes = production.diff().abs().dropna()
        alerts = baseline_history["income_alert"].astype(bool)
        alert_starts = baseline_history.loc[alerts & ~alerts.shift(fill_value=False), "date"].tolist()
        lines += [f"## Baseline: {baseline}", "", f"- Pontos históricos: {len(baseline_history)}.", f"- Faixa do score experimental: {baseline_history.experimental_score.min():.2f}–{baseline_history.experimental_score.max():.2f}.", f"- Maior variação mensal: {changes.max():.2f} ponto(s).", f"- Alertas de queda de renda: {int(baseline_history.income_alert.sum())}."]
        if not production.empty:
            lines += [
                f"- Faixa do score de produção alinhado: {production.min():.2f}–{production.max():.2f}.",
                f"- Maior variação mensal de produção: {production_changes.max():.2f} ponto(s).",
            ]
        lines.append(f"- Inícios de episódios de queda persistente: {', '.join(alert_starts) or 'nenhum'}.")
        lines.append("")
    if not assets.empty:
        alerts = assets.sort_values("six_month_change").head(10)
        lines += ["## Maiores quedas de renda em 6 meses", "", "| Ticker | Variação | Score experimental | Alerta |", "|---|---:|---:|---|"]
        lines += [f"| {row.ticker} | {row.six_month_change:.1%} | {row.experimental_score:.2f} | {'sim' if row.income_alert else 'não'} |" for row in alerts.itertuples() if pd.notna(row.six_month_change)]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_experiment(
    assets: Iterable[dict[str, Any]], db_path: Path, report_path: Path,
    dividend_loader: Callable[[str], pd.Series], baseline: str = "BCRI11",
) -> tuple[int, int]:
    connection = create_database(db_path)
    completed = failed = 0
    try:
        for asset in assets:
            try:
                dividends = normalize_dividends(dividend_loader(asset["ticker"]))
                history = calculate_history(asset, dividends)
                status = "ok" if history else "insufficient_history"
                save_asset_scores(connection, asset, calculate_current(asset, history), history, status)
                completed += status == "ok"
                failed += status != "ok"
            except Exception:
                save_asset_scores(connection, asset, None, [], "dividend_load_error")
                failed += 1
        connection.commit()
        build_report(connection, report_path, baseline)
    finally:
        connection.close()
    return completed, failed
