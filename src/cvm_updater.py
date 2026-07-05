"""
CVM open data client to download monthly FIAGRO reports and extract VPA values.
Saves mapped VPAs to data/fiagro_vpa.json for use by the daily pipeline.
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
CACHE_FILE = os.path.join(DATA_DIR, "fiagro_vpa.json")

# Predefined CNPJ mappings for FIAGROs in B3 config
CNPJ_MAPPING = {
    "AAGR11": "52670402000105",
    "AAZQ11": "44625826000111",
    "AGRX11": "43951911000107",
    "BBGO11": "42592257000120",
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

def update_fiagro_vpas(force: bool = False) -> None:
    """
    Downloads CVM FIAGRO monthly reports to extract and update
    VPA cache for our configured FIAGRO tickers.
    """
    # 1. Cache validation
    if not force and os.path.exists(CACHE_FILE):
        mtime = datetime.fromtimestamp(os.path.getmtime(CACHE_FILE))
        if datetime.now() - mtime < timedelta(days=7):
            logger.info("FIAGRO VPA cache is up to date (less than 7 days old). Skipping update.")
            return

    logger.info("Updating FIAGRO VPA cache from CVM...")

    # Load list of monitored tickers
    config_path = os.path.join(CONFIG_DIR, "tickers.json")
    if not os.path.exists(config_path):
        logger.error(f"Tickers configuration not found at {config_path}")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    fiagros = [t.replace(".SA", "") for t in config.get("fiagros", {}).get("tickers", [])]
    if not fiagros:
        logger.info("No FIAGROs configured. Skipping CVM download.")
        return

    # 2. Try download for recent periods (M-1, M-2, etc.)
    now = datetime.now()
    periods = []
    for i in range(1, 4):
        dt = now - timedelta(days=30 * i)
        periods.append(dt.strftime("%Y%m"))

    df = None
    selected_period = None
    for period in periods:
        url = f"https://dados.cvm.gov.br/dados/FIAGRO/DOC/INF_MENSAL/DADOS/inf_mensal_fiagro_{period}.zip"
        try:
            logger.info(f"Downloading {url}...")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                zip_data = resp.read()
            
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                filename = f"inf_mensal_fiagro_{period}.csv"
                if filename in zf.namelist():
                    with zf.open(filename) as csv_file:
                        temp_df = pd.read_csv(csv_file, sep=";", encoding="latin1")
                    # Check if we have complete data (at least 10 unique funds)
                    if temp_df["CNPJ_Classe"].nunique() >= 10:
                        df = temp_df
                        selected_period = period
                        logger.info(f"Successfully loaded data for period {period}")
                        break
                    else:
                        logger.warning(f"Period {period} has incomplete data, trying previous month.")
        except Exception as e:
            logger.warning(f"Failed to fetch period {period}: {e}")

    if df is None:
        logger.error("Could not load any valid monthly report from CVM. Using existing cache.")
        return

    # 3. Process and match tickers
    vpa_map = {}
    
    # Try to load existing cache to avoid losing records we might not find in this period
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                vpa_map = json.load(f)
        except Exception:
            pass

    for ticker in fiagros:
        vpa = None
        cnpj = CNPJ_MAPPING.get(ticker)
        
        # Match by CNPJ (First choice)
        if cnpj:
            match = df[df["CNPJ_Classe"].astype(str) == cnpj]
            if not match.empty:
                vpa = float(match.sort_values(by="Versao", ascending=False).iloc[0]["Valor_Patrimonial_Cotas"])
        
        # Match by ISIN substring (Second choice)
        if vpa is None:
            base = ticker[:4]
            match = df[df["Codigo_ISIN"].astype(str).str.contains(base, na=False, case=False)]
            if not match.empty:
                vpa = float(match.sort_values(by="Versao", ascending=False).iloc[0]["Valor_Patrimonial_Cotas"])

        # Validate VPA
        if vpa is not None:
            # Exclude extreme/class-level mismatched VPAs (e.g. FIDC classes with VPA = 190M)
            if 0.0 < vpa < 1000.0:
                vpa_map[ticker] = round(vpa, 4)
                logger.debug(f"Matched {ticker} -> VPA: {vpa}")
            else:
                logger.warning(f"Ignored abnormal VPA for {ticker}: {vpa}")

    # Write out the updated cache JSON
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(vpa_map, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Updated VPA cache saved to {CACHE_FILE} (matched {len(vpa_map)}/{len(fiagros)} tickers)")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    update_fiagro_vpas(force=True)
