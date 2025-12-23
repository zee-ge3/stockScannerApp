from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from database import get_session
from models import StockPrice
from scanner_logic import get_values, primary_screen
import pandas as pd

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    # This is the "Guest List". Only requests from this URL are allowed.
    allow_origins=["http://localhost:5173"], 
    allow_credentials=True,
    allow_methods=["*"], # Allow all types of requests (GET, POST, etc.)
    allow_headers=["*"],
)

@app.get("/scan")
def run_scan(session: Session = Depends(get_session)):
    passed_stocks = []
    
    # 1. Get a list of unique symbols
    # (In the future, we will have a Ticker table for this to be faster)
    print("Fetching symbols...")
    statement = select(StockPrice.symbol).distinct()
    symbols = session.exec(statement).all()
    
    # LIMIT to 50 for testing speed right now
    # If you remove this, it will scan all 500+ stocks
    test_symbols = symbols[:50] 

    for symbol in test_symbols:
        # 2. Query the DB for this specific stock
        statement = select(StockPrice).where(StockPrice.symbol == symbol).order_by(StockPrice.date)
        results = session.exec(statement).all()
        
        if not results:
            continue
            
        # 3. Convert SQL objects to a Pandas DataFrame
        # We convert the list of objects [StockPrice(...), StockPrice(...)] to a dict
        data = [r.model_dump() for r in results]
        df = pd.DataFrame(data)
        
        # 4. FIX: Rename columns to match what scanner_logic expects
        # SQL is lowercase, Logic expects Title Case
        df.rename(columns={
            "open": "Open", 
            "high": "High", 
            "low": "Low", 
            "close": "Close", 
            "volume": "Volume"
        }, inplace=True)
        
        # Set the Date as the index (required by your logic)
        df.set_index('date', inplace=True)

        # 5. Run Your Logic
        try:
            df = get_values(df) # Calculate indicators
            if primary_screen(df): # Check Minervini conditions
                passed_stocks.append(symbol)
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")

    return {"passed_stocks": passed_stocks, "scanned_count": len(test_symbols)}


@app.get("/")
def read_root():
    return {"message": "Welcome to the Stock Scanner API"}