"""
CVM open data client to download monthly FIAGRO & FII reports and extract VPA values.
Saves mapped VPAs to data/fiagro_vpa.json and data/fii_vpa.json for use by the daily pipeline.
"""
import io
import json
import logging
import os
import time
import urllib.request
import zipfile
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger("cvm_updater")

# Project directories
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SRC_DIR)
DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
CONFIG_DIR = os.path.join(_PROJECT_ROOT, "config")
FIAGRO_CACHE = os.path.join(DATA_DIR, "fiagro_vpa.json")
FII_CACHE = os.path.join(DATA_DIR, "fii_vpa.json")
FIAGRO_DY_CACHE = os.path.join(DATA_DIR, "fiagro_dy.json")
FII_DY_CACHE = os.path.join(DATA_DIR, "fii_dy.json")

# Maximum VPA value to accept (some funds have high NAV per share)
VPA_MAX_LIMIT = 5000.0

# Predefined CNPJ mappings for FIIs (enables matching by CNPJ instead of fragile ISIN substring)
FII_CNPJ_MAPPING = {
    "AFHF11": "60077386000161",
    "ALZC11": "40011324000140",
    "BTCI11": "09552812000114",
    "BTHF11": "45188176000157",
    "CPSH11": "47896665000199",
    "FYTO11": "18085673000157",
    "GZIT11": "15447108000102",
    "IRDM11": "41076564000195",
    # Note: KFOF11 (30091444000140) is not in tickers.json, keeping mapping for future use
    "KFOF11": "30091444000140",
    "KNUQ11": "42754362000118",
    "MCRE11": "36655973000106",
    "OXRL11": "58561237000121",
    "PCIP11": "28729197000113",
    "PMLL11": "26499833000132",
    "PSEC11": "35507457000171",
    "TVRI11": "14410722000129",
}

# Predefined CNPJ mappings for FIAGROs in B3 config
CNPJ_MAPPING = {
    "AAGR11": "52670402000105",
    "AAZQ11": "44625826000111",
    "AGRX11": "43951911000107",
    "BBGO11": "42592257000120",
    "BRFT11": "52512069000106",
    "BTAG11": "40771109000147",
    "CPTR11": "42537579000176",
    "CRAA11": "44449830000176",
    "CTEM11": "50749446000191",
    "DCRA11": "41697223000181",
    "EGAF11": "41530932000194",
    "FGAA11": "40450537000149",
    "FTCA11": "42537438000153",
    "FZDA11": "44585141000199",
    "FZDB11": "44585171000104",
    "GCRA11": "41999971000139",
    "GRWA11": "44866579000116",
    "HGAG11": "43015367000152",
    "IAGR11": "44286898000181",
    "JGPX11": "41178652000188",
    "KDIF11": "26324298000189",
    "KDOL11": "44286780000156",
    "KNCA11": "40439587000182",
    "KOPA11": "41804797000103",
    "LAFI11": "42323211000138",
    "LSAG11": "44309320000140",
    "NEXG11": "42537330000160",
    "OIAG11": "40439906000150",
    "PLCA11": "41793798000109",
    "ROCA11": "64611656000123",
    "RURA11": "42479593000160",
    "RZAG11": "41804822000150",
    "RZNE11": "41804847000153",
    "SNAG11": "43764834000139",
    "SNFZ11": "44537151000102",
    "VCRA11": "42537397000105",
    "VGIA11": "42479633000170",
    "VHFA11": "51658280000160",
    "XPCA11": "41794247000109"
}

def update_fiagro_vpas(force: bool = False) -> dict:
    """
    Downloads CVM FIAGRO monthly reports to extract and update
    VPA cache for our configured FIAGRO tickers.
    Returns the updated VPA map.
    """
    # 1. Cache validation
    if not force and os.path.exists(FIAGRO_CACHE):
        mtime = datetime.fromtimestamp(os.path.getmtime(FIAGRO_CACHE))
        if datetime.now() - mtime < timedelta(days=7):
            logger.info("FIAGRO VPA cache is up to date (less than 7 days old). Skipping update.")
            with open(FIAGRO_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)

    logger.info("Updating FIAGRO VPA cache from CVM...")

    # Load list of monitored tickers
    config_path = os.path.join(CONFIG_DIR, "tickers.json")
    if not os.path.exists(config_path):
        logger.error(f"Tickers configuration not found at {config_path}")
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    fiagros = [t.replace(".SA", "") for t in config.get("fiagros", {}).get("tickers", [])]
    if not fiagros:
        logger.info("No FIAGROs configured. Skipping CVM download.")
        return {}

    vpa_map = _download_and_match_vpas(
        tickers=fiagros,
        cvm_path="FIAGRO",
        cache_file=FIAGRO_CACHE,
        cnpj_mapping=CNPJ_MAPPING,
        min_unique_funds=10,
        label="FIAGRO",
        dy_column="Dividend_Yield_Mes",
        dy_cache_file=FIAGRO_DY_CACHE,
        dy_is_percentage=True,  # FIAGRO uses percentage format (e.g. 1.18 = 1.18%/mo)
    )
    return vpa_map


def update_fii_vpas(force: bool = False) -> dict:
    """
    Downloads CVM FII monthly reports to extract and update
    VPA cache for our configured FII tickers.
    Returns the updated VPA map.
    """
    # 1. Cache validation
    if not force and os.path.exists(FII_CACHE):
        mtime = datetime.fromtimestamp(os.path.getmtime(FII_CACHE))
        if datetime.now() - mtime < timedelta(days=7):
            logger.info("FII VPA cache is up to date (less than 7 days old). Skipping update.")
            with open(FII_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)

    logger.info("Updating FII VPA cache from CVM...")

    # Load list of monitored tickers
    config_path = os.path.join(CONFIG_DIR, "tickers.json")
    if not os.path.exists(config_path):
        logger.error(f"Tickers configuration not found at {config_path}")
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    fiis = [t.replace(".SA", "") for t in config.get("fiis", {}).get("tickers", [])]
    if not fiis:
        logger.info("No FIIs configured. Skipping CVM download.")
        return {}

    vpa_map = _download_and_match_vpas(
        tickers=fiis,
        cvm_path="FII",
        cache_file=FII_CACHE,
        cnpj_mapping=FII_CNPJ_MAPPING,  # Try CNPJ first, fallback to ISIN
        min_unique_funds=50,
        label="FII",
        period_format="annual",
        csv_suffix="_complemento",
        cnpj_column="CNPJ_Fundo_Classe",
        isin_column="Codigo_ISIN",
        dy_column="Percentual_Dividend_Yield_Mes",
        dy_cache_file=FII_DY_CACHE,
        dy_is_percentage=False,  # FII uses decimal format (e.g. 0.004342 = 0.43%/mo)
    )
    return vpa_map


def _download_and_match_vpas(
    tickers: list[str],
    cvm_path: str,
    cache_file: str,
    cnpj_mapping: dict[str, str],
    min_unique_funds: int,
    label: str,
    period_format: str = "monthly",
    csv_suffix: str = "",
    cnpj_column: str = "CNPJ_Classe",
    isin_column: str = "Codigo_ISIN",
    dy_column: str | None = None,
    dy_cache_file: str | None = None,
    dy_is_percentage: bool = False,
) -> dict:
    """
    Generic routine to download CVM reports, extract VPA and DY values,
    and save JSON caches.
    
    Args:
        period_format: "monthly" (YYYYMM) or "annual" (YYYY)
        csv_suffix: e.g., "_complemento" for FII complemento file
        cnpj_column: Column name for CNPJ (differs between FIAGRO/FII)
        isin_column: Column name for ISIN, or None if not available
        dy_column: Column name for monthly DY, or None to skip
        dy_cache_file: File path to save DY cache (requires dy_column)
        dy_is_percentage: If True, DY values are percentages (1.18=1.18%/mo).
                          If False, DY values are decimals (0.004342=0.43%/mo).
    """
    now = datetime.now()
    periods = []
    for i in range(1, 4):
        dt = now - timedelta(days=30 * i)
        if period_format == "annual":
            periods.append(dt.strftime("%Y"))
        else:
            periods.append(dt.strftime("%Y%m"))

    all_dfs = []
    isin_df = None
    for period in periods:
        if period_format == "annual":
            url = f"https://dados.cvm.gov.br/dados/{cvm_path}/DOC/INF_MENSAL/DADOS/inf_mensal_{cvm_path.lower()}_{period}.zip"
        else:
            url = f"https://dados.cvm.gov.br/dados/{cvm_path}/DOC/INF_MENSAL/DADOS/inf_mensal_{cvm_path.lower()}_{period}.zip"
        try:
            logger.info(f"Downloading {url}...")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                zip_data = resp.read()
            
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                # Find the main CSV file
                if csv_suffix:
                    filename = f"inf_mensal_{cvm_path.lower()}{csv_suffix}_{period}.csv"
                else:
                    filename = f"inf_mensal_{cvm_path.lower()}_{period}.csv"
                
                if filename in zf.namelist():
                    with zf.open(filename) as csv_file:
                        temp_df = pd.read_csv(csv_file, sep=";", encoding="latin1")
                    
                    # Also load geral CSV for ISIN data (if available in annual FII zips)
                    if period_format == "annual":
                        geral_filename = f"inf_mensal_{cvm_path.lower()}_geral_{period}.csv"
                        if geral_filename in zf.namelist():
                            with zf.open(geral_filename) as csv_file:
                                isin_df = pd.read_csv(csv_file, sep=";", encoding="latin1")
                            logger.info(f"  Loaded geral file for ISIN matching ({len(isin_df)} rows)")
                    
                    all_dfs.append(temp_df)
                    logger.info(f"Loaded data for period {period} ({temp_df[cnpj_column].nunique()} unique funds)")
                else:
                    logger.warning(f"CSV {filename} not found in zip (files: {zf.namelist()})")
        except Exception as e:
            logger.warning(f"Failed to fetch period {period}: {e}")

    if not all_dfs:
        logger.error(f"Could not load any valid report from CVM for {label}. Using existing cache.")
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    # Concatenate all periods for maximum coverage
    df = pd.concat(all_dfs, ignore_index=True)
    logger.info(f"Combined {len(all_dfs)} periods: {len(df)} total rows, {df[cnpj_column].nunique()} unique funds")

    # Normalize CNPJ column: strip non-digit characters so raw digit mappings match
    # (FII CSV uses formatted CNPJ like "45.188.176/0001-57", mapping uses "45188176000157")
    if cnpj_column in df.columns:
        df[cnpj_column] = df[cnpj_column].astype(str).str.replace(r"\D", "", regex=True)
        logger.debug(f"  Normalized {cnpj_column} (stripped non-digits)")

    # Merge ISIN data from geral CSV if available (for annual FII zips)
    if isin_df is not None and isin_column not in df.columns:
        merge_key = cnpj_column
        if merge_key in isin_df.columns:
            isin_df[merge_key] = isin_df[merge_key].astype(str).str.replace(r"\D", "", regex=True)
            df = df.merge(isin_df[[merge_key, isin_column]], on=merge_key, how="left")
            logger.info(f"  Merged ISIN data, {df[isin_column].notna().sum()} funds have ISIN")

    # Process and match tickers — extract both VPA and DY simultaneously
    vpa_map = {}
    dy_map: dict[str, float] = {}
    
    # Try to load existing caches to avoid losing records we might not find in this period
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                vpa_map = json.load(f)
        except Exception:
            pass
    if dy_cache_file and os.path.exists(dy_cache_file):
        try:
            with open(dy_cache_file, "r", encoding="utf-8") as f:
                dy_map = json.load(f)
        except Exception:
            pass

    for ticker in tickers:
        cnpj = cnpj_mapping.get(ticker)
        all_matches = None
        
        # Match by CNPJ (First choice)
        if cnpj:
            match = df[df[cnpj_column].astype(str) == cnpj]
            if not match.empty:
                all_matches = match
        
        # Match by ISIN substring (Second choice)
        if all_matches is None and isin_column and isin_column in df.columns:
            base = ticker[:4]
            match = df[df[isin_column].astype(str).str.contains(base, na=False, case=False)]
            if not match.empty:
                all_matches = match

        if all_matches is not None:
            all_matches = all_matches.sort_values(by="Versao", ascending=False)
            
            # --- Extract VPA (from highest Versao) ---
            best_vpa_row = all_matches.iloc[0]
            vpa = float(best_vpa_row["Valor_Patrimonial_Cotas"])
            if 0.0 < vpa < VPA_MAX_LIMIT:
                vpa_map[ticker] = round(vpa, 4)
            else:
                # Fallback: compute VPA from Patrimonio_Liquido / Cotas_Emitidas
                # Some funds (e.g. BRFT11) have total NAV in Valor_Patrimonial_Cotas
                # instead of per-share value. Compute it if possible.
                computed_vpa = None
                try:
                    pl = float(best_vpa_row.get("Patrimonio_Liquido", 0))
                    cotas = float(best_vpa_row.get("Cotas_Emitidas", 0))
                    if pl > 0 and cotas > 0:
                        computed_vpa = pl / cotas
                except (ValueError, TypeError):
                    pass
                
                if computed_vpa and 0.0 < computed_vpa < VPA_MAX_LIMIT:
                    vpa_map[ticker] = round(computed_vpa, 4)
                    logger.info(f"  Computed VPA for {ticker} from PL/Cotas: {computed_vpa:.4f} (raw VPA was {vpa})")
                else:
                    logger.warning(f"Ignored abnormal VPA for {ticker}: {vpa} (limit: {VPA_MAX_LIMIT})")
            
            # --- Extract DY (highest Versao with valid DY > 0) ---
            if dy_column and dy_column in df.columns:
                # Find the row with highest Versao that has valid DY > 0
                dy_row = None
                for idx in range(len(all_matches)):
                    candidate = all_matches.iloc[idx]
                    raw_dy_value = candidate[dy_column]
                    if raw_dy_value is not None and not pd.isna(raw_dy_value):
                        try:
                            raw_dy = float(raw_dy_value)
                            if raw_dy > 0:
                                dy_row = candidate
                                break
                        except (ValueError, TypeError):
                            continue
                
                if dy_row is not None:
                    raw_dy = float(dy_row[dy_column])
                    
                    if dy_is_percentage:
                        # FIAGRO: column stores percentage (1.18 = 1.18%/mo)
                        # Convert to monthly decimal
                        monthly_decimal = raw_dy / 100.0
                    else:
                        # FII: column stores decimal (0.010086 = 1.0086%/mo)
                        # But CVM is inconsistent: some values are in percentage format
                        # (0.935 = 0.935%/mo). Detect by magnitude:
                        # raw_dy > 0.20 would mean >20%/mo which is unrealistic.
                        if raw_dy > 0.20:
                            monthly_decimal = raw_dy / 100.0
                        else:
                            monthly_decimal = raw_dy
                    
                    # Annualize: monthly decimal × 12
                    dy_decimal = round(monthly_decimal * 12.0, 6)
                    dy_map[ticker] = dy_decimal

    # Write out VPA cache
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(vpa_map, f, indent=2, ensure_ascii=False)
    logger.info(f"Updated {label} VPA cache saved to {cache_file} (matched {len(vpa_map)}/{len(tickers)} tickers)")

    # Write out DY cache
    if dy_cache_file:
        with open(dy_cache_file, "w", encoding="utf-8") as f:
            json.dump(dy_map, f, indent=2, ensure_ascii=False)
        logger.info(f"Updated {label} DY cache saved to {dy_cache_file} (matched {len(dy_map)}/{len(tickers)} tickers)")

    return vpa_map

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    update_fiagro_vpas(force=True)
    update_fii_vpas(force=True)
