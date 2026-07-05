"""Query the top assets from the database and print them."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import database as db

stocks = db.get_all_stocks()
fiis = db.get_all_fiis()
fiagros = db.get_all_fiagros()

print("\n" + "=" * 90)
print("  TOP 10 ACOES (por Score)")
print("=" * 90)
print(f"{'Ticker':<10} {'Score':<7} {'DY':<8} {'P/L':<8} {'P/VP':<8} {'Preco':<10} {'Setor'}")
print("-" * 90)
for s in sorted(stocks, key=lambda x: x['score'], reverse=True)[:10]:
    dy = (s.get('dividend_yield') or 0) * 100
    pe = s.get('pe_ratio') or 0
    pb = s.get('pb_ratio') or 0
    price = s.get('price') or 0
    sector = (s.get('sector') or 'N/A')[:20]
    print(f"  {s['ticker']:<8} {s['score']:<7} {dy:>5.2f}%  {pe:>5.2f}  {pb:>5.2f}  R${price:>7.2f}  {sector}")

print("\n" + "=" * 90)
print("  TOP 10 FIIS (por Score)")
print("=" * 90)
print(f"{'Ticker':<10} {'Score':<7} {'DY':<8} {'P/VP':<8} {'Preco':<10}")
print("-" * 90)
for f in sorted(fiis, key=lambda x: x['score'], reverse=True)[:10]:
    dy = (f.get('dividend_yield') or 0) * 100
    pb = f.get('pb_ratio') or 0
    price = f.get('price') or 0
    print(f"  {f['ticker']:<8} {f['score']:<7} {dy:>5.2f}%  {pb:>5.2f}  R${price:>7.2f}")

print("\n" + "=" * 90)
print("  TOP 10 FIAGROS (por Score)")
print("=" * 90)
print(f"{'Ticker':<10} {'Score':<7} {'DY':<8} {'P/VP':<8} {'Preco':<10}")
print("-" * 90)
for a in sorted(fiagros, key=lambda x: x['score'], reverse=True)[:10]:
    dy = (a.get('dividend_yield') or 0) * 100
    pb = a.get('pb_ratio') or 0
    price = a.get('price') or 0
    print(f"  {a['ticker']:<8} {a['score']:<7} {dy:>5.2f}%  {pb:>5.2f}  R${price:>7.2f}")

print(f"\nTotal no banco: {len(stocks)} stocks, {len(fiis)} FIIs, {len(fiagros)} FIAGROs")
