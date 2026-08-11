import json
import sqlite3

import pandas as pd
import pytest

from fii_score_experiment import (
    SIX_MONTH_DROP_ALERT,
    calculate_history,
    calculate_income_components,
    run_experiment,
)


def make_asset() -> dict:
    months = pd.date_range("2024-01-01", periods=24, freq="MS")
    return {
        "ticker": "TEST11",
        "name": "FII de teste",
        "price": 100.0,
        "book_value": 100.0,
        "score_v2": 7.0,
        "history_json": json.dumps([
            {"date": date.date().isoformat(), "price": 100.0} for date in months
        ]),
    }


def make_dividends(last_six_months: float = 1.0) -> pd.Series:
    months = pd.date_range("2024-01-01", periods=24, freq="MS")
    values = [1.0] * 18 + [last_six_months] * 6
    return pd.Series(values, index=months)


def test_income_alert_requires_a_fifteen_percent_six_month_cut():
    dividends = make_dividends(last_six_months=0.80)

    _, _, _, change, _, alert = calculate_income_components(dividends, 100.0, dividends.index[-1])

    assert change == pytest.approx(-0.20)
    assert change <= SIX_MONTH_DROP_ALERT
    assert alert is True


def test_history_uses_continuous_valuation_and_keeps_score_in_range():
    history = calculate_history(make_asset(), make_dividends(last_six_months=0.80))

    assert history
    assert history[-1].income_alert is True
    assert all(0.0 <= point.score <= 10.0 for point in history)
    assert history[-1].valuation_score == 0.8


def test_experiment_writes_an_isolated_database_and_report(tmp_path):
    db_path = tmp_path / "experiment.db"
    report_path = tmp_path / "report.md"

    completed, failed = run_experiment(
        [make_asset()], db_path, report_path, lambda _: make_dividends(0.80), baseline="TEST11"
    )

    assert (completed, failed) == (1, 0)
    assert report_path.exists()
    assert "Inícios de episódios" in report_path.read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as connection:
        saved = connection.execute("SELECT income_alert FROM experimental_asset_scores").fetchone()
    assert saved == (1,)
