import yfinance as yf
import json

def test():
    # Test Stock
    print("Fetching PETR4.SA...")
    petr = yf.Ticker("PETR4.SA")
    petr_info = petr.info
    print("\nPETR4 Keys:")
    print(list(petr_info.keys())[:20])
    
    # Save a slice to verify values
    subset = {k: petr_info[k] for k in ['longName', 'currentPrice', 'trailingPE', 'priceToBook', 'dividendYield', 'trailingEps', 'bookValue'] if k in petr_info}
    print("\nPETR4 Sample Data:")
    print(json.dumps(subset, indent=2))

    # Test FII
    print("\nFetching MXRF11.SA...")
    mxrf = yf.Ticker("MXRF11.SA")
    mxrf_info = mxrf.info
    print("\nMXRF11 Keys:")
    print(list(mxrf_info.keys())[:20])
    
    subset_fii = {k: mxrf_info[k] for k in ['longName', 'currentPrice', 'trailingPE', 'priceToBook', 'dividendYield', 'trailingEps', 'bookValue', 'dividendRate'] if k in mxrf_info}
    print("\nMXRF11 Sample Data:")
    print(json.dumps(subset_fii, indent=2))

if __name__ == "__main__":
    test()
