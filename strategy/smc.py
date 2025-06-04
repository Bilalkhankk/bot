from .indicators import calculate_indicators, check_divergence, detect_liquidity_zones
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
    'trailing_distance': 0.8,        # Maintain 0.8x ATR from peak
    'min_atr_threshold': 0.005,      # Min ATR % of price (0.5%)
    'min_sl_buffer': 0.003           # 0.3% minimum stop loss buffer
}

# ========== ENHANCED LOGGING SETUP ==========
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Remove any existing handlers
if logger.hasHandlers():
    logger.handlers.clear()

# File handler (writes to smc_strategy.log)
file_handler = logging.FileHandler('smc_strategy.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Stream handler (prints to terminal)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(message)s'))  # Clean format for terminal

# Add both handlers
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

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
        """Calculate dynamic SL/TP with minimum buffer"""
        if self.market_condition in ["BULLISH", "BEARISH"]:
            sl_mult = SMC_PARAMS['sl_multiplier_trend'].get(self.symbol, 0.8)
            tp_mult = SMC_PARAMS['tp_multiplier_trend'].get(self.symbol, 2.5)
        else:  # NEUTRAL
            sl_mult = SMC_PARAMS['sl_multiplier_range']
            tp_mult = SMC_PARAMS['tp_multiplier_range']

        # Calculate base SL/TP
        if self.signal_type == "BUY":
            sl = self.entry_price - (sl_mult * self.atr)
            tp = self.entry_price + (tp_mult * self.atr)
        else:  # SELL
            sl = self.entry_price + (sl_mult * self.atr)
            tp = self.entry_price - (tp_mult * self.atr)
        
        # Add minimum buffer to avoid noise
        min_buffer = SMC_PARAMS['min_sl_buffer'] * self.entry_price
        if self.signal_type == "BUY":
            sl = min(sl, self.entry_price - min_buffer)
        else:
            sl = max(sl, self.entry_price + min_buffer)
            
        return sl, tp

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
    """Avoid low-liquidity periods (Asian session and weekends)"""
    utc_hour = datetime.utcnow().hour
    weekday = datetime.utcnow().weekday()
    return (8 <= utc_hour < 22) and (weekday < 5)

def check_market_condition() -> str:
    """Determine market condition using multiple assets with majority voting"""
    try:
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        trend_results = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
        btc_data = None
        
        for symbol in symbols:
            df = fetch_ohlcv(symbol, settings.TIMEFRAME, 100)
            if df is None or len(df) < 50:
                continue
                
            df = calculate_indicators(df)
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # Store BTC data for logging
            if symbol == "BTCUSDT":
                btc_data = (last, prev)
            
            # Determine trend strength
            adx_threshold = settings.ADX_THRESHOLDS.get(symbol, 20)
            adx_strong = last["adx"] > adx_threshold + 5
            adx_weak = last["adx"] < adx_threshold - 5
            
            # Define trend conditions
            uptrend = (
                last["ema10"] > last["ema20"] > last["ema50"] and
                adx_strong and
                last["close"] > last["recent_high"]
            )
            
            downtrend = (
                last["ema10"] < last["ema20"] < last["ema50"] and
                adx_strong and
                last["close"] < last["recent_low"]
            )
            
            neutral = (
                adx_weak or
                abs(last["ema10"] - last["ema20"]) / last["close"] < 0.008
            )
            
            # Classify market condition
            if uptrend:
                trend_results["BULLISH"] += 1
            elif downtrend:
                trend_results["BEARISH"] += 1
            elif neutral:
                trend_results["NEUTRAL"] += 1
        
        # Determine market condition by majority vote
        if trend_results["BULLISH"] >= 2:
            market_condition = "BULLISH"
        elif trend_results["BEARISH"] >= 2:
            market_condition = "BEARISH"
        else:
            market_condition = "NEUTRAL"
        
        # Log BTC status to terminal and file
        if btc_data:
            last, prev = btc_data
            logger.info(
                f"========================================\n"
                f"MARKET CONDITION: {market_condition}\n"
                f"BTC Price: ${last['close']:.2f}\n"
                f"EMAs: 10={last['ema10']:.2f} | 20={last['ema20']:.2f}\n"
                f"RSI: {last['rsi']:.1f} | ADX: {last['adx']:.1f}\n"
                f"Volume: {'Strong (UP)' if last['volume'] > last['volume_ma'] * 1.2 else 'Weak (DOWN)'}\n"
                f"========================================"
            )
        
        return market_condition
        
    except Exception as e:
        logger.error(f"Market check error: {str(e)}", exc_info=True)
        return "NEUTRAL"

def check_higher_timeframe_confirmation(symbol: str, signal_type: str, market_condition: str) -> bool:
    """Context-aware HTF confirmation"""
    try:
        htf_df = fetch_ohlcv(symbol, SMC_PARAMS['higher_timeframe'], 50)
        if htf_df is None or len(htf_df) < 20:
            return False
            
        htf_df = calculate_indicators(htf_df)
        last = htf_df.iloc[-1]
        
        # Strong confirmation required for counter-trend signals
        if market_condition == "BEARISH" and signal_type == "BUY":
            return (
                last['close'] > last['ema20'] and 
                last['rsi'] > 55 and
                last['adx'] > 25
            )
        elif market_condition == "BULLISH" and signal_type == "SELL":
            return (
                last['close'] < last['ema20'] and 
                last['rsi'] < 45 and
                last['adx'] > 25
            )
        
        # Standard trend-following confirmation
        if signal_type == "BUY":
            return (
                last['ema5'] > last['ema20'] and 
                last['close'] > last['bb_middle'] and
                last['rsi'] > 50
            )
        else:  # SELL
            return (
                last['ema5'] < last['ema20'] and 
                last['close'] < last['bb_middle'] and
                last['rsi'] < 50
            )
    except Exception as e:
        logger.error(f"HTF confirmation error for {symbol}: {str(e)}")
        return False

def calculate_position_size(atr: float, price: float, account_balance: float, symbol: str) -> float:
    """Position sizing with volatility adjustment"""
    volatility_rating = settings.VOLATILITY_RATINGS.get(symbol, 1.0)
    # More aggressive adjustment for high-volatility assets
    risk_multiplier = SMC_PARAMS['atr_risk_multiplier'] * (1.5 - volatility_rating)
    risk_amount = account_balance * (risk_multiplier / 100)
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
        'confirmed_resistance': False,
        'low_volatility': False,
        'strong_momentum': False,
        'at_key_level': False
    }
    
    try:
        # Volatility filter - reject low volatility signals
        atr_pct = last["atr"] / last["close"] if "atr" in last else 0
        conditions['low_volatility'] = atr_pct < SMC_PARAMS['min_atr_threshold']
        
        # Common conditions
        conditions.update({
            'broke_high': last["close"] > prev["high"],
            'broke_low': last["close"] < prev["low"],
            'rsi_ok': (params['rsi_oversold'] < last["rsi"] < params['rsi_overbought']),
            'vol_spike': (last["volume"] > last["volume_ma"] * params['volume_spike_multiplier']),
            'trend_aligned': (market_condition == "BULLISH" and last["ema5"] > last["ema10"]) or 
                            (market_condition == "BEARISH" and last["ema5"] < last["ema10"]),
            'vwap_confirm': 'vwap' in df.columns and last['close'] > last['vwap'],
            'trend_strength': last['adx'] > 25,
            'strong_momentum': (
                (last["rsi"] < 40) or  # Oversold for buys
                (last["rsi"] > 60)     # Overbought for sells
            )
        })
        
        # Liquidity zone detection
        zones = detect_liquidity_zones(df)
        conditions.update({
            'near_resistance': abs(last["close"] - zones['key_resistance']) / last["close"] < 0.005,
            'near_support': abs(last["close"] - zones['key_support']) / last["close"] < 0.005,
            'at_key_level': abs(last["close"] - zones['key_resistance']) / last["close"] < 0.005 or 
                           abs(last["close"] - zones['key_support']) / last["close"] < 0.005
        })
        
        # Specific conditions for NEUTRAL market
        if market_condition == "NEUTRAL":
            if not pd.isna(last["bb_lower"]) and not pd.isna(last["bb_upper"]):
                conditions.update({
                    'near_support': (abs(last["close"] - last["bb_lower"]) / last["close"] < params['bband_threshold']),
                    'near_resistance': (abs(last["close"] - last["bb_upper"]) / last["close"] < params['bband_threshold']),
                    'confirmed_support': (last["close"] > last["open"]) and 
                                        (last["volume"] > last["volume_ma"] * params['volume_spike_multiplier']),
                    'confirmed_resistance': (last["close"] < last["open"]) and 
                                           (last["volume"] > last["volume_ma"] * params['volume_spike_multiplier'])
                })
            else:
                logger.warning(f"Invalid BB values for {symbol} in NEUTRAL market")
        
        # Additional conditions
        conditions.update({
            'retest': (last["low"] > prev["high"] * (1 - params['retest_buffer'])) if conditions['broke_high'] else 
                     (last["high"] < prev["low"] * (1 + params['retest_buffer'])) if conditions['broke_low'] else False,
            'stoch_bullish': last["stoch_k"] > last["stoch_d"] and last["stoch_k"] < 80,
            'stoch_bearish': last["stoch_k"] < last["stoch_d"] and last["stoch_k"] > 20,
            'macd_bullish': last["macd_line"] > last["macd_signal"] and last["macd_hist"] > 0,
            'macd_bearish': last["macd_line"] < last["macd_signal"] and last["macd_hist"] < 0,
            'adx_ok': last["adx"] > settings.ADX_THRESHOLDS.get(symbol, 20)
        })
        
        # Check divergence
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
    """Calculate buy and sell scores with tiered weighting"""
    CORE_WEIGHT = 2.5  # Breakouts, volume spikes
    CONFIRM_WEIGHT = 1.5  # Trend alignment, ADX
    SECONDARY_WEIGHT = 0.7  # Oscillators
    NEGATIVE_WEIGHT = 2.0  # Penalties
    
    buy_score = sum([
        conditions['broke_high'] * CORE_WEIGHT,
        conditions['vol_spike'] * CORE_WEIGHT,
        conditions['trend_aligned'] * CONFIRM_WEIGHT,
        conditions['adx_ok'] * CONFIRM_WEIGHT,
        conditions['vwap_confirm'] * CONFIRM_WEIGHT,
        conditions['stoch_bullish'] * SECONDARY_WEIGHT,
        conditions['macd_bullish'] * SECONDARY_WEIGHT,
        conditions['retest'] * SECONDARY_WEIGHT,
        conditions['strong_momentum'] * 1.5,
        conditions['at_key_level'] * 1.2,
        # Penalties
        -NEGATIVE_WEIGHT if conditions['bear_div'] else 0,
        -NEGATIVE_WEIGHT if conditions['low_volatility'] else 0
    ])
    
    sell_score = sum([
        conditions['broke_low'] * CORE_WEIGHT,
        conditions['vol_spike'] * CORE_WEIGHT,
        (not conditions['trend_aligned'] and market_condition != "BULLISH") * CONFIRM_WEIGHT,
        conditions['adx_ok'] * CONFIRM_WEIGHT,
        (not conditions['vwap_confirm']) * CONFIRM_WEIGHT,
        conditions['stoch_bearish'] * SECONDARY_WEIGHT,
        conditions['macd_bearish'] * SECONDARY_WEIGHT,
        conditions['retest'] * SECONDARY_WEIGHT,
        conditions['strong_momentum'] * 1.5,
        conditions['at_key_level'] * 1.2,
        # Penalties
        -NEGATIVE_WEIGHT if conditions['bull_div'] else 0,
        -NEGATIVE_WEIGHT if conditions['low_volatility'] else 0
    ])
    
    return buy_score, sell_score

def get_signal(df: pd.DataFrame, symbol: str, market_condition: str, 
               consecutive_losses: int = 0) -> Optional[SMCSignal]:
    """Generate trading signal with improved filters"""
    if df is None or len(df) < 50:
        logger.warning(f"Insufficient data for {symbol}")
        return None
        
    if not is_optimal_trading_time():
        return None
        
    try:
        # Evaluate all conditions
        conditions = evaluate_conditions(df, market_condition, symbol)
        
        # Skip if low volatility
        if conditions['low_volatility']:
            return None
        
        # Check neutral market specific conditions
        if market_condition == "NEUTRAL":
            if not (conditions.get('confirmed_support', False) or 
                   conditions.get('confirmed_resistance', False)):
                return None
                
            if not conditions.get('rsi_ok', False):
                return None
                
            # Require strong momentum in neutral markets
            if not conditions['strong_momentum']:
                return None
                
            # Avoid counter-BTC trades in neutral markets
            btc_df = fetch_ohlcv("BTCUSDT", settings.TIMEFRAME, 50)
            if btc_df is not None and len(btc_df) > 0:
                btc_last = btc_df.iloc[-1]
                if symbol != "BTCUSDT":
                    if conditions['trend_aligned'] == False and btc_last['close'] > btc_last['ema20']:
                        return None

        # Calculate scores
        buy_score, sell_score = calculate_scores(conditions, market_condition)
        
        # Apply adaptive threshold
        adaptive_threshold = max(
            SMC_PARAMS['min_score_non_trend'],
            SMC_PARAMS['base_threshold'] - 
            (SMC_PARAMS['adaptive_loss_factor'] * min(consecutive_losses, 3))
        )
        
        # Check higher timeframe confirmation for stronger signals
        htf_confirm = check_higher_timeframe_confirmation(
            symbol,
            "BUY" if buy_score > sell_score else "SELL",
            market_condition
        )
        
        # Boost score if HTF confirms
        if htf_confirm:
            if buy_score > sell_score:
                buy_score += SMC_PARAMS['htf_confirm_weight']
            else:
                sell_score += SMC_PARAMS['htf_confirm_weight']
        
        # Generate signal
        atr = df["atr"].iloc[-1] if "atr" in df.columns else None
        entry_price = df["close"].iloc[-1]
        
        if (buy_score >= adaptive_threshold and 
            conditions['rsi_ok'] and
            (market_condition != "BEARISH" or buy_score > adaptive_threshold + 1.0)):
            return SMCSignal(
                "BUY", symbol, buy_score, adaptive_threshold,
                {k: v for k, v in conditions.items() if v},
                atr, entry_price, market_condition
            )
            
        elif (sell_score >= adaptive_threshold and 
              conditions['rsi_ok'] and
              (market_condition != "BULLISH" or sell_score > adaptive_threshold + 1.0)):
            return SMCSignal(
                "SELL", symbol, sell_score, adaptive_threshold,
                {k: v for k, v in conditions.items() if v},
                atr, entry_price, market_condition
            )
            
        return None
        
    except Exception as e:
        logger.error(f"Signal generation failed for {symbol}: {str(e)}", exc_info=True)
        return None