"""
Data ingestion pipeline for the Radar Fundamentalista B3.

Fetches asset data from Yahoo Finance (yfinance), computes fundamentalist
metrics via analyzer.py, and persists results to SQLite via database.py.

Improvements over v1:
  - Parallel fetching via ThreadPoolExecutor (5 workers)
  - Retry logic with exponential backoff for transient failures
  - Structured logging instead of print()
  - Configuration loaded from external JSON files
  - Thread-safe progress tracking
  - Graceful degradation on partial failures
"""
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Lock

from sources import fetch_asset_info, fetch_history

import database
import analyzer

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
MAPPINGS_FILE = os.path.join(DATA_DIR, "ticker_mappings.json")
FAILED_LOG_FILE = os.path.join(DATA_DIR, "failed_tickers.log")

os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logger = logging.getLogger("ingestion")
_log_handler = logging.StreamHandler(sys.stdout)
_log_handler.setFormatter(logging.Formatter(
    "[%(asctime)s] %(levelname)s - %(message)s", datefmt="%H:%M:%S"
))
logger.addHandler(_log_handler)
logger.setLevel(logging.INFO)
# Prevent propagation to root logger to avoid duplicate prints
logger.propagate = False


# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------
def load_config():
    """Load ticker lists and pipeline settings from config/tickers.json."""
    config_path = os.path.join(CONFIG_DIR, "tickers.json")
    defaults = {
        "stocks": {"tickers": []},
        "fiis": {"tickers": []},
        "fiagros": {"tickers": []},
        "brapi": {
            "token": "",
            "notes": "Obtenha um token gratuito em https://brapi.dev/dashboard"
        },
        "pipeline": {
            "max_workers": 5,
            "delay_between_tickers": 0.3,
            "retry_attempts": 3,
            "retry_delay_base": 2.0,
            "history_years": "10y",
            "history_sample_points": 60
        }
    }
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # Merge with defaults to ensure all keys exist
            for key in defaults:
                if key not in cfg:
                    cfg[key] = defaults[key]
                elif isinstance(defaults[key], dict):
                    for subkey in defaults[key]:
                        if subkey not in cfg[key]:
                            cfg[key][subkey] = defaults[key][subkey]
            return cfg
        except Exception as e:
            logger.warning(f"Failed to load config ({e}), using hardcoded defaults")
    return defaults


def load_ticker_mappings():
    """Load ticker rename/delist mappings from data/ticker_mappings.json."""
    if os.path.exists(MAPPINGS_FILE):
        try:
            with open(MAPPINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading ticker mappings: {e}")
    return {}


def resolve_ticker(ticker, mappings):
    """Resolve a ticker through mappings; returns (resolved_ticker, is_delisted)."""
    if ticker in mappings:
        resolved = mappings[ticker]
        if resolved is None:
            return ticker, True  # delisted
        return resolved, False
    return ticker, False


# ---------------------------------------------------------------------------
# Progress tracking (thread-safe)
# ---------------------------------------------------------------------------
class ProgressTracker:
    """Thread-safe progress tracker that writes status to JSON for the web UI."""

    def __init__(self, total=0):
        self._total = total
        self._processed = 0
        self._lock = Lock()
        self._results = {"ok": 0, "fail": 0}
        self._start_time = time.time()

    def set_total(self, total):
        self._total = total

    def increment(self, ok=True):
        with self._lock:
            self._processed += 1
            if ok:
                self._results["ok"] += 1
            else:
                self._results["fail"] += 1
            self._write_status()

    def _write_status(self):
        elapsed = round(time.time() - self._start_time, 1)
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "status": "running",
                    "progress": self._processed,
                    "total": self._total,
                    "ok": self._results["ok"],
                    "fail": self._results["fail"],
                    "elapsed": elapsed,
                    "timestamp": time.time()
                }, f)
        except Exception:
            pass

    def set_current_ticker(self, ticker):
        try:
            with self._lock:
                status_data = {"status": "running", "current": ticker}
            # Read existing, update, write back
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, "r", encoding="utf-8") as f:
                    status_data = json.load(f)
            status_data["current"] = ticker
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(status_data, f)
        except Exception:
            pass

    @property
    def results(self):
        with self._lock:
            return dict(self._results)

    @staticmethod
    def set_idle(current="Atualização concluída."):
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "status": "idle",
                    "current": current,
                    "timestamp": time.time()
                }, f)
        except Exception:
            pass

    @staticmethod
    def set_error(message):
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "status": "error",
                    "current": message,
                    "timestamp": time.time()
                }, f)
        except Exception:
            pass


def log_failed_ticker(ticker, reason):
    """Append a failed ticker to the persistent log file."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(FAILED_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {ticker} | {reason}\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Single asset ingestion (called by parallel workers)
# ---------------------------------------------------------------------------
def ingest_single_asset(ticker, asset_type, mappings, config, tracker):
    """
    Fetch, analyze, and persist a single asset.
    Returns True on success, False on failure.
    """
    pipeline_cfg = config.get("pipeline", {})
    retry_attempts = pipeline_cfg.get("retry_attempts", 3)
    retry_delay = pipeline_cfg.get("retry_delay_base", 2.0)

    resolved_ticker, delisted = resolve_ticker(ticker, mappings)

    if delisted:
        logger.info(f"  ⏭️  {ticker} → delisted, skipping")
        tracker.increment(ok=True)
        return True

    display_name = f"{ticker}→{resolved_ticker}" if resolved_ticker != ticker else ticker

    for attempt in range(1, retry_attempts + 1):
        try:
            tracker.set_current_ticker(ticker)

            # Fetch from primary source (brapi.dev) with yfinance fallback
            info = fetch_asset_info(resolved_ticker, asset_type, config)

            # Validate we got meaningful data
            if not info or ("longName" not in info and "shortName" not in info):
                msg = "No valid data from any source"
                if attempt < retry_attempts:
                    logger.warning(f"  ⚠️  {display_name}: {msg}, retry {attempt}/{retry_attempts}")
                    time.sleep(retry_delay * (2 ** (attempt - 1)))  # exponential backoff
                    continue
                logger.error(f"  ❌ {display_name}: {msg} after {retry_attempts} attempts")
                log_failed_ticker(ticker, f"{msg} (resolved: {resolved_ticker})")
                tracker.increment(ok=False)
                return False

            # Compute analysis
            if asset_type == "stock":
                analysis = analyzer.analyze_stock(resolved_ticker, info)
            else:  # FII / FIAGRO
                analysis = analyzer.analyze_fii(resolved_ticker, info)

            # Fetch history from primary source (brapi.dev) with yfinance fallback
            analysis["history_json"] = fetch_history(
                resolved_ticker, config,
                period=pipeline_cfg.get("history_years", "10y"),
                max_points=pipeline_cfg.get("history_sample_points", 60)
            )

            # Persist
            if asset_type == "stock":
                database.save_stock(analysis)
            elif asset_type == "fii":
                database.save_fii(analysis)
            else:
                database.save_fiagro(analysis)

            logger.info(f"  ✅ {display_name}")
            tracker.increment(ok=True)
            return True

        except Exception as e:
            if attempt < retry_attempts:
                delay = retry_delay * (2 ** (attempt - 1))
                logger.warning(f"  ⚠️  {display_name}: {e}, retry {attempt}/{retry_attempts} in {delay:.0f}s")
                time.sleep(delay)
            else:
                logger.error(f"  ❌ {display_name}: {e} after {retry_attempts} attempts")
                log_failed_ticker(ticker, f"Exception: {e} (resolved: {resolved_ticker})")
                tracker.increment(ok=False)
                return False

    return False  # should not reach here


# ---------------------------------------------------------------------------
# Batch ingestion (parallel)
# ---------------------------------------------------------------------------
def ingest_batch(tickers, asset_type, mappings, config, tracker):
    """
    Ingest a batch of assets in parallel using ThreadPoolExecutor.
    Returns (ok_count, fail_count).
    """
    if not tickers:
        return 0, 0

    pipeline_cfg = config.get("pipeline", {})
    max_workers = pipeline_cfg.get("max_workers", 5)
    label = {"stock": "Stocks", "fii": "FIIs", "fiagro": "FIAGROs"}.get(asset_type, asset_type)
    logger.info(f"── Ingesting {len(tickers)} {label} (workers={max_workers}) ──")

    ok_count = 0
    fail_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(ingest_single_asset, t, asset_type, mappings, config, tracker): t
            for t in tickers
        }
        for future in as_completed(future_map):
            try:
                if future.result():
                    ok_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                ticker = future_map[future]
                logger.error(f"  💥 {ticker}: unhandled exception {e}")
                log_failed_ticker(ticker, f"Unhandled exception: {e}")
                fail_count += 1
                tracker.increment(ok=False)

    return ok_count, fail_count


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------
def run_full_ingestion(max_age_hours=6, force=False):
    """
    Run the complete ingestion pipeline:
       1. Load config & mappings
       2. Initialize DB
       3. Filter to stale tickers (unless force)
       4. Ingest stocks, FIIs, FIAGROs in parallel batches
       5. Log results

    Parameters:
        max_age_hours: Skip tickers updated within this many hours (default 6)
        force: If True, ignores staleness and fetches ALL tickers
    """
    logger.info("=" * 60)
    logger.info("  INGESTION PIPELINE v2 — INICIANDO")
    logger.info("=" * 60)

    config = load_config()
    mappings = load_ticker_mappings()

    # Initialize database first (creates tables if needed)
    logger.info("Initializing database...")
    database.init_db()

    all_stocks = config.get("stocks", {}).get("tickers", [])
    all_fiis = config.get("fiis", {}).get("tickers", [])
    all_fiagros = config.get("fiagros", {}).get("tickers", [])
    total_all = len(all_stocks) + len(all_fiis) + len(all_fiagros)

    # Filter to stale tickers only (unless force)
    if force or max_age_hours <= 0:
        stocks_tickers, fiis_tickers, fiagros_tickers = all_stocks, all_fiis, all_fiagros
        skipped = 0
        logger.info("  🔄 Forçando refresh de TODOS os tickers")
    else:
        stocks_tickers = database.get_stale_tickers(all_stocks, "stocks", max_age_hours)
        fiis_tickers = database.get_stale_tickers(all_fiis, "fiis", max_age_hours)
        fiagros_tickers = database.get_stale_tickers(all_fiagros, "fiagros", max_age_hours)
        skipped = total_all - (len(stocks_tickers) + len(fiis_tickers) + len(fiagros_tickers))
        logger.info(f"  ⏭️  Pulando {skipped} tickers atualizados há <{max_age_hours}h")
    
    total = len(stocks_tickers) + len(fiis_tickers) + len(fiagros_tickers)

    tracker = ProgressTracker(total=total)
    start_time = time.time()
    started_at = datetime.now().isoformat()

    # Clear failed tickers log from previous run
    if os.path.exists(FAILED_LOG_FILE):
        try:
            os.remove(FAILED_LOG_FILE)
        except Exception:
            pass

    # Run batch ingestion
    stocks_ok, stocks_fail = ingest_batch(stocks_tickers, "stock", mappings, config, tracker)
    fiis_ok, fiis_fail = ingest_batch(fiis_tickers, "fii", mappings, config, tracker)
    fiagros_ok, fiagros_fail = ingest_batch(fiagros_tickers, "fiagro", mappings, config, tracker)

    duration = round(time.time() - start_time, 2)
    total_ok = stocks_ok + fiis_ok + fiagros_ok
    total_fail = stocks_fail + fiis_fail + fiagros_fail

    logger.info("=" * 60)
    logger.info(f"  INGESTION COMPLETE — {duration}s")
    logger.info(f"  ✅ OK: {total_ok}  |  ❌ Failed: {total_fail}  |  Total: {total}")
    logger.info("=" * 60)

    # Record pipeline run in DB
    stats = {
        "stocks_ok": stocks_ok, "stocks_fail": stocks_fail,
        "fiis_ok": fiis_ok, "fiis_fail": fiis_fail,
        "fiagros_ok": fiagros_ok, "fiagros_fail": fiagros_fail,
    }
    try:
        database.log_pipeline_run(
            started_at=started_at,
            finished_at=datetime.now().isoformat(),
            duration=duration,
            stats=stats,
            status="success" if total_fail == 0 else "partial"
        )
    except Exception as e:
        logger.warning(f"Could not log pipeline run: {e}")

    ProgressTracker.set_idle(
        f"OK: {total_ok}, Falhas: {total_fail}, Duração: {duration}s"
    )

    return {"ok": total_ok, "fail": total_fail, "duration": duration}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Support for CLI ticker args: python ingestion.py PETR4.SA HGLG11.SA
        args = sys.argv[1:]
        stocks = [t for t in args if not t.endswith("11.SA")]
        fiis = [t for t in args if t.endswith("11.SA")]

        # Build a minimal config with just these tickers
        config = load_config()
        config["stocks"]["tickers"] = stocks
        config["fiis"]["tickers"] = fiis
        config["fiagros"]["tickers"] = []

        mappings = load_ticker_mappings()
        total = len(stocks) + len(fiis)
        tracker = ProgressTracker(total=total)

        database.init_db()
        ingest_batch(stocks, "stock", mappings, config, tracker)
        ingest_batch(fiis, "fii", mappings, config, tracker)

        ProgressTracker.set_idle()
    else:
        run_full_ingestion()
