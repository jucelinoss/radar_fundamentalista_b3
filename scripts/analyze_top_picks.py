"""Detailed analysis of top assets for investment recommendation."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import database as db

stocks = db.get_all_stocks()
fiis = db.get_all_fiis()
fiagros = db.get_all_fiagros()

# Top 3 stocks by score, then by highest DY
top3_stocks = sorted(stocks, key=lambda x: (-x['score'], -(x.get('dividend_yield') or 0)))[:3]

print("=" * 90)
print("  TOP 3 ACOES - ANALISE DETALHADA")
print("=" * 90)
for s in top3_stocks:
    dy = (s.get('dividend_yield') or 0) * 100
    pe = s.get('pe_ratio') or 0
    pb = s.get('pb_ratio') or 0
    roe = (s.get('roe') or 0) * 100
    graham = s.get('graham_price') or 0
    bazin = s.get('bazin_price') or 0
    price = s.get('price') or 0
    print(f"\n  {s['ticker']} - {s.get('name', 'N/A')[:50]}")
    print(f"  {'-'*50}")
    print(f"    Score:        {s['score']}/5")
    print(f"    Preco:        R$ {price:.2f}")
    print(f"    DY:           {dy:.2f}%")
    print(f"    P/L:          {pe:.2f}")
    print(f"    P/VP:         {pb:.2f}")
    print(f"    ROE:          {roe:.2f}%")
    print(f"    Preco Graham: R$ {graham:.2f}")
    print(f"    Preco Bazin:  R$ {bazin:.2f}")
    if graham > 0:
        margem = (1 - price/graham) * 100
        print(f"    Margem Seg.:  {margem:.1f}%")
    if bazin > 0:
        print(f"    Situacao Bazin: {'COMPRA' if price < bazin else 'ACIMA DO PRECO TETO'}")

# Top 3 FIIs
top3_fiis = sorted(fiis, key=lambda x: (-x['score'], -(x.get('dividend_yield') or 0)))[:3]
print("\n\n" + "=" * 90)
print("  TOP 3 FIIS - ANALISE DETALHADA")
print("=" * 90)
for f in top3_fiis:
    dy_pct = (f.get('dividend_yield') or 0) * 100
    pb = f.get('pb_ratio') or 0
    rate = f.get('dividend_rate') or 0
    price = f.get('price') or 0
    monthly = rate if rate and rate < 50 else (rate / 12 if rate else 0)
    print(f"\n  {f['ticker']} - {f.get('name', 'N/A')[:50]}")
    print(f"  {'-'*50}")
    print(f"    Score:        {f['score']}/5")
    print(f"    Preco:        R$ {price:.2f}")
    print(f"    DY:           {dy_pct:.2f}%")
    print(f"    P/VP:         {pb:.2f}")
    print(f"    Dividend/cota: R$ {rate:.4f}")

print(f"\n\nBanco de dados: {len(stocks)} acoes, {len(fiis)} FIIs, {len(fiagros)} FIAGROs")
print(f"Atualizado em: {db.get_last_update_timestamp()}")
