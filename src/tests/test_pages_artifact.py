import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from validate_pages_artifact import validate_artifact


def test_validate_artifact_accepts_complete_data_contract(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "data.json").write_text('{"tesouro_direto": []}', encoding="utf-8")
    (tmp_path / "data" / "tesouro_history.json").write_text("{}", encoding="utf-8")
    for filename in ["export_ativos.json", "export_top_picks.json", "export_stocks.csv", "export_fiis.csv", "export_fiagros.csv"]:
        (tmp_path / filename).write_text("[]" if filename.endswith("json") else "header\n", encoding="utf-8")

    validate_artifact(tmp_path)


def test_validate_artifact_rejects_missing_tesouro_history(tmp_path):
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "data.json").write_text('{"tesouro_direto": []}', encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="tesouro_history"):
        validate_artifact(tmp_path)
