"""
HTTP server for the Radar Fundamentalista B3.

Serves the static dashboard and export files locally.
For production, use GitHub Pages (the dashboard is fully static).

Usage:
    python src/server.py          # Port 8000
    python src/server.py 3000     # Custom port
"""
import http.server
import logging
import os
import socketserver
import sys


PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger: logging.Logger = logging.getLogger("server")

# ── Alias map: short public URL → relative file path ─────────────
DIRECT_EXPORTS: dict[str, str] = {
    "/export_stocks.csv":    "data/export_stocks.csv",
    "/export_fiis.csv":      "data/export_fiis.csv",
    "/export_fiagros.csv":   "data/export_fiagros.csv",
    "/export_ativos.json":   "data/export_ativos.json",
    "/export_top_picks.json": "data/export_top_picks.json",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves static files with export aliases."""

    def do_GET(self) -> None:
        # Serve export files at short paths (e.g. /export_stocks.csv)
        if self.path in DIRECT_EXPORTS:
            abspath: str = os.path.join(PROJECT_ROOT, DIRECT_EXPORTS[self.path])
            if os.path.exists(abspath):
                with open(abspath, "rb") as f:
                    data: bytes = f.read()
                mime: str = "application/json" if self.path.endswith(".json") else "text/csv"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition",
                                 f'attachment; filename="{os.path.basename(abspath)}"')
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error": "Export file not found"}')
            return

        # Everything else → static file server
        super().do_GET()

    def log_message(self, fmt: str, *args) -> None:
        logger.info(f"{self.client_address[0]} — {fmt % args}")


def run_server(port: int = 8000) -> None:
    """Start the HTTP server."""
    os.chdir(PROJECT_ROOT)
    socketserver.ThreadingTCPServer.allow_reuse_address = True

    with socketserver.ThreadingTCPServer(("", port), Handler) as httpd:
        logger.info(f"  🌐 http://localhost:{port}")
        logger.info(f"  📊 http://localhost:{port}/index.html")
        logger.info("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            httpd.server_close()


if __name__ == "__main__":
    port: int = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port=port)
