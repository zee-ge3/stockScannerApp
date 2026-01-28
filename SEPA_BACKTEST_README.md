# SEPA Backtesting Module

This module implements the Specific Entry Point Analysis (SEPA) methodology for backtesting stock candidates.

## Features

The backtester filters stocks based on Mark Minervini's criteria:

1.  **Trend Template (Stage 2)**:
    *   Price > 150MA and 200MA
    *   150MA > 200MA
    *   200MA trending up (1 month min)
    *   50MA > 150MA and 200MA
    *   Price > 50MA
    *   Price > 1.3x 52-week Low
    *   Price within 25% of 52-week High
2.  **VCP Pattern**:
    *   Identifies Volatility Contraction Patterns.
    *   Detects breakouts from the pivot point.
3.  **Volume Confirmation**:
    *   Requires breakout volume to be > 1.5x the 50-day average volume.

## Usage

### API Endpoint

A new endpoint is available to run the backtest on a specific symbol:

`GET /backtest/{symbol}`

**Example:**
`http://localhost:8000/backtest/AAPL`

**Response:**
```json
{
  "symbol": "AAPL",
  "trades": [
    {
      "date": "2023-05-15T00:00:00",
      "price": 172.50,
      "stop_loss": 160.42,
      "target": 207.00,
      "type": "Buy",
      "reason": "SEPA VCP Breakout"
    }
  ]
}
```

## Notes

*   **Financial Data**: Currently, the backtest focuses purely on Technical Analysis (Price & Volume) and excludes fundamental data (Earnings, Sales).
*   **RS Rank**: The Relative Strength Ranking (0-99) is currently not implemented in the backtest as it requires market-wide comparative data at every historical time step.
*   **Performance**: The backtest runs daily analysis on the requested stock. For long histories, it may take a few seconds.
