import pandas_ta as ta
import pandas as pd
from typing import Optional

def calculate_indicators(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Calculate only necessary indicators for new strategy"""
    if df is None or len(df) < 50:
        return None
        
    try:
        df = df.copy()
        
        # Calculate RSI with two different periods
        df['rsi_fast'] = ta.rsi(df['close'], length=14)
        df['rsi_slow'] = ta.rsi(df['close'], length=21)
        
        # Calculate MACD
        macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
        df['macd_line'] = macd['MACD_12_26_9']
        df['macd_signal'] = macd['MACDs_12_26_9']
        
        # Add volume MA for reference
        df['volume_ma'] = df['volume'].rolling(20).mean()
        
        return df.dropna()
    except Exception as e:
        print(f"Indicator calculation failed: {str(e)}")
        return None