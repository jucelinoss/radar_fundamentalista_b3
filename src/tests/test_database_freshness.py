"""Regression tests for incremental-refresh completeness checks."""
from datetime import datetime

import database


def test_missing_score_breakdown_forces_refresh(tmp_path, monkeypatch):
    """Recent records without modal rating details must not be skipped."""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "investments.db"))
    database.init_db()

    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO stocks (ticker, updated_at, score_breakdown) VALUES (?, ?, ?)",
            ("COMP3.SA", datetime.now().isoformat(), None),
        )

    assert database.get_stale_tickers(["COMP3.SA"], "stocks", max_age_hours=24) == ["COMP3.SA"]


def test_recent_record_with_score_breakdown_is_fresh(tmp_path, monkeypatch):
    """Complete records keep the normal incremental-refresh behavior."""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "investments.db"))
    database.init_db()

    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO fiagros (ticker, updated_at, score_breakdown, history_version) VALUES (?, ?, ?, ?)",
            ("COMP11.SA", datetime.now().isoformat(), "[{\"label\": \"P/VP\"}]", database.HISTORY_ENRICHMENT_VERSION),
        )

    assert database.get_stale_tickers(["COMP11.SA"], "fiagros", max_age_hours=24) == []


def test_old_dividend_history_version_forces_one_refresh(tmp_path, monkeypatch):
    """FIIs/FIAGROs must be re-enriched after the historical formula changes."""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "investments.db"))
    database.init_db()

    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO fiis (ticker, updated_at, score_breakdown, history_version) VALUES (?, ?, ?, ?)",
            ("COMP11.SA", datetime.now().isoformat(), "[{\"label\": \"P/VP\"}]", 1),
        )

    assert database.get_stale_tickers(["COMP11.SA"], "fiis", max_age_hours=24) == ["COMP11.SA"]
