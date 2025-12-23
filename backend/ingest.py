import os
import pandas as pd
from sqlmodel import Session
from database import engine, create_db_and_tables
from models import StockPrice

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

if __name__ == "__main__":
    ingest_data()