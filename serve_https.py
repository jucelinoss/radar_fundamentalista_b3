"""
Quick HTTPS server for testing PWA on mobile.
Generates warning about self-signed cert — proceed anyway.
"""
import http.server
import logging
import os
import ssl
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8443

# Reuse the same handler from server.py
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))
from server import Handler

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("https-server")

os.chdir(PROJECT_ROOT)
httpd = http.server.HTTPServer(("0.0.0.0", PORT), Handler)

# Wrap with SSL
cert_file = os.path.join(PROJECT_ROOT, "server.crt")
key_file = os.path.join(PROJECT_ROOT, "server.key")

if os.path.exists(cert_file) and os.path.exists(key_file):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    logger.info(f"HTTPS ativo (certificado self-signed)")
else:
    logger.warning("Certificados SSL nao encontrados — rodando HTTP")

logger.info(f"  https://192.168.15.64:{PORT}/dashboard.html")
logger.info("  Aceite o aviso de seguranca no navegador")
logger.info("  Ctrl+C para parar")

try:
    httpd.serve_forever()
except KeyboardInterrupt:
    httpd.server_close()
    logger.info("Parou")
