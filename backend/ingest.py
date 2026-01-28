import os
import pandas as pd
from sqlmodel import Session
from database import engine, create_db_and_tables
from models import StockPrice, QuarterlyFinancials, EarningsSurprise

# folder with past csvs
# this project initially ran on csvs, first-time integration into SQLite
DATA_DIR = "/home/g30rgez/stockScannerApp/stockdata"

def ingest_data():
    # 1. SETUP: Create the empty table structure in the DB file
    create_db_and_tables()
    
    # 2. EXTRACT: Get a list of all CSV files
    csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
    total_files = len(csv_files)
    print(f"Found {total_files} CSV files. Starting ingestion...")
    
    with Session(engine) as session:
        
        for index, filename in enumerate(csv_files):
            symbol = filename.replace('.csv', '') # "AAPL.csv" -> "AAPL"
            file_path = os.path.join(DATA_DIR, filename)
            
            try:
                # Read the CSV
                df = pd.read_csv(file_path, index_col=0)
                
                # TRANSFORM: Ensure the index is actually a datetime object
                df.index = pd.to_datetime(df.index)
                
                # List to hold all the rows for this one stock
                prices_to_add = []
                
                for date, row in df.iterrows():
                    if pd.isna(row['Close']): 
                        continue
                    
                    # Create the Object
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
                
                # Save progress every 10 stocks
                if (index + 1) % 10 == 0:
                    session.commit()
                    print(f"Processed {index + 1}/{total_files} stocks...")

            except Exception as e:
                print(f"Skipping {symbol}: {e}")

        # Final save for the remaining stocks
        session.commit()
        print("Ingestion Complete! stocks.db is ready.")

def ingest_earnings():
    '''
    Ingests earnings into SQLite database from CSVs. See update.py.
    '''
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
                    df_fin = pd.read_csv(fin_path, index_col=0)
                    
                    df_fin = df_fin.T 
                    
                    # Convert index to datetime
                    df_fin.index = pd.to_datetime(df_fin.index, errors='coerce')
                    
                    # Iterate through the dates
                    for date, row in df_fin.iterrows():
                        if pd.isna(date): continue

                        # Create the object
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
                    df = pd.read_csv(dates_path, index_col=0)
                    
                    df.index = pd.to_datetime(df.index, errors='coerce', utc=True)

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

def reset_earnings_data():
    """Delete all earnings and surprise data from the database"""
    print("Resetting earnings data...")
    with Session(engine) as session:
        # Delete all earnings surprises
        session.exec(EarningsSurprise).delete()
        print("  Deleted all EarningsSurprise records")
        
        # Delete all quarterly financials
        session.exec(QuarterlyFinancials).delete()
        print("  Deleted all QuarterlyFinancials records")
        
        session.commit()
    print("Earnings data reset complete.\n")

# Testing/One-time
if __name__ == "__main__":
    create_db_and_tables()
    # ingest_data()       # Price History
    ingest_earnings()   # Quarterly Financials
    ingest_earnings_dates()
    # reset_earnings_data()
