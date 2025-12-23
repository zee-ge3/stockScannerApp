from fastapi import FastAPI
import pandas as pd
import os
from scanner_logic import get_values, primary_screen

app = FastAPI()

# Path to your stock data folder
DATA_DIR = "/home/g30rgez/stockScannerApp/stockdata"

@app.get("/scan")
def run_scan():
    passed_stocks = []
    
    # Limit to first 20 for testing speed
    tickers = [f.replace('.csv', '') for f in os.listdir(DATA_DIR) if f.endswith('.csv')][:20]
    
    for ticker in tickers:
        try:
            df = pd.read_csv(f"{DATA_DIR}/{ticker}.csv", index_col=0)
            df = get_values(df)

            if primary_screen(df):
                passed_stocks.append(ticker)
        except Exception as e:
            print(f"Error scanning {ticker}: {e}")
            
    return {"result": passed_stocks}