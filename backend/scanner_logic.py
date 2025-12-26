import pandas as pd
import talib as ta
import numpy as np
import pandas_ta_classic as pta
import os

def avgNA(series):
    series = series.copy()  # Create explicit copy
    for i in range(1, len(series) - 1):
        if pd.isna(series.iloc[i]):
            idx = series.index[i]
            series.loc[idx] = (series.iloc[i - 1] + series.iloc[i + 1]) / 2
    return series

def continuous_direction(series: pd.Series, decay=0.8, weigher=5):  # this is good for EPS, Sales, and NPM
    # Sort with most recent first, handle missing data
    sorted_series = series.sort_index(ascending=False).dropna()
    if len(sorted_series) < 2:
        return 0.0  # Insufficient data
    max_abs = max(abs(sorted_series))
    if max_abs == 0 or np.isnan(max_abs):
        return 0.0

    eps = sorted_series.values / max_abs  # Normalize to [-1, 1]
    time_points = np.arange(len(eps))
    
    # 1. Recent Momentum (50% weight)
    changes = -np.diff(eps)
    weights = decay ** np.arange(len(changes))  # [1, 0.6, 0.36...]
    weighted_momentum = np.sum(changes * weights[:len(changes)]) # / np.sum(weights[:len(changes)])
    # should have a max/min of +-2?
    
    # 2. Acceleration Component (30% weight)
    if len(changes) > 1:
        accelerations = -np.diff(changes)
        accel_weights = decay ** np.arange(len(accelerations))
        weighted_accel = np.sum(accelerations * accel_weights[:len(accelerations)])# / np.sum(accel_weights[:len(accelerations)])
        # should also be +-2 
    else:
        weighted_accel = 0.0

    
    # 3. Annual Growth (20% weight) - Only if 4 quarters available
    annual_growth = (eps[0] - eps[3]) if len(eps)>=4 else 0.0
    # also +-2
    
    # Combined score with nonlinear scaling
    raw_score = weigher * (
        0.5 * weighted_momentum +  # Scale momentum
        0.3 * weighted_accel +      # Scale acceleration
        0.2 * annual_growth/4             # Raw percentage
    )
    #print(weighted_momentum)
    #print(weighted_accel)
    #print(annual_growth)
    return (np.tanh(raw_score)/(2) + 1/2)  # Bounded [0, 1]

def eps_surprise_score(surprise_series: pd.Series, decay=0.5): # need to tweak the formula
    """Calculate EPS surprise score (0-1 scale) considering magnitude and consistency"""
    # Get last 4 quarters sorted oldest-first
    sorted_surprises = surprise_series.sort_index(ascending=True).dropna().tail(4)
    if len(sorted_surprises) < 1:
        return 0.0
    
    # Calculate decaying weights [1.0, decay, decay², decay³]
    weights = decay ** np.arange(len(sorted_surprises))
    total_weights = weights.sum()
    
    # 1. Weighted magnitude component (base score)
    weighted_avg = np.sum(sorted_surprises * weights) / total_weights # average EPS surprise
    
    # 2. Consecutive positive streak bonus
    streak = 0
    for s in sorted_surprises.values:
        if np.sign(sorted_surprises.iloc[0]) * s > 0:
            streak += 1
        else:
            break
    
    # Apply streak multiplier (10% bonus per consecutive positive)
    streak_factor = 1 + 0.025 * (streak**2)

    cons_scorer = weighted_avg * streak_factor

    # 1. Recent Momentum (50% weight)
    changes = -np.diff(sorted_surprises)
    weights = decay ** np.arange(len(changes))  # [1, 0.6, 0.36...]
    weighted_momentum = np.sum(changes * weights[:len(changes)]) / np.sum(weights[:len(changes)]) # average change in EPS surprise

    formula = 1.08 * (cons_scorer * 8 + weighted_momentum * 4) # a .1 and .05 = 1
    # Final score bounded [0,1]
    return (np.tanh(formula)+1)/2

def StochRSI(series, period=13, smoothK=3, smoothD=5, periodStoch = 21):
    # Calculate RSI
    delta = series.diff().dropna()
    ups = delta * 0
    downs = ups.copy()
    ups[delta > 0] = delta[delta > 0]
    downs[delta < 0] = -delta[delta < 0]
    ups[ups.index[period-1]] = np.mean( ups[:period] ) #first value is sum of avg gains
    ups = ups.drop(ups.index[:(period-1)])
    downs[downs.index[period-1]] = np.mean( downs[:period] ) #first value is sum of avg losses
    downs = downs.drop(downs.index[:(period-1)])
    rs = ups.ewm(com=period-1,min_periods=0,adjust=False,ignore_na=False).mean() / \
         downs.ewm(com=period-1,min_periods=0,adjust=False,ignore_na=False).mean()
    rsi = 100 - 100 / (1 + rs)

    # Calculate StochRSI
    stochrsi  = 100 * (rsi - rsi.rolling(periodStoch).min()) / (rsi.rolling(periodStoch).max() - rsi.rolling(periodStoch).min())
    stochrsi_K = stochrsi.rolling(smoothK).mean()
    stochrsi_D = stochrsi_K.rolling(smoothD).mean()

    return stochrsi, stochrsi_K, stochrsi_D

def get_values(stock_df: pd.DataFrame) -> pd.DataFrame:
    df = stock_df.copy()
    df['ma50'] = ta.SMA(df['Close'], timeperiod = 50)
    df['ma150'] = ta.SMA(df['Close'],timeperiod=150)
    df['ma200'] = ta.SMA(df['Close'],timeperiod=200)
    df['ma5'] = ta.SMA(df['Close'],timeperiod=5)
    df['ma13'] = ta.SMA(df['Close'],timeperiod=13)
    df['vol_ma50'] = ta.SMA(df['Volume'], timeperiod=50)
    
    df['MACD'], df['MACD Signal'], df['MACD Hist'] = ta.MACDEXT(df['Close'], 8, 0, 13, 0, 5, 0)
    df['StochRSI'], df['k'], df['d'] = StochRSI(df['Close'])
    df['+DMI'] = ta.PLUS_DI(df['High'],df['Low'],df['Close'],timeperiod=5)
    df['-DMI'] = ta.MINUS_DI(df['High'],df['Low'],df['Close'],timeperiod=5)

    rng = np.absolute((df['Close'] - df['Close'].shift(1))/df['Close'].shift(1) * 100)
    df['volatility'] = pta.rma(pta.median(rng,10),10)
    return df

def primary_screen(df: pd.DataFrame) -> bool:
    if len(df) < 260:
        return False

    low_of_52week = round(min(df["Low"].iloc[-260:]), 2)
    high_of_52week = round(max(df["High"].iloc[-260:]), 2)
    
    MAcondition = df['Close'].iloc[-1] > df['ma50'].iloc[-1] > df['ma150'].iloc[-1] > df['ma200'].iloc[-1]
    MATrendUp = df['ma200'].iloc[-1] > df['ma200'].iloc[-21]
    withinLow = df['Close'].iloc[-1] >= (1.3*low_of_52week)
    withinHigh = df['Close'].iloc[-1] >= (.75*high_of_52week)
    # overbought = ta.RSI(df['Close'],13).iloc[-1] < 70 # filter out overbought
    minervini = MAcondition and MATrendUp and withinLow and withinHigh # and overbought

    # should seek to filter out unsustainable 1 week/1 month uptrend, alert on 4month
    if np.isnan(df['ma200'].iloc[-1]): # attempt to expose to IPOs?
        if withinHigh and df['Close'].iloc[-1] > df['ma50'].iloc[-1] > df['ma150'].iloc[-1]:
            if ta.RSI(df['Close'],13).iloc[-1] < 70: # filter out overbought
                minervini = True
    
    return minervini

# this should probably be changed to relative ranks within the industry
def fundamental_screen(df_fin: pd.DataFrame, df_surprise: pd.DataFrame) -> None | dict:
    if len(df_fin) < 4 or df_surprise is None or len(df_surprise) < 3:
        return None

    ni = avgNA(df_fin["net_income"])
    sales = avgNA(df_fin["revenue"])
    eps = avgNA(df_fin["eps"])
    npm = ni / sales.replace(0,1)
    surprise_series = avgNA(df_surprise["surprise_percent"])

    eps_score = continuous_direction(eps)
    npm_score = continuous_direction(npm)
    sales_score = continuous_direction(sales, weigher = 10)
    surprise_score = eps_surprise_score(surprise_series)

    total_score = (eps_score * 52 + 
                  npm_score * 21 + 
                  sales_score * 21 + 
                  surprise_score * 6)
    return {
        'total_score': total_score,
        'components': {
            'eps': eps_score,
            'npm': npm_score,
            'sales': sales_score,
            'surprise': surprise_score
        }
    }

def vcp_analysis(df: pd.DataFrame, end_index: int = -1) -> dict | bool:
    """
    Analyzes the stock for a Volatility Contraction Pattern (VCP) setup.
    
    Refactored to prioritize contraction identification (The "V" in VCP).
    
    Returns:
    dict: { 'pivot_point': float, 'tightness': float, 'contractions': list } if setup exists.
    bool: False if no setup.
    """
    if end_index == -1:
        end_index = len(df) - 1
        
    # Need at least ~6 months of data to find a proper base
    if end_index < 130:
        return False
        
    # Work with data up to end_index
    # We look back ~160 days for the start of the base
    start_search_idx = max(0, end_index - 160)
    subset = df.iloc[start_search_idx : end_index + 1].copy()
    
    if len(subset) < 40: return False

    # 1. Identify the Start of the Base (Highest High)
    # We ignore the most recent 15 days to ensure the high is on the left
    lookback_window = subset.iloc[:-15] 
    base_high = lookback_window['High'].max()
    base_high_idx_rel = lookback_window['High'].argmax()
    
    # 2. Identify Contractions (Wave Decomposition)
    # We scan from the Base High to the present to find the series of contractions.
    contractions = []
    
    scan_start = base_high_idx_rel
    scan_end = len(subset) - 1
    
    curr_peak_idx = scan_start
    curr_peak_val = subset['High'].iloc[curr_peak_idx]
    
    loop_count = 0
    valid_vcp_structure = True
    
    while curr_peak_idx < scan_end and loop_count < 6:
        loop_count += 1
        
        # A. Find the Trough (Lowest Low) after the current peak
        remaining = subset.iloc[curr_peak_idx+1:]
        if len(remaining) == 0:
            break
            
        trough_idx_rel = remaining['Low'].argmin()
        trough_idx = curr_peak_idx + 1 + trough_idx_rel
        trough_val = remaining['Low'].iloc[trough_idx_rel]
        
        # Calculate depth of this contraction
        depth = (curr_peak_val - trough_val) / curr_peak_val
        
        # B. Find the Next Peak after this trough
        remaining_after_trough = subset.iloc[trough_idx+1:]
        
        if len(remaining_after_trough) == 0:
             # We are at the right edge of the chart (the potential pivot area)
             # This last leg is the current contraction we are in.
             contractions.append({
                'peak_date': str(subset.index[curr_peak_idx]),
                'peak_price': float(curr_peak_val),
                'trough_date': str(subset.index[trough_idx]),
                'trough_price': float(trough_val),
                'depth_pct': round(depth * 100, 2)
            })
             break
        
        next_peak_idx_rel = remaining_after_trough['High'].argmax()
        next_peak_idx = trough_idx + 1 + next_peak_idx_rel
        next_peak_val = remaining_after_trough['High'].iloc[next_peak_idx_rel]
        
        # Check if the pattern is broken (New High significantly above Base High)
        if next_peak_val > base_high * 1.05:
            # This is a new base or an uptrend, not a VCP within the original base
            valid_vcp_structure = False
            break
            
        # Record the contraction
        contractions.append({
            'peak_date': str(subset.index[curr_peak_idx]),
            'peak_price': float(curr_peak_val),
            'trough_date': str(subset.index[trough_idx]),
            'trough_price': float(trough_val),
            'depth_pct': round(depth * 100, 2)
        })
        
        # Advance
        curr_peak_idx = next_peak_idx
        curr_peak_val = next_peak_val
        
    if not valid_vcp_structure or len(contractions) == 0:
        return False

    # 3. Validate VCP Characteristics
    
    # A. Decreasing Volatility (Depths should generally decrease)
    # We allow some noise, but the first contraction should be larger than the last.
    first_depth = contractions[0]['depth_pct']
    last_depth = contractions[-1]['depth_pct']
    
    # The primary base depth (first contraction) should not be too deep (>50%)
    if first_depth > 50.0:
        return False
        
    # The last contraction should be tight (< 15% usually, often < 10%)
    if last_depth > 15.0:
        return False
        
    # Ideally, last_depth < first_depth
    if len(contractions) > 1 and last_depth > first_depth:
        # Volatility expanded at the end? Risky.
        return False

    # 4. Validate the Pivot Point (The Setup)
    # The pivot is the high of the LAST contraction (or the current price action if tight)
    # Actually, in a VCP, the buy point is breaking above the peak of the *last* completed contraction
    # OR the high of the current tight handle.
    
    # Let's look at the most recent price action (last 10 days)
    last_10 = subset.iloc[-10:]
    
    # Tightness Check: Average Daily Range < 5%
    avg_range_pct = ((last_10['High'] - last_10['Low']) / last_10['Close']).mean() * 100
    if avg_range_pct > 5.0:
        return False
        
    # Volume Contraction Check
    if 'vol_ma50' in subset.columns:
        vol_ma50 = subset['vol_ma50'].iloc[-1]
    else:
        vol_ma50 = subset['Volume'].rolling(50).mean().iloc[-1]
        
    recent_vol_avg = last_10['Volume'].mean()
    if recent_vol_avg > vol_ma50 * 1.2: # Supply must be drying up
        return False
        
    # Define Pivot Point
    # It is the high of the most recent tight area.
    # We can use the peak of the last contraction identified.
    pivot_point = contractions[-1]['peak_price']
    
    # If the last contraction is very fresh (trough was just a few days ago),
    # the pivot might be the peak of that contraction.
    
    # Ensure current price is near the pivot (within 10-15%)
    current_price = subset['Close'].iloc[-1]
    if current_price < pivot_point * 0.85:
        return False # Too deep in the handle/contraction
        
    return {
        'pivot_point': pivot_point,
        'base_depth': first_depth,
        'tightness': avg_range_pct,
        'volume_contraction': True,
        'breakout_confirmed': False,
        'contractions': contractions
    }

def generic_backtest(df: pd.DataFrame, screen_func, check_interval: int, min_bars: int = 260) -> pd.Series:
    """
    Generic backtesting framework that applies any screen function across historical data.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with OHLCV data and precomputed indicators
    screen_func : callable
        Function that takes (df, index) and returns bool. Must handle the index parameter
        to check conditions at a specific point in time.
    check_interval : int
        How many bars to skip between checks (e.g., 5 = check every 5 days)
    min_bars : int
        Minimum number of bars required before backtesting starts (default 260)
    
    Returns:
    --------
    pd.Series
        Series with dates as index and bool values indicating screen pass/fail
    """
    if len(df) < min_bars:
        return None
    
    res = {}
    
    check_indices = list(range(min_bars, len(df), check_interval))
    if len(df) - 1 not in check_indices:
        check_indices.append(len(df) - 1)
    
    for i in check_indices:
        result = screen_func(df, i)
        res[df.index[i]] = result
        
    return pd.Series(res, name="Screen_Result")


def _primary_screen_at_index(df: pd.DataFrame, index: int) -> bool:
    """
    Helper function for backtesting primary_screen at a specific index.
    Extracts the logic from primary_screen() but works with a specific point in time.
    """
    if index < 260:
        return False
    
    low_of_52week = round(min(df["Low"].iloc[index-260:index]), 2)
    high_of_52week = round(max(df["High"].iloc[index-260:index]), 2)
    
    MAcondition = df['Close'].iloc[index] > df['ma50'].iloc[index] > df['ma150'].iloc[index] > df['ma200'].iloc[index]
    MATrendUp = df['ma200'].iloc[index] > df['ma200'].iloc[index-21]
    withinLow = df['Close'].iloc[index] >= (1.3*low_of_52week)
    withinHigh = df['Close'].iloc[index] >= (.75*high_of_52week)
    # overbought = ta.RSI(df['Close'].iloc[:index+1], 13).iloc[-1] < 70  # filter out overbought
    minervini = MAcondition and MATrendUp and withinLow and withinHigh # and overbought

    # Handle IPOs (no ma200 yet)
    if np.isnan(df['ma200'].iloc[index]):
        if withinHigh and df['Close'].iloc[index] > df['ma50'].iloc[index] > df['ma150'].iloc[index]:
            if ta.RSI(df['Close'].iloc[:index+1], 13).iloc[-1] < 70:
                minervini = True
    
    return minervini


def backtest_primary_screen(df: pd.DataFrame, check_interval: int) -> pd.Series:
    """
    Backtest the primary screen across historical data.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with OHLCV data and precomputed indicators
    check_interval : int
        How many bars to skip between checks (e.g., 5 = check every 5 days)
    
    Returns:
    --------
    pd.Series
        Series with dates as index and bool values indicating screen pass/fail
    """
    return generic_backtest(df, _primary_screen_at_index, check_interval, min_bars=260)

def check_trend_template(df: pd.DataFrame, index: int = -1) -> bool:
    """
    Checks if the stock meets the Mark Minervini Trend Template criteria at a specific index.
    
    Criteria:
    1. Price > 150MA and > 200MA
    2. 150MA > 200MA
    3. 200MA trending up for at least 1 month
    4. 50MA > 150MA and > 200MA
    5. Price > 50MA
    6. Price >= 1.3 * 52-week low
    7. Price >= 0.75 * 52-week high
    """
    if index == -1:
        index = len(df) - 1
    
    if index < 260: # Need enough data for 200MA + trend
        return False

    # Ensure we have the required columns
    required_cols = ['Close', 'Low', 'High', 'ma50', 'ma150', 'ma200']
    if not all(col in df.columns for col in required_cols):
        return False

    # Current Price
    price = df['Close'].iloc[index]
    
    # Moving Averages
    ma50 = df['ma50'].iloc[index]
    ma150 = df['ma150'].iloc[index]
    ma200 = df['ma200'].iloc[index]
    
    # Check for NaN values
    if np.isnan(ma50) or np.isnan(ma150) or np.isnan(ma200):
        return False

    # 1. Price > 150MA and > 200MA
    c1 = price > ma150 and price > ma200
    
    # 2. 150MA > 200MA
    c2 = ma150 > ma200
    
    # 3. 200MA trending up for at least 1 month (20 days)
    # We check if current MA200 > MA200 20 days ago.
    ma200_prev = df['ma200'].iloc[index - 20]
    c3 = ma200 > ma200_prev
    
    # 4. 50MA > 150MA and > 200MA
    c4 = ma50 > ma150 and ma50 > ma200
    
    # 5. Price > 50MA
    c5 = price > ma50
    
    # 6. Price >= 1.3 * 52-week low
    # 52-week low window: index-260 to index
    # We use a slice to find the min low in the last year
    low_52w = df['Low'].iloc[index-260:index+1].min()
    c6 = price >= (1.3 * low_52w)
    
    # 7. Price >= 0.75 * 52-week high (within 25% of high)
    high_52w = df['High'].iloc[index-260:index+1].max()
    c7 = price >= (0.75 * high_52w)
    
    return c1 and c2 and c3 and c4 and c5 and c6 and c7

def calculate_trade_outcome(df: pd.DataFrame, entry_date, entry_price, stop_loss, target):
    """
    Helper to determine if a trade hit its target or stop loss first.
    """
    # this hasn't implemented RS or financial data
    # Get data AFTER the entry date
    future_data = df.loc[entry_date:].iloc[1:] # Skip entry day itself
    
    for date, row in future_data.iterrows():
        low = row['Low']
        high = row['High']
        
        # Check Stop Loss (Hit on Low)
        if low <= stop_loss:
            return {'result': 'Loss', 'exit_date': date, 'exit_price': stop_loss, 'return_pct': -7.0}
            
        # Check Target (Hit on High)
        if high >= target:
            return {'result': 'Win', 'exit_date': date, 'exit_price': target, 'return_pct': 25.0}
            
    # If neither hit by end of data
    current_price = df['Close'].iloc[-1]
    pct_change = ((current_price - entry_price) / entry_price) * 100
    return {'result': 'Open', 'exit_date': df.index[-1], 'exit_price': current_price, 'return_pct': pct_change}

def run_sepa_backtest(df: pd.DataFrame) -> list:
    """
    Runs a backtest using SEPA methodology:
    1. Trend Template (Stage 2)
    2. VCP Pattern
    3. Breakout on Volume
    
    Returns a list of trade signals with outcomes.
    """
    results = []
    
    # Ensure we have calculated values
    if 'ma200' not in df.columns:
        df = get_values(df)
        
    if len(df) < 260:
        return results

    # Iterate through the dataframe starting from when we have enough data
    # We check every day for a breakout signal
    i = 260
    while i < len(df):
        
        # 1. Check Trend Template
        if not check_trend_template(df, i):
            i += 1
            continue
            
        # 2. Check VCP Pattern (Setup)
        setup = vcp_analysis(df, end_index=i-1)
        
        if not setup:
            i += 1
            continue
            
        # 3. Check for Breakout
        pivot = setup['pivot_point']
        current_close = df['Close'].iloc[i]
        
        if current_close > pivot:
            
            # 4. Volume Confirmation
            vol = df['Volume'].iloc[i]
            avg_vol = df['vol_ma50'].iloc[i]
            
            if np.isnan(avg_vol) or avg_vol == 0:
                vol_cond = True 
            else:
                vol_cond = vol > (1.5 * avg_vol)
            
            if vol_cond:
                # Trade Parameters
                entry_price = current_close
                stop_loss = pivot * 0.93
                target = pivot * 1.25
                
                # Calculate Outcome
                outcome = calculate_trade_outcome(df, df.index[i], entry_price, stop_loss, target)
                
                # Record the signal
                results.append({
                    'date': df.index[i],
                    'price': entry_price,
                    'pivot': pivot,
                    'stop_loss': stop_loss,
                    'target': target,
                    'type': 'Buy',
                    'reason': 'SEPA VCP Breakout',
                    'tightness': setup['tightness'],
                    'contractions': setup['contractions'],
                    **outcome # Merge outcome data (result, exit_date, return_pct)
                })
                
                # Skip ahead to avoid duplicate signals?
                # If we entered a trade, we shouldn't enter another one until this one is done or some time passes.
                # Let's skip 20 days to avoid buying the same breakout multiple times.
                i += 20 
                continue
        
        i += 1
                    
    return results

if __name__ == "__main__":
    #t = pd.read_csv("/home/g30rgez/stockScannerApp/stockdata/ADPT.csv")
    #t = get_values(t)
    #print(backtest_primary_screen(t, 5))
    pass