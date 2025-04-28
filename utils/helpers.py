def initialize_log_file():
    import pandas as pd
    import os
    from config import settings
    
    if not os.path.exists(settings.LOG_FILE):
        pd.DataFrame(columns=["time", "symbol", "action", "price", "pnl", "reason", "market", "tp", "sl"]).to_csv(settings.LOG_FILE, index=False)

def setup_exchange():
    from data.fetcher import exchange
    from config import settings
    
    try:
        # Set up exchange
        exchange.load_markets()
        
        # Set leverage for all pairs
        for symbol in settings.PAIRS:
            try:
                exchange.set_leverage(settings.LEVERAGE, symbol)
            except:
                pass  # Some symbols might not support leverage setting
    except Exception as e:
        print(f"Exchange setup error: {str(e)[:100]}")
        raise
    
def get_account_balance():
    from data.fetcher import exchange, fetch_ohlcv
    """Fetch actual account balance from Binance"""
    try:
        balance = exchange.fetch_balance()
        usdt_balance = balance['total'].get('USDT', 0)
        print(f"\nCurrent Account Balance: ${usdt_balance:.2f}")
        return usdt_balance
    except Exception as e:
        print(f"Error fetching balance: {str(e)[:100]}")
        return 0