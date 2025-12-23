from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional

# 1. The Class Name becomes the Table Name (stockprice)
class StockPrice(SQLModel, table=True):
    # We need a primary key (a unique ID for every single row in the DB)
    id: Optional[int] = Field(default=None, primary_key=True)

    # The Ticker Symbol (e.g., "AAPL")
    # index=True makes searching by symbol instant
    symbol: str = Field(index=True)

    # The Date. index=True allows fast sorting by date
    date: datetime = Field(index=True)

    # The Core Data (Floats for prices, usually float for volume too)
    open: float
    high: float
    low: float
    close: float
    volume: float

    # OPTIONAL: You can add extra columns here later if you want 
    # to store calculated indicators permanently, e.g.:
    # rsi: Optional[float] = None