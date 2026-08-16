import sqlite3
import json
import os
import sys

sys.path.insert(0, os.path.abspath('src'))

from analyzer import (
    calculate_stock_score_continuous,
    calculate_fii_score_continuous,
    calculate_fiagro_score_continuous,
    _score_dy_stock, _score_pe_stock, _score_pb_stock, _score_roe_stock, _score_graham_stock,
    _score_pb_fii_unified, _score_dy_fii_v2, _score_dividend_consistency_v2,
    safe_float, normalize_dividend_yield
)
import generator
import tesouro_analyzer

db_path = os.path.join('data', 'investments.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 1. Update Stocks
cursor.execute("SELECT ticker, price, pb_ratio, pe_ratio, roe, dividend_yield, graham_price, dy_medio_3y, pe_medio_5y, sector FROM stocks")
stocks = cursor.fetchall()
print(f"[*] Processando {len(stocks)} Ações...")
for s in stocks:
    price = safe_float(s['price'])
    pb = safe_float(s['pb_ratio'])
    pe = safe_float(s['pe_ratio'])
    roe = safe_float(s['roe'])
    dy = safe_float(s['dividend_yield'])
    graham = safe_float(s['graham_price'])
    dy_3y = safe_float(s['dy_medio_3y'])
    pe_5y = safe_float(s['pe_medio_5y'])
    sector = s['sector']
    
    score_v2 = calculate_stock_score_continuous(
        dy_medio_3y=dy_3y or dy,
        pe_medio_5y=pe_5y or pe,
        pb_ratio=pb,
        roe=roe,
        price=price,
        graham_price=graham,
        peg_ratio=None,
        sector=sector
    )
    
    s_dy = _score_dy_stock(dy_3y or dy)
    s_pe = _score_pe_stock(pe_5y or pe)
    s_pb = _score_pb_stock(pb)
    s_roe = _score_roe_stock(roe)
    s_graham = _score_graham_stock(price, graham, peg_ratio=None, sector=sector)
    
    breakdown = [
        {"label": "DY Médio 3a (ou DY)", "score": s_dy, "max": 2.0, "desc": f"{(dy_3y or dy or 0)*100:.2f}%" if (dy_3y or dy) else "N/A", "tip": "Curva Gaussiana com centro em 9,5% (renda sustentável Bazin). Sobe suavemente e protege contra Dividend Traps (>15%)."},
        {"label": "P/L Médio 5a (ou P/L)", "score": s_pe, "max": 2.0, "desc": f"{pe_5y or pe:.2f}x" if (pe_5y or pe) else "N/A", "tip": "Curva Gaussiana com centro em 6,5x (múltiplo histórico B3 Póvoa). Evita picos cíclicos de commodities e transita suavemente para múltiplos altos."},
        {"label": "P/VP (Valor Patrimonial)", "score": s_pb, "max": 2.0, "desc": f"{pb:.2f}" if pb is not None else "N/A", "tip": "Curva Gaussiana com centro em 0,80 (Sweet Spot Deep Value Barsi/Graham). Permite descontos profundos de forma contínua com segurança."},
        {"label": "ROE (Rentabilidade)", "score": s_roe, "max": 2.0, "desc": f"{(roe*100):.2f}%" if roe is not None else "N/A", "tip": "Curva Sigmoide Logística. Inflexão em 12% (custo de capital Damodaran); empresas rentáveis (ROE > 20%) aproximam-se suavemente de 2,0 pts."},
        {"label": "Margem Graham / PEG", "score": s_graham, "max": 2.0, "desc": f"R$ {graham:.2f}" if graham else "N/A", "tip": "Curva Sigmoide Logística da margem de segurança de Graham (Preço Justo vs Cotação)."}
    ]
    
    cursor.execute("UPDATE stocks SET score_v2 = ?, score_breakdown = ? WHERE ticker = ?", (score_v2, json.dumps(breakdown, ensure_ascii=False), s['ticker']))

# 2. Update FIIs
cursor.execute("SELECT ticker, price, pb_ratio, dividend_yield, dividend_rate, dividend_consistency FROM fiis")
fiis = cursor.fetchall()
print(f"[*] Processando {len(fiis)} FIIs...")
for f in fiis:
    price = safe_float(f['price'])
    pb = safe_float(f['pb_ratio'])
    raw_dy = safe_float(f['dividend_yield'])
    raw_rate = safe_float(f['dividend_rate'])
    cons = safe_float(f['dividend_consistency'])
    
    from analyzer import _derive_dividend_fields
    dy, rate = _derive_dividend_fields(raw_dy, raw_rate, price)
    
    score_v2 = calculate_fii_score_continuous(pb, dy, cons)
    s_pb = _score_pb_fii_unified(pb)
    s_dy = _score_dy_fii_v2(dy, is_fiagro=False)
    s_cons = _score_dividend_consistency_v2(cons)
    
    breakdown = [
        {"label": "P/VP (Valor Patrimonial)", "score": s_pb, "max": 3.5, "desc": f"P/VP: {pb:.2f}" if pb is not None else "N/A", "tip": "Curva Gaussiana com centro em 0,95 (Sweet Spot: leve desconto sem risco de ruína). Nota máxima 3,5 pts em 0,95; transição suave para fundos em ágio ou deságio."},
        {"label": "Dividend Yield", "score": s_dy, "max": 4.0, "desc": f"DY: {(dy * 100):.2f}%" if dy is not None else "0.00%", "tip": "Curva Gaussiana com centro ideal em 11,5% (renda sustentável). Sobe suavemente a partir de 6,5% e protege contra Yield Traps (>15,5%)."},
        {"label": "Consistência de Proventos", "score": s_cons, "max": 2.5, "desc": f"{(cons * 100):.2f}%" if cons is not None else "N/D (neutro 1.5)", "tip": "Curva Sigmoide Logística de retenção semestral. Inflexão em 85%; fundos estáveis (≥95%) atingem até 2,5 pts. Sem histórico: 1,5 pts neutro."}
    ]
    
    cursor.execute("UPDATE fiis SET dividend_yield = ?, dividend_rate = ?, score_v2 = ?, score_breakdown = ? WHERE ticker = ?", (dy, rate, score_v2, json.dumps(breakdown, ensure_ascii=False), f['ticker']))

# 3. Update FIAGROs
cursor.execute("SELECT ticker, price, pb_ratio, dividend_yield, dividend_rate, dividend_consistency FROM fiagros")
fiagros = cursor.fetchall()
print(f"[*] Processando {len(fiagros)} FIAGROs...")
for f in fiagros:
    price = safe_float(f['price'])
    pb = safe_float(f['pb_ratio'])
    raw_dy = safe_float(f['dividend_yield'])
    raw_rate = safe_float(f['dividend_rate'])
    cons = safe_float(f['dividend_consistency'])
    
    from analyzer import _derive_dividend_fields
    dy, rate = _derive_dividend_fields(raw_dy, raw_rate, price)
    
    score_v2 = calculate_fiagro_score_continuous(pb, dy, cons)
    s_pb = _score_pb_fii_unified(pb)
    s_dy = _score_dy_fii_v2(dy, is_fiagro=True)
    s_cons = _score_dividend_consistency_v2(cons)
    
    breakdown = [
        {"label": "P/VP (Valor Patrimonial)", "score": s_pb, "max": 3.5, "desc": f"P/VP: {pb:.2f}" if pb is not None else "N/A", "tip": "Curva Gaussiana com centro em 0,95 (Sweet Spot: leve desconto sem risco de ruína). Nota máxima 3,5 pts em 0,95."},
        {"label": "Dividend Yield Agro", "score": s_dy, "max": 4.0, "desc": f"DY: {(dy * 100):.2f}%" if dy is not None else "0.00%", "tip": "Curva Gaussiana com centro em 13,5% (incorporando prêmio de risco agro). Sobe a partir de 8,5% e decai suavemente acima de 17,5%."},
        {"label": "Consistência de Proventos", "score": s_cons, "max": 2.5, "desc": f"{(cons * 100):.2f}%" if cons is not None else "N/D (neutro 1.5)", "tip": "Curva Sigmoide Logística de retenção semestral. Inflexão em 85%; fundos estáveis (≥95%) atingem até 2,5 pts. Sem histórico: 1,5 pts neutro."}
    ]
    
    cursor.execute("UPDATE fiagros SET dividend_yield = ?, dividend_rate = ?, score_v2 = ?, score_breakdown = ? WHERE ticker = ?", (dy, rate, score_v2, json.dumps(breakdown, ensure_ascii=False), f['ticker']))

conn.commit()
conn.close()

# 4. Regenerate Dashboard and data.json
print("[*] Sincronizando data.json e construindo dashboard...")
generator.generate_dashboard()
print("[+] Execução completa com sucesso!")
