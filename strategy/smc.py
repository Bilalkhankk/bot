import pandas as pd
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class Signal:
    def __init__(self, signal_type: str, symbol: str, entry_price: float):
        self.signal_type = signal_type
        self.symbol = symbol
        self.entry_price = entry_price
        
        # Dynamic risk management (1% risk)
        risk_percent = 0.01
        if signal_type == "BUY":
            self.sl_price = entry_price * (1 - risk_percent)
            self.tp_price = entry_price * (1 + risk_percent * 2)  # 1:2 risk ratio
        else:  # "SELL"
            self.sl_price = entry_price * (1 + risk_percent)
            self.tp_price = entry_price * (1 - risk_percent * 2)

def get_signal(df: pd.DataFrame, symbol: str, market_condition: str) -> Optional[Signal]:
    """Generate signals based on RSI and MACD crossovers with more practical conditions"""
    if len(df) < 3:
        return None

    try:
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Bullish conditions
        bullish_rsi = (prev['rsi_fast'] <= prev['rsi_slow']) and (current['rsi_fast'] > current['rsi_slow'])
        bullish_macd = (prev['macd_line'] <= prev['macd_signal']) and (current['macd_line'] > current['macd_signal'])
        volume_ok = current['volume'] > current['volume_ma']  # Volume above MA
        
        # Bearish conditions
        bearish_rsi = (prev['rsi_fast'] >= prev['rsi_slow']) and (current['rsi_fast'] < current['rsi_slow'])
        bearish_macd = (prev['macd_line'] >= prev['macd_signal']) and (current['macd_line'] < current['macd_signal'])
        
        # Generate signals with more practical conditions
        if bullish_rsi and bullish_macd and volume_ok:
            # Additional confirmation: Price above opening price
            if current['close'] > current['open']:
                return Signal("BUY", symbol, current['close'])
        elif bearish_rsi and bearish_macd and volume_ok:
            # Additional confirmation: Price below opening price
            if current['close'] < current['open']:
                return Signal("SELL", symbol, current['close'])
            
        return None
        
    except Exception as e:
        logger.error(f"Signal generation error: {str(e)}")
        return None

def check_market_condition() -> str:
    return "NEUTRAL"