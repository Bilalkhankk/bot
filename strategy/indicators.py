import pandas_ta as ta
import pandas as pd
import numpy as np
from typing import Optional, Tuple

# ========== CONFIGURABLE PARAMETERS ==========
INDICATOR_PARAMS = {
    # AlphaTrend Parameters
    'alphatrend_length': 14,
    'alphatrend_multiplier': 1.0,
    'alphatrend_use_mfi': True,
    
    # EMA Parameters
    'ema_lengths': [5, 9, 10, 18, 20, 50],
    
    # MACD Parameters
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    
    # RSI Parameters
    'rsi_length': 14,
    
    # Bollinger Bands Parameters
    'bb_length': 20,
    'bb_std': 2.0,
    
    # SuperTrend Parameters
    'supertrend_atr_length': 10,
    'supertrend_multiplier': 3.0,
}

class IndicatorError(Exception):
    pass

def calculate_alphatrend(df, length=14, multiplier=1.0, use_mfi=True):
    """Calculate AlphaTrend indicator as per TradingView script"""
    try:
        # Calculate ATR
        tr = ta.true_range(df['high'], df['low'], df['close'])
        atr = ta.sma(tr, length=length)
        
        # Calculate upT and downT
        df['upT'] = df['low'] - atr * multiplier
        df['downT'] = df['high'] + atr * multiplier
        
        # Initialize AlphaTrend
        alpha_trend = np.zeros(len(df))
        last_value = np.nan
        
        for i in range(len(df)):
            if use_mfi:
                # We'll pre-calculate MFI separately
                cond = df['mfi'].iloc[i] >= 50 if i < len(df) else False
            else:
                cond = df['rsi'].iloc[i] >= 50 if i < len(df) else False
                
            if np.isnan(last_value):
                alpha_trend[i] = df['upT'].iloc[i] if cond else df['downT'].iloc[i]
            else:
                if cond:
                    if df['upT'].iloc[i] < last_value:
                        alpha_trend[i] = last_value
                    else:
                        alpha_trend[i] = df['upT'].iloc[i]
                else:
                    if df['downT'].iloc[i] > last_value:
                        alpha_trend[i] = last_value
                    else:
                        alpha_trend[i] = df['downT'].iloc[i]
            
            last_value = alpha_trend[i]
        
        return alpha_trend
    except Exception as e:
        raise IndicatorError(f"AlphaTrend calculation failed: {str(e)}")

def calculate_indicators(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Enhanced indicator calculation with AlphaTrend strategy"""
    if df is None or len(df) < 100:
        return None
        
    required_columns = {'open', 'high', 'low', 'close', 'volume'}
    if not required_columns.issubset(df.columns):
        raise IndicatorError(f"Missing required columns: {required_columns}")
    
    try:
        df = df.copy()
        params = INDICATOR_PARAMS
        
        # ===== CORE ALPHATREND STRATEGY INDICATORS =====
        # 1. AlphaTrend
        df['mfi'] = ta.mfi(df['high'], df['low'], df['close'], df['volume'], 
                          length=params['alphatrend_length'])
        df['rsi'] = ta.rsi(df['close'], length=params['rsi_length'])
        df['AlphaTrend'] = calculate_alphatrend(
            df, 
            length=params['alphatrend_length'],
            multiplier=params['alphatrend_multiplier'],
            use_mfi=params['alphatrend_use_mfi']
        )
        df['AlphaTrend_trigger'] = df['AlphaTrend'].shift(2)
        
        # 2. EMAs
        for length in params['ema_lengths']:
            df[f"ema{length}"] = ta.ema(df["close"], length=length)
        
        # 3. MACD
        macd = ta.macd(
            df["close"],
            fast=params['macd_fast'],
            slow=params['macd_slow'],
            signal=params['macd_signal']
        )
        df["macd_line"] = macd[f"MACD_{params['macd_fast']}_{params['macd_slow']}_{params['macd_signal']}"]
        df["macd_signal"] = macd[f"MACDs_{params['macd_fast']}_{params['macd_slow']}_{params['macd_signal']}"]
        
        # 4. Bollinger Bands
        bb = ta.bbands(
            df["close"],
            length=params['bb_length'],
            std=params['bb_std']
        )
        df["bb_upper"] = bb[f"BBU_{params['bb_length']}_{params['bb_std']}"]
        df["bb_lower"] = bb[f"BBL_{params['bb_length']}_{params['bb_std']}"]
        df["bb_middle"] = bb[f"BBM_{params['bb_length']}_{params['bb_std']}"]
        
        # 5. SuperTrend
        supertrend = ta.supertrend(
            df['high'], df['low'], df['close'],
            length=params['supertrend_atr_length'],
            multiplier=params['supertrend_multiplier']
        )
        df['supertrend'] = supertrend[f'SUPERT_{params["supertrend_atr_length"]}_{params["supertrend_multiplier"]}']
        df['supertrend_dir'] = supertrend[f'SUPERTd_{params["supertrend_atr_length"]}_{params["supertrend_multiplier"]}']
        
        # ===== ADDITIONAL INDICATORS FOR RISK MANAGEMENT =====
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)
        df["volume_ma"] = df["volume"].rolling(20).mean()
        
        return df.dropna()
    except Exception as e:
        raise IndicatorError(f"Indicator calculation failed: {str(e)}")