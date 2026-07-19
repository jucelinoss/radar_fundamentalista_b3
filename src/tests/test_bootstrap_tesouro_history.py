import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from bootstrap_tesouro_history import build_history


def test_build_history_uses_published_tesouro_series():
    payload = {
        "tesouro_direto": [
            {"name": "Tesouro IPCA+ 2035", "history": [{"date": "2026-07-13", "buy_yield": 0.068}]},
            {"name": "Sem histórico", "history": []},
        ]
    }

    assert build_history(payload) == {
        "Tesouro IPCA+ 2035": [{"date": "2026-07-13", "buy_yield": 0.068}]
    }
