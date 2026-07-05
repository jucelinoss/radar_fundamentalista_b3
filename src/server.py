"""
HTTP server for the B3 Fundamentalist Screener.

Serves the static dashboard and provides API endpoints for
triggering data refresh (POST /api/refresh) and checking status (GET /api/refresh-status).

Usage:
    python src/server.py          # Port 8000
    python src/server.py 3000     # Custom port

Note: For production, use a proper WSGI server (gunicorn, waitress) behind nginx.
"""
import http.server
import json
import logging
import os
import socketserver
import sys
import threading

# Ensure src/ is in path
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

STATUS_FILE = os.path.join(PROJECT_ROOT, "data", "status.json")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("server")


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------
STALE_TIMEOUT = 600  # 10 minutes — if "running" lasts longer, assume crashed

def get_status():
    """Read current pipeline status from status.json."""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Detect stale "running" — if no progress update for > 10 min, reset
            if data.get("status") == "running":
                last_ts = data.get("timestamp", 0)
                if last_ts and (time.time() - last_ts) > STALE_TIMEOUT:
                    logger.warning("Stale 'running' status detected — resetting to idle")
                    data["status"] = "error"
                    data["current"] = "Travado (execução anterior foi interrompida)"
                    with open(STATUS_FILE, "w", encoding="utf-8") as f:
                        json.dump(data, f)
            return data
        except Exception:
            pass
    return {"status": "idle"}


def reset_status():
    """Force status back to idle."""
    data = {"status": "idle", "current": "Pronto", "timestamp": time.time()}
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        logger.info("Status reset to idle")
    except Exception as e:
        logger.error(f"Failed to reset status: {e}")


def run_pipeline_in_background():
    """Run full pipeline (ingestion + generate) in a background thread."""
    try:
        from pipeline import run_full_pipeline
        run_full_pipeline()
    except Exception as e:
        logger.error(f"Background pipeline failed: {e}")
        # Write error status
        try:
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "status": "error",
                    "current": f"Falha: {str(e)}",
                    "timestamp": time.time(),
                }, f)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Export endpoints configuration
# ---------------------------------------------------------------------------
EXPORT_ENDPOINTS = {
    "/api/export/stocks.csv":   {"file": "data/export_stocks.csv",   "mime": "text/csv",        "label": "export_stocks.csv"},
    "/api/export/fiis.csv":     {"file": "data/export_fiis.csv",     "mime": "text/csv",        "label": "export_fiis.csv"},
    "/api/export/fiagros.csv":  {"file": "data/export_fiagros.csv",  "mime": "text/csv",        "label": "export_fiagros.csv"},
    "/api/export/ativos.csv":   {"file": "data/export_stocks.csv",   "mime": "text/csv",        "label": "screener_ativos.csv"},
    "/api/export/ativos.json":  {"file": "data/export_ativos.json",  "mime": "application/json", "label": "screener_ativos.json"},
    "/api/export/top-picks":    {"file": "data/export_top_picks.json", "mime": "application/json", "label": "screener_top_picks.json"},
}


def ensure_export_files():
    """Auto-generate export files if they don't exist."""
    for info in EXPORT_ENDPOINTS.values():
        abspath = os.path.join(PROJECT_ROOT, info["file"])
        if not os.path.exists(abspath):
            try:
                sys.path.insert(0, SRC_DIR)
                from exporter import export_csv, export_json, export_top_picks
                export_csv()
                export_json()
                export_top_picks()
                logger.info("Export files auto-generated")
                return
            except Exception as e:
                logger.debug(f"Could not auto-generate exports: {e}")
                return


# ---------------------------------------------------------------------------
# Custom HTTP handler
# ---------------------------------------------------------------------------
class CustomHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        # ── Export endpoints ─────────────────────────────────────
        if self.path.startswith("/api/export/"):
            info = EXPORT_ENDPOINTS.get(self.path)
            if info is None:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Unknown export endpoint"}).encode("utf-8"))
                return

            abspath = os.path.join(PROJECT_ROOT, info["file"])
            if not os.path.exists(abspath):
                ensure_export_files()

            if not os.path.exists(abspath):
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "Export file not found. Run: python pipeline.py --export-all"
                }).encode("utf-8"))
                return

            fs = os.stat(abspath)
            with open(abspath, "rb") as f:
                data = f.read()

            self.send_response(200)
            self.send_header("Content-Type", info["mime"])
            self.send_header("Content-Length", str(fs.st_size))
            self.send_header("Content-Disposition", f'attachment; filename="{info["label"]}"')
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(data)
            return

        # ── API status endpoints ──────────────────────────────────
        if self.path == "/api/refresh-status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(json.dumps(get_status()).encode("utf-8"))
            return

        if self.path == "/api/reset-status":
            reset_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "idle", "message": "Status resetado com sucesso"}).encode("utf-8"))
            return

        # ── Static files ─────────────────────────────────────────
        super().do_GET()

    def do_POST(self):
        if self.path == "/api/refresh":
            status_data = get_status()
            if status_data.get("status") == "running":
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"error": "Já existe uma atualização em andamento."}).encode("utf-8")
                )
                return

            # Start pipeline in background thread
            t = threading.Thread(target=run_pipeline_in_background, daemon=True)
            t.start()

            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"message": "Atualização iniciada em segundo plano."}).encode("utf-8")
            )
        else:
            self.send_response(404)
            self.end_headers()

    # Suppress default request logging (we use our own)
    def log_message(self, format, *args):
        logger.info(f"{self.client_address[0]} - {format % args}")


# ---------------------------------------------------------------------------
# Server runner
# ---------------------------------------------------------------------------
def run_server(port=8000):
    """Start the HTTP server."""
    os.chdir(PROJECT_ROOT)
    socketserver.ThreadingTCPServer.allow_reuse_address = True

    with socketserver.ThreadingTCPServer(("", port), CustomHandler) as httpd:
        logger.info(f"🌐 Server started at http://localhost:{port}")
        logger.info(f"📊 Dashboard: http://localhost:{port}/dashboard.html")
        logger.info(f"🔄 Refresh:   POST http://localhost:{port}/api/refresh")
        logger.info(f"📈 Status:    GET  http://localhost:{port}/api/refresh-status")
        logger.info("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down server...")
            httpd.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port=port)
