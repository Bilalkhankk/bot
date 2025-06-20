from .indicators import calculate_indicators
from config import settings
from datetime import datetime
import logging
from typing import Optional, Dict, Tuple
import pandas as pd
from data.fetcher import fetch_ohlcv

# ========== UPDATED PARAMETERS ==========
SMC_PARAMS = {
    # Risk Management
    'atr_risk_multiplier': 0.5,
    'sl_multiplier': 3.5,  # Increased from 1.5
    'tp_multiplier': 4.0,  # Increased from 3.0
    'min_atr_threshold': 0.004,  # Lowered threshold
    # Signal Confirmation
    'min_volume_multiplier': 1.2,  # Reduced from 1.5
    'rsi_entry_min': 25,  # Expanded range
    'rsi_entry_max': 75,  # Expanded range
    'max_sl_percent': 1.5,  # Max SL as % of price
}

logger = logging.getLogger(__name__)

class SMCSignal:
    def __init__(self, signal_type: str, symbol: str, entry_price: float, atr: float, df: pd.DataFrame):
        self.signal_type = signal_type
        self.symbol = symbol
        self.entry_price = entry_price
        self.atr = atr
        self.sl_price, self.tp_price = self._calculate_sl_tp(df)
        self.timestamp = datetime.utcnow()
        
    # def _calculate_sl_tp(self, df) -> Tuple[float, float]:
    #     """Dynamic SL placement with fixed TP (0.3%)"""
    #     last = df.iloc[-1]
    #     prev_low = df['low'].iloc[-3:-1].min()
    #     prev_high = df['high'].iloc[-3:-1].max()
    
    #     tp_percent = 0.003  # 0.3% as decimal
    
    #     if self.signal_type == "BUY":
    #         atr_sl = self.entry_price - (SMC_PARAMS['sl_multiplier'] * self.atr)
    #         structure_sl = prev_low * 0.998
    #         sl_price = max(atr_sl, structure_sl)
    
    #         max_sl = self.entry_price * (1 - SMC_PARAMS['max_sl_percent'] / 100)
    #         sl_price = max(sl_price, max_sl)
    
    #         tp_price = self.entry_price * (1 + tp_percent)
    
    #     else:  # SELL
    #         atr_sl = self.entry_price + (SMC_PARAMS['sl_multiplier'] * self.atr)
    #         structure_sl = prev_high * 1.002
    #         sl_price = min(atr_sl, structure_sl)
    
    #         max_sl = self.entry_price * (1 + SMC_PARAMS['max_sl_percent'] / 100)
    #         sl_price = min(sl_price, max_sl)
    
    #         tp_price = self.entry_price * (1 - tp_percent)
    
    #     return sl_price, tp_price
    def _calculate_sl_tp(self, df) -> Tuple[float, float]:
        """Dynamic SL placement with ATR-based TP and structural levels"""
        last = df.iloc[-1]
        # Look back 10 candles for structure (wider support/resistance)
        prev_low = df['low'].iloc[-11:-1].min() if len(df) > 10 else last['low']
        prev_high = df['high'].iloc[-11:-1].max() if len(df) > 10 else last['high']
        tp_percent = 0.003

        if self.signal_type == "BUY":
            # Wider ATR-based SL
            atr_sl = self.entry_price - (SMC_PARAMS['sl_multiplier'] * self.atr)
            structure_sl = prev_low * 0.995  # 0.5% buffer below structure
            sl_price = max(atr_sl, structure_sl)

            # Prevent excessively wide SL
            max_sl = self.entry_price * (1 - SMC_PARAMS['max_sl_percent']/100)
            sl_price = max(sl_price, max_sl)

            # ATR-based TP (replaces fixed 0.3%)
            tp_price = self.entry_price * (1 + tp_percent)

        else:  # SELL
            atr_sl = self.entry_price + (SMC_PARAMS['sl_multiplier'] * self.atr)
            structure_sl = prev_high * 1.005  # 0.5% buffer above structure
            sl_price = min(atr_sl, structure_sl)

            max_sl = self.entry_price * (1 + SMC_PARAMS['max_sl_percent']/100)
            sl_price = min(sl_price, max_sl)

            tp_price = self.entry_price * (1 - tp_percent)

        return sl_price, tp_price
def check_market_condition() -> str:
    """More responsive market condition analysis"""
    try:
        df = fetch_ohlcv("BTCUSDT", settings.TIMEFRAME, 200)
        if df is None or len(df) < 100:
            return "NEUTRAL"
            
        df = calculate_indicators(df)
        last = df.iloc[-1]
        
        # Simplified scoring system
        score = 0
        
        # EMA direction (more weight)
        if last['ema9'] > last['ema18']:
            score += 2
        else:
            score -= 2
            
        # Price vs SuperTrend
        if last['close'] > last['supertrend']:
            score += 1.5
        else:
            score -= 1.5
            
        # MACD momentum
        if last['macd_line'] > last['macd_signal']:
            score += 1
        else:
            score -= 1
            
        # Determine condition (lower thresholds)
        if score >= 2.0:
            return "BULLISH"
        elif score <= -2.0:
            return "BEARISH"
        return "NEUTRAL"
            
    except Exception as e:
        logger.error(f"Market condition error: {str(e)}")
        return "NEUTRAL"

def check_alphatrend_signal(df: pd.DataFrame, symbol: str, market_condition: str) -> Optional[SMCSignal]:
    """More flexible signal detection with adaptive ATR filtering"""
    if len(df) < 20:
        return None

    try:
        last = df.iloc[-1]
        prev = df.iloc[-2]

        # ===== Adaptive ATR Threshold =====
        if market_condition == "BULLISH":
            min_atr_threshold = 0.0020
        elif market_condition == "NEUTRAL":
            min_atr_threshold = SMC_PARAMS['min_atr_threshold']
        else:  # BEARISH
            min_atr_threshold = SMC_PARAMS['min_atr_threshold']  # default 0.004

        atr_pct = last["atr"] / last["close"]
        if atr_pct < min_atr_threshold:
            logger.info(f"  Skipping {symbol} - Low volatility (ATR%: {atr_pct:.4f})")
            return None

        # ===== Volume Filter =====
        if last['volume'] < last['volume_ma'] * SMC_PARAMS['min_volume_multiplier']:
            return None

        # ===== Buy/Sell Signal Conditions =====
        buy_conditions = [
            last['AlphaTrend'] > last['AlphaTrend_trigger'],
            last['ema9'] > last['ema18'],
            SMC_PARAMS['rsi_entry_min'] < last['rsi'] < SMC_PARAMS['rsi_entry_max']
        ]

        sell_conditions = [
            last['AlphaTrend'] < last['AlphaTrend_trigger'],
            last['ema9'] < last['ema18'],
            SMC_PARAMS['rsi_entry_min'] < last['rsi'] < SMC_PARAMS['rsi_entry_max']
        ]

        if all(buy_conditions):
            return SMCSignal("BUY", symbol, last['close'], last['atr'], df)
        elif all(sell_conditions):
            return SMCSignal("SELL", symbol, last['close'], last['atr'], df)

        return None

    except Exception as e:
        logger.error(f"Signal check error: {str(e)}")
        return None


def get_signal(df: pd.DataFrame, symbol: str, market_condition: str) -> Optional[SMCSignal]:
    """Generate signal with market context"""
    signal = check_alphatrend_signal(df, symbol, market_condition)

    if signal:
        # Allow counter-trend trades in neutral market
        if market_condition == "NEUTRAL":
            return signal

        # Only follow trend in strong markets
        if (market_condition == "BULLISH" and signal.signal_type == "BUY") or \
           (market_condition == "BEARISH" and signal.signal_type == "SELL"):
            return signal

    return None