import math


def safe_float(value):
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


def calculate_graham_price(eps, book_value):
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
        return round(math.sqrt(22.5 * eps * book_value), 2)
    except ValueError:
        return 0.0

def calculate_bazin_price(dividend_rate):
    """
    Calculates Bazin's Ceiling Price (Preço Teto de Bazin): Dividend Rate / 0.06
    """
    if dividend_rate is None or dividend_rate <= 0:
        return 0.0
    return round(dividend_rate / 0.06, 2)

def normalize_dividend_yield(dy):
    """
    Normalizes dividend yield from yfinance.
    Sometimes it is returned as a percentage (e.g. 9.48) and sometimes as a decimal (e.g. 0.0948).
    We convert it to a standard decimal representation.
    """
    if dy is None:
        return 0.0
    # If it is greater than 1, it's almost certainly a percentage (e.g. 6.5 instead of 0.065)
    if dy > 1.0:
        return round(dy / 100.0, 6)
    return round(dy, 6)

def calculate_stock_score(price, eps, book_value, pe_ratio, pb_ratio, dividend_yield, roe, graham_price, bazin_price):
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
    
    # Normalize yield to make sure threshold check is correct
    dy_norm = normalize_dividend_yield(dividend_yield)
    
    # 1. Dividend Yield check (Bazin threshold: >= 6% or 0.06)
    if dy_norm >= 0.06:
        score += 1
        
    # 2. P/L (P/E Ratio) check (Graham threshold: 0 < P/L <= 15)
    if pe_ratio is not None and 0 < pe_ratio <= 15:
        score += 1
        
    # 3. P/VP (P/B Ratio) check (Graham threshold: 0 < P/VP <= 1.5)
    if pb_ratio is not None and 0 < pb_ratio <= 1.5:
        score += 1
        
    # 4. ROE check (Healthy profitability: > 10% or 0.10)
    if roe is not None and roe >= 0.10:
        score += 1
        
    # 5. Margin of Safety check (Current Price < Graham Price)
    if price is not None and graham_price is not None and price < graham_price:
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

def analyze_stock(ticker, info):
    """
    Parses yfinance raw stock info and calculates fundamentalist metrics.
    """
    # Extract values safely with sanitization
    price = info.get('currentPrice')
    if price is None:
        price = info.get('regularMarketPrice') # fallback
    price = safe_float(price)
        
    eps = safe_float(info.get('trailingEps'))
    book_value = safe_float(info.get('bookValue'))
    pe_ratio = safe_float(info.get('trailingPE'))
    pb_ratio = safe_float(info.get('priceToBook'))
    
    # Dividend rates
    dividend_yield = info.get('dividendYield')
    dividend_yield = normalize_dividend_yield(dividend_yield)
    dividend_rate = safe_float(info.get('dividendRate'))
    
    # In yfinance, sometimes dividendRate is present but dividendYield is missing, or vice versa
    if (dividend_yield is None or dividend_yield == 0.0) and dividend_rate and price:
        dividend_yield = normalize_dividend_yield(dividend_rate / price)
    if dividend_rate is None and dividend_yield and price:
        dividend_rate = dividend_yield * price
        
    roe = safe_float(info.get('returnOnEquity'))
    name = info.get('longName') or info.get('shortName', ticker)
    
    # Translate sector
    raw_sector = info.get('sector', 'Outros')
    sector = SECTOR_MAP.get(raw_sector, raw_sector)
    
    # Calculations
    graham_price = calculate_graham_price(eps, book_value)
    bazin_price = calculate_bazin_price(dividend_rate)
    
    score = calculate_stock_score(
        price, eps, book_value, pe_ratio, pb_ratio, dividend_yield, roe, graham_price, bazin_price
    )
    
    return {
        'ticker': ticker,
        'name': name,
        'sector': sector,
        'price': price,
        'pe_ratio': pe_ratio,
        'pb_ratio': pb_ratio,
        'dividend_yield': dividend_yield,
        'roe': roe,
        'eps': eps,
        'book_value': book_value,
        'graham_price': graham_price,
        'bazin_price': bazin_price,
        'score': score
    }


def calculate_fii_score(price, pb_ratio, dividend_yield, dividend_rate):
    """
    Calculates a 0-5 scorecard ranking for FIIs/FIAGROs based on key REIT metrics.
    All numeric values are sanitized via safe_float.
    """
    score = 0
    
    pb_ratio = safe_float(pb_ratio)
    dividend_rate = safe_float(dividend_rate)
    
    # 1. Valuation: P/VP in the ideal range (0.85 to 1.05)
    if pb_ratio is not None and 0.85 <= pb_ratio <= 1.05:
        score += 1
        
    # 2. Valuation: P/VP is not extremely expensive (P/VP <= 1.15)
    if pb_ratio is not None and 0 < pb_ratio <= 1.15:
        score += 1
        
    # 3. Dividend Yield: Minimum yield of 8% (0.08)
    dy_norm = normalize_dividend_yield(dividend_yield)
    if dy_norm >= 0.08:
        score += 1
        
    # 4. Dividend Yield: Excellent yield of 10% (0.10)
    if dy_norm >= 0.10:
        score += 1
        
    # 5. Dividend Rate: Consistent regular distribution
    if dividend_rate is not None and dividend_rate > 0:
        score += 1
        
    return score

def analyze_fii(ticker, info):
    """
    Parses yfinance raw FII info and extracts REIT-specific metrics.
    """
    price = info.get('currentPrice')
    if price is None:
        price = info.get('regularMarketPrice')
    price = safe_float(price)
        
    pb_ratio = safe_float(info.get('priceToBook'))  # P/VP
    dividend_yield = info.get('dividendYield')
    dividend_yield = normalize_dividend_yield(dividend_yield)
    dividend_rate = safe_float(info.get('dividendRate'))
    name = info.get('longName') or info.get('shortName', ticker)
    
    # Fallback to lastDividendValue if yield/rate are missing (common in FIAGROs)
    last_div = safe_float(info.get('lastDividendValue'))
    if (dividend_yield is None or dividend_yield == 0.0) and (dividend_rate is None or dividend_rate == 0.0) and last_div and price:
        dividend_rate = last_div * 12
        dividend_yield = dividend_rate / price

    if (dividend_yield is None or dividend_yield == 0.0) and dividend_rate and price:
        dividend_yield = normalize_dividend_yield(dividend_rate / price)
    if dividend_rate is None and dividend_yield and price:
        dividend_rate = dividend_yield * price
        
    score = calculate_fii_score(price, pb_ratio, dividend_yield, dividend_rate)
        
    return {
        'ticker': ticker,
        'name': name,
        'price': price,
        'pb_ratio': pb_ratio,
        'dividend_yield': dividend_yield,
        'dividend_rate': dividend_rate,
        'score': score
    }
