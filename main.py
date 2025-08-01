"""
Production-ready Binance Futures Signal Bot
Optimized RSI-9/RSI-21 + MACD(8,21,5) Strategy for Maximum Accuracy
"""
import asyncio
import time
import logging
import pandas as pd
import ccxt
import requests
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

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
    """Initialize Binance Futures exchange with optimized settings"""
    return ccxt.binance({
        'options': {'defaultType': 'future'},
        'enableRateLimit': True,
        'rateLimit': 100,  # Optimized for live data
        'timeout': 20000,
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
    
    # Enhanced volume filter
    if curr['volume_ratio'] < 1.2:  # Volume must be 20% above average
        return None
    
    # Buy Signal with improved conditions (avoid extreme oversold)
    # Enhanced conditions for accuracy:
    # 1. Improved RSI ranges to avoid quick reversals
    # 2. Sustained crossover (confirmed over 2 periods)
    # 3. RSI-9 trending upward
    if (prev2['rsi_9'] < prev2['rsi_21'] and 
        prev['rsi_9'] <= prev['rsi_21'] and 
        curr['rsi_9'] > curr['rsi_21'] and
        35 < curr['rsi_9'] < 75 and 40 < curr['rsi_21'] < 70 and  # Avoid extreme oversold
        curr['rsi_9'] > prev['rsi_9']):  # RSI-9 trending up
        return 'BUY'
    
    # Sell Signal with improved conditions (avoid extreme overbought)
    # Enhanced conditions for accuracy:
    # 1. Improved RSI ranges to avoid quick reversals
    # 2. Sustained crossover (confirmed over 2 periods)  
    # 3. RSI-9 trending downward
    if (prev2['rsi_9'] > prev2['rsi_21'] and 
        prev['rsi_9'] >= prev['rsi_21'] and 
        curr['rsi_9'] < curr['rsi_21'] and
        25 < curr['rsi_9'] < 65 and 30 < curr['rsi_21'] < 60 and  # Avoid extreme overbought
        curr['rsi_9'] < prev['rsi_9']):  # RSI-9 trending down
        return 'SELL'
    
    return None

def confirm_with_macd(df, signal_type):
    """Enhanced MACD confirmation with symbol-aware strength requirements"""
    if len(df) < 2:
        return False
        
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    
    # Symbol-aware MACD strength requirements
    symbol = df.attrs.get('symbol', '')
    if 'DOGE' in symbol or 'ADA' in symbol:
        min_strength = 0.002  # Higher threshold for volatile small-cap coins
    elif 'BTC' in symbol:
        min_strength = 50     # BTC has larger MACD values
    elif 'ETH' in symbol:
        min_strength = 5      # ETH moderate MACD values
    else:
        min_strength = 1      # Other pairs
    
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

def additional_market_filters(df, signal_type):
    """Enhanced 15m-optimized filters for better entries"""
    curr = df.iloc[-1]
    closes = df['close']
    highs = df['high']
    lows = df['low']

    # 15m-optimized trend filter using EMA-20 (more responsive than EMA-50)
    ema20 = closes.ewm(span=20, adjust=False).mean().iloc[-1]
    if signal_type == 'BUY' and curr['close'] < ema20:
        return False
    if signal_type == 'SELL' and curr['close'] > ema20:
        return False

    # Recent price position filter (avoid buying tops/selling bottoms)
    recent_highs = highs.tail(5).max()
    recent_lows = lows.tail(5).min()
    if recent_highs != recent_lows:  # Avoid division by zero
        current_position = (curr['close'] - recent_lows) / (recent_highs - recent_lows)
        
        # Don't sell at the bottom 30% of recent range, don't buy at top 70%
        if signal_type == 'SELL' and current_position < 0.3:
            return False
        if signal_type == 'BUY' and current_position > 0.7:
            return False

    # Choppiness filter (slightly adjusted for 15m)
    price_range = (highs.tail(10).max() - lows.tail(10).min()) / closes.tail(10).mean()
    if price_range < 0.002:  # <0.2% range = too flat
        return False
    if price_range > 0.06:   # >6% range = too wild
        return False

    # Faster momentum confirmation for 15m (2-candle lookback)
    if signal_type == 'BUY' and closes.iloc[-1] < closes.iloc[-2]:
        return False
    if signal_type == 'SELL' and closes.iloc[-1] > closes.iloc[-2]:
        return False

    return True

def generate_signal(symbol, df, timeframe):
    """Generate high-accuracy trading signal with multiple confirmations"""
    # Add symbol info to dataframe for MACD filtering
    df.attrs['symbol'] = symbol
    
    # First check: RSI crossover
    signal_type = detect_rsi_crossover(df)
    if not signal_type:
        return None

    # Second check: MACD confirmation
    if not confirm_with_macd(df, signal_type):
        logger.debug(f"{symbol} {timeframe}: RSI signal but MACD not confirmed")
        return None

    # Third check: Market condition filters
    if not additional_market_filters(df, signal_type):
        logger.debug(f"{symbol} {timeframe}: Signal filtered out by market conditions")
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
        'signal_type': signal_type,
        'entry_price': entry_price,
        'tp_price': tp_price,
        'sl_price': sl_price,
        'timeframe': timeframe,
        'rsi_9': curr['rsi_9'],
        'rsi_21': curr['rsi_21'],
        'macd_line': curr['macd_line'],
        'macd_signal': curr['macd_signal'],
        'volume_ratio': curr['volume_ratio'],
        'timestamp': pd.Timestamp.now()
    }

def format_signal_message(signal):
    return (
        f"[{signal['symbol']}] {signal['signal_type']}\n"
        f"Entry: {signal['entry_price']:.6f}\n"
        f"TP: {signal['tp_price']:.6f} (+0.50%)\n"
        f"SL: {signal['sl_price']:.6f} (-0.50%)\n"
        f"Signal Time: {signal['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}"
    )

def format_result_message(signal, hit_type, hit_price):
    return (
        f"[{signal['symbol']}] {signal['signal_type']}\n"
        f"{hit_type} HIT at {hit_price:.6f}\n"
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
def check_tp_sl_hits(symbol):
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
            message = format_result_message(signal, "TP", current_price)
            send_discord_message(message)
            logger.info(f"TP HIT: {symbol} {signal['signal_type']} @ {current_price:.4f} - Signal closed")
            signals_to_remove.append(signal_id)
            save_active_signals()
        elif sl_hit:
            message = format_result_message(signal, "SL", current_price)
            send_discord_message(message)
            logger.info(f"SL HIT: {symbol} {signal['signal_type']} @ {current_price:.4f} - Signal closed")
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
                check_tp_sl_hits(symbol)
                
                # Generate high-accuracy signal
                signal = generate_signal(symbol, df, timeframe)
                
                if signal:
                    # One signal per symbol rule
                    if symbol in active_signals and active_signals[symbol]:
                        logger.debug(f"Skipping new signal for {symbol} - existing signal active")
                        continue
                    
                    # Enhanced duplicate prevention (include timeframe and price range)
                    signal_key = f"{symbol}_{timeframe}_{signal['signal_type']}_{signal['entry_price']:.2f}"
                    
                    if signal_key not in last_signals:
                        # Send optimized signal to Discord
                        message = format_signal_message(signal)
                        send_discord_message(message)
                        
                        # Enhanced logging
                        logger.info(f"HIGH-ACCURACY SIGNAL: {symbol} {timeframe} {signal['signal_type']} @ {signal['entry_price']:.4f}")
                        logger.info(f"RSI(9,21): {signal['rsi_9']:.1f}/{signal['rsi_21']:.1f} | MACD: {signal['macd_line']:.6f}")
                        
                        # Store signal
                        last_signals[signal_key] = time.time()
                        
                        # Add to active monitoring
                        if symbol not in active_signals:
                            active_signals[symbol] = {}
                        active_signals[symbol][signal_key] = signal
                        save_active_signals()
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
    logger.info("🚀 Starting OPTIMIZED Binance Futures Signal Bot")
    logger.info(f"📊 Monitoring pairs: {settings.PAIRS}")
    logger.info(f"⏱️ Timeframes: 15m")
    logger.info(f"🎯 Strategy: RSI(9,21) + MACD(9,21,9) - Improved for Higher Win Rate")
    logger.info(f"💰 Fixed TP/SL: {settings.TP_PERCENT*100:.2f}%")
    logger.info(f"🔧 Enhanced Filters: Volume, Volatility, Momentum")
    
    # Setup optimized exchange
    exchange = setup_exchange()
    
    # Test Discord connection
    send_discord_message(
        f"``` BOT SUCCESSFULLY STARTED +```\n"
        f"🤖🚀 **OPTIMIZED TRADING BOT ONLINE** 🚀🤖\n"
        f"⏰ **Started:** `{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
        f"═══════════════════════════════════\n"
        f"```\n"
        f"🔥 **READY TO HUNT HIGH-PROBABILITY SIGNALS!** 🔥"
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
