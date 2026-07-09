import math
from typing import Any

# ---------------------------------------------------------------------------
# Constants — Legacy (v2.4)
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

# ---------------------------------------------------------------------------
# Constants — v2.5 Continuous Score
# ---------------------------------------------------------------------------

# Stock criteria max values for proportional scoring
DY_MAX_SCORE_PCT = 0.15         # DY max for 2.0 pts (15%)
ROE_MAX_SCORE_PCT = 0.30        # ROE max for 2.0 pts (30%)
DY_FACTOR = 1.0 / (DY_MAX_SCORE_PCT - DY_THRESHOLD)  # ~11.111
ROE_FACTOR = 1.0 / (ROE_MAX_SCORE_PCT - ROE_MIN)     # 5.0

# Stock P/VP bounds
PB_MIN_STOCK = 0.50
PB_MAX_STOCK = 1.50

# FII/FIAGRO v2.5 constants
PB_FII_FLOOR = 0.70            # Piso de ruína
PB_FII_CEILING = 1.05          # Teto faixa ideal
PB_FII_LIMIT_LOW = 0.60        # Limite inferior da faixa de borda
PB_FII_LIMIT_HIGH = 1.15       # Limite superior da faixa de borda

DY_FII_MIN = 0.08              # DY mínimo FII
DY_FIAGRO_MIN = 0.10           # DY mínimo FIAGRO
DY_FII_CAP = 0.145             # Trava de risco crédito FII (14.5%)
DY_FIAGRO_CAP = 0.165          # Trava de risco crédito FIAGRO (16.5%)
DY_FII_FACTOR = 1.0 / (DY_FII_CAP - DY_FII_MIN)       # ~15.38
DY_FIAGRO_FACTOR = 1.0 / (DY_FIAGRO_CAP - DY_FIAGRO_MIN)  # ~15.38

CONSISTENCY_TARGET = 0.95      # Meta de retenção semestral (95%)

# Normalization
DY_PERCENTAGE_THRESHOLD = 1.0  # Values > 1 are treated as percentages
DY_PERCENTAGE_DIVISOR = 100.0
# Rounding
ROUND_DECIMALS = 2
DY_DECIMALS = 6
SCORE_DECIMALS = 2


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


# ---------------------------------------------------------------------------
# v2.5 Continuous Scoring Functions
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value between lo and hi."""
    return max(lo, min(hi, value))


def _score_dy_stock(dy_medio_3y: float | None) -> float:
    """
    Stock Dividend Yield criterion (0-2 pts).
    Meta: >= 6%. Max at 15%.
    """
    if dy_medio_3y is None or dy_medio_3y < DY_THRESHOLD:
        return 0.0
    bonus = (dy_medio_3y - DY_THRESHOLD) * DY_FACTOR
    return round(_clamp(1.0 + bonus, 0.0, 2.0), SCORE_DECIMALS)


def _score_pe_stock(pe_medio_5y: float | None) -> float:
    """
    Stock P/L criterion (0-2 pts).
    Meta: 0 < pe <= 15. Proportional: lower is better.
    """
    if pe_medio_5y is None or pe_medio_5y <= 0 or pe_medio_5y > PE_MAX_GRAHAM:
        return 0.0
    proportion = (PE_MAX_GRAHAM - pe_medio_5y) / PE_MAX_GRAHAM  # 0 at pe=15, 1 at pe=0
    return round(_clamp(1.0 + proportion * 1.0, 0.0, 2.0), SCORE_DECIMALS)


def _score_pb_stock(pb_ratio: float | None) -> float:
    """
    Stock P/VP criterion (0-2 pts), ASSIMETRIC.
    Formula: 2.0 * (1.50 - pb), capped at piso 0.50.
    pb=0.50→2.0, pb=1.00→1.0, pb=1.50→0.0
    """
    if pb_ratio is None or pb_ratio < PB_MIN_STOCK or pb_ratio > PB_MAX_STOCK:
        return 0.0
    # Assimetric: lower P/VP (within safe range) = higher score
    return round(_clamp(2.0 * (PB_MAX_STOCK - pb_ratio), 0.0, 2.0), SCORE_DECIMALS)


def _score_roe_stock(roe: float | None) -> float:
    """
    Stock ROE criterion (0-2 pts).
    Meta: >= 10%. Max at 30%.
    """
    if roe is None or roe < ROE_MIN:
        return 0.0
    bonus = (roe - ROE_MIN) * ROE_FACTOR
    return round(_clamp(1.0 + bonus, 0.0, 2.0), SCORE_DECIMALS)


def _score_graham_stock(price: float | None, graham_price: float | None,
                         peg_ratio: float | None = None, sector: str | None = None) -> float:
    """
    Stock Margin of Safety criterion (0-2 pts).
    Traditional sectors: price < graham_price.
    Tech/light capital: PEG <= 1.0.
    """
    tech_sectors = {'Technology', 'Communication Services'}

    # PEG path for tech sectors
    if sector in tech_sectors and peg_ratio is not None and 0 < peg_ratio <= PEG_MAX:
        proportion = (PEG_MAX - peg_ratio) / PEG_MAX  # 0 at peg=1, ~1 at peg=0
        return round(_clamp(1.0 + proportion * 1.0, 0.0, 2.0), SCORE_DECIMALS)

    # Graham path for all sectors
    if price is None or graham_price is None or graham_price <= 0:
        return 0.0
    if price >= graham_price:
        return 0.0
    margin = (graham_price - price) / price  # 0 at price=gp, ~1 at price=0.5*gp
    return round(_clamp(1.0 + margin, 0.0, 2.0), SCORE_DECIMALS)


def calculate_stock_score_continuous(
    dy_medio_3y: Any, pe_medio_5y: Any, pb_ratio: Any,
    roe: Any, price: Any, graham_price: Any,
    peg_ratio: Any = None, sector: str | None = None
) -> float:
    """
    Calculates a continuous 0-10 scorecard for stocks (v2.5).
    Each of 5 criteria scores 0.0-2.0, summed = 0.0-10.0.
    """
    dy_medio_3y = safe_float(dy_medio_3y)
    pe_medio_5y = safe_float(pe_medio_5y)
    pb_ratio = safe_float(pb_ratio)
    roe = safe_float(roe)
    price = safe_float(price)
    graham_price = safe_float(graham_price)
    peg_ratio = safe_float(peg_ratio)

    s1 = _score_dy_stock(dy_medio_3y)
    s2 = _score_pe_stock(pe_medio_5y)
    s3 = _score_pb_stock(pb_ratio)
    s4 = _score_roe_stock(roe)
    s5 = _score_graham_stock(price, graham_price, peg_ratio=peg_ratio, sector=sector)

    return round(s1 + s2 + s3 + s4 + s5, SCORE_DECIMALS)


def _score_pb_fii_ideal(pb_ratio: float | None) -> float:
    """
    FII P/VP Ajustado (0-2 pts, kept for backward compat).
    Piso 0.70, teto 1.05. Scores proportionally: lower pb = better.
    """
    if pb_ratio is None or pb_ratio < PB_FII_FLOOR or pb_ratio > PB_FII_CEILING:
        return 0.0
    proportion = (PB_FII_CEILING - pb_ratio) / (PB_FII_CEILING - PB_FII_FLOOR)
    return round(_clamp(proportion * 2.0, 0.0, 2.0), SCORE_DECIMALS)


def _score_pb_fii_limite(pb_ratio: float | None) -> float:
    """
    FII P/VP Limite (0-2 pts, kept for backward compat).
    Edge zones: 0.60-0.70 (distress) or 1.05-1.15 (slight premium).
    """
    if pb_ratio is None:
        return 0.0
    if PB_FII_LIMIT_LOW <= pb_ratio < PB_FII_FLOOR:
        proportion = (pb_ratio - PB_FII_LIMIT_LOW) / (PB_FII_FLOOR - PB_FII_LIMIT_LOW)
        return round(_clamp(proportion * 2.0, 0.0, 2.0), SCORE_DECIMALS)
    if PB_FII_CEILING < pb_ratio <= PB_FII_LIMIT_HIGH:
        proportion = (PB_FII_LIMIT_HIGH - pb_ratio) / (PB_FII_LIMIT_HIGH - PB_FII_CEILING)
        return round(_clamp(proportion * 2.0, 0.0, 2.0), SCORE_DECIMALS)
    return 0.0


def _score_dy_fii(dy: float | None, is_fiagro: bool = False) -> float:
    """
    FII/FIAGRO DY Minimum criterion (0-2 pts, kept for backward compat).
    """
    min_dy = DY_FIAGRO_MIN if is_fiagro else DY_FII_MIN
    cap_dy = DY_FIAGRO_CAP if is_fiagro else DY_FII_CAP
    factor = DY_FIAGRO_FACTOR if is_fiagro else DY_FII_FACTOR
    if dy is None or dy < min_dy:
        return 0.0
    bonus = (dy - min_dy) * factor
    return round(_clamp(1.0 + bonus, 0.0, 2.0), SCORE_DECIMALS)


def _score_yield_cap(dy: float | None, is_fiagro: bool = False) -> float:
    """
    FII/FIAGRO Trava de Risco (0-2 pts, kept for backward compat).
    """
    cap_dy = DY_FIAGRO_CAP if is_fiagro else DY_FII_CAP
    if dy is None or dy > cap_dy:
        return 0.0
    proportion = 1.0 - (dy / cap_dy)
    return round(_clamp(proportion * 2.0, 0.0, 2.0), SCORE_DECIMALS)


def _score_dividend_consistency(consistency: float | None) -> float:
    """
    FII/FIAGRO Consistência de Proventos (0-2 pts, kept for backward compat).
    """
    if consistency is None:
        return 1.0  # Neutral when no data
    if consistency >= CONSISTENCY_TARGET:
        return 2.0
    if consistency <= 0:
        return 0.0
    return round(_clamp(consistency / CONSISTENCY_TARGET * 2.0, 0.0, 2.0), SCORE_DECIMALS)


# ---------------------------------------------------------------------------
# v2.5.1 — 4 criteria × 2.5 pts each (recalibrated for better distribution)
# ---------------------------------------------------------------------------

_SCALE_TO_2_5: float = 2.5 / 2.0  # 1.25


def _score_pb_fii_unified(pb_ratio: float | None) -> float:
    """
    FII/FIAGRO P/VP unificado (0-2.5 pts).
    MAX(P/VP Ajustado, P/VP Limite), reescalonado de 0-2 para 0-2.5.
    """
    return round(max(_score_pb_fii_ideal(pb_ratio),
                     _score_pb_fii_limite(pb_ratio)) * _SCALE_TO_2_5,
                 SCORE_DECIMALS)


def _score_dy_fii_v2(dy: float | None, is_fiagro: bool = False) -> float:
    """
    FII/FIAGRO DY Minimum (0-2.5 pts). Reescalonado de 0-2 para 0-2.5.
    """
    return round(_score_dy_fii(dy, is_fiagro) * _SCALE_TO_2_5, SCORE_DECIMALS)


def _score_yield_cap_v2(dy: float | None, is_fiagro: bool = False) -> float:
    """
    FII/FIAGRO Trava de Risco suavizada (0-2.5 pts).
    Curva: zera apenas em 2× o cap nominal. Ex:
    - DY=0%   → 2.5 (máximo)
    - DY=cap  → 1.25 (meio)
    - DY=2×cap→ 0.0 (zera)
    """
    cap_nominal = DY_FIAGRO_CAP if is_fiagro else DY_FII_CAP
    cap_efetivo = cap_nominal * 2.0
    if dy is None or dy > cap_efetivo:
        return 0.0
    proportion = 1.0 - (dy / cap_efetivo)
    return round(_clamp(proportion * 2.5, 0.0, 2.5), SCORE_DECIMALS)


def _score_dividend_consistency_v2(consistency: float | None) -> float:
    """
    FII/FIAGRO Consistência (0-2.5 pts). Neutro=1.5 quando sem dados.
    """
    if consistency is None:
        return 1.5  # Neutral mais generoso quando sem dados
    if consistency >= CONSISTENCY_TARGET:
        return 2.5
    if consistency <= 0:
        return 0.0
    return round(_clamp(consistency / CONSISTENCY_TARGET * 2.5, 0.0, 2.5), SCORE_DECIMALS)


def calculate_fii_score_continuous(
    pb_ratio: Any, dividend_yield: Any,
    dividend_consistency: float | None = None
) -> float:
    """
    Calculates a continuous 0-10 scorecard for FIIs (v2.5.1).
    4 criteria, each 0.0-2.5.
    """
    pb_ratio = safe_float(pb_ratio)
    dy = normalize_dividend_yield(dividend_yield)

    s1 = _score_pb_fii_unified(pb_ratio)       # 0-2.5
    s2 = _score_dy_fii_v2(dy, is_fiagro=False)  # 0-2.5
    s3 = _score_yield_cap_v2(dy, is_fiagro=False)  # 0-2.5
    s4 = _score_dividend_consistency_v2(dividend_consistency)  # 0-2.5

    return round(s1 + s2 + s3 + s4, SCORE_DECIMALS)


def calculate_fiagro_score_continuous(
    pb_ratio: Any, dividend_yield: Any,
    dividend_consistency: float | None = None
) -> float:
    """
    Calculates a continuous 0-10 scorecard for FIAGROs (v2.5.1).
    4 criteria, each 0.0-2.5.
    """
    pb_ratio = safe_float(pb_ratio)
    dy = normalize_dividend_yield(dividend_yield)

    s1 = _score_pb_fii_unified(pb_ratio)      # 0-2.5
    s2 = _score_dy_fii_v2(dy, is_fiagro=True)  # 0-2.5
    s3 = _score_yield_cap_v2(dy, is_fiagro=True)  # 0-2.5
    s4 = _score_dividend_consistency_v2(dividend_consistency)  # 0-2.5

    return round(s1 + s2 + s3 + s4, SCORE_DECIMALS)


# ---------------------------------------------------------------------------
# Legacy Scoring Functions (v2.4) — Kept for backward compatibility
# ---------------------------------------------------------------------------

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


def _calc_dy_medio_3y(yf_ticker: Any | None, price: float | None) -> float | None:
    """
    Calculate 3-year average dividend yield from yfinance history.
    Sum of dividends over last 1095 days / current price.
    """
    if yf_ticker is None or price is None or price <= 0:
        return None
    try:
        history = yf_ticker.actions
        if history is not None and not history.empty and 'Dividends' in history.columns:
            from pandas import DateOffset
            from datetime import datetime
            cutoff = datetime.now() - DateOffset(days=1095)
            recent = history[history.index >= cutoff]
            total_divs = recent['Dividends'].sum()
            if total_divs > 0:
                return round(total_divs / price, DY_DECIMALS)
    except Exception:
        pass
    return None


def _calc_pe_medio_5y(yf_ticker: Any | None, current_price: float | None) -> float | None:
    """
    Calculate 5-year average P/E from yfinance history.
    Current price / average EPS over last 5 years.
    """
    if yf_ticker is None or current_price is None or current_price <= 0:
        return None
    try:
        financials = yf_ticker.financials
        if financials is None or financials.empty:
            return None
        if 'Net Income' not in financials.index:
            return None
        # Get net income for last 5 fiscal years
        net_income = financials.loc['Net Income'].dropna().head(5)
        if len(net_income) == 0:
            return None
        avg_net_income = net_income.mean()
        # Get shares outstanding
        info_attr = getattr(yf_ticker, 'info', None) or {}
        shares = safe_float(info_attr.get('sharesOutstanding'))
        if shares is None or shares <= 0 or avg_net_income <= 0:
            return None
        avg_eps = avg_net_income / shares
        if avg_eps <= 0:
            return None
        return round(current_price / avg_eps, ROUND_DECIMALS)
    except Exception:
        pass
    return None


def _calc_net_debt_ebitda(yf_ticker: Any | None) -> float | None:
    """
    Calculate Net Debt / EBITDA from yfinance financials.
    Informational only (not scored).
    """
    if yf_ticker is None:
        return None
    try:
        financials = yf_ticker.financials
        if financials is None or financials.empty:
            return None
        # Try to get from the financials statement
        if 'EBITDA' in financials.index and 'Total Debt' in financials.index:
            ebitda = safe_float(financials.loc['EBITDA'].dropna().iloc[0]) if not financials.loc['EBITDA'].dropna().empty else None
            total_debt = safe_float(financials.loc['Total Debt'].dropna().iloc[0]) if not financials.loc['Total Debt'].dropna().empty else None
            if ebitda and ebitda > 0 and total_debt is not None:
                # Try to get cash from balance sheet
                bs = yf_ticker.balance_sheet
                cash = 0
                if bs is not None and not bs.empty and 'Cash And Cash Equivalents' in bs.index:
                    cash_val = safe_float(bs.loc['Cash And Cash Equivalents'].dropna().iloc[0]) if not bs.loc['Cash And Cash Equivalents'].dropna().empty else 0
                    cash = cash_val or 0
                net_debt = total_debt - cash
                return round(net_debt / ebitda, ROUND_DECIMALS)
    except Exception:
        pass
    return None


def _calc_dividend_consistency(yf_ticker: Any | None) -> float | None:
    """
    Calculate FII/FIAGRO semi-annual dividend consistency.
    Compares last 6 months dividends vs previous 6 months.
    Target: >= 95% retention.
    """
    if yf_ticker is None:
        return None
    try:
        history = yf_ticker.actions
        if history is not None and not history.empty and 'Dividends' in history.columns:
            from pandas import DateOffset
            from datetime import datetime
            now = datetime.now()
            # Last 6 months
            div_6m = history['Dividends'].last('180D').sum()
            # Previous 6 months (6-12 months ago)
            cutoff_6m = now - DateOffset(days=180)
            cutoff_12m = now - DateOffset(days=365)
            div_prev_6m = history[
                (history.index >= cutoff_12m) & (history.index < cutoff_6m)
            ]['Dividends'].sum()
            if div_prev_6m > 0:
                return round(div_6m / div_prev_6m, SCORE_DECIMALS)
    except Exception:
        pass
    return None


def analyze_stock(ticker: str, info: dict[str, Any]) -> dict[str, Any]:
    """
    Parses yfinance raw stock info and calculates fundamentalist metrics.
    Returns both legacy (v2.4) and continuous (v2.5) scores.
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
    
    # Legacy v2.4 score
    score_legacy = calculate_stock_score(
        price, eps, book_value, pe_ratio, pb_ratio, dy, roe, graham_price, bazin_price,
        peg_ratio=peg_ratio, sector=raw_sector
    )
    
    # v2.5 historical data (from yf_ticker passed via info)
    yf_ticker = info.get('_yf_ticker')
    dy_medio_3y = _calc_dy_medio_3y(yf_ticker, price)
    pe_medio_5y = _calc_pe_medio_5y(yf_ticker, price)
    net_debt_ebitda = _calc_net_debt_ebitda(yf_ticker)
    
    # Fallback to current values if historical data unavailable
    if dy_medio_3y is None or dy_medio_3y == 0.0:
        dy_medio_3y = dy  # fallback to current DY
    if pe_medio_5y is None or pe_medio_5y <= 0:
        pe_medio_5y = pe_ratio  # fallback to current P/E
    
    # v2.5 continuous score
    score_v2 = calculate_stock_score_continuous(
        dy_medio_3y, pe_medio_5y, pb_ratio, roe, price, graham_price,
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
        'score': score_legacy,
        # v2.5 fields
        'dy_medio_3y': dy_medio_3y,
        'pe_medio_5y': pe_medio_5y,
        'net_debt_ebitda': net_debt_ebitda,
        'score_v2': score_v2
    }


# Legacy FII score — kept for backward compatibility
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


# Legacy FIAGRO score — kept for backward compatibility
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
    Returns both legacy (v2.4) and continuous (v2.5) scores.
    """
    price = _parse_price(info)
    pb_ratio = safe_float(info.get('priceToBook'))
    
    # VPA (book value per share) — reference only, not used in scoring
    book_value = safe_float(info.get('bookValue'))
    if book_value is None and price is not None and pb_ratio is not None and pb_ratio > 0:
        book_value = round(price / pb_ratio, 2)
    
    dy, dividend_rate = _derive_dividend_fields(
        info.get('dividendYield'),
        info.get('dividendRate'),
        price,
        last_div=info.get('lastDividendValue')
    )
    
    name = info.get('longName') or info.get('shortName', ticker)
    hist_divs = info.get('_dividends_365d')
    
    # Legacy v2.4 score
    score_legacy = calculate_fii_score(price, pb_ratio, dy, dividend_rate,
                                       historical_dividends_365d=hist_divs)
    
    # v2.5 consistency data
    yf_ticker = info.get('_yf_ticker')
    dividend_consistency = _calc_dividend_consistency(yf_ticker)
    
    # v2.5 continuous score
    score_v2 = calculate_fii_score_continuous(pb_ratio, dy, dividend_consistency)
        
    return {
        'ticker': ticker,
        'name': name,
        'price': price,
        'book_value': book_value,
        'pb_ratio': pb_ratio,
        'dividend_yield': dy,
        'dividend_rate': dividend_rate,
        'score': score_legacy,
        # v2.5 fields
        'dividend_consistency': dividend_consistency,
        'score_v2': score_v2
    }


def analyze_fiagro(ticker: str, info: dict[str, Any]) -> dict[str, Any]:
    """
    Parses yfinance raw FIAGRO info and calculates FIAGRO-specific metrics.
    Returns both legacy (v2.4) and continuous (v2.5) scores.
    """
    price = _parse_price(info)
    pb_ratio = safe_float(info.get('priceToBook'))
    
    # VPA (book value per share) — reference only, not used in scoring
    book_value = safe_float(info.get('bookValue'))
    if book_value is None and price is not None and pb_ratio is not None and pb_ratio > 0:
        book_value = round(price / pb_ratio, 2)
    
    dy, dividend_rate = _derive_dividend_fields(
        info.get('dividendYield'),
        info.get('dividendRate'),
        price,
        last_div=info.get('lastDividendValue')
    )
    
    name = info.get('longName') or info.get('shortName', ticker)
    hist_divs = info.get('_dividends_365d')
    
    # Legacy v2.4 score
    score_legacy = calculate_fiagro_score(price, pb_ratio, dy, dividend_rate,
                                          historical_dividends_365d=hist_divs)
    
    # v2.5 consistency data
    yf_ticker = info.get('_yf_ticker')
    dividend_consistency = _calc_dividend_consistency(yf_ticker)
    
    # v2.5 continuous score
    score_v2 = calculate_fiagro_score_continuous(pb_ratio, dy, dividend_consistency)
        
    return {
        'ticker': ticker,
        'name': name,
        'price': price,
        'book_value': book_value,
        'pb_ratio': pb_ratio,
        'dividend_yield': dy,
        'dividend_rate': dividend_rate,
        'score': score_legacy,
        # v2.5 fields
        'dividend_consistency': dividend_consistency,
        'score_v2': score_v2
    }
