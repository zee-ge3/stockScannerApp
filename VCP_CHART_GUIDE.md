# VCP Analysis Chart Visualization Guide

## Overview
The chart now displays Volatility Contraction Pattern (VCP) analysis data overlaid on the stock price candlestick chart.

## What's Displayed

### 1. **Contraction Zones**
Each contraction is represented by:
- **Dashed horizontal lines** showing the peak and trough prices
- **Colored markers** indicating:
  - `1P`, `2P`, `3P`, etc. = Peak of each contraction (above bars)
  - `1T`, `2T`, `3T`, etc. = Trough of each contraction (below bars)
- **Color-coded** using:
  - Amber (Yellow)
  - Blue
  - Purple
  - Cyan

### 2. **Key Levels**
- **Green dashed line**: Highest high in the base formation
- **Red dashed line**: Lowest low in the base formation

## How VCP Analysis Works

The backend algorithm (`vcp_analysis` in `scanner_logic.py`) identifies:

1. **Base Formation**: 
   - Looks back ~150 days
   - Finds the highest high
   - Identifies the lowest low after that high

2. **Successive Contractions**:
   - Each contraction must be **smaller** than the previous one
   - Shows decreasing volatility (tightening pattern)
   - Indicates accumulation and reduced selling pressure

3. **Breakout Confirmation**:
   - Detects if price has broken above the highest high
   - Indicates potential trend continuation

## Data Flow

```
Backend (scanner_logic.py)
    ↓
  vcp_analysis(df_price)
    ↓
Returns: {
  contractions: [...],
  highest_high: float,
  lowest_low: float,
  base_length_days: int,
  base_depth_percent: float,
  breakout_confirmed: bool/str
}
    ↓
Backend (main.py)
  Converts indices to dates
    ↓
Frontend (App.tsx)
  Passes to TVChart
    ↓
Chart (TVChart.tsx)
  Renders visual overlay
```

## Chart Features

- **Candlestick series**: Shows OHLC price data
- **Line series**: Peak and trough levels for each contraction
- **Markers**: Visual indicators at key points
- **Legend**: Shows highest/lowest levels

## Interpreting the Pattern

A valid VCP should show:
1. ✅ Decreasing contraction depths (3rd < 2nd < 1st)
2. ✅ Horizontal lines getting closer together (tightening)
3. ✅ Base depth typically 10-40% from highest high
4. ✅ Eventual breakout above the highest high

## Technical Notes

- Uses **lightweight-charts v5** API
- Contractions rendered as separate line series
- Markers use `setMarkers()` API for peak/trough indicators
- Responsive design with auto-resize handler
