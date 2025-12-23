import pandas as pd
import numpy as np
import pandas_ta_classic as pta
import os

try:
    import talib as ta
except ImportError:
    # Create a mock class/object for ta if not found
    class MockTalib:
        def SMA(self, series, timeperiod=30):
            return series.rolling(window=timeperiod).mean()

        def RSI(self, series, timeperiod=14):
            # Approximation of RSI
            delta = series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=timeperiod).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=timeperiod).mean()
            rs = gain / loss
            return 100 - (100 / (1 + rs))

        def MACDEXT(self, series, fastperiod=12, fastmatype=0, slowperiod=26, slowmatype=0, signalperiod=9, signalmatype=0):
            # Very basic MACD approximation
            ema_fast = series.ewm(span=fastperiod, adjust=False).mean()
            ema_slow = series.ewm(span=slowperiod, adjust=False).mean()
            macd = ema_fast - ema_slow
            signal = macd.ewm(span=signalperiod, adjust=False).mean()
            hist = macd - signal
            return macd, signal, hist

        def PLUS_DI(self, high, low, close, timeperiod=14):
             return pd.Series(np.zeros(len(close)), index=close.index) # Dummy

        def MINUS_DI(self, high, low, close, timeperiod=14):
             return pd.Series(np.zeros(len(close)), index=close.index) # Dummy

    ta = MockTalib()

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
    overbought = ta.RSI(df['Close'],13).iloc[-1] < 70 # filter out overbought
    minervini = MAcondition and MATrendUp and withinLow and withinHigh and overbought

    # should seek to filter out unsustainable 1 week/1 month uptrend, alert on 4month
    if np.isnan(df['ma200'].iloc[-1]): # attempt to expose to IPOs?
        if withinHigh and df['Close'].iloc[-1] > df['ma50'].iloc[-1] > df['ma150'].iloc[-1]:
            if ta.RSI(df['Close'],13).iloc[-1] < 70: # filter out overbought
                minervini = True
    
    return minervini

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

def vcp_analysis(df: pd.DataFrame) -> dict | bool:
    """
    Analyzes the base pattern of a stock price, focusing on contractions and their decreasing nature.


    Parameters:
    df (pandas.DataFrame): DataFrame containing stock price data with columns ['Open', 'High', 'Low', 'Close', 'Volume'].

    Returns:
    dict: A dictionary containing analysis results such as contractions, breakout confirmation, etc.
    """

    if len(df) < 150: return False
    # Parameters for analysis
    percentage_threshold = 10  # Percentage drop to identify a peak after retracement

    # 1. Identify the highest high in the last 126 days (approx. 6 months)
    highestHigh = df['High'].iloc[-150]
    highBar = -150
    for i in range(-149, -5):
        if df['High'].iloc[i] > highestHigh:
            highestHigh = df['High'].iloc[i]
            highBar = i

    # 2. From the highest high, find the lowest low to define the base
    lowestLow = df['Low'].iloc[highBar]
    lowBar = highBar
    for i in range(highBar, -1):
        if df['Low'].iloc[i] < lowestLow:
            lowestLow = df['Low'].iloc[i]
            lowBar = i

    # Compute the first contraction depth
    first_contraction_depth = ((highestHigh - lowestLow) / highestHigh) * 100


    # Computing Previous High
    prevHigh = df['High'].iloc[(highBar-50):(highBar-10)].max()
    prevHighBar = df['High'].iloc[(highBar-50):(highBar-10)].values.argmax() + highBar - 50

    prevLow = df['Low'].iloc[(prevHighBar+1):(highBar-1)].min()
    prevLowBar = df['Low'].iloc[(prevHighBar+1):(highBar-1)].values.argmin() + prevHighBar + 1

    prev_contraction_depth = ((prevHigh - prevLow) / prevHigh) * 100
    # Initialize contractions list with the first contraction

    contractions = [{
        'peak_index': prevHighBar,
        'peak_price': prevHigh,
        'trough_index': prevLowBar,
        'trough_price': prevLow,
        'depth': prev_contraction_depth
    }]
    
    contractions.append({
        'peak_index': highBar,
        'peak_price': highestHigh,
        'trough_index': lowBar,
        'trough_price': lowestLow,
        'depth': first_contraction_depth
    })

    # Set previous contraction depth
    previous_contraction_depth = first_contraction_depth

    # Start from the day after the first trough
    current_index = lowBar + 1 if lowBar >= 0 else len(df) + lowBar + 1

    # retracement_level remains constant at 50% retracement of initial contraction
    retracement_level = lowestLow + 0.5 * (highestHigh - lowestLow)
    searching_for_retracement = True

    while current_index < len(df):
        current_price = df['Close'].iloc[current_index]

        if searching_for_retracement:
            # Look for when price reaches the 50% retracement level
            if current_price >= retracement_level:
                retracement_index = current_index
                highest_price_since_retracement = current_price
                highest_price_index = current_index
                # Set the price at which we consider a 5% drop
                drop_trigger_price = highest_price_since_retracement -((highestHigh - lowestLow) * percentage_threshold / 100)
                searching_for_retracement = False
        else:
            # Update the highest price since retracement
            if df['High'].iloc[current_index] > highest_price_since_retracement:
                highest_price_since_retracement = df['High'].iloc[current_index]
                highest_price_index = current_index
                # Update the drop trigger price based on the new high
                drop_trigger_price = highest_price_since_retracement -((highestHigh - lowestLow) * percentage_threshold / 100)

            # Check if price has dropped by the percentage threshold from the highest price
            if current_price <= drop_trigger_price:
                # Second peak found at highest_price_since_retracement
                second_peak_price = highest_price_since_retracement
                second_peak_index = highest_price_index

                # Now, find the lowest low from the second peak to the current date
                next_trough_price = df['Low'].iloc[second_peak_index]
                next_trough_index = second_peak_index

                for idx in range(second_peak_index + 1, len(df)):
                    price = df['Low'].iloc[idx]
                    if price < next_trough_price:
                        next_trough_price = price
                        next_trough_index = idx

                # Calculate the contraction depth
                contraction_depth = ((second_peak_price - next_trough_price) / second_peak_price) * 100

                # Check if the contraction depth is smaller than the previous one
                if contraction_depth < previous_contraction_depth:
                    # Record the contraction with negative indices
                    contractions.append({
                        'peak_index': second_peak_index - len(df),
                        'peak_price': second_peak_price,
                        'trough_index': next_trough_index - len(df),
                        'trough_price': next_trough_price,
                        'depth': contraction_depth
                    })
                    # Update the previous contraction depth
                    previous_contraction_depth = contraction_depth

                    # Prepare for the next contraction
                    current_index = next_trough_index
                    # retracement_level remains constant
                    searching_for_retracement = True
                else:
                    # Contraction is not smaller; stop the search
                    break
        current_index += 1

    # Determine breakout_confirmed and breakout_date_index
    breakout_confirmed = False
    breakout_date_index = None

    # Check for breakout 'positive'
    for idx in range(highBar + 1, 0):
        price = df['Close'].iloc[idx]
        if price >= highestHigh:
            breakout_confirmed = 'positive'
            breakout_date_index = idx
            break


    # Adjust base_length_days
    if breakout_confirmed:
        # base_length_days is days between highBar and breakout_date_index
        base_length_days = abs(breakout_date_index - highBar)
    else:
        # base_length_days is days between highBar and current day (-1)
        base_length_days = abs(-1 - highBar)

    # Compile the base analysis results
    base_analysis = {
        'contractions': contractions,
        'highest_high': highestHigh,
        'lowest_low': lowestLow,
        'base_length_days': base_length_days,
        'base_depth_percent': ((highestHigh - lowestLow) / highestHigh) * 100,
        'breakout_confirmed': breakout_confirmed,
        'breakout_date_index': breakout_date_index,
        'current_price': df['Close'].iloc[-1]
        # Additional analysis results can be added here
    }
    
    return base_analysis


