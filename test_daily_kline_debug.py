import akshare as ak
import pandas as pd

def test_akshare_hist(symbol):
    print(f"Testing symbol: {symbol}")
    try:
        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date="20240101", end_date="20240110", adjust="qfq")
        print(f"Result shape: {df.shape}")
        if not df.empty:
            print(df.head(1))
        else:
            print("Empty DataFrame")
    except Exception as e:
        print(f"Error: {e}")

print("--- Testing '600519' (Pure Number) ---")
test_akshare_hist("600519")

print("\n--- Testing 'sh600519' (With Prefix) ---")
test_akshare_hist("sh600519")

print("\n--- Testing '000001' (Pure Number) ---")
test_akshare_hist("000001")

print("\n--- Testing 'sz000001' (With Prefix) ---")
test_akshare_hist("sz000001")

