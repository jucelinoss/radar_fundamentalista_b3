import os
import json
import sqlite3
import re
import pytest

# Paths
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
DB_PATH = os.path.join(PROJECT_ROOT, "data", "investments.db")
JSON_PATH = os.path.join(PROJECT_ROOT, "data.json")


def test_json_internal_consistency():
    """Verify that Top Picks scores in data.json match the main asset lists."""
    if not os.path.exists(JSON_PATH):
        pytest.skip(f"data.json not found at {JSON_PATH}. Run generator first.")

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Index main list assets by ticker
    json_assets = {}
    for cat in ["stocks", "fiis", "fiagros"]:
        for asset in data.get(cat, []):
            json_assets[asset["ticker"]] = asset

    # Assert matching scores for each top pick
    for cat in ["top_stocks", "top_fiis", "top_fiagros"]:
        for top_item in data.get(cat, []):
            ticker = top_item["ticker"]
            main_item = json_assets.get(ticker)
            assert main_item is not None, f"Top pick {ticker} not found in main asset list."
            assert abs(top_item["score"] - main_item["score"]) < 0.01, (
                f"Score mismatch for {ticker} in data.json: "
                f"Top pick has {top_item['score']}, Main list has {main_item['score']}."
            )


def test_db_vs_json_consistency():
    """Verify that scores and parameters in data.json match database records."""
    if not os.path.exists(DB_PATH):
        pytest.skip(f"Database not found at {DB_PATH}. Run ingestion first.")
    if not os.path.exists(JSON_PATH):
        pytest.skip(f"data.json not found at {JSON_PATH}. Run generator first.")

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Verify Stocks
    cursor.execute("SELECT ticker, score_v2 FROM stocks")
    db_stocks = {row["ticker"].replace(".SA", ""): row for row in cursor.fetchall()}
    for item in data.get("stocks", []):
        ticker = item["ticker"]
        db_row = db_stocks.get(ticker)
        assert db_row is not None, f"Stock {ticker} in data.json is missing from DB."
        assert abs(item["score"] - (db_row["score_v2"] or 0)) < 0.01, (
            f"Score mismatch for Stock {ticker}: "
            f"data.json has {item['score']}, Database has {db_row['score_v2']}."
        )

    # Verify FIIs
    cursor.execute("SELECT ticker, score_v2 FROM fiis")
    db_fiis = {row["ticker"].replace(".SA", ""): row for row in cursor.fetchall()}
    for item in data.get("fiis", []):
        ticker = item["ticker"]
        db_row = db_fiis.get(ticker)
        assert db_row is not None, f"FII {ticker} in data.json is missing from DB."
        assert abs(item["score"] - (db_row["score_v2"] or 0)) < 0.01, (
            f"Score mismatch for FII {ticker}: "
            f"data.json has {item['score']}, Database has {db_row['score_v2']}."
        )

    # Verify FIAGROs
    cursor.execute("SELECT ticker, score_v2 FROM fiagros")
    db_fiagros = {row["ticker"].replace(".SA", ""): row for row in cursor.fetchall()}
    for item in data.get("fiagros", []):
        ticker = item["ticker"]
        db_row = db_fiagros.get(ticker)
        assert db_row is not None, f"FIAGRO {ticker} in data.json is missing from DB."
        assert abs(item["score"] - (db_row["score_v2"] or 0)) < 0.01, (
            f"Score mismatch for FIAGRO {ticker}: "
            f"data.json has {item['score']}, Database has {db_row['score_v2']}."
        )

    conn.close()


def test_html_templates_consistency():
    """Verify frontend HTML files render from pre-calculated data without client-side score recalculation."""
    templates = ["index.html", "index-v2.html"]
    recalcs = ["scoreDYStock", "scorePEStock", "scorePBStock", "scoreROEStock", "scoreGrahamStock", "scorePBFii", "scoreDYFiiV2", "scoreConsistencyV2"]

    for t_file in templates:
        t_path = os.path.join(PROJECT_ROOT, t_file)
        if not os.path.exists(t_path):
            continue

        with open(t_path, "r", encoding="utf-8") as f:
            content = f.read()

        # index-v2 mantém a estrutura no HTML e o comportamento em asset externo.
        # Valide ambos como uma única interface para não perder contratos após
        # uma extração legítima de JS/CSS.
        for script_src in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', content):
            script_path = os.path.join(PROJECT_ROOT, script_src.replace("/", os.sep))
            if os.path.exists(script_path):
                with open(script_path, "r", encoding="utf-8") as script_file:
                    content += "\n" + script_file.read()

        # 1. Assert they don't compute score inside openDetailModal
        modal_match = re.search(r"function openDetailModal\(.*?\)\s*\{(.*?)\n\s*\}", content, re.DOTALL)
        if modal_match:
            modal_body = modal_match.group(1)
            for fn in recalcs:
                assert fn not in modal_body, (
                    f"Recalculation function '{fn}' was found inside openDetailModal of {t_file}. "
                    "Detail modal must load pre-calculated scores instead of computing client-side."
                )

        # 2. Assert they render the breakdown attribute
        assert "data-breakdown=" in content, (
            f"data-breakdown attribute is missing in row templates of {t_file}."
        )


def test_historical_score_consistency():
    """Verify that history_json has been successfully enriched with scores and other metrics."""
    if not os.path.exists(DB_PATH):
        pytest.skip(f"Database not found at {DB_PATH}. Run ingestion first.")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    for table in ["stocks", "fiis", "fiagros"]:
        cursor.execute(f"SELECT ticker, history_json FROM {table}")
        rows = cursor.fetchall()
        for r in rows:
            ticker = r["ticker"]
            hist_str = r["history_json"]
            if not hist_str:
                continue

            try:
                history = json.loads(hist_str)
            except Exception as e:
                pytest.fail(f"Invalid history_json format for {ticker} in {table}: {e}")

            # If there is history, verify structure
            if history:
                assert isinstance(history, list), f"history_json for {ticker} is not a list."
                # We check the last point which should be enriched (if it was ingested recently)
                last_pt = history[-1]
                assert "date" in last_pt, f"Missing date in history point for {ticker}."
                assert "price" in last_pt, f"Missing price in history point for {ticker}."
                
                # Check for new keys (they will exist after we run the ingestion pipeline)
                # We assert their structure if present.
                if "score" in last_pt:
                    score = last_pt["score"]
                    assert isinstance(score, (int, float)), f"Historical score for {ticker} must be a number."
                    assert 0.0 <= score <= 10.0, f"Historical score {score} for {ticker} is out of bounds."
                if "pb" in last_pt:
                    assert last_pt["pb"] is None or isinstance(last_pt["pb"], (int, float)), f"pb for {ticker} must be a number or null."
                if "dy" in last_pt:
                    assert last_pt["dy"] is None or isinstance(last_pt["dy"], (int, float)), f"dy for {ticker} must be a number or null."

    conn.close()
