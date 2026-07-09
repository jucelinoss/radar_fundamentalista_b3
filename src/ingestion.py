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
from typing import Any

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
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingestion")


# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------
def load_config() -> dict[str, Any]:
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


def load_ticker_mappings() -> dict[str, Any]:
    """Load ticker rename/delist mappings from data/ticker_mappings.json."""
    if os.path.exists(MAPPINGS_FILE):
        try:
            with open(MAPPINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading ticker mappings: {e}")
    return {}


def resolve_ticker(ticker: str, mappings: dict[str, Any]) -> tuple[str, bool]:
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

    def __init__(self, total: int = 0) -> None:
        self._total: int = total
        self._processed: int = 0
        self._lock: Lock = Lock()
        self._results: dict[str, int] = {"ok": 0, "fail": 0}
        self._start_time: float = time.time()

    def set_total(self, total: int) -> None:
        self._total = total

    def increment(self, ok: bool = True) -> None:
        with self._lock:
            self._processed += 1
            if ok:
                self._results["ok"] += 1
            else:
                self._results["fail"] += 1
            self._write_status()

    def _write_status(self) -> None:
        elapsed: float = round(time.time() - self._start_time, 1)
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

    def set_current_ticker(self, ticker: str) -> None:
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
    def results(self) -> dict[str, int]:
        with self._lock:
            return dict(self._results)

    @staticmethod
    def set_idle(current: str = "Atualização concluída.") -> None:
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
    def set_error(message: str) -> None:
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "status": "error",
                    "current": message,
                    "timestamp": time.time()
                }, f)
        except Exception:
            pass


def log_failed_ticker(ticker: str, reason: str) -> None:
    """Append a failed ticker to the persistent log file."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(FAILED_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {ticker} | {reason}\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers for single asset ingestion
# ---------------------------------------------------------------------------

def _persist_asset(analysis: dict[str, Any], asset_type: str) -> None:
    """Save analysis result to the correct table based on asset type."""
    if asset_type == "stock":
        database.save_stock(analysis)
    elif asset_type == "fii":
        database.save_fii(analysis)
    else:
        database.save_fiagro(analysis)


def _fetch_with_retry(ticker: str, resolved_ticker: str, asset_type: str,
                      config: dict[str, Any], retry_attempts: int,
                      retry_delay: float) -> dict[str, Any] | None:
    """
    Fetch asset info with exponential backoff retry.
    Returns the analysis dict on success, None on failure.
    """
    pipeline_cfg = config.get("pipeline", {})
    import yfinance as yf

    for attempt in range(1, retry_attempts + 1):
        info = fetch_asset_info(resolved_ticker, asset_type, config)

        if info and ("longName" in info or "shortName" in info):
            # Attach yfinance Ticker for historical data (v2.5 continuous score)
            try:
                yf_ticker = yf.Ticker(resolved_ticker)
                # Quick sanity check that it resolved
                _ = yf_ticker.info.get('longName') or yf_ticker.info.get('shortName', '')
                info['_yf_ticker'] = yf_ticker
            except Exception:
                info['_yf_ticker'] = None

            if asset_type == "stock":
                analysis = analyzer.analyze_stock(resolved_ticker, info)
            elif asset_type == "fiagro":
                analysis = analyzer.analyze_fiagro(resolved_ticker, info)
            else:
                analysis = analyzer.analyze_fii(resolved_ticker, info)
            analysis["history_json"] = fetch_history(
                resolved_ticker, config,
                period=pipeline_cfg.get("history_years", "10y"),
                max_points=pipeline_cfg.get("history_sample_points", 60),
            )
            return analysis

        msg = "No valid data from any source"
        if attempt < retry_attempts:
            logger.warning(f"  ⚠️  {ticker}: {msg}, retry {attempt}/{retry_attempts}")
            time.sleep(retry_delay * (2 ** (attempt - 1)))
        else:
            logger.error(f"  ❌ {ticker}: {msg} after {retry_attempts} attempts")
    return None


# ---------------------------------------------------------------------------
# Single asset ingestion (called by parallel workers)
# ---------------------------------------------------------------------------
def ingest_single_asset(ticker: str, asset_type: str, mappings: dict[str, Any], config: dict[str, Any], tracker: ProgressTracker) -> bool:
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

    tracker.set_current_ticker(ticker)

    try:
        analysis = _fetch_with_retry(ticker, resolved_ticker, asset_type, config, retry_attempts, retry_delay)
        if analysis is None:
            log_failed_ticker(ticker, f"No data (resolved: {resolved_ticker})")
            tracker.increment(ok=False)
            return False

        _persist_asset(analysis, asset_type)
        logger.info(f"  ✅ {display_name}")
        tracker.increment(ok=True)
        return True

    except Exception as e:
        logger.error(f"  ❌ {display_name}: {e} after {retry_attempts} attempts")
        log_failed_ticker(ticker, f"Exception: {e} (resolved: {resolved_ticker})")
        tracker.increment(ok=False)
        return False


# ---------------------------------------------------------------------------
# Batch ingestion (parallel)
# ---------------------------------------------------------------------------
def ingest_batch(tickers: list[str], asset_type: str, mappings: dict[str, Any], config: dict[str, Any], tracker: ProgressTracker) -> tuple[int, int]:
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
# Orchestration helpers
# ---------------------------------------------------------------------------

def _prepare_ticker_lists(config: dict[str, Any], max_age_hours: int, force: bool) -> tuple[list[str], list[str], list[str], int]:
    """Load all tickers and filter to stale ones (unless force). Returns (stocks, fiis, fiagros, skipped)."""
    all_stocks = config.get("stocks", {}).get("tickers", [])
    all_fiis = config.get("fiis", {}).get("tickers", [])
    all_fiagros = config.get("fiagros", {}).get("tickers", [])
    total_all = len(all_stocks) + len(all_fiis) + len(all_fiagros)

    if force or max_age_hours <= 0:
        logger.info("  🔄 Forçando refresh de TODOS os tickers")
        return all_stocks, all_fiis, all_fiagros, 0

    stocks_tickers = database.get_stale_tickers(all_stocks, "stocks", max_age_hours)
    fiis_tickers = database.get_stale_tickers(all_fiis, "fiis", max_age_hours)
    fiagros_tickers = database.get_stale_tickers(all_fiagros, "fiagros", max_age_hours)
    skipped = total_all - (len(stocks_tickers) + len(fiis_tickers) + len(fiagros_tickers))
    logger.info(f"  ⏭️  Pulando {skipped} tickers atualizados há <{max_age_hours}h")
    return stocks_tickers, fiis_tickers, fiagros_tickers, skipped


def _log_pipeline_summary(total_ok: int, total_fail: int, total: int, duration: float) -> None:
    """Log the final pipeline summary."""
    logger.info("=" * 60)
    logger.info(f"  INGESTION COMPLETE — {duration}s")
    logger.info(f"  ✅ OK: {total_ok}  |  ❌ Failed: {total_fail}  |  Total: {total}")
    logger.info("=" * 60)


def _record_pipeline_run(started_at: str, duration: float, stats: dict[str, int], total_fail: int) -> None:
    """Record pipeline execution to DB and set idle status."""
    try:
        database.log_pipeline_run(
            started_at=started_at,
            finished_at=datetime.now().isoformat(),
            duration=duration,
            stats=stats,
            status="success" if total_fail == 0 else "partial",
        )
    except Exception as e:
        logger.warning(f"Could not log pipeline run: {e}")

    total_ok = stats.get("stocks_ok", 0) + stats.get("fiis_ok", 0) + stats.get("fiagros_ok", 0)
    ProgressTracker.set_idle(f"OK: {total_ok}, Falhas: {total_fail}, Duração: {duration}s")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------
def run_full_ingestion(max_age_hours: int = 6, force: bool = False) -> dict[str, Any]:
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

    logger.info("Initializing database...")
    database.init_db()

    stocks_tickers, fiis_tickers, fiagros_tickers, _ = _prepare_ticker_lists(
        config, max_age_hours, force
    )
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

    _log_pipeline_summary(total_ok, total_fail, total, duration)

    stats = {
        "stocks_ok": stocks_ok, "stocks_fail": stocks_fail,
        "fiis_ok": fiis_ok, "fiis_fail": fiis_fail,
        "fiagros_ok": fiagros_ok, "fiagros_fail": fiagros_fail,
    }
    _record_pipeline_run(started_at, duration, stats, total_fail)

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
