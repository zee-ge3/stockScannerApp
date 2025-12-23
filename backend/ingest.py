import os
import pandas as pd
from sqlmodel import Session
from database import engine, create_db_and_tables
from models import StockPrice, QuarterlyFinancials, EarningsSurprise

# UPDATE THIS PATH if your folder is somewhere else
DATA_DIR = "/home/g30rgez/stockScannerApp/stockdata"

def ingest_data():
    # 1. SETUP: Create the empty table structure in the DB file
    print("Creating database tables...")
    create_db_and_tables()
    
    # 2. EXTRACT: Get a list of all CSV files
    csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
    total_files = len(csv_files)
    print(f"Found {total_files} CSV files. Starting ingestion...")
    
    # Open a single session for the entire job
    # (You could also open one session per file, but this is fine for a script)
    with Session(engine) as session:
        
        for index, filename in enumerate(csv_files):
            symbol = filename.replace('.csv', '') # "AAPL.csv" -> "AAPL"
            file_path = os.path.join(DATA_DIR, filename)
            
            try:
                # Read the CSV
                # index_col=0 assumes your Date is the index (standard for yfinance)
                df = pd.read_csv(file_path, index_col=0)
                
                # TRANSFORM: Ensure the index is actually a datetime object
                # If your CSV format is messy, this line fixes the dates
                df.index = pd.to_datetime(df.index)
                
                # List to hold all the rows for this one stock
                prices_to_add = []
                
                for date, row in df.iterrows():
                    # Skip rows that are empty/NaN (common in financial data)
                    if pd.isna(row['Close']): 
                        continue
                    
                    # Create the Object (The Blueprint)
                    # Notice we do NOT pass 'id'. The DB handles that.
                    price_entry = StockPrice(
                        symbol=symbol,
                        date=date,
                        open=row['Open'],
                        high=row['High'],
                        low=row['Low'],
                        close=row['Close'],
                        volume=row['Volume']
                    )
                    prices_to_add.append(price_entry)
                
                # LOAD: Add all 200+ price rows for this stock at once
                session.add_all(prices_to_add)
                
                # Save progress every 10 stocks so we don't lose everything if it crashes
                if (index + 1) % 10 == 0:
                    session.commit()
                    print(f"Processed {index + 1}/{total_files} stocks...")

            except Exception as e:
                print(f"Skipping {symbol}: {e}")

        # Final save for the remaining stocks
        session.commit()
        print("Ingestion Complete! stocks.db is ready.")

def ingest_earnings():
    print("Starting Earnings Ingestion...")
    EARNINGS_DIR = os.path.join(DATA_DIR, "earnings")
    
    if not os.path.exists(EARNINGS_DIR):
        print(f"Error: Could not find {EARNINGS_DIR}")
        return

    # Get all ticker folders inside 'earnings/'
    ticker_folders = [f for f in os.listdir(EARNINGS_DIR) if os.path.isdir(os.path.join(EARNINGS_DIR, f))]
    
    with Session(engine) as session:
        for ticker in ticker_folders:
            print(f"Processing financials for {ticker}...")
            folder_path = os.path.join(EARNINGS_DIR, ticker)
            
            # 1. READ FINANCIALS (Revenue, Net Income, EPS)
            fin_path = os.path.join(folder_path, "financials.csv")
            if os.path.exists(fin_path):
                try:
                    # This file likely has Dates as COLUMNS and Metrics as ROWS
                    df_fin = pd.read_csv(fin_path, index_col=0)
                    
                    # TRANSPOSE: Flip it so Dates are rows
                    df_fin = df_fin.T 
                    
                    # Convert index to datetime
                    df_fin.index = pd.to_datetime(df_fin.index, errors='coerce')
                    
                    # Iterate through the dates
                    for date, row in df_fin.iterrows():
                        if pd.isna(date): continue

                        # Create the object
                        # We use .get() because column names might vary slightly
                        fin_entry = QuarterlyFinancials(
                            symbol=ticker,
                            date=date,
                            revenue=row.get("Total Revenue"),
                            net_income=row.get("Net Income"),
                            eps=row.get("Basic EPS")
                        )
                        session.add(fin_entry)
                        
                except Exception as e:
                    print(f"Error reading financials for {ticker}: {e}")

        session.commit()
    print("Earnings Ingestion Complete.")

def ingest_earnings_dates():
    EARNINGS_DIR = os.path.join(DATA_DIR, "earnings")
    print(f"Scanning earnings dates in: {EARNINGS_DIR}")
    
    ticker_folders = [f for f in os.listdir(EARNINGS_DIR) if os.path.isdir(os.path.join(EARNINGS_DIR, f))]
    
    with Session(engine) as session:
        for ticker in ticker_folders:
            folder_path = os.path.join(EARNINGS_DIR, ticker)
            dates_path = os.path.join(folder_path, "earningsdates.csv")
            
            if os.path.exists(dates_path):
                try:
                    # 1. READ: index_col=0 is usually the Date
                    df = pd.read_csv(dates_path, index_col=0)
                    
                    # 2. CLEAN DATES: Convert index to datetime
                    df.index = pd.to_datetime(df.index, errors='coerce', utc=True)

                    # 3. ITERATE
                    for date, row in df.iterrows():
                        if pd.isna(date): 
                            continue
                        
                        # Skip rows where surprisePercent is missing (usually future dates)
                        if pd.isna(row.get("surprisePercent")): 
                            continue

                        surprise_entry = EarningsSurprise(
                            symbol=ticker,
                            date=date,
                            eps_estimate=row.get("epsEstimate"),
                            eps_actual=row.get("epsActual"),
                            surprise_percent=row.get("surprisePercent")
                        )
                        session.add(surprise_entry)
                        
                    print(f"Ingested surprises for {ticker}")

                except Exception as e:
                    print(f"Error on {ticker} dates: {e}")
        
        session.commit()
    print("Earnings Surprise Ingestion Complete.")

if __name__ == "__main__":
    create_db_and_tables()
    # ingest_data()       # Price History
    # ingest_earnings()   # Quarterly Financials
    ingest_earnings_dates()
