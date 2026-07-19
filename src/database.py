"""
Database persistence layer for the Radar Fundamentalista B3.
Provides context-managed SQLite connections, schema initialization, and CRUD operations.
"""
import sqlite3
import os
from contextlib import contextmanager
from collections.abc import Generator
from datetime import datetime, timedelta
from typing import Any

DB_PATH: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "investments.db")


@contextmanager
def get_connection() -> Generator[sqlite3.Connection]:
    """Context manager for SQLite connections. Auto-closes on exit.
    Supports ':memory:' for testing — skips directory creation."""
    db_dir: str = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn: sqlite3.Connection = sqlite3.connect(DB_PATH, timeout=30)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _create_stocks_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stocks (
        ticker TEXT PRIMARY KEY, name TEXT, sector TEXT,
        price REAL, pe_ratio REAL, pb_ratio REAL, dividend_yield REAL,
        roe REAL, eps REAL, book_value REAL,
        graham_price REAL, bazin_price REAL, score REAL,
        history_json TEXT, updated_at TEXT
    )
    """)
    _add_column_if_not_exists(cursor, "stocks", "sector", "TEXT")
    # v2.5 continuous score columns
    _add_column_if_not_exists(cursor, "stocks", "dy_medio_3y", "REAL")
    _add_column_if_not_exists(cursor, "stocks", "pe_medio_5y", "REAL")
    _add_column_if_not_exists(cursor, "stocks", "net_debt_ebitda", "REAL")
    _add_column_if_not_exists(cursor, "stocks", "score_v2", "REAL")
    _add_column_if_not_exists(cursor, "stocks", "score_breakdown", "TEXT")


def _create_fiis_table(cursor: sqlite3.Cursor, table: str) -> None:
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {table} (
        ticker TEXT PRIMARY KEY, name TEXT, price REAL,
        pb_ratio REAL, dividend_yield REAL, dividend_rate REAL,
        book_value REAL, score REAL, history_json TEXT, updated_at TEXT
    )
    """)
    _add_column_if_not_exists(cursor, table, "score", "REAL")
    _add_column_if_not_exists(cursor, table, "book_value", "REAL")
    # v2.5 continuous score columns
    _add_column_if_not_exists(cursor, table, "dividend_consistency", "REAL")
    _add_column_if_not_exists(cursor, table, "score_v2", "REAL")
    _add_column_if_not_exists(cursor, table, "score_breakdown", "TEXT")


def _create_pipeline_log_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pipeline_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT, finished_at TEXT, duration_seconds REAL,
        stocks_ok INTEGER, stocks_fail INTEGER,
        fiis_ok INTEGER, fiis_fail INTEGER,
        fiagros_ok INTEGER, fiagros_fail INTEGER,
        status TEXT
    )
    """)


def init_db() -> None:
    """Initialize database schema with idempotent CREATE TABLE and migration columns."""
    with get_connection() as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        _create_stocks_table(cursor)
        _create_fiis_table(cursor, "fiis")
        _create_fiis_table(cursor, "fiagros")
        _create_pipeline_log_table(cursor)


def _add_column_if_not_exists(cursor: sqlite3.Cursor, table_name: str, column_name: str, column_type: str) -> None:
    """Safely add a column if it doesn't already exist (idempotent migration)."""
    try:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
    except sqlite3.OperationalError:
        pass


# ---------------------------------------------------------------------------
# Stock operations
# ---------------------------------------------------------------------------


def save_stock(data: dict[str, Any]) -> None:
    """Insert or replace a stock record."""
    import json
    breakdown_json = json.dumps(data.get('score_breakdown') or [])
    with get_connection() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO stocks (
            ticker, name, sector, price, pe_ratio, pb_ratio, dividend_yield,
            roe, eps, book_value, graham_price, bazin_price, score, history_json, updated_at,
            dy_medio_3y, pe_medio_5y, net_debt_ebitda, score_v2, score_breakdown
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['ticker'], data.get('name'), data.get('sector', 'Outros'),
            data.get('price'), data.get('pe_ratio'),
            data.get('pb_ratio'), data.get('dividend_yield'), data.get('roe'),
            data.get('eps'), data.get('book_value'), data.get('graham_price'),
            data.get('bazin_price'), data.get('score'), data.get('history_json'),
            datetime.now().isoformat(),
            data.get('dy_medio_3y'), data.get('pe_medio_5y'),
            data.get('net_debt_ebitda'), data.get('score_v2'),
            breakdown_json
        ))


def get_all_stocks() -> list[dict[str, Any]]:
    """Return all stocks ordered by score descending."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute("SELECT * FROM stocks ORDER BY score DESC")
        return [dict(row) for row in cursor.fetchall()]


def get_stock_by_ticker(ticker: str) -> dict[str, Any] | None:
    """Return a single stock by ticker, or None."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute("SELECT * FROM stocks WHERE ticker = ?", (ticker,))
        row: sqlite3.Row | None = cursor.fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# FII operations
# ---------------------------------------------------------------------------


def save_fii(data: dict[str, Any]) -> None:
    """Insert or replace a FII record."""
    import json
    breakdown_json = json.dumps(data.get('score_breakdown') or [])
    with get_connection() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO fiis (
            ticker, name, price, pb_ratio, dividend_yield, dividend_rate,
            book_value, score, history_json, updated_at,
            dividend_consistency, score_v2, score_breakdown
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['ticker'], data.get('name'), data.get('price'),
            data.get('pb_ratio'), data.get('dividend_yield'),
            data.get('dividend_rate'), data.get('book_value'),
            data.get('score', 0),
            data.get('history_json'), datetime.now().isoformat(),
            data.get('dividend_consistency'), data.get('score_v2'),
            breakdown_json
        ))


def get_all_fiis() -> list[dict[str, Any]]:
    """Return all FIIs ordered by score descending, then P/B ascending."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute("SELECT * FROM fiis ORDER BY score DESC, pb_ratio ASC")
        return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# FIAGRO operations
# ---------------------------------------------------------------------------


def save_fiagro(data: dict[str, Any]) -> None:
    """Insert or replace a FIAGRO record."""
    import json
    breakdown_json = json.dumps(data.get('score_breakdown') or [])
    with get_connection() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO fiagros (
            ticker, name, price, pb_ratio, dividend_yield, dividend_rate,
            book_value, score, history_json, updated_at,
            dividend_consistency, score_v2, score_breakdown
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['ticker'], data.get('name'), data.get('price'),
            data.get('pb_ratio'), data.get('dividend_yield'),
            data.get('dividend_rate'), data.get('book_value'),
            data.get('score', 0),
            data.get('history_json'), datetime.now().isoformat(),
            data.get('dividend_consistency'), data.get('score_v2'),
            breakdown_json
        ))


def get_all_fiagros() -> list[dict[str, Any]]:
    """Return all FIAGROs ordered by score descending, then P/B ascending."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute("SELECT * FROM fiagros ORDER BY score DESC, pb_ratio ASC")
        return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Pipeline log operations
# ---------------------------------------------------------------------------


def log_pipeline_run(started_at: str, finished_at: str, duration: float,
                     stats: dict[str, int], status: str) -> None:
    """Record a pipeline execution in the database for audit/history."""
    with get_connection() as conn:
        conn.execute("""
        INSERT INTO pipeline_log (
            started_at, finished_at, duration_seconds,
            stocks_ok, stocks_fail, fiis_ok, fiis_fail,
            fiagros_ok, fiagros_fail, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            started_at, finished_at, duration,
            stats.get('stocks_ok', 0), stats.get('stocks_fail', 0),
            stats.get('fiis_ok', 0), stats.get('fiis_fail', 0),
            stats.get('fiagros_ok', 0), stats.get('fiagros_fail', 0),
            status
        ))


# ---------------------------------------------------------------------------
# Incremental refresh helpers
# ---------------------------------------------------------------------------

VALID_TABLES: set[str] = {"stocks", "fiis", "fiagros"}


def get_stale_tickers(ticker_list: list[str], table_name: str, max_age_hours: int = 6) -> list[str]:
    """
    From a list of ticker symbols, return only those that need refreshing.

    A ticker is 'stale' (needs refresh) if:
    - It has never been fetched (updated_at IS NULL), OR
    - It was last updated more than `max_age_hours` ago.
    - Its current score breakdown is missing. This is required for the
      analytical rating shown in the asset detail modal.

    A ticker is 'fresh' (skip) only if its updated_at is within
    `max_age_hours` and it has a populated score breakdown.
    """
    if not ticker_list:
        return []

    if table_name not in VALID_TABLES:
        raise ValueError(f"Invalid table: {table_name}")

    with get_connection() as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        placeholders: str = ','.join(['?'] * len(ticker_list))
        threshold: str = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()

        cursor.execute(f"""
            SELECT ticker FROM {table_name}
            WHERE ticker IN ({placeholders})
              AND updated_at IS NOT NULL
              AND updated_at > ?
              AND score_breakdown IS NOT NULL
              AND TRIM(score_breakdown) NOT IN ('', '[]')
        """, [*ticker_list, threshold])
        fresh_tickers: set[str] = {row[0] for row in cursor.fetchall()}

    stale: list[str] = [t for t in ticker_list if t not in fresh_tickers]
    return stale


def get_last_update_timestamp() -> str | None:
    """Return the most recent updated_at across all asset tables, or None."""
    with get_connection() as conn:
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute("""
            SELECT MAX(max_update) FROM (
                SELECT MAX(updated_at) AS max_update FROM stocks
                UNION ALL
                SELECT MAX(updated_at) AS max_update FROM fiis
                UNION ALL
                SELECT MAX(updated_at) AS max_update FROM fiagros
            )
        """)
        row: tuple[str | None] | None = cursor.fetchone()
        return row[0] if row and row[0] else None


def get_pipeline_history(limit: int = 10) -> list[dict[str, Any]]:
    """Return the last N pipeline runs for monitoring."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor: sqlite3.Cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM pipeline_log ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]
