import ccxt
import pandas as pd
from datetime import datetime, timezone
from config import settings

exchange = ccxt.binanceusdm(settings.EXCHANGE_CONFIG)

def fetch_ohlcv(symbol, timeframe, limit=100):
    """Fetch OHLCV data from exchange"""
    try:
        data = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.set_index("timestamp").sort_index()
        return df
    except Exception as e:
        print(f"Data error for {symbol}: {str(e)[:100]}")
        return None