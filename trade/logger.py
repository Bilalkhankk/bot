import pandas as pd
import os
from datetime import datetime, timezone
from config import settings

def log_trade(symbol, action, price=None, pnl=None, reason=None, active_trades=None):
    log_data = {
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": symbol,
        "action": action,
        "price": price,
        "pnl": pnl,
        "reason": reason,
        "market": active_trades[symbol]["market_condition"] if active_trades and symbol in active_trades else None,
        "tp": active_trades[symbol]["tp"] if active_trades and symbol in active_trades else None,
        "sl": active_trades[symbol]["sl"] if active_trades and symbol in active_trades else None
    }
    
    pd.DataFrame([log_data]).to_csv(settings.LOG_FILE, mode="a", header=not os.path.exists(settings.LOG_FILE), index=False)