from .indicators import calculate_indicators, check_divergence
from config import settings
from datetime import datetime
import logging
from typing import Optional, Dict, Tuple
import pandas as pd
from data.fetcher import fetch_ohlcv

# ========== CONFIGURABLE PARAMETERS ==========
SMC_PARAMS = {
    # Thresholds
    'bband_threshold': 0.005,
    'volume_spike_multiplier': 1.5,
    'rsi_oversold': 30,
    'rsi_overbought': 70,
    'retest_buffer': 0.002,  # 0.2%
    
    # Scoring
    'base_threshold': 4.0,
    'adaptive_loss_factor': 0.2,
    'min_score_non_trend': 5.0,
    
    # Multi-timeframe
    'higher_timeframe': '1h',
    'htf_confirm_weight': 0.5,
    
    # Position sizing
    'atr_risk_multiplier': 0.5,  # Risk 0.5% of capital per trade
    # Enhanced SL/TP Parameters
    'sl_multiplier_trend': {
        "XRPUSDT": 0.7, "DOGEUSDT": 0.6, "ADAUSDT": 0.75,
        "ETHUSDT": 0.8, "TRXUSDT": 0.5, "SOLUSDT": 0.85
    },
    'tp_multiplier_trend': {
        "XRPUSDT": 2.8, "DOGEUSDT": 3.0, "ADAUSDT": 2.5,
        "ETHUSDT": 2.3, "TRXUSDT": 3.2, "SOLUSDT": 2.2
    },
    'sl_multiplier_range': 1.2,      # Wider SL in ranges
    'tp_multiplier_range': 2.2,
    'trailing_activation': 1.5,      # Activate after 1.5x ATR profit
    'trailing_distance': 0.8         # Maintain 0.8x ATR from peak
}

# ========== LOGGING SETUP ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='smc_strategy.log'
)
logger = logging.getLogger(__name__)

class SMCSignal:
    def __init__(self, signal_type: str, symbol: str, score: float, 
                 threshold: float, conditions: Dict, atr: float,
                 entry_price: float, market_condition: str):
        self.signal_type = signal_type
        self.symbol = symbol
        self.score = score
        self.threshold = threshold
        self.conditions = conditions
        self.atr = atr
        self.entry_price = entry_price
        self.market_condition = market_condition
        self.timestamp = datetime.utcnow()
        self.trailing_active = False
        self.trailing_stop = None
        self.sl_price, self.tp_price = self._calculate_sl_tp()
    def _calculate_sl_tp(self) -> Tuple[float, float]:
        """Calculate dynamic SL/TP based on market condition"""
        if self.market_condition in ["BULLISH", "BEARISH"]:
            sl_mult = SMC_PARAMS['sl_multiplier_trend'].get(self.symbol, 0.8)
            tp_mult = SMC_PARAMS['tp_multiplier_trend'].get(self.symbol, 2.5)
        else:  # NEUTRAL
            sl_mult = SMC_PARAMS['sl_multiplier_range']
            tp_mult = SMC_PARAMS['tp_multiplier_range']

        if self.signal_type == "BUY":
            return (
                self.entry_price - (sl_mult * self.atr),
                self.entry_price + (tp_mult * self.atr)
            )
        else:  # SELL
            return (
                self.entry_price + (sl_mult * self.atr),
                self.entry_price - (tp_mult * self.atr)
            )

    def update_trailing_stop(self, current_price: float) -> Optional[float]:
        """Update trailing stop based on price movement"""
        if not self.trailing_active:
            profit = abs(current_price - self.entry_price)
            if profit >= (SMC_PARAMS['trailing_activation'] * self.atr):
                self.trailing_active = True
        
        if self.trailing_active:
            if self.signal_type == "BUY":
                new_stop = current_price - (SMC_PARAMS['trailing_distance'] * self.atr)
                self.trailing_stop = max(new_stop, self.trailing_stop) if self.trailing_stop else new_stop
            else:  # SELL
                new_stop = current_price + (SMC_PARAMS['trailing_distance'] * self.atr)
                self.trailing_stop = min(new_stop, self.trailing_stop) if self.trailing_stop else new_stop
            return self.trailing_stop
        return None
        
    def to_dict(self):
        return {
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'signal': self.signal_type,
            'score': self.score,
            'threshold': self.threshold,
            'conditions': self.conditions,
            'atr': self.atr,
            'entry_price': self.entry_price,
            'sl_price': self.sl_price,
            'tp_price': self.tp_price,
            'trailing_stop': self.trailing_stop
        }

def is_optimal_trading_time() -> bool:
    """Avoid low-liquidity periods (00:00-04:00 UTC)"""
    utc_hour = datetime.utcnow().hour
    return 4 <= utc_hour < 24

def check_market_condition() -> str:
    """Determine the overall market condition (BULLISH, BEARISH, or NEUTRAL)"""
    try:
        btc_df = fetch_ohlcv("BTCUSDT", settings.TIMEFRAME, 100)
        btc_df = calculate_indicators(btc_df)
        
        if btc_df is None or len(btc_df) < 50:
            return "NEUTRAL"
            
        last = btc_df.iloc[-1]
        prev = btc_df.iloc[-2]
        
        adx_threshold = settings.ADX_THRESHOLDS.get("BTCUSDT", 20)
        adx_weak = last["adx"] < (adx_threshold - 5)
        narrow_bb = last["bb_width"] < 0.03
        low_volatility = (btc_df["close"].pct_change().abs().rolling(20).mean().iloc[-1] < 0.002)
        ema_distance = abs(last["ema10"] - last["ema20"]) / last["close"] < 0.008
        
        higher_high = last["close"] > prev["recent_high"]
        lower_low = last["close"] < prev["recent_low"]
        volume_ok = last["volume"] > last["volume_ma"] * 1.2
        
        trend_up = (last["ema10"] > last["ema20"] > last["ema50"]) and (last["adx"] > adx_threshold + 5)
        trend_down = (last["ema10"] < last["ema20"] < last["ema50"]) and (last["adx"] > adx_threshold + 5)
        
        if adx_weak and (narrow_bb or low_volatility):
            market_condition = "NEUTRAL"
        elif trend_up and (higher_high or volume_ok):
            market_condition = "BULLISH"
        elif trend_down and (lower_low or volume_ok):
            market_condition = "BEARISH"
        else:
            market_condition = "NEUTRAL"
        
        print(f"\nMarket: {market_condition} | BTC: {last['close']:.2f}")
        print(f"EMA10: {last['ema10']:.2f} | EMA20: {last['ema20']:.2f}")
        print(f"RSI: {last['rsi']:.1f} | ADX: {last['adx']:.1f} (Threshold: {adx_threshold})")
        print(f"Volume: {'Strong' if volume_ok else 'Weak'}")
        print(f"BB Width: {last['bb_width']:.4f} | Volatility: {'Low' if low_volatility else 'Normal'}")
        
        return market_condition
        
    except Exception as e:
        logger.error(f"Market check error: {str(e)}", exc_info=True)
        return "NEUTRAL"

def check_higher_timeframe_confirmation(exchange, symbol: str, signal_type: str) -> bool:
    """Check higher timeframe alignment"""
    try:
        htf_df = fetch_ohlcv(symbol, SMC_PARAMS['higher_timeframe'], 50)
        if htf_df is None or len(htf_df) < 20:
            return False
            
        htf_df = calculate_indicators(htf_df)
        last = htf_df.iloc[-1]
        
        if signal_type == "BUY":
            return (last['ema5'] > last['ema20'] and 
                    last['close'] > last['bb_middle'] and
                    last['rsi'] > 50)
        return (last['ema5'] < last['ema20'] and 
                last['close'] < last['bb_middle'] and
                last['rsi'] < 50)
    except Exception as e:
        logger.error(f"HTF confirmation error for {symbol}: {str(e)}")
        return False

def calculate_position_size(atr: float, price: float, account_balance: float) -> float:
    """Calculate position size based on volatility"""
    risk_amount = account_balance * (SMC_PARAMS['atr_risk_multiplier'] / 100)
    return risk_amount / (atr / price)

def evaluate_conditions(df: pd.DataFrame, market_condition: str, symbol: str) -> Dict:
    """Evaluate all trading conditions with proper error handling"""
    last = df.iloc[-1]
    prev = df.iloc[-2]
    params = SMC_PARAMS
    
    # Initialize default conditions
    conditions = {
        'broke_high': False,
        'broke_low': False,
        'rsi_ok': False,
        'vol_spike': False,
        'trend_aligned': False,
        'vwap_confirm': False,
        'trend_strength': False,
        'near_support': False,
        'near_resistance': False,
        'confirmed_support': False,
        'confirmed_resistance': False
    }
    
    try:
        # Common conditions
        conditions.update({
            'broke_high': last["close"] > prev["high"],
            'broke_low': last["close"] < prev["low"],
            'rsi_ok': (params['rsi_oversold'] < last["rsi"] < params['rsi_overbought']),
            'vol_spike': (last["volume"] > last["volume_ma"] * (0.8 if market_condition == "NEUTRAL" else 1.0)),
            'trend_aligned': (market_condition == "BULLISH" and last["ema5"] > last["ema10"]) or 
                            (market_condition == "BEARISH" and last["ema5"] < last["ema10"]),
            'vwap_confirm': 'vwap' in df.columns and last['close'] > last['vwap'],
            'trend_strength': last['adx'] > 30
        })
        
        # Specific conditions for NEUTRAL market
        if market_condition == "NEUTRAL":
            if not pd.isna(last["bb_lower"]) and not pd.isna(last["bb_upper"]):
                conditions.update({
                    'near_support': (abs(last["close"] - last["bb_lower"]) / last["close"] < params['bband_threshold']),
                    'near_resistance': (abs(last["close"] - last["bb_upper"]) / last["close"] < params['bband_threshold']),
                    'confirmed_support': (conditions['near_support'] and 
                                        (last["close"] > last["open"]) and 
                                        (last["volume"] > last["volume_ma"] * params['volume_spike_multiplier'])),
                    'confirmed_resistance': (conditions['near_resistance'] and 
                                           (last["close"] < last["open"]) and 
                                           (last["volume"] > last["volume_ma"] * params['volume_spike_multiplier']))
                })
            else:
                logger.warning(f"Invalid BB values for {symbol} in NEUTRAL market")
        
        # Additional conditions
        conditions.update({
            'retest': (last["low"] > prev["high"] * (1 - params['retest_buffer'])) if conditions['broke_high'] else 
                     (last["high"] < prev["low"] * (1 + params['retest_buffer'])) if conditions['broke_low'] else False,
            'stoch_bullish': last["stoch_k"] > last["stoch_d"],
            'stoch_bearish': last["stoch_k"] < last["stoch_d"],
            'macd_bullish': last["macd_line"] > last["macd_signal"],
            'macd_bearish': last["macd_line"] < last["macd_signal"],
            'adx_ok': last["adx"] > settings.ADX_THRESHOLDS.get(symbol, 20)
        })
        
        bull_div, bear_div = check_divergence(df)
        conditions.update({
            'bull_div': bull_div,
            'bear_div': bear_div
        })
        
    except KeyError as e:
        logger.error(f"Missing key in data for {symbol}: {str(e)}")
    except Exception as e:
        logger.error(f"Error evaluating conditions for {symbol}: {str(e)}")
    
    return conditions

def calculate_scores(conditions: Dict, market_condition: str) -> Tuple[float, float]:
    """Calculate buy and sell scores"""
    params = SMC_PARAMS
    
    buy_score = sum([
        conditions['broke_high'] * 1.8,
        conditions['stoch_bullish'] * 1.0,
        conditions['vol_spike'] * 1.0,
        conditions['trend_aligned'] * 0.8,
        conditions['macd_bullish'] * 0.8,
        conditions['adx_ok'] * 0.5,
        conditions['retest'] * 0.7,
        (not conditions['bear_div']) * 0.5,
        conditions['vwap_confirm'] * 0.7,
        conditions['trend_strength'] * 0.5,
    ])
    
    sell_score = sum([
        conditions['broke_low'] * 1.8,
        conditions['stoch_bearish'] * 1.0,
        conditions['vol_spike'] * 1.0,
        (not conditions['trend_aligned']) * 0.8,
        conditions['macd_bearish'] * 0.8,
        conditions['adx_ok'] * 0.5,
        conditions['retest'] * 0.7,
        (not conditions['bull_div']) * 0.5,
        ('vwap' in conditions and not conditions['vwap_confirm']) * 0.7,
        conditions['trend_strength'] * 0.5,
    ])
    
    return buy_score, sell_score

def get_signal(df: pd.DataFrame, symbol: str, market_condition: str, 
               consecutive_losses: int = 0, exchange=None) -> Optional[SMCSignal]:
    """Generate trading signal with improved error handling"""
    if df is None or len(df) < 50:
        logger.warning(f"Insufficient data for {symbol}")
        return None
        
    if not is_optimal_trading_time():
        return None
        
    try:
        # Evaluate all conditions with proper validation
        conditions = evaluate_conditions(df, market_condition, symbol)
        
        # Check neutral market specific conditions
        if market_condition == "NEUTRAL":
            if not all(key in conditions for key in ['confirmed_support', 'confirmed_resistance']):
                logger.warning(f"Missing required conditions for {symbol} in NEUTRAL market")
                return None
                
            if not (conditions.get('confirmed_support', False) or 
                   conditions.get('confirmed_resistance', False)):
                return None
                
            if not conditions.get('rsi_ok', False):
                return None
        
        # Calculate scores
        buy_score, sell_score = calculate_scores(conditions, market_condition)
        
        # Apply adaptive threshold
        adaptive_threshold = SMC_PARAMS['base_threshold'] - (
            SMC_PARAMS['adaptive_loss_factor'] * min(consecutive_losses, 3))
        
        # Check higher timeframe confirmation if available
        htf_confirm = False
        if exchange:
            htf_confirm = check_higher_timeframe_confirmation(exchange, symbol, 
                "BUY" if buy_score > sell_score else "SELL")
            if htf_confirm:
                buy_score += SMC_PARAMS['htf_confirm_weight']
                sell_score += SMC_PARAMS['htf_confirm_weight']
        
        # Generate signal with all conditions validated
        atr = df["atr"].iloc[-1] if "atr" in df.columns else None
        entry_price = df["close"].iloc[-1]
        if (buy_score >= adaptive_threshold and conditions.get('rsi_ok', False) and 
            (buy_score >= SMC_PARAMS['min_score_non_trend'] or market_condition != "BEARISH")):
            return SMCSignal(
                "BUY", symbol, buy_score, adaptive_threshold,
                {k: v for k, v in conditions.items() if v},
                atr, entry_price, market_condition
            )
            
        elif (sell_score >= adaptive_threshold and conditions.get('rsi_ok', False) and 
              (sell_score >= SMC_PARAMS['min_score_non_trend'] or market_condition != "BULLISH")):
            return SMCSignal(
                "SELL", symbol, sell_score, adaptive_threshold,
                {k: v for k, v in conditions.items() if v},
                atr, entry_price, market_condition
            )
            
        return None
        
    except Exception as e:
        logger.error(f"Signal generation failed for {symbol}: {str(e)}", exc_info=True)
        return None