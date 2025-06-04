from .indicators import calculate_indicators
from config import settings
from datetime import datetime
import logging
from typing import Optional, Dict, Tuple
import pandas as pd
from data.fetcher import fetch_ohlcv

# ========== CONFIGURABLE PARAMETERS ==========
SMC_PARAMS = {
    # Risk Management
    'atr_risk_multiplier': 0.5,
    'sl_multiplier': 1.5,
    'tp_multiplier': 3.0,
    'min_atr_threshold': 0.005,
    
    # AlphaTrend Signal Confirmation
    'min_volume_multiplier': 1.5,
    'rsi_entry_min': 30,
    'rsi_entry_max': 70,
}

# ========== LOGGING SETUP ==========
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if logger.hasHandlers():
    logger.handlers.clear()

file_handler = logging.FileHandler('smc_strategy.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(message)s'))

logger.addHandler(file_handler)
logger.addHandler(stream_handler)

class SMCSignal:
    def __init__(self, signal_type: str, symbol: str, entry_price: float, atr: float):
        self.signal_type = signal_type
        self.symbol = symbol
        self.entry_price = entry_price
        self.atr = atr
        self.sl_price, self.tp_price = self._calculate_sl_tp()
        self.timestamp = datetime.utcnow()
        
    def _calculate_sl_tp(self) -> Tuple[float, float]:
        """Calculate SL/TP based on ATR"""
        if self.signal_type == "BUY":
            return (
                self.entry_price - (SMC_PARAMS['sl_multiplier'] * self.atr),
                self.entry_price + (SMC_PARAMS['tp_multiplier'] * self.atr)
            )
        else:
            return (
                self.entry_price + (SMC_PARAMS['sl_multiplier'] * self.atr),
                self.entry_price - (SMC_PARAMS['tp_multiplier'] * self.atr)
            )
            
    def to_dict(self):
        return {
            'symbol': self.symbol,
            'signal': self.signal_type,
            'entry_price': self.entry_price,
            'sl_price': self.sl_price,
            'tp_price': self.tp_price,
            'atr': self.atr
        }

def is_optimal_trading_time() -> bool:
    utc_hour = datetime.utcnow().hour
    weekday = datetime.utcnow().weekday()
    return (8 <= utc_hour < 22) and (weekday < 5)

def check_alphatrend_signal(df: pd.DataFrame, symbol: str) -> Optional[SMCSignal]:
    """Check for AlphaTrend signals with confirmation"""
    if df is None or len(df) < 5:
        return None
        
    try:
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Skip low volatility periods
        atr_pct = last["atr"] / last["close"]
        if atr_pct < SMC_PARAMS['min_atr_threshold']:
            return None
            
        # Volume filter
        if last['volume'] < last['volume_ma'] * SMC_PARAMS['min_volume_multiplier']:
            return None
        
        # AlphaTrend signals
        buy_signal = (
            last['AlphaTrend'] > last['AlphaTrend_trigger'] and
            last['ema9'] > last['ema18'] and
            last['macd_line'] > last['macd_signal'] and
            SMC_PARAMS['rsi_entry_min'] < last['rsi'] < SMC_PARAMS['rsi_entry_max'] and
            last['close'] > last['bb_lower'] and
            last['supertrend_dir'] == 1
        )
        
        sell_signal = (
            last['AlphaTrend'] < last['AlphaTrend_trigger'] and
            last['ema9'] < last['ema18'] and
            last['macd_line'] < last['macd_signal'] and
            SMC_PARAMS['rsi_entry_min'] < last['rsi'] < SMC_PARAMS['rsi_entry_max'] and
            last['close'] < last['bb_upper'] and
            last['supertrend_dir'] == -1
        )
        
        if buy_signal:
            return SMCSignal("BUY", symbol, last['close'], last['atr'])
        elif sell_signal:
            return SMCSignal("SELL", symbol, last['close'], last['atr'])
            
        return None
        
    except Exception as e:
        logger.error(f"AlphaTrend signal check failed for {symbol}: {str(e)}")
        return None

def get_signal(df: pd.DataFrame, symbol: str, market_condition: str) -> Optional[SMCSignal]:
    """Generate signal based on AlphaTrend strategy"""
    if not is_optimal_trading_time():
        return None
        
    # Get signal from AlphaTrend system
    signal = check_alphatrend_signal(df, symbol)
    
    # Additional risk management filters
    if signal:
        last = df.iloc[-1]
        
        # Avoid trading against market condition
        if market_condition == "BEARISH" and signal.signal_type == "BUY":
            return None
        if market_condition == "BULLISH" and signal.signal_type == "SELL":
            return None
            
        # Ensure sufficient volatility
        if signal.atr / last['close'] < 0.002:
            return None
            
    return signal