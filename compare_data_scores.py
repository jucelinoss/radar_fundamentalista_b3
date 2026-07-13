import json
import os
import re
from bs4 import BeautifulSoup

def run_comparison():
    print("=" * 60)
    print("  Radar Fundamentalista B3 - Data Consistency Check")
    print("=" * 60)
    
    # 1. Load data.json
    data_json_path = "data.json"
    if not os.path.exists(data_json_path):
        print(f"[-] ERROR: {data_json_path} not found. Run generator first.")
        return
        
    with open(data_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    print(f"[+] Loaded {data_json_path}")
    print(f"    Stocks in JSON: {len(data.get('stocks', []))}")
    print(f"    FIIs in JSON: {len(data.get('fiis', []))}")
    print(f"    FIAGROs in JSON: {len(data.get('fiagros', []))}")
    print(f"    Top Stocks: {len(data.get('top_stocks', []))}")
    print(f"    Top FIIs: {len(data.get('top_fiis', []))}")
    print(f"    Top FIAGROs: {len(data.get('top_fiagros', []))}")
    
    # Map from ticker to asset info in JSON
    json_assets = {}
    for cat in ["stocks", "fiis", "fiagros"]:
        for asset in data.get(cat, []):
            json_assets[asset["ticker"]] = asset
            
    # Check top picks consistency with main lists in JSON
    print("\n--- JSON Internal Consistency Check (Top Picks vs Main List) ---")
    mismatches_json = 0
    for cat in ["top_stocks", "top_fiis", "top_fiagros"]:
        for item in data.get(cat, []):
            ticker = item["ticker"]
            list_asset = json_assets.get(ticker)
            if not list_asset:
                print(f"[-] WARNING: Top pick {ticker} not found in main lists.")
                mismatches_json += 1
                continue
            
            if item["score"] != list_asset["score"]:
                print(f"[-] MISMATCH: Top pick {ticker} has score {item['score']} but main list has {list_asset['score']}")
                mismatches_json += 1
                
    if mismatches_json == 0:
        print("[+] JSON is internally consistent (Top Picks scores match main list scores).")
    else:
        print(f"[-] Found {mismatches_json} internal mismatches in data.json.")
        
    # 2. Compare with SQLite Database
    print("\n--- Database vs data.json Consistency Check ---")
    db_path = os.path.join("data", "investments.db")
    if not os.path.exists(db_path):
        print(f"[-] ERROR: Database not found at {db_path}")
        return
        
    db_mismatches = 0
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Stocks DB check
        cursor.execute("SELECT ticker, score_v2, score_breakdown FROM stocks")
        db_stocks = {r["ticker"].replace(".SA", ""): r for r in cursor.fetchall()}
        for item in data.get("stocks", []):
            ticker = item["ticker"]
            db_row = db_stocks.get(ticker)
            if not db_row:
                print(f"[-] DB MISMATCH: Stock {ticker} is in data.json but not in DB.")
                db_mismatches += 1
                continue
            if abs(item["score"] - (db_row["score_v2"] or 0)) > 0.01:
                print(f"[-] DB MISMATCH: Stock {ticker} has score {item['score']} in JSON but {db_row['score_v2']} in DB.")
                db_mismatches += 1
                
        # FIIs DB check
        cursor.execute("SELECT ticker, score_v2, score_breakdown FROM fiis")
        db_fiis = {r["ticker"].replace(".SA", ""): r for r in cursor.fetchall()}
        for item in data.get("fiis", []):
            ticker = item["ticker"]
            db_row = db_fiis.get(ticker)
            if not db_row:
                print(f"[-] DB MISMATCH: FII {ticker} is in data.json but not in DB.")
                db_mismatches += 1
                continue
            if abs(item["score"] - (db_row["score_v2"] or 0)) > 0.01:
                print(f"[-] DB MISMATCH: FII {ticker} has score {item['score']} in JSON but {db_row['score_v2']} in DB.")
                db_mismatches += 1
                
        # FIAGROs DB check
        cursor.execute("SELECT ticker, score_v2, score_breakdown FROM fiagros")
        db_fiagros = {r["ticker"].replace(".SA", ""): r for r in cursor.fetchall()}
        for item in data.get("fiagros", []):
            ticker = item["ticker"]
            db_row = db_fiagros.get(ticker)
            if not db_row:
                print(f"[-] DB MISMATCH: FIAGRO {ticker} is in data.json but not in DB.")
                db_mismatches += 1
                continue
            if abs(item["score"] - (db_row["score_v2"] or 0)) > 0.01:
                print(f"[-] DB MISMATCH: FIAGRO {ticker} has score {item['score']} in JSON but {db_row['score_v2']} in DB.")
                db_mismatches += 1
                
        conn.close()
    except Exception as e:
        print(f"[-] Database check failed: {e}")
        db_mismatches += 1
        
    if db_mismatches == 0:
        print("[+] Database is fully consistent with data.json.")
    else:
        print(f"[-] Found {db_mismatches} mismatches between database and data.json.")

    # 3. Check index.html and index-v2.html files
    # We will parse the files to find the static markup or see if there's any discrepancy
    for html_file in ["index.html", "index-v2.html"]:
        if not os.path.exists(html_file):
            print(f"[-] {html_file} not found.")
            continue
            
        print(f"\n--- Checking {html_file} templates ---")
        with open(html_file, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Let's search if there are any hardcoded/template table rows, or check the JS rendering logic.
        # Let's inspect the javascript code to ensure it's not overriding the values.
        # Specifically, check if there is any client-side score computation functions being called in openDetailModal.
        has_client_side_calc = False
        recalcs = ["scoreDYStock", "scorePEStock", "scorePBStock", "scoreROEStock", "scoreGrahamStock", "scorePBFii", "scoreDYFiiV2", "scoreConsistencyV2"]
        for fn in recalcs:
            if re.search(rf"\b{fn}\(", content):
                # Check if it's called inside openDetailModal
                # Let's locate the openDetailModal definition block
                modal_match = re.search(r"function openDetailModal\(.*?\)\s*\{(.*?)\n\s*\}", content, re.DOTALL)
                if modal_match:
                    modal_body = modal_match.group(1)
                    if fn in modal_body:
                        print(f"[-] WARNING: {html_file} calls client-side calculator '{fn}' inside openDetailModal.")
                        has_client_side_calc = True
                        
        if not has_client_side_calc:
            print(f"[+] {html_file} detail modal does not perform client-side score recalculations.")
            
        # Check if the map loop renders the breakdown attributes correctly
        has_breakdown_attr = "data-breakdown=" in content
        if has_breakdown_attr:
            print(f"[+] {html_file} table rows render data-breakdown attribute.")
        else:
            print(f"[-] WARNING: {html_file} table rows DO NOT render data-breakdown attribute.")

if __name__ == "__main__":
    # Import sqlite3 here if not imported globally
    import sqlite3
    run_comparison()
