import os
import requests
from jinja2 import Environment, FileSystemLoader

# Get the directory of this script
MVP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(MVP_DIR)
TEMPLATES_DIR = os.path.join(MVP_DIR, "templates")

# Try to load HG key from .env (if present)
hg_key = None
env_path = os.path.join(PROJECT_ROOT, ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            if line.strip().startswith("hgbrasil="):
                hg_key = line.strip().split("=")[1].strip()
            elif line.strip().startswith("hg_key="):
                hg_key = line.strip().split("=")[1].strip()

print(f"HG Brasil API Key: {'Loaded' if hg_key else 'NOT found (running in keyless/demo mode)'}")

def get_market_data():
    # Set default realistic fallbacks
    data = {
        "currencies": {
            "USD": {"buy": 5.254, "variation": 0.12},
            "EUR": {"buy": 5.672, "variation": -0.05},
            "BTC": {"buy": 358420.00, "variation": 1.45}
        },
        "stocks": {
            "IBOVESPA": {"points": 128450, "variation": 0.35},
            "IFIX": {"points": 3242, "variation": 0.08},
            "NASDAQ": {"points": 16420, "variation": -0.22}
        }
    }
    
    url = "https://api.hgbrasil.com/finance"
    params = {}
    if hg_key:
        params["key"] = hg_key
        
    try:
        print("Querying HG Brasil Finance main endpoint...")
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            res_data = res.json().get("results", {})
            currencies = res_data.get("currencies", {})
            stocks = res_data.get("stocks", {})
            
            if currencies:
                data["currencies"]["USD"] = {
                    "buy": currencies.get("USD", {}).get("buy", data["currencies"]["USD"]["buy"]),
                    "variation": currencies.get("USD", {}).get("variation", data["currencies"]["USD"]["variation"])
                }
                data["currencies"]["EUR"] = {
                    "buy": currencies.get("EUR", {}).get("buy", data["currencies"]["EUR"]["buy"]),
                    "variation": currencies.get("EUR", {}).get("variation", data["currencies"]["EUR"]["variation"])
                }
                data["currencies"]["BTC"] = {
                    "buy": currencies.get("BTC", {}).get("buy", data["currencies"]["BTC"]["buy"]),
                    "variation": currencies.get("BTC", {}).get("variation", data["currencies"]["BTC"]["variation"])
                }
            if stocks:
                data["stocks"]["IBOVESPA"] = {
                    "points": stocks.get("IBOVESPA", {}).get("points", data["stocks"]["IBOVESPA"]["points"]),
                    "variation": stocks.get("IBOVESPA", {}).get("variation", data["stocks"]["IBOVESPA"]["variation"])
                }
                data["stocks"]["NASDAQ"] = {
                    "points": stocks.get("NASDAQ", {}).get("points", data["stocks"]["NASDAQ"]["points"]),
                    "variation": stocks.get("NASDAQ", {}).get("variation", data["stocks"]["NASDAQ"]["variation"])
                }
                # Check for IFIX index if present
                if "IFIX" in stocks:
                    data["stocks"]["IFIX"] = {
                        "points": stocks.get("IFIX", {}).get("points", 3242),
                        "variation": stocks.get("IFIX", {}).get("variation", 0.08)
                    }
            print("Successfully updated market data from HG Brasil!")
        else:
            print(f"Failed to query main endpoint (Status {res.status_code}), using fallback data.")
    except Exception as e:
        print(f"Error querying main endpoint: {e}, using fallback data.")
        
    return data

def get_stocks_data():
    default_stocks = [
        {"ticker": "PETR4", "name": "Petroleo Brasileiro SA Petrobras", "price": 38.45, "change": 0.44, "updated_at": "17:00:00"},
        {"ticker": "VALE3", "name": "Vale SA", "price": 62.10, "change": -0.85, "updated_at": "17:00:00"},
        {"ticker": "WEGE3", "name": "WEG SA", "price": 39.80, "change": 1.22, "updated_at": "17:00:00"}
    ]
    
    url = "https://api.hgbrasil.com/finance/stock_price"
    params = {"symbol": "PETR4,VALE3,WEGE3"}
    if hg_key:
        params["key"] = hg_key
        
    try:
        print("Querying HG Brasil Finance stock_price endpoint...")
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            res_data = res.json().get("results", {})
            updated_stocks = []
            for item in default_stocks:
                ticker = item["ticker"]
                stock_info = res_data.get(ticker, {})
                if stock_info:
                    updated_stocks.append({
                        "ticker": ticker,
                        "name": stock_info.get("company_name", item["name"]),
                        "price": stock_info.get("price", item["price"]),
                        "change": stock_info.get("change_percent", item["change"]),
                        "updated_at": stock_info.get("updated_at", item["updated_at"]).split()[-1]
                    })
                else:
                    updated_stocks.append(item)
            print("Successfully updated stock data from HG Brasil!")
            return updated_stocks
        else:
            print(f"Failed to query stock prices (Status {res.status_code}), using fallback stock prices.")
    except Exception as e:
        print(f"Error querying stock prices: {e}, using fallback stock prices.")
        
    return default_stocks

def main():
    market_data = get_market_data()
    stocks_data = get_stocks_data()
    
    # Render template
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("index_template.html")
    html_output = template.render(
        currencies=market_data["currencies"],
        stocks=market_data["stocks"],
        assets=stocks_data
    )
    
    # Save output to index.html
    output_path = os.path.join(MVP_DIR, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_output)
        
    print(f"\nHG Brasil MVP generated successfully at: {output_path}")

if __name__ == "__main__":
    main()
