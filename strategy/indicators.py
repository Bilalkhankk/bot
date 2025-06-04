import pandas_ta as ta
import pandas as pd
from typing import Optional, Tuple

# ========== CONFIGURABLE PARAMETERS ==========
INDICATOR_PARAMS = {
    # EMA Parameters
    'ema_lengths': [5, 10, 20, 50],
    
    # RSI Parameters
    'rsi_length': 14,
    
    # Stochastic Parameters
    'stoch_k': 14,
    'stoch_d': 3,
    'stoch_smooth': 3,
    
    # ATR Parameters
    'atr_length': 14,
    
    # Volume MA Parameters
    'volume_ma_length': 20,
    
    # MACD Parameters
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    
    # ADX Parameters
    'adx_length': 14,
    'strong_trend_threshold': 25,
    
    # Bollinger Bands Parameters
    'bb_length': 20,
    'bb_std': 2.0,
    
    # Recent High/Low Parameters
    'recent_period': 5,
    
    # Divergence Parameters
    'divergence_lookback': 6,
    'divergence_volume_multiplier': 1.2,
    
    # Liquidity Zones
    'liquidity_lookback': 50
}

class IndicatorError(Exception):
    """Custom exception for indicator calculation errors"""
    pass

def calculate_indicators(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Calculate technical indicators for the given DataFrame.
    
    Args:
        df (pd.DataFrame): Input DataFrame with OHLCV data (columns: 'open', 'high', 'low', 'close', 'volume')
        
    Returns:
        pd.DataFrame: DataFrame with added indicator columns, or None if calculation fails
    """
    # Input validation
    if df is None or len(df) < 50:
        return None
        
    required_columns = {'open', 'high', 'low', 'close', 'volume'}
    if not required_columns.issubset(df.columns):
        raise IndicatorError(f"Missing required columns. Needed: {required_columns}")
    
    try:
        df = df.copy()
        params = INDICATOR_PARAMS
        
        # ===== CORE INDICATORS =====
        # EMAs
        for length in params['ema_lengths']:
            df[f"ema{length}"] = ta.ema(df["close"], length=length)
        
        # RSI
        df["rsi"] = ta.rsi(df["close"], length=params['rsi_length'])
        
        # ===== MOMENTUM INDICATORS =====
        # Stochastic
        stoch = ta.stoch(
            df["high"], df["low"], df["close"],
            k=params['stoch_k'],
            d=params['stoch_d'],
            smooth_k=params['stoch_smooth']
        )
        df["stoch_k"] = stoch[f"STOCHk_{params['stoch_k']}_{params['stoch_d']}_{params['stoch_smooth']}"]
        df["stoch_d"] = stoch[f"STOCHd_{params['stoch_k']}_{params['stoch_d']}_{params['stoch_smooth']}"]
        
        # ===== VOLATILITY & VOLUME =====
        # ATR
        df["atr"] = ta.atr(
            df["high"], df["low"], df["close"],
            length=params['atr_length']
        )
        
        # Volume indicators
        df["volume_ma"] = df["volume"].rolling(params['volume_ma_length']).mean()
        df["obv"] = ta.obv(df["close"], df["volume"])
        
        # VWAP
        df["vwap"] = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
        
        # ===== TREND INDICATORS =====
        # MACD
        macd = ta.macd(
            df["close"],
            fast=params['macd_fast'],
            slow=params['macd_slow'],
            signal=params['macd_signal']
        )
        df["macd_line"] = macd[f"MACD_{params['macd_fast']}_{params['macd_slow']}_{params['macd_signal']}"]
        df["macd_signal"] = macd[f"MACDs_{params['macd_fast']}_{params['macd_slow']}_{params['macd_signal']}"]
        df["macd_hist"] = macd[f"MACDh_{params['macd_fast']}_{params['macd_slow']}_{params['macd_signal']}"]
        
        # ADX
        adx_data = ta.adx(
            df["high"], df["low"], df["close"],
            length=params['adx_length']
        )
        df["adx"] = adx_data[f"ADX_{params['adx_length']}"]
        
        # Supertrend
        supertrend = ta.supertrend(
            df["high"], df["low"], df["close"],
            length=7,
            multiplier=3
        )
        df["supertrend"] = supertrend["SUPERT_7_3.0"]
        df["supertrend_dir"] = (df["close"] > df["supertrend"]).astype(int)
        
        # ===== PRICE STRUCTURE =====
        # Bollinger Bands
        bb = ta.bbands(
            df["close"],
            length=params['bb_length'],
            std=params['bb_std']
        )
        df["bb_upper"] = bb[f"BBU_{params['bb_length']}_{params['bb_std']}"]
        df["bb_lower"] = bb[f"BBL_{params['bb_length']}_{params['bb_std']}"]
        df["bb_middle"] = bb[f"BBM_{params['bb_length']}_{params['bb_std']}"]
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["close"]
        
        # ===== RECENT PRICE LEVELS =====
        df['recent_high'] = df['high'].rolling(params['recent_period']).max()
        df['recent_low'] = df['low'].rolling(params['recent_period']).min()
        
        # ===== CONFIRMATION FILTERS =====
        df['trend_strength'] = df['adx'] > params['strong_trend_threshold']
        
        return df.dropna()
        
    except KeyError as e:
        raise IndicatorError(f"Missing required column: {str(e)}") from e
    except Exception as e:
        raise IndicatorError(f"Indicator calculation failed: {str(e)}") from e

def check_divergence(df: pd.DataFrame) -> Tuple[bool, bool]:
    """
    Check for regular bullish and bearish divergences.
    """
    if len(df) < 20:
        return False, False
    
    params = INDICATOR_PARAMS
    lookback = params['divergence_lookback']
    
    try:
        # Price Levels
        price_lows = df["low"].rolling(5).min().iloc[-lookback:]
        price_highs = df["high"].rolling(5).max().iloc[-lookback:]
        
        # Indicator Levels (smoothed)
        rsi_lows = df["rsi"].rolling(3).mean().iloc[-lookback:]
        rsi_highs = df["rsi"].rolling(3).mean().iloc[-lookback:]
        macd_lows = df["macd_hist"].rolling(3).mean().iloc[-lookback:]
        macd_highs = df["macd_hist"].rolling(3).mean().iloc[-lookback:]
        
        # Bullish divergence: price makes lower low but indicator makes higher low
        bull_div = (
            (price_lows.iloc[-1] < price_lows.iloc[-2]) and 
            (
                (rsi_lows.iloc[-1] > rsi_lows.iloc[-2] + 3) or 
                (macd_lows.iloc[-1] > macd_lows.iloc[-2] + 0.001)
            ) and
            (df['volume'].iloc[-1] > df['volume_ma'].iloc[-1] * params['divergence_volume_multiplier'])
        )
        
        # Bearish divergence: price makes higher high but indicator makes lower high
        bear_div = (
            (price_highs.iloc[-1] > price_highs.iloc[-2]) and 
            (
                (rsi_highs.iloc[-1] < rsi_highs.iloc[-2] - 3) or 
                (macd_highs.iloc[-1] < macd_highs.iloc[-2] - 0.001)
            ) and
            (df['volume'].iloc[-1] > df['volume_ma'].iloc[-1] * params['divergence_volume_multiplier'])
        )
        
        return bull_div, bear_div
        
    except Exception as e:
        raise IndicatorError(f"Divergence check failed: {str(e)}") from e

def detect_liquidity_zones(df: pd.DataFrame, lookback: int = None) -> dict:
    """
    Identify significant support/resistance levels
    """
    params = INDICATOR_PARAMS
    if lookback is None:
        lookback = params.get('liquidity_lookback', 50)
    
    if len(df) < lookback:
        return {'key_support': 0, 'key_resistance': 0}
    
    try:
        # Use recent high/low as key levels
        return {
            'key_support': df['low'].iloc[-lookback:].min(),
            'key_resistance': df['high'].iloc[-lookback:].max()
        }
    except Exception as e:
        raise IndicatorError(f"Liquidity zone detection failed: {str(e)}") from e