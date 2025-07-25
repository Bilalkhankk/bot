import pandas_ta as ta
import pandas as pd
from typing import Optional

def calculate_indicators(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Calculate indicators with improved parameters"""
    if df is None or len(df) < 50:
        return None
        
    try:
        df = df.copy()
        
        # Calculate RSI with optimized periods (RSI 9,21 for better accuracy)
        df['rsi_fast'] = ta.rsi(df['close'], length=9)   # Faster response (was 10)
        df['rsi_slow'] = ta.rsi(df['close'], length=21)  # Better trend confirmation (was 20)
        
        # Calculate MACD with improved parameters for higher win rate
        macd = ta.macd(df['close'], fast=9, slow=21, signal=9)
        df['macd_line'] = macd['MACD_9_21_9']
        df['macd_signal'] = macd['MACDs_9_21_9']
        
        # Add volume MA with shorter period
        df['volume_ma'] = df['volume'].rolling(10).mean()  # 10-period MA
        
        return df.dropna()
    except Exception as e:
        print(f"Indicator calculation failed: {str(e)}")
        return None