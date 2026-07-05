#!/usr/bin/env python3
"""
Pipeline Orchestrator — Radar Fundamentalista B3

Unified entry point for data ingestion and dashboard generation.
Supports:
  - One-shot:  python pipeline.py
  - Schedule:  python pipeline.py --schedule        (runs daily at 8AM BRT)
  - Daemon:    python pipeline.py --daemon           (runs immediately, then every 24h)
  - Quick:     python pipeline.py --quick            (skip history, just fundamentals)
  - Report:    python pipeline.py --report           (show last pipeline runs)

Usage:
    python pipeline.py                  # Full ingestion + dashboard generation
    python pipeline.py --ingest-only    # Only fetch data, skip dashboard gen
    python pipeline.py --generate-only  # Only regenerate dashboard from existing DB
    python pipeline.py --schedule       # Register scheduled task (Windows: schtasks, Linux: cron)
    python pipeline.py --daemon         # Run in loop with 24h interval
    python pipeline.py --report         # Show last 10 pipeline execution stats
"""
import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any

# Paths
SRC_DIR: str = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT: str = os.path.dirname(SRC_DIR)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger: logging.Logger = logging.getLogger("pipeline")

# File handler for persistent log
LOG_DIR: str = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
_file_handler: logging.FileHandler = logging.FileHandler(
    os.path.join(LOG_DIR, f"pipeline_{datetime.now().strftime('%Y%m%d')}.log"),
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)-8s %(name)s - %(message)s"
))
logging.getLogger().addHandler(_file_handler)


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------
STATUS_FILE: str = os.path.join(PROJECT_ROOT, "data", "status.json")


def _reset_status_file() -> None:
    """Reset pipeline status to idle (clears stale 'running' states)."""
    try:
        import json as _json
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            _json.dump({"status": "idle", "current": "Iniciando...", "timestamp": time.time()}, f)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Core pipeline steps
# ---------------------------------------------------------------------------
def run_ingestion(max_age_hours: int = 6, force: bool = False) -> dict[str, Any]:
    """Execute the data ingestion pipeline."""
    import ingestion
    logger.info("=" * 60)
    logger.info("  STEP 1/2: DATA INGESTION")
    logger.info("=" * 60)
    result: dict[str, Any] = ingestion.run_full_ingestion(max_age_hours=max_age_hours, force=force)
    logger.info(f"Ingestion result: {result}")
    return result


def run_generator() -> bool:
    """Execute the dashboard generator."""
    import generator
    logger.info("=" * 60)
    logger.info("  STEP 2/2: DASHBOARD GENERATION")
    logger.info("=" * 60)
    generator.generate_dashboard()
    logger.info("Dashboard generation complete.")
    return True


def run_full_pipeline(max_age_hours: int = 6, force: bool = False) -> bool:
    """Run ingestion followed by dashboard generation."""
    _reset_status_file()
    start: float = time.time()
    logger.info("PIPELINE STARTED")
    logger.info(f"    DateTime: {datetime.now().isoformat()}")
    logger.info(f"    Python:   {sys.version.split()[0]}")
    logger.info(f"    Platform: {sys.platform}")

    try:
        result: dict[str, Any] = run_ingestion(max_age_hours=max_age_hours, force=force)
        if result["ok"] > 0 or result["fail"] == 0:
            run_generator()
        else:
            logger.warning("No successful ingestions; skipping dashboard generation")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return False

    duration: float = round(time.time() - start, 2)
    logger.info(f"PIPELINE COMPLETE in {duration}s")
    return True


# ---------------------------------------------------------------------------
# Schedule management
# ---------------------------------------------------------------------------
def setup_windows_schedule() -> None:
    """Register a daily Windows scheduled task (schtasks)."""
    python_exe: str = sys.executable
    pipeline_script: str = os.path.join(SRC_DIR, "pipeline.py")
    task_name: str = "RadarFundamentalistaPipeline"

    cmd: list[str] = [
        "schtasks", "/Create", "/F",
        "/TN", task_name,
        "/TR", f'"{python_exe}" "{pipeline_script}"',
        "/SC", "DAILY",
        "/ST", "08:00",
        "/RL", "HIGHEST",
        "/DELAY", "0001:00",
    ]
    logger.info(f"Registering Windows scheduled task: {task_name}")
    try:
        result: subprocess.CompletedProcess = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            logger.info(f"Scheduled task '{task_name}' created successfully")
            logger.info("   Will run daily at 08:00")
        else:
            logger.error(f"Failed to create task: {result.stderr.strip()}")
    except FileNotFoundError:
        logger.error("schtasks not found - are you on Windows?")
    except Exception as e:
        logger.error(f"Error creating task: {e}")


def setup_linux_schedule() -> None:
    """Register a daily cron job (Linux/macOS)."""
    python_exe: str = sys.executable
    pipeline_script: str = os.path.join(SRC_DIR, "pipeline.py")
    cron_line: str = f"0 8 * * 1-5 {python_exe} {pipeline_script} >> {LOG_DIR}/cron.log 2>&1"

    logger.info("To set up a daily cron job (Linux/macOS), run:")
    logger.info(f'  (crontab -l 2>/dev/null; echo "{cron_line}") | crontab -')
    logger.info("Or copy the line above into your crontab manually.")
    logger.info(f"Logs will be written to: {LOG_DIR}/cron.log")


def setup_schedule() -> None:
    """Auto-detect platform and set up scheduled execution."""
    if sys.platform == "win32":
        setup_windows_schedule()
    else:
        setup_linux_schedule()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def show_report() -> None:
    """Show pipeline execution history from the database."""
    import database
    try:
        logs: list[dict[str, Any]] = database.get_pipeline_history(limit=15)
        if not logs:
            print("No pipeline runs recorded yet.")
            return

        print(f"\n{'='*70}")
        print(f"  PIPELINE EXECUTION HISTORY (last {len(logs)} runs)")
        print(f"{'='*70}")
        print(f"{'#':>3} {'Started':<22} {'Duration':<10} {'Status':<10} "
              f"{'Stocks':<10} {'FIIs':<10} {'FIAGROs':<10}")
        print(f"{'-'*3} {'-'*22} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")

        for i, log in enumerate(logs, 1):
            stocks: str = f"{log['stocks_ok']}/{log['stocks_fail']}"
            fiis: str = f"{log['fiis_ok']}/{log['fiis_fail']}"
            fiagros: str = f"{log['fiagros_ok']}/{log['fiagros_fail']}"
            dur: str = f"{log['duration_seconds']:.1f}s" if log['duration_seconds'] else "N/A"
            started: str = log.get('started_at', '')[:19] if log.get('started_at') else 'N/A'
            status: str = log.get('status', 'N/A')[:10]

            print(f"{i:>3} {started:<22} {dur:<10} {status:<10} "
                  f"{stocks:<10} {fiis:<10} {fiagros:<10}")

        print(f"{'='*70}\n")

        last_ts: str | None = database.get_last_update_timestamp()
        if last_ts:
            print(f"  Last data update: {last_ts[:19]}")
            hours_ago: float = (datetime.now() - datetime.fromisoformat(last_ts)).total_seconds() / 3600
            if hours_ago < 24:
                print(f"  Data is fresh ({hours_ago:.1f}h old)")
            else:
                print(f"  Data is stale ({hours_ago:.1f}h old) - consider running the pipeline")
        print()

    except Exception as e:
        logger.error(f"Could not generate report: {e}")


# ---------------------------------------------------------------------------
# Daemon mode (for containerized / always-on environments)
# ---------------------------------------------------------------------------
def run_daemon(interval_hours: int = 24, max_age_hours: int = 6) -> None:
    """Run the pipeline in a loop, sleeping `interval_hours` between runs."""
    logger.info(f"Daemon mode: running every {interval_hours}h")
    while True:
        run_full_pipeline(max_age_hours=max_age_hours)
        next_run: float = datetime.now().timestamp() + interval_hours * 3600
        next_str: str = datetime.fromtimestamp(next_run).strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Sleeping {interval_hours}h until {next_str}...")
        time.sleep(interval_hours * 3600)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Radar Fundamentalista B3 - Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--ingest-only", action="store_true", help="Only fetch/update data, skip dashboard generation")
    parser.add_argument("--generate-only", action="store_true", help="Only regenerate dashboard from existing database")
    parser.add_argument("--schedule", action="store_true", help="Register a daily scheduled task")
    parser.add_argument("--daemon", action="store_true", help="Run continuously with 24h interval")
    parser.add_argument("--report", action="store_true", help="Show pipeline execution history and exit")
    parser.add_argument("--interval", type=int, default=24, help="Hours between runs in daemon mode (default: 24)")
    parser.add_argument("--export-csv", action="store_true", help="Export all assets to CSV")
    parser.add_argument("--export-json", action="store_true", help="Export all assets to JSON")
    parser.add_argument("--export-top-picks", action="store_true", help="Export top picks for AI/portfolio analysis")
    parser.add_argument("--export-all", action="store_true", help="Export all formats")
    parser.add_argument("--reset-status", action="store_true", help="Reset stuck pipeline status")
    parser.add_argument("--max-age-hours", type=int, default=6,
                        help="Skip tickers updated within this many hours (default: 6). Use 0 to fetch all.")
    parser.add_argument("--force", action="store_true", help="Fetch ALL tickers regardless of staleness")

    args = parser.parse_args()

    if args.reset_status:
        import json as _json
        status_file: str = os.path.join(PROJECT_ROOT, "data", "status.json")
        with open(status_file, "w", encoding="utf-8") as f:
            _json.dump({"status": "idle", "current": "Resetado manualmente", "timestamp": time.time()}, f)
        logger.info("Status resetado para 'idle'. Recarregue o dashboard.")
        return

    if args.report:
        show_report()
    elif args.schedule:
        setup_schedule()
    elif args.daemon:
        run_daemon(interval_hours=args.interval, max_age_hours=args.max_age_hours)
    elif args.ingest_only:
        run_ingestion()
    elif args.generate_only:
        run_generator()
    elif args.export_all or args.export_csv or args.export_json or args.export_top_picks:
        from exporter import export_csv, export_json, export_top_picks
        logger.info("EXPORTANDO DADOS DO RADAR")
        if args.export_all or args.export_csv:
            export_csv()
        if args.export_all or args.export_json:
            export_json()
        if args.export_all or args.export_top_picks:
            export_top_picks()
        logger.info("Export complete")
    else:
        max_age: int = args.max_age_hours
        force: bool = args.force or max_age <= 0
        success: bool = run_full_pipeline(max_age_hours=max_age, force=force)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
