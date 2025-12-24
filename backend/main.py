from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from database import get_session
from models import StockPrice, QuarterlyFinancials, EarningsSurprise
from scanner_logic import get_values, primary_screen, fundamental_screen, vcp_analysis
import pandas as pd
from update import update_prices, update_fundamentals_full, update_specific_ticker

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    # This is the "Guest List". Only requests from this URL are allowed.
    allow_origins=["http://localhost:5173", "http://192.168.1.125:5173"], 
    allow_credentials=True,
    allow_methods=["*"], # Allow all types of requests (GET, POST, etc.)
    allow_headers=["*"],
)

@app.get("/scan")
def run_primary_scan(session: Session = Depends(get_session)):
    passed_stocks = []
    
    # 1. Fetch Symbols
    statement = select(StockPrice.symbol).distinct()
    symbols = session.exec(statement).all()
    
    for symbol in symbols:
        try:
            # --- STEP A: Technical Screen (Prices) ---
            statement_price = select(StockPrice).where(StockPrice.symbol == symbol).order_by(StockPrice.date)
            results_price = session.exec(statement_price).all()
            
            if not results_price: continue
            
            df_price = pd.DataFrame([r.model_dump() for r in results_price])
            df_price.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
            df_price.set_index('date', inplace=True)

            if len(df_price) < 200:
                continue

            # Run Technical Analysis
            df_price = get_values(df_price)
            if not primary_screen(df_price):
                continue # Failed technicals, skip

            # --- STEP B: Fundamental Screen (Financials) ---
            # If it passed technicals, we fetch the data needed for the Score
            
            # 1. Fetch Financials
            statement_fin = select(QuarterlyFinancials).where(QuarterlyFinancials.symbol == symbol).order_by(QuarterlyFinancials.date)
            results_fin = session.exec(statement_fin).all()
            
            # 2. Fetch Surprise
            statement_surprise = select(EarningsSurprise).where(EarningsSurprise.symbol == symbol).order_by(EarningsSurprise.date)
            results_surprise = session.exec(statement_surprise).all()

            # 3. Calculate Score
            score = 0
            if results_fin and results_surprise:
                df_fin = pd.DataFrame([r.model_dump() for r in results_fin])
                df_fin.set_index('date', inplace=True)
                
                df_surprise = pd.DataFrame([r.model_dump() for r in results_surprise])
                df_surprise.set_index('date', inplace=True)
                
                # Run your custom scoring logic
                score_result = fundamental_screen(df_fin, df_surprise)
                
                # fundamental_screen returns a DICT or None
                if score_result:
                    score = score_result['total_score']
            
            # --- STEP C: Add to Results ---
            # We append the OBJECT (Dictionary), not just the string
            passed_stocks.append({
                "symbol": symbol,
                "score": int(score) # Ensure it's a number
            })

        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")

    # Sort by Score (Highest First)
    passed_stocks.sort(key=lambda x: x['score'], reverse=True)

    return {"passed_stocks": passed_stocks, "scanned_count": len(symbols)}

@app.get("/")
def read_root():
    return {"message": "Welcome to the Stock Scanner API"}

@app.get("/stock/{symbol}")
def get_stock_detail(symbol: str, session: Session = Depends(get_session)):
    symbol = symbol.upper() 
    
    # get stock price history
    statement_price = select(StockPrice).where(StockPrice.symbol == symbol).order_by(StockPrice.date)
    results_price = session.exec(statement_price).all()

    if not results_price:
        raise HTTPException(status_code=404, detail="Price data not found")

    # Grab the last year of data
    price_data = [r.model_dump() for r in results_price]

    # 1. Fetch Financials
    statement_fin = select(QuarterlyFinancials).where(QuarterlyFinancials.symbol == symbol).order_by(QuarterlyFinancials.date)
    results_fin = session.exec(statement_fin).all()
    
    if not results_fin:
        raise HTTPException(status_code=404, detail="Financial data not found")

    # 2. Fetch Surprise
    statement_surprise = select(EarningsSurprise).where(EarningsSurprise.symbol == symbol).order_by(EarningsSurprise.date)
    results_surprise = session.exec(statement_surprise).all()
    
    # 3. Calculate Score
    # We reconstruct the DataFrames just like in the scanner
    df_fin = pd.DataFrame([r.model_dump() for r in results_fin])
    df_fin.set_index('date', inplace=True)
    
    df_surprise = pd.DataFrame()
    if results_surprise:
        df_surprise = pd.DataFrame([r.model_dump() for r in results_surprise])
        df_surprise.set_index('date', inplace=True)
    
    # Use your custom logic function
    score_dict = fundamental_screen(df_fin, df_surprise)

    if score_dict is None:
        raise HTTPException(status_code=404, detail="Fundamental data not found")

    # 4. Run VCP Analysis
    df_price = pd.DataFrame(price_data)
    df_price.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
    df_price.set_index('date', inplace=True)
    
    vcp_data = vcp_analysis(df_price)
    if vcp_data and isinstance(vcp_data, dict):
        # Convert negative indices to dates for the frontend
        contractions_with_dates = []
        for c in vcp_data.get('contractions', []):
            peak_idx = c['peak_index']
            trough_idx = c['trough_index']
            
            # Get actual dates from the dataframe
            peak_date = df_price.index[peak_idx].strftime('%Y-%m-%d') if isinstance(df_price.index[peak_idx], pd.Timestamp) else str(df_price.index[peak_idx]).split('T')[0]
            trough_date = df_price.index[trough_idx].strftime('%Y-%m-%d') if isinstance(df_price.index[trough_idx], pd.Timestamp) else str(df_price.index[trough_idx]).split('T')[0]
            
            contractions_with_dates.append({
                'peak_date': peak_date,
                'peak_price': c['peak_price'],
                'trough_date': trough_date,
                'trough_price': c['trough_price'],
                'depth': c['depth']
            })
        vcp_result = {
            'contractions': contractions_with_dates,
            'highest_high': vcp_data.get('highest_high'),
            'lowest_low': vcp_data.get('lowest_low'),
            'base_length_days': vcp_data.get('base_length_days'),
            'base_depth_percent': vcp_data.get('base_depth_percent'),
            'breakout_confirmed': vcp_data.get('breakout_confirmed'),
            'current_price': vcp_data.get('current_price')
        }
    else:
        vcp_result = None

    # 5. Return everything needed for the UI
    return {
        "symbol": symbol,
        "total_score": score_dict.get("total_score"),
        "components": score_dict.get("components"),
        # We send the raw records so the frontend can display a table of the last 4 quarters
        "financials": [r.model_dump() for r in results_fin[-4:]], # Last 4 quarters
        "surprises": [r.model_dump() for r in results_surprise[-4:]] if results_surprise else [],
        "prices": price_data,
        "vcp_analysis": vcp_result
    }

@app.post("/update")
def trigger_update(session: Session = Depends(get_session)):
    """
    Triggers the Yahoo Finance download for all stocks.
    """
    try:
        # We run the update logic inside the API call
        # Note: For 500 stocks, this might take 1-2 minutes.
        # Ideally this runs in a background task, but for a personal app, waiting is fine.
        update_prices(session)
        return {"status": "success", "message": "Prices updated successfully"}
    except Exception as e:
        print(f"Update failed: {e}")
        return {"status": "error", "message": str(e)}
    
@app.post("/update-earnings")
def trigger_earnings_update():
    """
    Triggers the heavy earnings download and ingestion.
    WARNING: This can take a long time (minutes to hours).
    """
    try:
        print("Starting Earnings Update via API...")
        # Note: This will block the server until finished. 
        # For a local app, this is fine, but the UI will spin for a while.
        update_fundamentals_full()
        return {"status": "success", "message": "Earnings data updated successfully"}
    except Exception as e:
        print(f"Earnings update failed: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/refresh-stock/{symbol}")
def refresh_specific_stock(symbol: str, session: Session = Depends(get_session)):
    """
    Refreshes price data for a specific stock ticker.
    Downloads all available historical data from Yahoo Finance.
    """
    try:
        symbol = symbol.upper()
        print(f"Refreshing data for {symbol}...")
        rows_added = update_specific_ticker(session, symbol)
        
        if rows_added is not None:
            return {
                "status": "success", 
                "message": f"Successfully updated {symbol} with {rows_added} days of data",
                "rows_added": rows_added
            }
        else:
            return {
                "status": "error", 
                "message": f"Failed to update {symbol}. Stock may not exist or no data available."
            }
    except Exception as e:
        print(f"Refresh failed for {symbol}: {e}")
        return {"status": "error", "message": str(e)}