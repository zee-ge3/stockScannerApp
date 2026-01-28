from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from database import get_session
from models import StockPrice, QuarterlyFinancials, EarningsSurprise
from scanner_logic import get_values, primary_screen, fundamental_screen, vcp_analysis, backtest_primary_screen, run_sepa_backtest, check_trend_template
import pandas as pd
from update import update_prices, update_fundamentals_full, update_specific_ticker

app = FastAPI()
# This is the core scanner logic. Base for the web backend, calls on algorithms in scanner_logic.


app.add_middleware(
    CORSMiddleware,
    # frontend port needs to be able to access
    allow_origins=["http://localhost:5173", "http://192.168.1.125:5173"], 
    allow_credentials=True,
    allow_methods=["*"], # Allow all types of requests (GET, POST, etc.)
    allow_headers=["*"],
)

@app.get("/scan")
def run_primary_scan(session: Session = Depends(get_session)):
    '''
    Main scan.
    '''
    passed_stocks = []
    
    # 1. Fetch Symbols
    statement = select(StockPrice.symbol).distinct()
    symbols = session.exec(statement).all()
    
    for symbol in symbols:
        try:
            # techincal screen, SQL query
            statement_price = select(StockPrice).where(StockPrice.symbol == symbol).order_by(StockPrice.date)
            results_price = session.exec(statement_price).all()
            
            if not results_price: continue
            
            df_price = pd.DataFrame([r.model_dump() for r in results_price])
            # rename to use legacy algorithm
            df_price.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
            df_price.set_index('date', inplace=True)

            if len(df_price) < 260: # Need enough data for SEPA
                continue

            # Run Technical Analysis
            df_price = get_values(df_price)
            
            # Financial screen
            # filter by Score > 70 FIRST to save processing time
            
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
                
                score_result = fundamental_screen(df_fin, df_surprise)
                if score_result:
                    score = score_result['total_score']
            
            # Filter: Must have Score >= 70
            if score < 70:
                continue

            # SEPA VCP analysis
            # We check if it broke out today, yesterday, or is setting up.
            
            # 1. Check Trend Template (Must be in Stage 2)
            if not check_trend_template(df_price, index=-1):
                continue

            # 2. Check VCP Setup
            setup = vcp_analysis(df_price, end_index=-1)
            
            status = None
            pivot = 0.0
            
            if setup:
                # It is currently in a setup (Pre-Breakout)
                status = "Setting Up"
                pivot = setup['pivot_point']
            else:
                # Check if it broke out TODAY
                # We need to see if there was a valid setup YESTERDAY that triggered TODAY
                setup_yesterday = vcp_analysis(df_price, end_index=-2)
                if setup_yesterday:
                    pivot_yest = setup_yesterday['pivot_point']
                    if df_price['Close'].iloc[-1] > pivot_yest and df_price['Close'].iloc[-2] <= pivot_yest:
                         status = "Breakout Today"
                         pivot = pivot_yest
                
                # Check if it broke out YESTERDAY
                if not status:
                    setup_2days = vcp_analysis(df_price, end_index=-3)
                    if setup_2days:
                        pivot_2d = setup_2days['pivot_point']
                        if df_price['Close'].iloc[-2] > pivot_2d and df_price['Close'].iloc[-3] <= pivot_2d:
                            status = "Breakout Yesterday"
                            pivot = pivot_2d

            if status:
                passed_stocks.append({
                    "symbol": symbol,
                    "score": int(score),
                    "status": status,
                    "pivot": pivot,
                    "price": df_price['Close'].iloc[-1]
                })

        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")

    # Sort by Status (Breakouts first) then Score
    # Custom sort order: Breakout Today > Breakout Yesterday > Setting Up
    status_order = {"Breakout Today": 0, "Breakout Yesterday": 1, "Setting Up": 2}
    passed_stocks.sort(key=lambda x: (status_order.get(x['status'], 99), -x['score']))

    return {"passed_stocks": passed_stocks, "scanned_count": len(symbols)}

@app.get("/")
def read_root():
    return {"message": "Welcome to the Stock Scanner API"}

@app.get("/stock/{symbol}")
def get_stock_detail(symbol: str, session: Session = Depends(get_session)):
    '''
    Stock specific scanning.
    '''
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
    # reconstruct the DataFrames just like in the scanner
    df_fin = pd.DataFrame([r.model_dump() for r in results_fin])
    df_fin.set_index('date', inplace=True)
    
    df_surprise = pd.DataFrame()
    if results_surprise:
        df_surprise = pd.DataFrame([r.model_dump() for r in results_surprise])
        df_surprise.set_index('date', inplace=True)
    
    score_dict = fundamental_screen(df_fin, df_surprise)

    if score_dict is None:
        raise HTTPException(status_code=404, detail="Fundamental data not found")

    # 4. Run VCP Analysis
    df_price = pd.DataFrame(price_data)
    df_price.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
    df_price.set_index('date', inplace=True)
    
    vcp_data = vcp_analysis(df_price)
    if vcp_data and isinstance(vcp_data, dict):
        # The new vcp_analysis returns dates directly
        contractions_with_dates = []
        for c in vcp_data.get('contractions', []):
            p_date = str(c['peak_date'])
            if ' ' in p_date: p_date = p_date.split(' ')[0]
            if 'T' in p_date: p_date = p_date.split('T')[0]
            
            t_date = str(c['trough_date'])
            if ' ' in t_date: t_date = t_date.split(' ')[0]
            if 'T' in t_date: t_date = t_date.split('T')[0]

            contractions_with_dates.append({
                'peak_date': p_date,
                'peak_price': c['peak_price'],
                'trough_date': t_date,
                'trough_price': c['trough_price'],
                'depth': c.get('depth_pct', c.get('depth'))
            })
            
        vcp_result = {
            'contractions': contractions_with_dates,
            'breakout_confirmed': vcp_data.get('breakout_confirmed'),
            'base_depth_percent': vcp_data.get('base_depth', 0),
            'base_length_days': 0 # Not calculated in new logic yet
        }
    else:
        vcp_result = None

    # 5. Return everything needed for the UI
    return {
        "symbol": symbol,
        "total_score": score_dict.get("total_score"),
        "components": score_dict.get("components"),
        # send the raw records so the frontend can display a table of the last 4 quarters
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
        # should be in the background
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
        # might block the app
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

@app.get("/backtest/{symbol}")
def backtest_stock(symbol: str, session: Session = Depends(get_session)):
    # Fetch data
    statement = select(StockPrice).where(StockPrice.symbol == symbol).order_by(StockPrice.date)
    results = session.exec(statement).all()
    
    if not results:
        raise HTTPException(status_code=404, detail="Stock not found")
        
    df = pd.DataFrame([r.model_dump() for r in results])
    df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
    df.set_index('date', inplace=True)
    
    # Filter for last 2 years (approx 520 trading days)
    # But we need 260 days prior for MA calculation, so we need ~780 days total if available
    # Or we just run the backtest on the whole history and filter the RESULTS.
    
    # Run Backtest on full history to ensure MAs are correct
    all_trades = run_sepa_backtest(df)
    
    # Filter trades to only those in the last 2 years
    cutoff_date = pd.Timestamp.now() - pd.DateOffset(years=2)
    recent_trades = [t for t in all_trades if t['date'] >= cutoff_date]
    
    return {"symbol": symbol, "trades": recent_trades}

@app.post("/backtest-portfolio")
def backtest_portfolio(symbols: list[str], session: Session = Depends(get_session)):
    """
    Runs SEPA backtest on a list of symbols and calculates cumulative return.
    Assumes $100,000 allocated to EACH stock independently (not a shared portfolio).
    Ensures full historical data is available for each stock before running.
    """
    portfolio_results = []
    total_initial_capital = len(symbols) * 100000
    total_final_capital = 0
    
    for symbol in symbols:
        symbol = symbol.upper()
        try:
            # 1. Ensure we have FULL history for this stock
            # We check if we have data, and if the data starts reasonably long ago (e.g. > 2 years ago)
            statement = select(StockPrice).where(StockPrice.symbol == symbol).order_by(StockPrice.date)
            results = session.exec(statement).all()
            
            needs_update = False
            if not results:
                needs_update = True
            else:
                # Check if data is updated (last date < today - 3 days)
                last_date = results[-1].date
                if last_date.date() < (pd.Timestamp.now() - pd.Timedelta(days=3)).date():
                    needs_update = True
                
                # Check if data is too short (start date > 2 years ago)
                start_date = results[0].date
                required_start = pd.Timestamp.now() - pd.DateOffset(years=3)
                if start_date > required_start:
                    needs_update = True

            if needs_update:
                print(f"Downloading full history for {symbol}...")
                update_specific_ticker(session, symbol)
                # Re-fetch after update
                results = session.exec(statement).all()
            
            if not results:
                print(f"Skipping {symbol}: No data found after update attempt.")
                continue
                
            df = pd.DataFrame([r.model_dump() for r in results])
            df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
            df.set_index('date', inplace=True)
            
            # Run Backtest
            trades = run_sepa_backtest(df)
            
            # Calculate Performance for this stock
            # Start with 100k
            capital = 100000.0
            
            # Filter for last 2 years to match the single stock view 
            cutoff_date = pd.Timestamp.now() - pd.DateOffset(years=2)
            recent_trades = [t for t in trades if t['date'] >= cutoff_date]
            
            for t in recent_trades:
                # return_pct is in percent (e.g. 7.5 for 7.5%)
                # Capital grows by this percent
                pct = t['return_pct'] / 100.0
                capital = capital * (1 + pct)
                
            total_final_capital += capital
            
            portfolio_results.append({
                "symbol": symbol,
                "trades_count": len(recent_trades),
                "final_capital": round(capital, 2),
                "return_pct": round(((capital - 100000) / 100000) * 100, 2)
            })
            
        except Exception as e:
            print(f"Error backtesting {symbol}: {e}")
            continue
            
    # Aggregate
    total_return_pct = ((total_final_capital - total_initial_capital) / total_initial_capital) * 100 if total_initial_capital > 0 else 0
    
    return {
        "summary": {
            "total_initial_capital": total_initial_capital,
            "total_final_capital": round(total_final_capital, 2),
            "total_return_pct": round(total_return_pct, 2),
            "stocks_tested": len(portfolio_results)
        },
        "details": portfolio_results
    }