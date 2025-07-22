import pandas as pd
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class Signal:
    def __init__(self, signal_type: str, symbol: str, entry_price: float):
        self.signal_type = signal_type
        self.symbol = symbol
        self.entry_price = entry_price
        # Fixed SL and TP at 0.5%
        if signal_type == "BUY":
            self.sl_price = entry_price * (1 - 0.005)
            self.tp_price = entry_price * (1 + 0.005)
        else:  # "SELL"
            self.sl_price = entry_price * (1 + 0.005)
            self.tp_price = entry_price * (1 - 0.005)

def get_signal(df: pd.DataFrame, symbol: str, market_condition: str) -> Optional[Signal]:
    """Generate signals based on RSI and MACD crossovers"""
    if len(df) < 2:  # Need at least 2 candles for crossover detection
        return None

    try:
        # Get current and previous candle
        current = df.iloc[-1]
        previous = df.iloc[-2]
        
        # Long entry conditions
        long_rsi = (previous['rsi_fast'] <= previous['rsi_slow']) and (current['rsi_fast'] > current['rsi_slow'])
        long_macd = (previous['macd_line'] <= previous['macd_signal']) and (current['macd_line'] > current['macd_signal'])
        
        # Short entry conditions
        short_rsi = (previous['rsi_fast'] >= previous['rsi_slow']) and (current['rsi_fast'] < current['rsi_slow'])
        short_macd = (previous['macd_line'] >= previous['macd_signal']) and (current['macd_line'] < current['macd_signal'])
        
        # Generate signals
        if long_rsi and long_macd:
            return Signal("BUY", symbol, current['close'])
        elif short_rsi and short_macd:
            return Signal("SELL", symbol, current['close'])
            
        return None
        
    except Exception as e:
        logger.error(f"Signal generation error: {str(e)}")
        return None

# Market condition function kept but simplified
def check_market_condition() -> str:
    """Simplified market condition analysis"""
    return "NEUTRAL"  # Not used in new strategy but required by main.py