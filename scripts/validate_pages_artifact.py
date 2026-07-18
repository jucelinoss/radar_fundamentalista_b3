#!/usr/bin/env python3
"""Valida os dados obrigatórios no artefato estático do GitHub Pages."""
from __future__ import annotations

import json
import sys
from pathlib import Path


REQUIRED_FILES = (
    "index.html",
    "data.json",
    "data/tesouro_history.json",
    "export_ativos.json",
    "export_top_picks.json",
    "export_stocks.csv",
    "export_fiis.csv",
    "export_fiagros.csv",
)


def validate_artifact(site_dir: Path) -> None:
    for relative_path in REQUIRED_FILES:
        path = site_dir / relative_path
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"Required deploy file missing or empty: {relative_path}")

    for relative_path in ("data.json", "data/tesouro_history.json", "export_ativos.json", "export_top_picks.json"):
        with (site_dir / relative_path).open(encoding="utf-8") as file:
            json.load(file)


def main() -> None:
    validate_artifact(Path(sys.argv[1]))
    print("Pages data artifact validated.")


if __name__ == "__main__":
    main()
