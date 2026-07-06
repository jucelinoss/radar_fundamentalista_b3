#!/bin/bash
echo "==================================================="
echo "  Radar Fundamentalista B3 - Inicializador"
echo "==================================================="
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "[ERROR] Ambiente virtual .venv nao encontrado!"
    echo "Por favor, crie o ambiente virtual e instale as dependencias primeiro:"
    echo "python3 -m venv .venv"
    echo "source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

echo "Iniciando o servidor local na porta 8000..."
echo "Acesse: http://127.0.0.1:8000/index.html"
echo ""

# Open browser after a short delay
(sleep 2 && (xdg-open http://127.0.0.1:8000/index.html || open http://127.0.0.1:8000/index.html || termux-open http://127.0.0.1:8000/index.html) 2>/dev/null) &

# Run the server using python in .venv
./.venv/bin/python src/server.py
