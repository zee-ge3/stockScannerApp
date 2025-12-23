import yfinance as yf
from sqlmodel import Session, select, func, delete
from database import engine
from models import StockPrice, QuarterlyFinancials, EarningsSurprise
from datetime import timedelta, datetime
import pandas as pd
import requests
import math
import time
import os
from ingest import ingest_earnings, ingest_earnings_dates

def get_tickers(filtered=True):
    print("Fetching tickers from Nasdaq...")
    url = 'https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true'

    headers = {
        'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36'
    }
    
    try:
        resp = requests.get(url, headers=headers)
        json_data = resp.json()
        df = pd.DataFrame(json_data['data']['rows'], columns=json_data['data']['headers'])
        df.to_csv('nasdaqauto.csv', index=False) # Helper file for debugging

        # Filter for things that have value
        if filtered:
            # Clean weird formatting in volume column if necessary
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0)
            df = df[df['volume'].astype(int) >= 50000]

        df = df[~df['name'].str.contains('|'.join(['Preferred', 'Warrant', 'Notes', 'Debenture', 'Right', "%"]), case=True, na=False)]

        # Filter for naming conventions
        symbols = df["symbol"]
        
        # convert DataFrame to list, then to sets
        symbols = set(symbols.tolist())
        symbols = {x for x in symbols if not (isinstance(x, float) and math.isnan(x))}
        
        # Some stocks are 5 characters. Those stocks with the suffixes listed below are not of interest.
        my_list = ['W', 'R', 'P', 'Q']
        sav_set = set()
        
        for symbol in symbols:
            # Filter out symbols with ^ (indices) or bad suffixes
            if (len(symbol) > 4 and symbol[-1] in my_list) or ("^" in symbol):
                continue
            else:
                sav_set.add(symbol)
        
        tickers = list(sav_set)
        tickers = [item.replace(".", "-") for item in tickers] # Yahoo Finance uses dashes instead of dots
        tickers = [item.replace("/", "-") for item in tickers] 
        tickers = [_.strip() for _ in tickers]

        print(f"Found {len(tickers)} valid tickers.")
        return tickers
    
    except Exception as e:
        print(f"Error fetching Nasdaq tickers: {e}")
        return []

# --- CLEANUP LOGIC ---
def sync_tickers(session: Session, valid_tickers: list):
    """
    Removes any ticker from the DB that is NOT in the valid_tickers list.
    """
    print("Syncing Database with Nasdaq list...")
    
    # 1. Get all symbols currently in DB
    db_symbols = session.exec(select(StockPrice.symbol).distinct()).all()
    db_set = set(db_symbols)
    valid_set = set(valid_tickers)
    
    # 2. Identify Invalid Symbols (In DB but not in Nasdaq list)
    tickers_to_remove = list(db_set - valid_set)
    
    if not tickers_to_remove:
        print("Database is clean. No tickers to remove.")
        return

    print(f"Removing {len(tickers_to_remove)} obsolete tickers (e.g., {tickers_to_remove[:5]}...)")
    
    # 3. Delete them from ALL tables
    # Note: This might take a moment if you have tons of data
    for table in [StockPrice, QuarterlyFinancials, EarningsSurprise]:
        statement = delete(table).where(table.symbol.in_(tickers_to_remove))
        session.exec(statement)
    
    session.commit()
    print("Cleanup complete.")

# --- UPDATE LOGIC ---
def update_prices(session: Session):
    # 1. Get the Master List from Nasdaq
    nasdaq_tickers = get_tickers(filtered=True)
    
    if not nasdaq_tickers:
        print("Aborting update: Failed to fetch tickers.")
        return

    # 2. Remove bad tickers from DB
    sync_tickers(session, nasdaq_tickers)
    
    # 3. Update/Add tickers from the Master List
    print(f"--- Updating Prices for {len(nasdaq_tickers)} Stocks ---")
    
    for i, symbol in enumerate(nasdaq_tickers):
        try:
            # Find the last recorded date for this stock
            statement = select(func.max(StockPrice.date)).where(StockPrice.symbol == symbol)
            last_date = session.exec(statement).one()
            
            if not last_date:
                # NEW STOCK: Download roughly 1 year of data
                start_date = (datetime.today() - timedelta(days=505)).strftime('%Y-%m-%d')
                print(f"New Stock Found: {symbol}")
            else:
                # EXISTING STOCK: Start from next day
                start_date = (last_date + timedelta(days=1)).strftime('%Y-%m-%d')

            # If up to date, skip
            if last_date and last_date.date() >= datetime.today().date():
                continue

            # Download
            df = yf.download(symbol, start=start_date, progress=False)
            
            if df.empty:
                continue

            # Add to DB
            new_rows = []
            for date, row in df.iterrows():
                # Safe access for yfinance multi-index
                def get_val(col_name):
                    val = row[col_name]
                    return float(val.iloc[0]) if isinstance(val, pd.Series) else float(val)

                price = StockPrice(
                    symbol=symbol,
                    date=date,
                    open=get_val('Open'),
                    high=get_val('High'),
                    low=get_val('Low'),
                    close=get_val('Close'),
                    volume=get_val('Volume')
                )
                new_rows.append(price)
            
            if new_rows:
                session.add_all(new_rows)
                session.commit()
                print(f"[{i+1}/{len(nasdaq_tickers)}] Updated {symbol}: +{len(new_rows)} days")
            
            # Rate limit protection
            time.sleep(0.1) 
            
        except Exception as e:
            print(f"Failed to update {symbol}: {e}")
            time.sleep(1)

def ticker_earnings(tickers):
    print(f"--- Starting Heavy Download for {len(tickers)} stocks ---")
    success_list = []
    failed_list = []
    
    # Create base directory if not exists
    os.makedirs('stockdata/earnings', exist_ok=True)

    try:
        for i, ticker in enumerate(tickers):
            print(f"[{i+1}/{len(tickers)}] Downloading {ticker}...")
            try:
                t = yf.Ticker(ticker)
                
                # Check 1: Earnings History (Dates & Surprise)
                # Note: yfinance attribute might be 'earnings_dates' or 'earnings_history' depending on version
                try:
                    earnings = t.earnings_dates 
                except:
                    earnings = t.earnings_history

                if earnings is not None and not earnings.empty:
                     # Standardize index to avoid timezone issues
                    if earnings.index.tz is not None:
                        earnings.index = earnings.index.tz_localize(None)

                    # Ensure we have data
                    if not earnings.isna().all().all():
                        os.makedirs(f'stockdata/earnings/{ticker}', exist_ok=True)
                        earnings.to_csv(f'stockdata/earnings/{ticker}/earningsdates.csv')
                        
                        # Check 2: Quarterly Financials
                        qf = t.quarterly_financials
                        if qf is not None and not qf.empty:
                            qf.to_csv(f'stockdata/earnings/{ticker}/financials.csv')
                            
                        success_list.append(ticker)
                    else:
                        failed_list.append(ticker)
                else:
                    failed_list.append(ticker)
                    
                # Rate Limit Sleep (Crucial for heavy downloads)
                time.sleep(0.5) 

            except Exception:
                # print(f"yfinance overload on {ticker}")
                # print(traceback.format_exc())
                failed_list.append(ticker)
                
    finally:
        if success_list:
            pd.DataFrame(success_list).to_csv("success_earnings.csv", index=False)
            print(f"Successfully downloaded {len(success_list)} stocks.")
        if failed_list:
            pd.DataFrame(failed_list).to_csv("failed_earnings.csv", index=False)

def update_fundamentals_full():
    """
    This runs your HEAVY logic.
    1. Download CSVs using ticker_earnings()
    2. Read CSVs into DB using ingest functions
    """
    # 1. Get List
    tickers = get_tickers(filtered=True)
    
    # 2. Download CSVs (Your Logic)
    ticker_earnings(tickers)
    
    # 3. Ingest CSVs into Database
    print("--- Ingesting Downloaded CSVs into Database ---")
    ingest_earnings()       # From ingest.py
    ingest_earnings_dates() # From ingest.py
    print("--- Fundamentals Update Complete ---")

if __name__ == "__main__":
    with Session(engine) as session:
        update_prices(session)
        # update_fundamentals_full()