"""
Production-ready Binance Futures Signal Bot - SIGNAL GENERATION ONLY
Optimized RSI-9/RSI-21 + MACD(8,21,5) Strategy for Maximum Accuracy
LIVE TRADING DISABLED - Signals Only
"""
import asyncio
import time
import logging
import pandas as pd
import ccxt
import requests
from datetime import datetime
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# TRADING CONTROL - Set to False to disable all live trading
LIVE_TRADING_ENABLED = False

# Global state
last_signals = {}  # Prevent duplicate signals
active_signals = {}  # Track active signals for TP/SL monitoring
import json
import os
current_prices = {}  # Current price tracking

# --- Persistent Storage for Active Signals ---
SIGNALS_FILE = "active_signals.json"

def save_active_signals():
    with open(SIGNALS_FILE, "w") as f:
        json.dump(active_signals, f, default=str)

def load_active_signals():
    global active_signals
    if os.path.exists(SIGNALS_FILE):
        with open(SIGNALS_FILE, "r") as f:
            active_signals = json.load(f)
    else:
        active_signals = {}

# Load signals at startup
load_active_signals()

# --- Exchange Setup ---
def setup_exchange():
    """Initialize Binance Futures exchange with trading capabilities"""
    return ccxt.binance({
        'apiKey': settings.BINANCE_API_KEY,
        'secret': settings.BINANCE_SECRET_KEY,
        'options': {'defaultType': 'future'},
        'enableRateLimit': True,
        'rateLimit': 100,  # Optimized for live data
        'timeout': 20000,
        'sandbox': False,  # Live trading
    })

# --- Discord Messaging ---
def send_discord_message(message):
    """Send message to Discord webhook"""
    if not hasattr(settings, 'DISCORD_WEBHOOK_URL') or not settings.DISCORD_WEBHOOK_URL:
        logger.warning("Discord webhook URL not configured")
        return
    
    try:
        response = requests.post(
            settings.DISCORD_WEBHOOK_URL, 
            json={"content": message},
            timeout=10
        )
        if response.status_code == 204:
            logger.info("Discord message sent successfully")
        else:
            logger.error(f"Discord error: {response.status_code}")
    except Exception as e:
        logger.error(f"Discord error: {str(e)}")

# --- Position Size Calculation ---
def calculate_position_size(exchange, symbol, entry_price):
    """Calculate position size based on your risk management"""
    try:
        # Get account balance
        balance = exchange.fetch_balance()
        usdt_balance = balance['USDT']['free']
        
        # Your plan: $3 per trade with 50x leverage
        trade_amount = min(3.0, usdt_balance * 0.10)  # Max 10% of account or $3
        
        # Calculate position size (leverage is set on Binance account)
        position_size = trade_amount / entry_price
        
        # Round to appropriate precision for the symbol
        if 'DOGE' in symbol:
            position_size = round(position_size, 0)  # Whole numbers for DOGE
        elif 'BTC' in symbol:
            position_size = round(position_size, 3)  # 3 decimal places for BTC
        else:
            position_size = round(position_size, 2)  # 2 decimal places for others
            
        return position_size
        
    except Exception as e:
        logger.error(f"Error calculating position size: {e}")
        return 0

# --- Trading Functions ---
def place_futures_order(exchange, symbol, side, amount):
    """Place a futures market order on Binance"""
    try:
        # Convert symbol format (BTCUSDT -> BTC/USDT)
        ccxt_symbol = f"{symbol[:-4]}/{symbol[-4:]}" if symbol.endswith('USDT') else symbol
        
        order = exchange.create_market_order(
            symbol=ccxt_symbol,
            side=side.lower(),
            amount=amount,
        )
        
        logger.info(f"✅ ORDER PLACED: {symbol} {side} {amount} @ Market")
        return order
        
    except Exception as e:
        logger.error(f"❌ ORDER FAILED: {symbol} {side} - {str(e)}")
        return None

def close_position(exchange, symbol, signal_type):
    """Close futures position by placing opposite market order"""
    try:
        # Convert symbol format
        ccxt_symbol = f"{symbol[:-4]}/{symbol[-4:]}" if symbol.endswith('USDT') else symbol
        
        # Get current positions
        positions = exchange.fetch_positions([ccxt_symbol])
        
        # Find the position to close
        for position in positions:
            if position['symbol'] == ccxt_symbol and float(position['size']) > 0:
                # Determine close side (opposite of original signal)
                close_side = 'sell' if signal_type == 'BUY' else 'buy'
                amount = abs(float(position['size']))
                
                # Place close order
                close_order = exchange.create_market_order(
                    symbol=ccxt_symbol,
                    side=close_side,
                    amount=amount,
                )
                
                logger.info(f"✅ POSITION CLOSED: {symbol} {close_side} {amount} @ Market")
                return close_order
        
        logger.warning(f"⚠️ No position found to close for {symbol}")
        return None
        
    except Exception as e:
        logger.error(f"❌ CLOSE FAILED: {symbol} - {str(e)}")
        return None

# --- Technical Indicators (Optimized for Crypto) ---
def calculate_rsi(prices, period):
    """Calculate RSI using Wilder's smoothing method for better accuracy"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # Use Wilder's smoothing (more accurate than simple moving average)
    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(prices, fast=9, slow=21, signal=9):
    """Calculate MACD with improved periods for higher win rate"""
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, macd_signal

def add_indicators(df):
    """Add optimized technical indicators"""
    if len(df) < 50:  # Need more data for accuracy
        return df
    
    # Optimized RSI settings for crypto
    df['rsi_9'] = calculate_rsi(df['close'], 9)   # Short-term (responsive)
    df['rsi_21'] = calculate_rsi(df['close'], 21) # Long-term (trend confirmation)
    
    # Optimized MACD settings for higher win rate
    df['macd_line'], df['macd_signal'] = calculate_macd(df['close'], fast=9, slow=21, signal=9)
    
    # Additional filter: Volume confirmation
    df['volume_sma'] = df['volume'].rolling(window=20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_sma']
    
    return df.dropna()

# --- Advanced Signal Generation (Accuracy-Focused) ---
def detect_rsi_crossover(df):
    """Enhanced RSI crossover detection to avoid extreme conditions"""
    if len(df) < 3:  # Need at least 3 candles for confirmation
        return None
    
    prev2 = df.iloc[-3]
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    
    # BALANCED volume filter - require decent volume but not extreme
    if curr['volume_ratio'] < 0.7:  # Volume must be at least 70% of average
        return None
    
    # BALANCED Buy Signal - reasonable RSI ranges for quality signals
    if (prev2['rsi_9'] < prev2['rsi_21'] and 
        prev['rsi_9'] <= prev['rsi_21'] and 
        curr['rsi_9'] > curr['rsi_21'] and
        25 < curr['rsi_9'] < 65 and 30 < curr['rsi_21'] < 60 and  # BALANCED ranges
        curr['rsi_9'] > prev['rsi_9']):  # RSI-9 trending up
        return 'BUY'
    
    # BALANCED Sell Signal - reasonable RSI ranges for quality signals
    if (prev2['rsi_9'] > prev2['rsi_21'] and 
        prev['rsi_9'] >= prev['rsi_21'] and 
        curr['rsi_9'] < curr['rsi_21'] and
        35 < curr['rsi_9'] < 75 and 40 < curr['rsi_21'] < 70 and  # BALANCED ranges
        curr['rsi_9'] < prev['rsi_9']):  # RSI-9 trending down
        return 'SELL'
    
    return None

def confirm_with_macd(df, signal_type, symbol):
    """Enhanced MACD confirmation with symbol-aware strength requirements"""
    if len(df) < 2:
        return False
        
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    
    # BALANCED MACD strength requirements for reasonable signal frequency
    if 'DOGE' in symbol or 'ADA' in symbol:
        min_strength = 0.0002  # Slightly higher for small-cap coins for quality
    elif 'BTC' in symbol:
        min_strength = 8       # Balanced for BTC (not too low, not too high)
    elif 'ETH' in symbol:
        min_strength = 0.8     # Balanced for ETH
    else:
        min_strength = 0.15    # Balanced for other pairs
    
    # For BUY: MACD line above signal AND gaining momentum AND sufficient strength
    if signal_type == 'BUY':
        return (curr['macd_line'] > curr['macd_signal'] and 
                curr['macd_line'] > prev['macd_line'] and
                abs(curr['macd_line']) > min_strength)  # MACD gaining upward momentum
    
    # For SELL: MACD line below signal AND losing momentum AND sufficient strength
    elif signal_type == 'SELL':
        return (curr['macd_line'] < curr['macd_signal'] and 
                curr['macd_line'] < prev['macd_line'] and
                abs(curr['macd_line']) > min_strength)  # MACD gaining downward momentum
    
    return False

def detect_market_condition(df):
    """Detect if market is trending or choppy based on price action and volatility"""
    closes = df['close']
    highs = df['high']
    lows = df['low']
    
    # Get recent 20 candles for analysis
    recent_data = df.tail(20)
    
    # Calculate price range percentage over last 20 candles
    recent_high = recent_data['high'].max()
    recent_low = recent_data['low'].min()
    price_range_pct = ((recent_high - recent_low) / recent_low) * 100
    
    # Calculate Average True Range (ATR) for volatility
    high_low = recent_data['high'] - recent_data['low']
    high_close = abs(recent_data['high'] - recent_data['close'].shift())
    low_close = abs(recent_data['low'] - recent_data['close'].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=14).mean().iloc[-1]
    atr_pct = (atr / closes.iloc[-1]) * 100
    
    # Calculate trend strength using EMA slope
    ema20 = closes.ewm(span=20).mean()
    ema_slope = (ema20.iloc[-1] - ema20.iloc[-5]) / ema20.iloc[-5] * 100
    
    # Calculate choppiness using price swings
    price_swings = 0
    for i in range(-10, -1):
        if i + 1 < 0:  # Ensure we don't go out of bounds
            if ((closes.iloc[i] > closes.iloc[i-1] and closes.iloc[i+1] < closes.iloc[i]) or 
                (closes.iloc[i] < closes.iloc[i-1] and closes.iloc[i+1] > closes.iloc[i])):
                price_swings += 1
    
    # Market condition logic
    if price_range_pct > 2.5 and abs(ema_slope) > 0.3 and price_swings < 4:
        condition = "TRENDING"
        strength = "Strong" if price_range_pct > 4 else "Moderate"
    elif price_range_pct < 1.5 and abs(ema_slope) < 0.2 and price_swings > 6:
        condition = "CHOPPY"
        strength = "High" if price_swings > 8 else "Moderate"
    else:
        condition = "MIXED"
        strength = "Moderate"
    
    return {
        'condition': condition,
        'strength': strength,
        'price_range_pct': price_range_pct,
        'volatility_pct': atr_pct,
        'trend_slope': ema_slope
    }

def additional_market_filters(df, signal_type):
    """BALANCED filters to protect against poor conditions while allowing reasonable signals"""
    curr = df.iloc[-1]
    closes = df['close']
    highs = df['high']
    lows = df['low']

    # STRICT trend filter - only trade WITH strong trends
    ema20 = closes.ewm(span=20, adjust=False).mean().iloc[-1]
    ema_trend_strength = (ema20 - closes.ewm(span=20, adjust=False).mean().iloc[-5]) / closes.ewm(span=20, adjust=False).mean().iloc[-5]
    
    if signal_type == 'BUY':
        if curr['close'] < ema20 * 1.002:  # Must be 0.2% above EMA
            return False
        if ema_trend_strength < 0.0008:  # EMA must be rising
            return False
    else:
        if curr['close'] > ema20 * 0.998:  # Must be 0.2% below EMA  
            return False
        if ema_trend_strength > -0.0008:  # EMA must be falling
            return False

    # STRICT volatility requirement - avoid dead markets
    volatility = highs.rolling(20).std() / closes.rolling(20).mean()
    if volatility.iloc[-1] < 0.015:  # Require significant movement
        return False

    # STRICT price position filter - avoid ranging extremes
    recent_highs = highs.tail(20).max()
    recent_lows = lows.tail(20).min()
    if recent_highs != recent_lows:
        current_position = (curr['close'] - recent_lows) / (recent_highs - recent_lows)
        
        # Only trade in favorable positions
        if signal_type == 'SELL' and current_position < 0.25:  # Avoid bottom 25%
            return False
        if signal_type == 'BUY' and current_position > 0.75:   # Avoid top 25%
            return False

    # STRICT momentum requirement - price must be moving in signal direction
    momentum_5 = (curr['close'] - df.iloc[-5]['close']) / df.iloc[-5]['close']
    if signal_type == 'BUY' and momentum_5 < 0.002:  # 0.2% bullish momentum required
        return False
    if signal_type == 'SELL' and momentum_5 > -0.002:  # 0.2% bearish momentum required
        return False

    # STRICT choppiness avoidance
    price_range = (highs.tail(20).max() - lows.tail(20).min()) / closes.tail(20).mean()
    if price_range < 0.008:  # Avoid flat markets (<0.8% range)
        return False
    if price_range > 0.15:    # Avoid extremely volatile markets (>15% range)
        return False

    # Volume confirmation - need above average activity
    avg_volume = df['volume'].rolling(20).mean().iloc[-1]
    if curr['volume'] < avg_volume * 1.1:  # Require 10% above average volume
        return False

    return True

def generate_signal(symbol, df, timeframe):
    """Generate high-accuracy trading signal with multiple confirmations"""
    # First check: RSI crossover
    signal_type = detect_rsi_crossover(df)
    if not signal_type:
        logger.info(f"{symbol} {timeframe}: No RSI crossover detected (RSI9: {df.iloc[-1]['rsi_9']:.1f}, RSI21: {df.iloc[-1]['rsi_21']:.1f}, Vol: {df.iloc[-1]['volume_ratio']:.2f})")
        return None

    # Second check: MACD confirmation (pass symbol as parameter)
    if not confirm_with_macd(df, signal_type, symbol):
        logger.info(f"{symbol} {timeframe}: RSI {signal_type} signal but MACD not confirmed")
        return None

    # Third check: Market condition filters
    if not additional_market_filters(df, signal_type):
        logger.info(f"{symbol} {timeframe}: {signal_type} signal filtered out by market conditions")
        return None

    # Detect market condition for signal context
    market_info = detect_market_condition(df)
    
    # BALANCED market condition filter - avoid only extreme conditions
    if market_info['condition'] == 'CHOPPY':
        logger.info(f"{symbol} {timeframe}: {signal_type} signal blocked - CHOPPY market detected")
        return None
    
    # For MIXED markets, only block if volatility is very high (dangerous conditions)
    if market_info['condition'] == 'MIXED' and market_info['volatility'] > 0.025:  # 2.5% volatility threshold
        logger.info(f"{symbol} {timeframe}: {signal_type} signal blocked - High volatility MIXED market")
        return None

    curr = df.iloc[-1]
    entry_price = curr['close']

    # Fixed 0.50% TP and SL as requested
    if signal_type == 'BUY':
        tp_price = entry_price * (1 + settings.TP_PERCENT)
        sl_price = entry_price * (1 - settings.SL_PERCENT)
    else:  # SELL
        tp_price = entry_price * (1 - settings.TP_PERCENT)
        sl_price = entry_price * (1 + settings.SL_PERCENT)

    return {
        'symbol': symbol,
        'type': signal_type,  # Fix: was 'signal_type', should be 'type'
        'entry_price': entry_price,
        'tp': tp_price,  # Fix: was 'tp_price', should be 'tp'
        'sl': sl_price,  # Fix: was 'sl_price', should be 'sl'
        'timeframe': timeframe,
        'market_condition': market_info['condition'],
        'market_strength': market_info['strength'],
        'trend_slope': market_info['trend_slope'],
        'volatility': market_info['volatility_pct'],
        'rsi_9': curr['rsi_9'],
        'rsi_21': curr['rsi_21'],
        'macd_line': curr['macd_line'],
        'macd_signal': curr['macd_signal'],
        'volume_ratio': curr['volume_ratio'],
        'timestamp': pd.Timestamp.now()
    }

def format_signal_message(signal):
    # Determine market condition emoji
    if signal['market_condition'] == 'TRENDING':
        market_emoji = "📈" if signal['trend_slope'] > 0 else "📉"
    elif signal['market_condition'] == 'CHOPPY':
        market_emoji = "⚡"
    else:
        market_emoji = "📊"
    
    return (
        f"🚀 [{signal['symbol']}] {signal['type']} SIGNAL\n"
        f"💰 Entry: {signal['entry_price']:.6f}\n"
        f"🎯 TP: {signal['tp']:.6f} (+{settings.TP_PERCENT*100:.2f}%)\n"
        f"🛑 SL: {signal['sl']:.6f} (-{settings.SL_PERCENT*100:.2f}%)\n"
        f"{market_emoji} Market: {signal['market_condition']} ({signal['market_strength']})\n"
        f"📊 Volatility: {signal['volatility']:.2f}%\n"
        f"⏰ Time: {signal['timestamp'].strftime('%H:%M:%S')}"
    )

def format_result_message(signal, hit_type, hit_price, symbol):
    return (
        f"[{symbol}] {signal['signal_type']}\n"
        f"{hit_type} HIT at {hit_price:.6f}\n"
        f"Entry: {signal['entry_price']:.6f}\n"
        f"Time: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

# --- Optimized Data Fetching ---
def fetch_candles(exchange, symbol, timeframe, limit=100):
    """Fetch OHLCV data with error handling and price tracking"""
    try:
        # Convert symbol format for ccxt (BTCUSDT -> BTC/USDT)
        ccxt_symbol = f"{symbol[:-4]}/{symbol[-4:]}" if symbol.endswith('USDT') else symbol
        
        # Fetch with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                ohlcv = exchange.fetch_ohlcv(ccxt_symbol, timeframe, limit=limit)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                time.sleep(1)  # Fixed: use time.sleep instead of await
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # Update current price for TP/SL monitoring
        if len(df) > 0:
            current_prices[symbol] = df.iloc[-1]['close']
        
        return df
    except Exception as e:
        logger.error(f"Error fetching {symbol} {timeframe}: {str(e)}")
        return pd.DataFrame()


# --- TP/SL Monitoring ---
def check_tp_sl_hits(symbol, exchange=None):
    """Check if TP or SL is hit for any active signal for the symbol."""
    if symbol not in active_signals or not active_signals[symbol]:
        return
    signals_to_remove = []
    current_price = current_prices.get(symbol)
    if current_price is None:
        return
    for signal_id, signal in list(active_signals[symbol].items()):
        tp_hit = False
        sl_hit = False
        if signal['signal_type'] == 'BUY':
            if current_price >= signal['tp_price']:
                tp_hit = True
            elif current_price <= signal['sl_price']:
                sl_hit = True
        elif signal['signal_type'] == 'SELL':
            if current_price <= signal['tp_price']:
                tp_hit = True
            elif current_price >= signal['sl_price']:
                sl_hit = True
        if tp_hit:
            message = format_result_message(signal, "TP", current_price, symbol)
            send_discord_message(message)
            logger.info(f"TP HIT: {symbol} {signal['signal_type']} @ {current_price:.4f} - Signal closed")
            
            # DISABLED: Position closing is turned off - only monitoring for signals
            if LIVE_TRADING_ENABLED and hasattr(settings, 'BINANCE_API_KEY') and exchange:
                close_position(exchange, symbol, signal['signal_type'])
            else:
                logger.info(f"📊 SIGNAL MONITORING: {symbol} TP would close @ {current_price:.4f} but live trading disabled")
            
            signals_to_remove.append(signal_id)
            save_active_signals()
        elif sl_hit:
            message = format_result_message(signal, "SL", current_price, symbol)
            send_discord_message(message)
            logger.info(f"SL HIT: {symbol} {signal['signal_type']} @ {current_price:.4f} - Signal closed")
            
            # DISABLED: Position closing is turned off - only monitoring for signals
            if LIVE_TRADING_ENABLED and hasattr(settings, 'BINANCE_API_KEY') and exchange:
                close_position(exchange, symbol, signal['signal_type'])
            else:
                logger.info(f"📊 SIGNAL MONITORING: {symbol} SL would close @ {current_price:.4f} but live trading disabled")
            
            signals_to_remove.append(signal_id)
            save_active_signals()
    # Remove completed signals
    for signal_id in signals_to_remove:
        del active_signals[symbol][signal_id]
    # Clean up empty symbol entries
    if symbol in active_signals and not active_signals[symbol]:
        del active_signals[symbol]

# --- Optimized Trading Loop ---
async def monitor_symbol(exchange, symbol, timeframes=['15m']):
    """Monitor symbol with optimized multi-timeframe analysis"""
    logger.info(f"Starting optimized monitoring for {symbol}")
    
    while True:
        try:
            for timeframe in timeframes:
                # Fetch latest candles with more data for accuracy
                df = fetch_candles(exchange, symbol, timeframe, limit=100)
                
                if len(df) < 50:  # Need more data for accurate indicators
                    logger.warning(f"Insufficient data for {symbol} {timeframe}")
                    continue
                
                # Add optimized indicators
                df = add_indicators(df)
                
                if len(df) < 10:  # Need sufficient data after dropna()
                    continue
                
                # Check TP/SL hits for existing signals
                check_tp_sl_hits(symbol, exchange)
                
                # Generate high-accuracy signal
                signal = generate_signal(symbol, df, timeframe)
                
                if signal:
                    # One signal per symbol rule
                    if symbol in active_signals and active_signals[symbol]:
                        logger.debug(f"Skipping new signal for {symbol} - existing signal active")
                        continue
                    
                    # Enhanced duplicate prevention (include timeframe and price range)
                    signal_key = f"{symbol}_{timeframe}_{signal['type']}_{signal['entry_price']:.2f}"
                    
                    if signal_key not in last_signals:
                        # Store signal with entry price for position sizing
                        entry_price = signal['entry_price']
                        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                        signal_id = f"{symbol}_{signal['type']}_{timestamp}"
                        
                        active_signals.setdefault(symbol, {})[signal_id] = {
                            'signal_type': signal['type'],
                            'entry_price': entry_price,
                            'tp_price': signal['tp'],
                            'sl_price': signal['sl'],
                            'timestamp': timestamp
                        }
                        save_active_signals()
                        
                        # DISABLED: Live trading is turned off - only generating signals
                        if LIVE_TRADING_ENABLED and hasattr(settings, 'BINANCE_API_KEY') and exchange:
                            position_size = calculate_position_size(exchange, symbol, entry_price)
                            if position_size > 0:
                                side = 'buy' if signal['type'] == 'BUY' else 'sell'
                                trade_result = place_futures_order(exchange, symbol, side, position_size)
                                
                                if trade_result:
                                    logger.info(f"🚀 LIVE TRADE EXECUTED: {symbol} {signal['type']} Size: {position_size} ($3)")
                        else:
                            logger.info(f"📊 SIGNAL-ONLY MODE: {symbol} {signal['type']} (live trading disabled)")
                        
                        # Send optimized signal to Discord
                        message = format_signal_message(signal)
                        send_discord_message(message)
                        
                        # Enhanced logging
                        logger.info(f"HIGH-ACCURACY SIGNAL: {symbol} {timeframe} {signal['type']} @ {signal['entry_price']:.4f}")
                        logger.info(f"RSI(9,21): {signal.get('rsi_9', 0):.1f}/{signal.get('rsi_21', 0):.1f} | MACD: {signal.get('macd_line', 0):.6f}")
                        
                        # Store signal
                        last_signals[signal_key] = time.time()
                        
                        # Add to active monitoring (clean up old format)
                        if symbol not in active_signals:
                            active_signals[symbol] = {}
                        
                        # Clean old signals (4 hours for crypto volatility)
                        current_time = time.time()
                        old_signals = [k for k, v in last_signals.items() if current_time - v > 14400]
                        for old_key in old_signals:
                            if old_key in last_signals:
                                del last_signals[old_key]
            
            # Optimized delay for 15m timeframe
            await asyncio.sleep(5)  # 5 seconds for 15m timeframe
            
        except Exception as e:
            logger.error(f"Error monitoring {symbol}: {str(e)}")
            await asyncio.sleep(10)

async def main():
    """Main application entry point with optimized settings"""
    logger.info("� Starting SIGNAL-ONLY Binance Futures Bot")
    logger.info(f"📊 Monitoring pairs: {settings.PAIRS}")
    logger.info(f"⏱️ Timeframes: 15m")
    logger.info(f"🎯 Strategy: RSI(9,21) + MACD(9,21,9) - Signal Generation Only")
    logger.info(f"💰 Fixed TP/SL: {settings.TP_PERCENT*100:.2f}%")
    logger.info(f"🔧 Enhanced Filters: Volume, Volatility, Momentum")
    logger.info(f"❌ Live Trading: DISABLED (LIVE_TRADING_ENABLED = {LIVE_TRADING_ENABLED})")
    
    # Setup exchange for data fetching only
    exchange = None
    if hasattr(settings, 'BINANCE_API_KEY') and settings.BINANCE_API_KEY != "your_binance_api_key_here":
        exchange = setup_exchange()
        if exchange:
            logger.info("🚀 LIVE TRADING MODE - Binance API connected successfully!")
        else:
            logger.warning("⚠️ Failed to connect to Binance API - Running in signal-only mode")
    else:
        logger.info("📊 SIGNAL-ONLY MODE - Add API keys to settings.py for live trading")
        exchange = setup_exchange()  # For data fetching only
    
    # Test Discord connection
    send_discord_message(
        f"```BOT SUCCESSFULLY STARTED```\n"
        f"� **SIGNAL-ONLY BOT ONLINE** �\n"
        f"⏰ **Started:** `{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
        f"🔄 **Mode:** `SIGNAL GENERATION ONLY`\n"
        f"❌ **Live Trading:** `DISABLED`\n"
        f"═══════════════════════════════════\n"
        f"🔥 **READY TO GENERATE SIGNALS!** 🔥"
    )
    
    # Create monitoring tasks for all symbols
    tasks = [monitor_symbol(exchange, symbol) for symbol in settings.PAIRS]
    
    # Run all tasks concurrently
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        send_discord_message(f"🚨 **Bot Error** - {str(e)}")
