"""
Database persistence layer for the Radar Fundamentalista B3.
Provides context-managed SQLite connections, schema initialization, and CRUD operations.
"""
import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "investments.db")


@contextmanager
def get_connection():
    """Context manager for SQLite connections. Auto-closes on exit.
    Supports ':memory:' for testing — skips directory creation."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database schema with idempotent CREATE TABLE and migration columns."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Table for Stocks
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            sector TEXT,
            price REAL,
            pe_ratio REAL,
            pb_ratio REAL,
            dividend_yield REAL,
            roe REAL,
            eps REAL,
            book_value REAL,
            graham_price REAL,
            bazin_price REAL,
            score REAL,
            history_json TEXT,
            updated_at TEXT
        )
        """)
        # Idempotent migration: add sector column if it doesn't exist
        _add_column_if_not_exists(cursor, "stocks", "sector", "TEXT")

        # Table for FIIs (Real Estate Funds)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS fiis (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            price REAL,
            pb_ratio REAL,
            dividend_yield REAL,
            dividend_rate REAL,
            score REAL,
            history_json TEXT,
            updated_at TEXT
        )
        """)
        _add_column_if_not_exists(cursor, "fiis", "score", "REAL")

        # Table for FIAGROs (Agricultural Receivables Funds)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS fiagros (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            price REAL,
            pb_ratio REAL,
            dividend_yield REAL,
            dividend_rate REAL,
            score REAL,
            history_json TEXT,
            updated_at TEXT
        )
        """)
        _add_column_if_not_exists(cursor, "fiagros", "score", "REAL")

        # Table to track pipeline execution history
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            finished_at TEXT,
            duration_seconds REAL,
            stocks_ok INTEGER,
            stocks_fail INTEGER,
            fiis_ok INTEGER,
            fiis_fail INTEGER,
            fiagros_ok INTEGER,
            fiagros_fail INTEGER,
            status TEXT
        )
        """)


def _add_column_if_not_exists(cursor, table_name, column_name, column_type):
    """Safely add a column if it doesn't already exist (idempotent migration)."""
    try:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
    except sqlite3.OperationalError:
        pass


# ---------------------------------------------------------------------------
# Stock operations
# ---------------------------------------------------------------------------

def save_stock(data):
    """Insert or replace a stock record."""
    with get_connection() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO stocks (
            ticker, name, sector, price, pe_ratio, pb_ratio, dividend_yield,
            roe, eps, book_value, graham_price, bazin_price, score, history_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['ticker'], data.get('name'), data.get('sector', 'Outros'),
            data.get('price'), data.get('pe_ratio'),
            data.get('pb_ratio'), data.get('dividend_yield'), data.get('roe'),
            data.get('eps'), data.get('book_value'), data.get('graham_price'),
            data.get('bazin_price'), data.get('score'), data.get('history_json'),
            datetime.now().isoformat()
        ))


def get_all_stocks():
    """Return all stocks ordered by score descending."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM stocks ORDER BY score DESC")
        return [dict(row) for row in cursor.fetchall()]


def get_stock_by_ticker(ticker):
    """Return a single stock by ticker, or None."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM stocks WHERE ticker = ?", (ticker,))
        row = cursor.fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# FII operations
# ---------------------------------------------------------------------------

def save_fii(data):
    """Insert or replace a FII record."""
    with get_connection() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO fiis (
            ticker, name, price, pb_ratio, dividend_yield, dividend_rate,
            score, history_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['ticker'], data.get('name'), data.get('price'),
            data.get('pb_ratio'), data.get('dividend_yield'),
            data.get('dividend_rate'), data.get('score', 0),
            data.get('history_json'), datetime.now().isoformat()
        ))


def get_all_fiis():
    """Return all FIIs ordered by score descending, then P/B ascending."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fiis ORDER BY score DESC, pb_ratio ASC")
        return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# FIAGRO operations
# ---------------------------------------------------------------------------

def save_fiagro(data):
    """Insert or replace a FIAGRO record."""
    with get_connection() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO fiagros (
            ticker, name, price, pb_ratio, dividend_yield, dividend_rate,
            score, history_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['ticker'], data.get('name'), data.get('price'),
            data.get('pb_ratio'), data.get('dividend_yield'),
            data.get('dividend_rate'), data.get('score', 0),
            data.get('history_json'), datetime.now().isoformat()
        ))


def get_all_fiagros():
    """Return all FIAGROs ordered by score descending, then P/B ascending."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fiagros ORDER BY score DESC, pb_ratio ASC")
        return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Pipeline log operations
# ---------------------------------------------------------------------------

def log_pipeline_run(started_at, finished_at, duration, stats, status):
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

VALID_TABLES = {"stocks", "fiis", "fiagros"}

def get_stale_tickers(ticker_list, table_name, max_age_hours=6):
    """
    From a list of ticker symbols, return only those that need refreshing.

    A ticker is 'stale' (needs refresh) if:
    - It has never been fetched (updated_at IS NULL), OR
    - It was last updated more than `max_age_hours` ago.

    A ticker is 'fresh' (skip) if its updated_at is within max_age_hours.
    """
    if not ticker_list:
        return []

    if table_name not in VALID_TABLES:
        raise ValueError(f"Invalid table: {table_name}")

    with get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ','.join(['?'] * len(ticker_list))
        threshold = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()

        cursor.execute(f"""
            SELECT ticker FROM {table_name}
            WHERE ticker IN ({placeholders})
              AND updated_at IS NOT NULL
              AND updated_at > ?
        """, [*ticker_list, threshold])
        fresh_tickers = {row[0] for row in cursor.fetchall()}

    stale = [t for t in ticker_list if t not in fresh_tickers]
    return stale


def get_last_update_timestamp():
    """Return the most recent updated_at across all asset tables, or None."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MAX(max_update) FROM (
                SELECT MAX(updated_at) AS max_update FROM stocks
                UNION ALL
                SELECT MAX(updated_at) AS max_update FROM fiis
                UNION ALL
                SELECT MAX(updated_at) AS max_update FROM fiagros
            )
        """)
        row = cursor.fetchone()
        return row[0] if row and row[0] else None


def get_pipeline_history(limit=10):
    """Return the last N pipeline runs for monitoring."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM pipeline_log ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]
