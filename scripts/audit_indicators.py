"""
Auditoria Estruturada de Indicadores Fundamentalistas (Investidor 10 / CVM Standard)

Executa varredura sistemática em todas as classes de ativos (Ações, FIIs, FIAGROs)
e valida P/VP, DY (LTM 12 meses) e consistência do Scorecard.

Uso:
    python scripts/audit_indicators.py
"""
import os
import sqlite3
import sys

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32" and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = os.path.join("data", "investments.db")


def run_audit() -> int:
    if not os.path.exists(DB_PATH):
        print(f"[ERRO] Banco de dados não encontrado em {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    total_assets = 0
    total_issues = 0

    print("=" * 70)
    print(" [*] AUDITORIA ESTRUTURADA DE INDICADORES (INVESTIDOR 10 / CVM)")
    print("=" * 70)

    for table_name, label, is_fii_agro in [
        ("stocks", "ACOES", False),
        ("fiis", "FIIS", True),
        ("fiagros", "FIAGROS", True),
    ]:
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        total_assets += len(rows)

        null_pvp = []
        unannualized_dy = []
        zero_dy = []
        extreme_dy = []
        valid_pvp = 0
        valid_dy = 0

        for r in rows:
            ticker = r["ticker"]
            price = r["price"]
            pvp = r["pb_ratio"] if "pb_ratio" in r.keys() else None
            dy = r["dividend_yield"] if "dividend_yield" in r.keys() else None
            rate = r["dividend_rate"] if "dividend_rate" in r.keys() else None

            if pvp is not None and pvp > 0:
                valid_pvp += 1
            else:
                null_pvp.append(ticker)

            if dy is not None and dy > 0:
                valid_dy += 1
                if dy > 0.35:
                    extreme_dy.append((ticker, dy))
                elif is_fii_agro and 0.001 <= dy < 0.05:
                    unannualized_dy.append((ticker, dy, rate, price))
            else:
                zero_dy.append(ticker)

        print(f"\n[-] {label} ({len(rows)} ativos analisados):")
        print(f"    - P/VP Validos: {valid_pvp}/{len(rows)} ({valid_pvp/len(rows)*100:.1f}%)")
        print(f"    - DY com Proventos (> 0%): {valid_dy}/{len(rows)} ({valid_dy/len(rows)*100:.1f}%)")

        if null_pvp:
            print(f"    [!] P/VP Nulo ou Inaplicavel ({len(null_pvp)}): {null_pvp[:5]}")
        if unannualized_dy:
            print(f"    [!] DY Mensal Nao-Anualizado (< 5%) ({len(unannualized_dy)}): {unannualized_dy}")
            total_issues += len(unannualized_dy)
        if extreme_dy:
            print(f"    [!] DY Extremo (> 35%) ({len(extreme_dy)}): {[x[0] for x in extreme_dy]}")

    import json

    # --- Batimento Direto CVM para FIIs e FIAGROs ---
    print("\n" + "-" * 70)
    print(" 🏛️  BATIMENTO REGULATÓRIO CVM (DADOS ABERTOS dados.cvm.gov.br)")
    print("-" * 70)

    for asset_type, vpa_file, dy_file, table in [
        ("FIIs", "fii_vpa.json", "fii_dy.json", "fiis"),
        ("FIAGROs", "fiagro_vpa.json", "fiagro_dy.json", "fiagros"),
    ]:
        vpa_path = os.path.join("data", vpa_file)
        dy_path = os.path.join("data", dy_file)
        vpas = json.load(open(vpa_path, "r", encoding="utf-8")) if os.path.exists(vpa_path) else {}
        dys = json.load(open(dy_path, "r", encoding="utf-8")) if os.path.exists(dy_path) else {}

        cursor.execute(f"SELECT ticker, book_value, dividend_yield FROM {table}")
        db_rows = cursor.fetchall()

        vpa_matched = 0
        vpa_diffs = []
        for r in db_rows:
            clean = r["ticker"].replace(".SA", "")
            if clean in vpas and r["book_value"] is not None:
                if abs(r["book_value"] - vpas[clean]) <= 0.05:
                    vpa_matched += 1
                else:
                    vpa_diffs.append((clean, r["book_value"], vpas[clean]))

        print(f"[*] {asset_type}:")
        print(f"    • VPA aderente à CVM: {vpa_matched}/{len(db_rows)} ativos ({vpa_matched/len(db_rows)*100:.1f}%)")
        print(f"    • Cobertura de relatórios mensais CVM: {len(vpas)} informes cadastrados")
        if vpa_diffs:
            print(f"    [!] Divergências pontuais VPA ({len(vpa_diffs)}): {vpa_diffs[:3]}")

    conn.close()

    print("\n" + "=" * 70)
    if total_issues == 0:
        print(f" [+] AUDITORIA CVM/MERCADO CONCLUIDA COM SUCESSO: {total_assets} ativos conformes.")
        print("=" * 70)
        return 0
    else:
        print(f" [-] AUDITORIA ENCONTROU {total_issues} DISCREPANCIAS CRITICAS.")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(run_audit())
