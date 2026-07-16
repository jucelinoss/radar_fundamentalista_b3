#!/usr/bin/env python3
"""Reconstrói o cache do Tesouro a partir do data.json publicado."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def build_history(payload: dict) -> dict[str, list[dict]]:
    return {
        bond["name"]: bond.get("history", [])
        for bond in payload.get("tesouro_direto", [])
        if bond.get("name") and bond.get("history")
    }


def main() -> None:
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    payload = json.loads(source.read_text(encoding="utf-8"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_history(payload), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
