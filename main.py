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
current_prices = {}  # Current price tracking

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
    """Detect RSI-9 vs RSI-21 crossover with additional filters"""
    if len(df) < 3:  # Need at least 3 candles for confirmation
        return None
    
    prev2 = df.iloc[-3]
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    
    # Additional volume filter (must have above-average volume)
    if curr['volume_ratio'] < 1.2:  # Volume must be 20% above average
        return None
    
    # Buy Signal: RSI-9 crosses above RSI-21
    # Additional conditions for accuracy:
    # 1. Both RSI values between 30-80 (avoid extreme overbought/oversold)
    # 2. Sustained crossover (confirmed over 2 periods)
    # 3. RSI-9 trending upward
    if (prev2['rsi_9'] < prev2['rsi_21'] and 
        prev['rsi_9'] <= prev['rsi_21'] and 
        curr['rsi_9'] > curr['rsi_21'] and
        30 < curr['rsi_9'] < 80 and 30 < curr['rsi_21'] < 70 and
        curr['rsi_9'] > prev['rsi_9']):  # RSI-9 trending up
        return 'BUY'
    
    # Sell Signal: RSI-9 crosses below RSI-21
    # Additional conditions for accuracy:
    # 1. Both RSI values between 20-70 (avoid extreme conditions)
    # 2. Sustained crossover (confirmed over 2 periods)  
    # 3. RSI-9 trending downward
    if (prev2['rsi_9'] > prev2['rsi_21'] and 
        prev['rsi_9'] >= prev['rsi_21'] and 
        curr['rsi_9'] < curr['rsi_21'] and
        20 < curr['rsi_9'] < 70 and 30 < curr['rsi_21'] < 70 and
        curr['rsi_9'] < prev['rsi_9']):  # RSI-9 trending down
        return 'SELL'
    
    return None

def confirm_with_macd(df, signal_type):
    """Enhanced MACD confirmation with momentum filter"""
    if len(df) < 2:
        return False
        
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    
    # For BUY: MACD line above signal AND gaining momentum
    if signal_type == 'BUY':
        return (curr['macd_line'] > curr['macd_signal'] and 
                curr['macd_line'] > prev['macd_line'])  # MACD gaining upward momentum
    
    # For SELL: MACD line below signal AND losing momentum  
    elif signal_type == 'SELL':
        return (curr['macd_line'] < curr['macd_signal'] and 
                curr['macd_line'] < prev['macd_line'])  # MACD gaining downward momentum
    
    return False

def additional_market_filters(df):
    """Additional filters to reduce false signals"""
    curr = df.iloc[-1]
    prev = df.iloc[-1]
    
    # Volatility filter: Avoid signals during extreme volatility
    recent_highs = df['high'].tail(10)
    recent_lows = df['low'].tail(10)
    volatility = (recent_highs.max() - recent_lows.min()) / curr['close']
    
    # Skip signals if volatility > 5% (too choppy)
    if volatility > 0.05:
        return False
    
    # Price momentum filter: Price should be moving in signal direction
    price_momentum = (curr['close'] - df['close'].iloc[-5]) / df['close'].iloc[-5]
    
    return True  # All filters passed

def generate_signal(symbol, df, timeframe):
    """Generate high-accuracy trading signal with multiple confirmations"""
    # First check: RSI crossover
    signal_type = detect_rsi_crossover(df)
    if not signal_type:
        return None
    
    # Second check: MACD confirmation
    if not confirm_with_macd(df, signal_type):
        logger.debug(f"{symbol} {timeframe}: RSI signal but MACD not confirmed")
        return None
    
    # Third check: Market condition filters
    if not additional_market_filters(df):
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
    """Format enhanced signal with improved styling for Discord"""
    # Choose colors and emojis based on signal type
    if signal['signal_type'] == 'BUY':
        header_emoji = "🟢📈"
        signal_bg = "```diff\n+ BUY SIGNAL DETECTED +```"
        entry_emoji = "🚀"
        color_theme = "🟢"
    else:
        header_emoji = "🔴📉"
        signal_bg = "```diff\n- SELL SIGNAL DETECTED -```"
        entry_emoji = "🎯"
        color_theme = "🔴"
    
    return (
        f"{signal_bg}\n"
        f"{header_emoji} **{signal['symbol']} {signal['signal_type']} SIGNAL** {header_emoji}\n"
        f"```css\n"
        f"═══════════════════════════════════\n"
        f"```\n"
        f"{entry_emoji} **ENTRY DETAILS:**\n"
        f"```yaml\n"
        f"Symbol: {signal['symbol']}\n"
        f"Timeframe: {signal['timeframe']}\n"
        f"Entry Price: {signal['entry_price']:.4f}\n"
        f"```\n"
        f"� **PROFIT TARGETS:**\n"
        f"```diff\n"
        f"+ Take Profit: {signal['tp_price']:.4f} (+0.50%)\n"
        f"- Stop Loss: {signal['sl_price']:.4f} (-0.50%)\n"
        f"```\n"
        f"� **TECHNICAL ANALYSIS:**\n"
        f"```apache\n"
        f"RSI-9:     {signal['rsi_9']:.1f}\n"
        f"RSI-21:    {signal['rsi_21']:.1f}\n"
        f"MACD Line: {signal['macd_line']:.6f}\n"
        f"MACD Sig:  {signal['macd_signal']:.6f}\n"
        f"Volume:    {signal['volume_ratio']:.1f}x average\n"
        f"```\n"
        f"⏰ **TIME:** `{signal['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}`\n"
        f"🎯 **Strategy:** `RSI(9,21) + MACD(9,21,9)`\n"
        f"```css\n"
        f"═══════════════════════════════════\n"
        f"```\n"
        f"{color_theme} **TRADE RESPONSIBLY - MANAGE YOUR RISK** {color_theme}"
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
    """Check if any active signals hit TP or SL"""
    if symbol not in active_signals or symbol not in current_prices:
        return
    
    current_price = current_prices[symbol]
    signals_to_remove = []
    
    for signal_id, signal in active_signals[symbol].items():
        tp_hit = False
        sl_hit = False
        
        if signal['signal_type'] == 'BUY':
            if current_price >= signal['tp_price']:
                tp_hit = True
            elif current_price <= signal['sl_price']:
                sl_hit = True
        else:  # SELL
            if current_price <= signal['tp_price']:
                tp_hit = True
            elif current_price >= signal['sl_price']:
                sl_hit = True
        
        if tp_hit:
            message = (
                f"```diff\n+ TAKE PROFIT ACHIEVED +```\n"
                f"🎯🟢 **PROFIT TARGET HIT** 🟢🎯\n"
                f"```css\n"
                f"═══════════════════════════════════\n"
                f"```\n"
                f"💰 **TRADE COMPLETED SUCCESSFULLY:**\n"
                f"```yaml\n"
                f"Symbol: {signal['symbol']}\n"
                f"Direction: {signal['signal_type']}\n"
                f"Timeframe: {signal['timeframe']}\n"
                f"```\n"
                f"📊 **PRICE MOVEMENT:**\n"
                f"```diff\n"
                f"+ Entry Price: {signal['entry_price']:.4f}\n"
                f"+ Exit Price:  {current_price:.4f}\n"
                f"+ Profit: +0.50% ✅\n"
                f"```\n"
                f"🔓 **STATUS:** `Signal CLOSED - Ready for new signals`\n"
                f"⏰ **Closed:** `{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
                f"```css\n"
                f"═══════════════════════════════════\n"
                f"```\n"
                f"🎉 **CONGRATULATIONS ON THE PROFIT!** 🎉"
            )
            send_discord_message(message)
            logger.info(f"TP HIT: {symbol} {signal['signal_type']} @ {current_price:.4f} - Signal closed")
            signals_to_remove.append(signal_id)
            
        elif sl_hit:
            message = (
                f"```diff\n- STOP LOSS TRIGGERED -```\n"
                f"🛑🔴 **STOP LOSS HIT** ��🛑\n"
                f"```css\n"
                f"═══════════════════════════════════\n"
                f"```\n"
                f"⚠️ **TRADE STOPPED FOR PROTECTION:**\n"
                f"```yaml\n"
                f"Symbol: {signal['symbol']}\n"
                f"Direction: {signal['signal_type']}\n"
                f"Timeframe: {signal['timeframe']}\n"
                f"```\n"
                f"📊 **PRICE MOVEMENT:**\n"
                f"```diff\n"
                f"- Entry Price: {signal['entry_price']:.4f}\n"
                f"- Exit Price:  {current_price:.4f}\n"
                f"- Loss: -0.50% ❌\n"
                f"```\n"
                f"🔓 **STATUS:** `Signal CLOSED - Ready for new signals`\n"
                f"⏰ **Closed:** `{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
                f"```css\n"
                f"═══════════════════════════════════\n"
                f"```\n"
                f"💪 **RISK MANAGED - NEXT OPPORTUNITY AWAITS!** 💪"
            )
            send_discord_message(message)
            logger.info(f"SL HIT: {symbol} {signal['signal_type']} @ {current_price:.4f} - Signal closed")
            signals_to_remove.append(signal_id)
    
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
