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

class QuarterlyFinancials(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True) # The link to our other data
    date: datetime = Field(index=True)
    
    # The columns match the data you use in 'FundamentalScreen'
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    eps: Optional[float] = None
    # can add other stuff later
    
    # From earningsdates.csv
    surprise_percent: Optional[float] = None


class EarningsSurprise(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    date: datetime = Field(index=True) # This is the REPORT date (e.g., Apr 25)
    
    eps_estimate: Optional[float] = None
    eps_actual: Optional[float] = None
    surprise_percent: Optional[float] = None