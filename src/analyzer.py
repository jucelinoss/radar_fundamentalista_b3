import math
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Graham's fair price multiplier: 22.5 = 15 (max P/E) * 1.5 (max P/B)
GRAHAM_MULTIPLIER = 22.5
# Bazin's target annual dividend yield (6%)
BAZIN_TARGET_DY = 0.06
# Dividend yield thresholds for scoring
DY_THRESHOLD = 0.06        # Minimum DY for stocks (Bazin)
DY_FII_GOOD = 0.08         # Good DY for FIIs
DY_FII_EXCELLENT = 0.10    # Excellent DY for FIIs
DY_FIAGRO_GOOD = 0.10      # Minimum DY for FIAGROs (elevated risk premium)
DY_FIAGRO_EXCELLENT = 0.12 # Excellent DY for FIAGROs
# Valuation thresholds
PE_MAX_GRAHAM = 15          # Max P/E for Graham value
PB_MAX_GRAHAM = 1.5         # Max P/B for Graham value
ROE_MIN = 0.10              # Min ROE for profitability
PB_FII_IDEAL_LOW = 0.70     # P/VP >= 0.70 = blindagem contra value traps
PB_FII_IDEAL_HIGH = 1.05    # P/VP <= 1.05 = valor justo (ideal)

PB_FII_MAX = 1.15           # Max P/VP for FIIs
PEG_MAX = 1.0               # Max PEG ratio for growth/value balance
# Normalization
DY_PERCENTAGE_THRESHOLD = 1.0  # Values > 1 are treated as percentages
DY_PERCENTAGE_DIVISOR = 100.0
# Rounding
ROUND_DECIMALS = 2
DY_DECIMALS = 6


def safe_float(value: Any) -> float | None:
    """Convert value to float safely, handling None, strings like 'Infinity', 'NaN', etc.
    
    yfinance sometimes returns problematic values:
      - 'Infinity' (string) for trailingPE when EPS is 0 or negative
      - None when data is unavailable
      - Various numeric types (int, float, numpy types)
    
    Returns None if the value cannot be converted to a finite number.
    """
    if value is None:
        return None
    try:
        f = float(value)
        if math.isinf(f) or math.isnan(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def calculate_graham_price(eps: float | None, book_value: float | None) -> float | None:
    """
    Calculates Graham's Fair Price: sqrt(22.5 * LPA * VPA)
    LPA (EPS) = Earnings Per Share
    VPA (Book Value) = Book Value Per Share
    """
    if eps is None or book_value is None:
        return None
    if eps <= 0 or book_value <= 0:
        return 0.0  # Graham's formula is not applicable for loss-making or net-negative companies
    
    try:
        return round(math.sqrt(GRAHAM_MULTIPLIER * eps * book_value), ROUND_DECIMALS)
    except ValueError:
        return 0.0


def calculate_bazin_price(dividend_rate: float | None) -> float:
    """
    Calculates Bazin's Ceiling Price (Preço Teto de Bazin): Dividend Rate / 0.06
    """
    if dividend_rate is None or dividend_rate <= 0:
        return 0.0
    return round(dividend_rate / BAZIN_TARGET_DY, ROUND_DECIMALS)


def normalize_dividend_yield(dy: float | None) -> float:
    """
    Normalizes dividend yield from yfinance.
    Sometimes it is returned as a percentage (e.g. 9.48) and sometimes as a decimal (e.g. 0.0948).
    We convert it to a standard decimal representation.
    """
    if dy is None:
        return 0.0
    # If it is greater than 1, it's almost certainly a percentage (e.g. 6.5 instead of 0.065)
    if dy > DY_PERCENTAGE_THRESHOLD:
        return round(dy / DY_PERCENTAGE_DIVISOR, DY_DECIMALS)
    return round(dy, DY_DECIMALS)


def get_true_yield(ticker_info: dict[str, Any], yf_ticker: Any | None = None, price: float | None = None) -> float:
    """
    Extrai o dividend yield real usando histórico de 365 dias como fonte primária,
    com fallback para o campo estático dividendYield do Yahoo Finance.
    
    Fluxo:
      1. Se yf_ticker e price estão disponíveis, tenta usar ticker.actions
         para somar dividendos dos últimos 365 dias e dividir pelo preço.
      2. Fallback: retorna normalize_dividend_yield(ticker_info.get('dividendYield')).
    """
    if yf_ticker is not None and price is not None and price > 0:
        try:
            history = yf_ticker.actions
            if history is not None and not history.empty and 'Dividends' in history.columns:
                from pandas import DateOffset
                from datetime import datetime
                cutoff = datetime.now() - DateOffset(days=365)
                recent = history[history.index >= cutoff]
                total_divs = recent['Dividends'].sum()
                if total_divs > 0:
                    return round(total_divs / price, DY_DECIMALS)
        except Exception:
            pass
    return normalize_dividend_yield(ticker_info.get('dividendYield'))

def calculate_stock_score(price: Any, eps: Any, book_value: Any, pe_ratio: Any, pb_ratio: Any, dividend_yield: Any, roe: Any, graham_price: Any, bazin_price: Any, peg_ratio: Any = None, sector: str | None = None) -> int:
    """
    Calculates a custom 0-5 scorecard ranking for stocks based on fundamentalist criteria.
    All numeric values are sanitized via safe_float to handle yfinance quirks
    (e.g. 'Infinity' strings, NaN, None).
    """
    score = 0
    
    # Sanitize all inputs
    price = safe_float(price)
    pe_ratio = safe_float(pe_ratio)
    pb_ratio = safe_float(pb_ratio)
    roe = safe_float(roe)
    graham_price = safe_float(graham_price)
    peg_ratio = safe_float(peg_ratio)
    
    # Normalize yield to make sure threshold check is correct
    dy_norm = normalize_dividend_yield(dividend_yield)
    
    # 1. Dividend Yield check (Bazin threshold: >= 6%)
    if dy_norm >= DY_THRESHOLD:
        score += 1
        
    # 2. P/L (P/E Ratio) check (Graham threshold: 0 < P/L <= 15)
    if pe_ratio is not None and 0 < pe_ratio <= PE_MAX_GRAHAM:
        score += 1
        
    # 3. P/VP (P/B Ratio) check (Graham threshold: 0 < P/VP <= 1.5)
    if pb_ratio is not None and 0 < pb_ratio <= PB_MAX_GRAHAM:
        score += 1
        
    # 4. ROE check (Healthy profitability: > 10%)
    if roe is not None and roe >= ROE_MIN:
        score += 1
        
    # 5. Margin of Safety check
    #    - Setores tradicionais: Preço < Preço Justo Graham
    #    - Tecnologia / serviços leves: PEG Ratio <= 1.0
    tech_sectors = {'Technology', 'Communication Services'}
    if sector in tech_sectors and peg_ratio is not None and 0 < peg_ratio <= PEG_MAX:
        score += 1
    elif price is not None and graham_price is not None and price < graham_price:
        score += 1
        
    return score

SECTOR_MAP = {
    'Financial Services': 'Serviços Financeiros',
    'Utilities': 'Utilidade Pública',
    'Energy': 'Energia',
    'Basic Materials': 'Materiais Básicos',
    'Consumer Defensive': 'Consumo Defensivo',
    'Consumer Cyclical': 'Consumo Cíclico',
    'Industrials': 'Bens Industriais',
    'Healthcare': 'Saúde',
    'Technology': 'Tecnologia',
    'Communication Services': 'Telecomunicações',
    'Real Estate': 'Imobiliário'
}

def _parse_price(info: dict[str, Any]) -> float | None:
    """Extract and sanitize the current price from yfinance info."""
    price = info.get('currentPrice')
    if price is None:
        price = info.get('regularMarketPrice')
    return safe_float(price)


def _derive_dividend_fields(dividend_yield: Any, dividend_rate: Any, price: float | None, last_div: Any = None) -> tuple[float, float | None]:
    """
    Derive dividend_yield and dividend_rate when one is missing.
    
    yfinance often provides one but not the other; this fills the gap.
    For FIIs/FIAGROs, lastDividendValue may also be available.
    Returns (normalized_yield, rate).
    """
    dy = normalize_dividend_yield(dividend_yield)
    rate = safe_float(dividend_rate)
    
    # Fallback to lastDividendValue for FIIs/FIAGROs
    if last_div is not None:
        last_div = safe_float(last_div)
        if (not dy or dy == 0.0) and (not rate or rate == 0.0) and last_div and price:
            rate = last_div * 12
            dy = normalize_dividend_yield(rate / price)
            if dy != rate / price:
                rate = round(dy * price, 4)
    
    if (not dy or dy == 0.0) and rate and price:
        dy = normalize_dividend_yield(rate / price)
    if not rate and dy and price:
        rate = dy * price
        
    # Re-align rate if it is 100x larger than dy * price (cents vs. BRL mismatch)
    if dy and rate and price:
        expected_annual = dy * price
        if abs(rate - expected_annual * 100.0) < (expected_annual * 10.0) and abs(rate - expected_annual) > 1.0:
            rate = round(expected_annual, 4)
    
    return dy, rate


def analyze_stock(ticker: str, info: dict[str, Any]) -> dict[str, Any]:
    """
    Parses yfinance raw stock info and calculates fundamentalist metrics.
    """
    price = _parse_price(info)
    
    eps = safe_float(info.get('trailingEps'))
    book_value = safe_float(info.get('bookValue'))
    pe_ratio = safe_float(info.get('trailingPE'))
    pb_ratio = safe_float(info.get('priceToBook'))
    
    dy, dividend_rate = _derive_dividend_fields(
        info.get('dividendYield'),
        info.get('dividendRate'),
        price
    )
    
    roe = safe_float(info.get('returnOnEquity'))
    name = info.get('longName') or info.get('shortName', ticker)
    
    # Translate sector
    raw_sector = info.get('sector', 'Outros')
    sector = SECTOR_MAP.get(raw_sector, raw_sector)
    
    graham_price = calculate_graham_price(eps, book_value)
    bazin_price = calculate_bazin_price(dividend_rate)
    peg_ratio = safe_float(info.get('pegRatio'))
    
    score = calculate_stock_score(
        price, eps, book_value, pe_ratio, pb_ratio, dy, roe, graham_price, bazin_price,
        peg_ratio=peg_ratio, sector=raw_sector
    )
    
    return {
        'ticker': ticker,
        'name': name,
        'sector': sector,
        'price': price,
        'pe_ratio': pe_ratio,
        'pb_ratio': pb_ratio,
        'dividend_yield': dy,
        'roe': roe,
        'eps': eps,
        'book_value': book_value,
        'graham_price': graham_price,
        'bazin_price': bazin_price,
        'score': score
    }


def calculate_fii_score(price: Any, pb_ratio: Any, dividend_yield: Any, dividend_rate: Any,
                        historical_dividends_365d: float | None = None) -> int:
    """
    Calculates a 0-5 scorecard ranking for FIIs based on key REIT metrics.
    
    Critérios (hierárquicos — C2 é a base, C1 é bônus dentro da base):
      1. P/VP entre 0.70 e 1.05 (faixa ideal — bônus)
      2. P/VP ≤ 1.15 (limite geral — base)
      3. DY >= 8% (base — mínimo)
      4. DY >= 10% (bônus — excelente)
      5. Distribuição histórica 12m > 0
    """
    score = 0
    
    pb_ratio = safe_float(pb_ratio)
    dividend_rate = safe_float(dividend_rate)
    
    # 2. P/VP ≤ 1.15 (base — ativo não está excessivamente caro)
    if pb_ratio is not None and pb_ratio <= PB_FII_MAX:
        score += 1
        
    # 1. P/VP entre 0.70 e 1.05 (bônus aninhado na base — faixa ideal)
    if pb_ratio is not None and PB_FII_IDEAL_LOW <= pb_ratio <= PB_FII_IDEAL_HIGH:
        score += 1
        
    # 3. DY >= 8% (base — mínimo)
    dy_norm = normalize_dividend_yield(dividend_yield)
    if dy_norm >= DY_FII_GOOD:
        score += 1
        
    # 4. DY >= 10% (bônus — excelente, aninhado na base)
    if dy_norm >= DY_FII_EXCELLENT:
        score += 1
        
    # 5. Distribuição acumulada nos últimos 12 meses > 0
    if historical_dividends_365d is not None and historical_dividends_365d > 0:
        score += 1
    elif dividend_rate is not None and dividend_rate > 0:
        score += 1
        
    return score


def calculate_fiagro_score(price: Any, pb_ratio: Any, dividend_yield: Any, dividend_rate: Any,
                            historical_dividends_365d: float | None = None) -> int:
    """
    Calculates a 0-5 scorecard ranking for FIAGROs.
    
    Critérios (hierárquicos — C2 é a base, C1 é bônus dentro da base):
    DY elevado vs FIIs devido ao maior risco de crédito agropecuário:
      1. P/VP entre 0.70 e 1.05 (faixa ideal — bônus)
      2. P/VP ≤ 1.15 (limite geral — base)
      3. DY >= 10% (base — mínimo, vs 8% nos FIIs)
      4. DY >= 12% (bônus — excelente, vs 10% nos FIIs)
      5. Distribuição histórica 12m > 0
    """
    score = 0
    
    pb_ratio = safe_float(pb_ratio)
    dividend_rate = safe_float(dividend_rate)
    
    # 2. P/VP ≤ 1.15 (base — ativo não está excessivamente caro)
    if pb_ratio is not None and pb_ratio <= PB_FII_MAX:
        score += 1
        
    # 1. P/VP entre 0.70 e 1.05 (bônus aninhado na base — faixa ideal)
    if pb_ratio is not None and PB_FII_IDEAL_LOW <= pb_ratio <= PB_FII_IDEAL_HIGH:
        score += 1
        
    # 3. DY >= 10% (base — mínimo elevado)
    dy_norm = normalize_dividend_yield(dividend_yield)
    if dy_norm >= DY_FIAGRO_GOOD:
        score += 1
        
    # 4. DY >= 12% (bônus — excelente, aninhado na base)
    if dy_norm >= DY_FIAGRO_EXCELLENT:
        score += 1
        
    # 5. Distribuição acumulada nos últimos 12 meses > 0
    if historical_dividends_365d is not None and historical_dividends_365d > 0:
        score += 1
    elif dividend_rate is not None and dividend_rate > 0:
        score += 1
        
    return score

def analyze_fii(ticker: str, info: dict[str, Any]) -> dict[str, Any]:
    """
    Parses yfinance raw FII info and extracts REIT-specific metrics.
    """
    price = _parse_price(info)
    pb_ratio = safe_float(info.get('priceToBook'))
    
    dy, dividend_rate = _derive_dividend_fields(
        info.get('dividendYield'),
        info.get('dividendRate'),
        price,
        last_div=info.get('lastDividendValue')
    )
    
    name = info.get('longName') or info.get('shortName', ticker)
    hist_divs = info.get('_dividends_365d')
    score = calculate_fii_score(price, pb_ratio, dy, dividend_rate,
                                historical_dividends_365d=hist_divs)
        
    return {
        'ticker': ticker,
        'name': name,
        'price': price,
        'pb_ratio': pb_ratio,
        'dividend_yield': dy,
        'dividend_rate': dividend_rate,
        'score': score
    }


def analyze_fiagro(ticker: str, info: dict[str, Any]) -> dict[str, Any]:
    """
    Parses yfinance raw FIAGRO info and calculates FIAGRO-specific metrics.
    Uses calculate_fiagro_score() with elevated DY thresholds.
    """
    price = _parse_price(info)
    pb_ratio = safe_float(info.get('priceToBook'))
    
    dy, dividend_rate = _derive_dividend_fields(
        info.get('dividendYield'),
        info.get('dividendRate'),
        price,
        last_div=info.get('lastDividendValue')
    )
    
    name = info.get('longName') or info.get('shortName', ticker)
    hist_divs = info.get('_dividends_365d')
    score = calculate_fiagro_score(price, pb_ratio, dy, dividend_rate,
                                    historical_dividends_365d=hist_divs)
        
    return {
        'ticker': ticker,
        'name': name,
        'price': price,
        'pb_ratio': pb_ratio,
        'dividend_yield': dy,
        'dividend_rate': dividend_rate,
        'score': score
    }
