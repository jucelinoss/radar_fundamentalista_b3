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

    # Client disconnects mid-request are common on Windows (refresh, cancel, prefetch).
    _CLIENT_GONE = (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)

    def handle(self) -> None:
        try:
            super().handle()
        except self._CLIENT_GONE:
            pass

    def finish(self) -> None:
        try:
            super().finish()
        except self._CLIENT_GONE:
            pass

    def do_GET(self) -> None:
        path: str = self.path.split("?", 1)[0]

        # Browser default favicon probe → project SVG icon
        if path in ("/favicon.ico", "/favicon.ico/"):
            abspath: str = os.path.join(PROJECT_ROOT, "icons", "icon.svg")
            if os.path.exists(abspath):
                with open(abspath, "rb") as f:
                    data: bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_response(404)
            self.end_headers()
            return

        # Serve export files at short paths (e.g. /export_stocks.csv)
        if path in DIRECT_EXPORTS:
            abspath = os.path.join(PROJECT_ROOT, DIRECT_EXPORTS[path])
            if os.path.exists(abspath):
                with open(abspath, "rb") as f:
                    data = f.read()
                mime: str = "application/json" if path.endswith(".json") else "text/csv"
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


class QuietThreadingTCPServer(socketserver.ThreadingTCPServer):
    """Threading server that ignores client disconnect noise on Windows."""

    allow_reuse_address = True

    def handle_error(self, request, client_address) -> None:
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


def run_server(port: int = 8000) -> None:
    """Start the HTTP server."""
    os.chdir(PROJECT_ROOT)

    with QuietThreadingTCPServer(("", port), Handler) as httpd:
        logger.info(f"  🌐 http://localhost:{port}")
        logger.info(f"  📊 http://localhost:{port}/index-v2.html")
        logger.info("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            httpd.server_close()


if __name__ == "__main__":
    port: int = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port=port)
