import os
import time
import requests
from jinja2 import Environment, FileSystemLoader

# Get the directory of this script
MVP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(MVP_DIR)
TEMPLATES_DIR = os.path.join(MVP_DIR, "templates")

# Load token from .env
token = None
env_path = os.path.join(PROJECT_ROOT, ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            if line.strip().startswith("brapi="):
                token = line.strip().split("=")[1].strip()

print(f"Token: {'Loaded' if token else 'NOT found'}")

def get_macro_data():
    # Realistic fallback defaults in case of network issues or limits
    macro = {"selic": 10.75, "cdi": 10.65, "ipca": 4.18}
    if not token:
        return macro

    # 1. Fetch Selic/CDI (Prime)
    try:
        url = "https://brapi.dev/api/v2/prime"
        res = requests.get(url, params={"token": token, "country": "brazil"})
        if res.status_code == 200:
            data = res.json()
            prime_list = data.get("prime", [])
            for item in prime_list:
                name = item.get("name", "").lower()
                val = float(item.get("value", 0))
                if "selic" in name:
                    macro["selic"] = val
                elif "cdi" in name:
                    macro["cdi"] = val
    except Exception as e:
        print(f"Failed to fetch prime rate: {e}")

    # 2. Fetch IPCA (Inflation)
    try:
        url = "https://brapi.dev/api/v2/inflation"
        res = requests.get(url, params={"token": token, "country": "brazil"})
        if res.status_code == 200:
            data = res.json()
            inflation_list = data.get("inflation", [])
            if inflation_list:
                # Get the latest value
                macro["ipca"] = float(inflation_list[0].get("value", 4.18))
    except Exception as e:
        print(f"Failed to fetch inflation rate: {e}")

    return macro

def fetch_asset_quote(ticker):
    print(f"Fetching BRAPI quote for {ticker}...", end="", flush=True)
    url = f"https://brapi.dev/api/quote/{ticker}"
    params = {"token": token}
    try:
        res = requests.get(url, params=params)
        if res.status_code == 200:
            results = res.json().get("results", [])
            if results:
                r = results[0]
                print(" [OK]")
                return {
                    "ticker": r.get("symbol"),
                    "name": r.get("longName", ticker),
                    "price": r.get("regularMarketPrice"),
                    "change": r.get("regularMarketChangePercent"),
                    "logourl": r.get("logourl")
                }
        print(f" [FAILED: Status {res.status_code}]")
    except Exception as e:
        print(f" [ERROR: {e}]")
    
    return {
        "ticker": ticker,
        "name": "N/A",
        "price": None,
        "change": None,
        "logourl": None
    }

def main():
    macro = get_macro_data()
    print(f"Macro Data Loaded: {macro}")

    assets_to_fetch = ["PETR4", "VALE3", "WEGE3", "MXRF11", "HGLG11", "KNCA11"]
    assets_data = []

    for ticker in assets_to_fetch:
        data = fetch_asset_quote(ticker)
        assets_data.append(data)
        time.sleep(1) # respect API request spacing to prevent rate limits

    # Render template
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("index_template.html")
    html_output = template.render(macro=macro, assets=assets_data)

    # Save to index.html
    output_path = os.path.join(MVP_DIR, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_output)
    
    print(f"\nBRAPI MVP generated successfully at: {output_path}")

if __name__ == "__main__":
    main()
