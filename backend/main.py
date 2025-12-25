from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from database import get_session
from models import StockPrice, QuarterlyFinancials, EarningsSurprise
from scanner_logic import get_values, primary_screen, fundamental_screen, vcp_analysis, backtest_primary_screen
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


@app.get("/stock/{symbol}/markers/{interval}")
def get_markers(symbol: str, interval: int = 5, session: Session = Depends(get_session)):
    """Return primary screen backtest markers for a symbol.
    Changes markers to only show points where the pass/fail status changes.

    Query params:
    - symbol: ticker symbol
    - interval: check interval (days) used when backtesting (default 5)

    Returns a list of objects: { time: 'YYYY-MM-DD', pass: bool, label?: str, color?: str }
    """
    symbol = symbol.upper()

    # get stock price history
    statement_price = select(StockPrice).where(StockPrice.symbol == symbol).order_by(StockPrice.date)
    results_price = session.exec(statement_price).all()

    if not results_price:
        raise HTTPException(status_code=404, detail="Price data not found")

    price_data = [r.model_dump() for r in results_price]

    # Build DataFrame like other endpoints
    df_price = pd.DataFrame(price_data)
    df_price.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
    df_price.set_index('date', inplace=True)

    # Ensure indicators are present
    df_price = get_values(df_price)

    # Run backtest
    try:
        series = backtest_primary_screen(df_price, int(interval))
    except Exception as e:
        print(f"Backtest failed for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    markers = []
    # series may be empty dict or Series
    if isinstance(series, pd.Series) and not series.empty:
        # 1. Identify where the current value is different from the previous value
        # We also keep the first row (index 0) because it's the start of the sequence
        change_mask = series != series.shift()
        
        # 2. Filter the series to only include these change points
        filtered_series = series[change_mask]

        # 3. Format the result
        for idx, val in filtered_series.items():
            time_str = idx.strftime('%Y-%m-%d') if isinstance(idx, pd.Timestamp) else str(idx).split('T')[0]
            markers.append({
                'time': time_str,
                'pass': bool(val)
            })

    return { 'symbol': symbol, 'markers': markers }

@app.get("/stock/{symbol}/profitability/{interval}")
def get_profitability(symbol: str, interval: int = 1, capital: int = 100000, session: Session = Depends(get_session)) -> dict:
    """This should return the trades taken for a stock based on the primary screen backtest.
    for the past year (252 trading days). It also includes the winrate, trades taken,
    longest and average trade length, final capital, average profit per winning/losing trade"""
    """Should scale this to not only be primary screens"""

    symbol = symbol.upper()
    # get stock price history
    statement_price = select(StockPrice).where(StockPrice.symbol == symbol).order_by(StockPrice.date)
    results_price = session.exec(statement_price).all()
    if not results_price:
        raise HTTPException(status_code=404, detail="Price data not found")
    price_data = [r.model_dump() for r in results_price]

    # Build DataFrame like other endpoints
    df_price = pd.DataFrame(price_data)
    df_price.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
    df_price.set_index('date', inplace=True)
    # Ensure indicators are present
    df_price = get_values(df_price)

    # get backtest markers
    try:
        series = backtest_primary_screen(df_price, int(interval))
    except Exception as e:
        print(f"Backtest failed for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    markers = []
    # series may be empty dict or Series
    if isinstance(series, pd.Series) and not series.empty:
        # 1. Identify where the current value is different from the previous value
        # We also keep the first row (index 0) because it's the start of the sequence
        change_mask = series != series.shift()
        
        # 2. Filter the series to only include these change points
        filtered_series = series[change_mask]

        # 3. Format the result
        for idx, val in filtered_series.items():
            time_str = idx.strftime('%Y-%m-%d') if isinstance(idx, pd.Timestamp) else str(idx).split('T')[0]
            markers.append({
                'time': time_str,
                'pass': bool(val)
            })
    
    # truncate to last 252 days of data for the markers
    # Find the first pass mark: then take the open of the next day as entry
    # exit is when it fails the primary screen again: take close of that day as exit
    # calculate profit/loss for each trade
    # return trades taken, winrate, longest and average trade length, final capital,
    # average profit per winning/losing trade

    markers = [m for m in markers if m['time'] >= df_price.index[-252].strftime('%Y-%m-%d')]
    PCT_ALLOC = 1 # 100% allocation per trade
    trades = []
    in_trade = False
    entry_price = 0.0
    entry_date = ""

    # Helper to find the next available trading index after a date string
    def next_trading_index(date_str):
        # find first index strictly greater than date_str
        for i in range(len(df_price)):
            idx = df_price.index[i]
            idx_str = idx.strftime('%Y-%m-%d') if isinstance(idx, pd.Timestamp) else str(idx).split('T')[0]
            if idx_str > date_str:
                return i
        return None

    # Process markers sequentially to build trades
    for m in markers:
        if not in_trade and m['pass']:
            # Entry: use the open price of the next trading day after marker time
            next_idx = next_trading_index(m['time'])
            if next_idx is None or next_idx >= len(df_price):
                # no next day available
                continue
            entry_price = df_price['Open'].iloc[next_idx]
            entry_date = df_price.index[next_idx].strftime('%Y-%m-%d') if isinstance(df_price.index[next_idx], pd.Timestamp) else str(df_price.index[next_idx]).split('T')[0]
            in_trade = True
        elif in_trade and not m['pass']:
            # Exit: use the OPEN price of the next trading day after the marker time
            next_idx = next_trading_index(m['time'])
            if next_idx is None or next_idx >= len(df_price):
                # no next day available
                continue
            exit_price = df_price['Open'].iloc[next_idx]
            exit_date = df_price.index[next_idx].strftime('%Y-%m-%d') if isinstance(df_price.index[next_idx], pd.Timestamp) else str(df_price.index[next_idx]).split('T')[0]

            # Compute P/L percent
            pnl_pct = (exit_price - entry_price) / entry_price
            trades.append({
                'entry_date': entry_date,
                'entry_price': float(entry_price),
                'exit_date': exit_date,
                'exit_price': float(exit_price),
                'pnl_pct': float(pnl_pct)
            })

            in_trade = False

    # If still in trade at the end, close at last available close
    if in_trade:
        exit_price = df_price['Close'].iloc[-1]
        exit_date = df_price.index[-1].strftime('%Y-%m-%d') if isinstance(df_price.index[-1], pd.Timestamp) else str(df_price.index[-1]).split('T')[0]
        pnl_pct = (exit_price - entry_price) / entry_price
        trades.append({
            'entry_date': entry_date,
            'entry_price': float(entry_price),
            'exit_date': exit_date,
            'exit_price': float(exit_price),
            'pnl_pct': float(pnl_pct)
        })

    # Summarize
    total_trades = len(trades)
    wins = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] <= 0]
    win_rate = (len(wins) / total_trades) if total_trades > 0 else 0.0
    avg_trade_length = 0
    longest_trade = 0
    avg_win = 0
    avg_loss = 0

    if total_trades > 0:
        lengths = []
        win_pnls = []
        loss_pnls = []
        for t in trades:
            sd = pd.to_datetime(t['entry_date'])
            ed = pd.to_datetime(t['exit_date'])
            length = (ed - sd).days
            lengths.append(length)
            if t['pnl_pct'] > 0:
                win_pnls.append(t['pnl_pct'])
            else:
                loss_pnls.append(t['pnl_pct'])

        avg_trade_length = sum(lengths) / len(lengths) if lengths else 0
        longest_trade = max(lengths) if lengths else 0
        avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0
        avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0

    # Final capital assuming starting capital and PCT_ALLOC per trade compounded
    capital_now = capital
    for t in trades:
        capital_now = capital_now * (1 + t['pnl_pct'] * PCT_ALLOC)

    result = {
        'symbol': symbol,
        'trades': trades,
        'summary': {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'longest_trade_days': longest_trade,
            'avg_trade_length_days': avg_trade_length,
            'final_capital': capital_now,
            'avg_win_pct': avg_win,
            'avg_loss_pct': avg_loss
        }
    }

    return result

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