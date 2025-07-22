import ccxt
import pandas as pd
import time

# Global exchange instance for data fetching
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',  # Use spot for data fetching
    }
})

def fetch_ohlcv(symbol, timeframe, limit=100):
    """Fetch OHLCV data with retry logic"""
    for _ in range(3):  # Retry up to 3 times
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df
        except ccxt.NetworkError as e:
            print(f"Network error: {str(e)} - retrying in 5 seconds")
            time.sleep(5)
        except ccxt.ExchangeError as e:
            print(f"Exchange error: {str(e)}")
            return None
    return None