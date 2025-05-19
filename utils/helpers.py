import pandas as pd
import os
from config import settings
import ccxt

exchange = None  # Global exchange object

def initialize_log_file():
    if not os.path.exists(settings.LOG_FILE):
        pd.DataFrame(columns=["time", "symbol", "action", "price", "pnl", "reason", "market", "tp", "sl"]).to_csv(settings.LOG_FILE, index=False)

def setup_exchange():
    """Sets up the Binance Futures exchange with public access only."""
    global exchange
    try:
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
            }
        })
        exchange.load_markets()
    except Exception as e:
        print(f"Exchange setup error: {str(e)[:100]}")
        raise
