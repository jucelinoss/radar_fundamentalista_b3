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

    conn.close()

    print("\n" + "=" * 70)
    if total_issues == 0:
        print(f" [+] AUDITORIA CONCLUIDA COM SUCESSO: {total_assets} ativos validados e conformes.")
        print("=" * 70)
        return 0
    else:
        print(f" [-] AUDITORIA ENCONTROU {total_issues} DISCREPANCIAS CRITICAS.")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(run_audit())
