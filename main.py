import time
import pandas as pd
from data.fetcher import fetch_ohlcv
from strategy.indicators import calculate_indicators
from strategy.smc import get_signal
from config import settings
import requests
import logging
import ccxt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

last_pair_refresh = 0
PAIRS = []

def refresh_top_pairs():
    """Fetch top USDT pairs by 24h volume"""
    global last_pair_refresh
    try:
        logger.info("Fetching top trading pairs by volume...")
        exchange = ccxt.binance()
        markets = exchange.load_markets()
        usdt_pairs = []

        for symbol, market in markets.items():
            if market['quote'] == 'USDT' and market['active']:
                # Check if it's a spot or futures market
                if 'spot' in market['type'] or 'future' in market['type']:
                    volume = float(market['info'].get('quoteVolume', 0))
                    usdt_pairs.append({
                        'symbol': symbol.replace('/', ''),
                        'volume': volume
                    })

        usdt_pairs.sort(key=lambda x: x['volume'], reverse=True)
        top_pairs = [pair['symbol'] for pair in usdt_pairs[:settings.TOP_PAIRS_NUMBER]]
        logger.info(f"Top {settings.TOP_PAIRS_NUMBER} pairs: {', '.join(top_pairs)}")
        last_pair_refresh = time.time()
        return top_pairs

    except Exception as e:
        logger.error(f"Error fetching pairs: {str(e)}")
        return ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT']

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': settings.TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, data=payload)
        return response.json()
    except Exception as e:
        logger.error(f"Telegram error: {str(e)}")
        return None

def generate_signal_message(signal, df):
    last = df.iloc[-1]
    return (
        f"🚨 *{signal.symbol} {signal.signal_type} Signal* 🚨\n"
        f"📊 Entry: {signal.entry_price:.4f}\n"
        f"🔴 SL: {signal.sl_price:.4f} (0.5%)\n"
        f"🟢 TP: {signal.tp_price:.4f} (0.5%)\n"
        f"📈 RSI Fast: {last['rsi_fast']:.1f}\n"
        f"📉 RSI Slow: {last['rsi_slow']:.1f}\n"
        f"💹 MACD Line: {last['macd_line']:.4f}\n"
        f"⚡ MACD Signal: {last['macd_signal']:.4f}\n"
        f"⏰ Time: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

def run_signal_bot():
    global PAIRS
    logger.info("\n=== SIGNAL ONLY BOT ===")
    logger.info("Bot will only send signals, NOT place trades")

    PAIRS = refresh_top_pairs()
    logger.info(f"Timeframe: {settings.TIMEFRAME}")
    logger.info(f"Initial pairs: {', '.join(PAIRS)}\n")

    while True:
        try:
            # Refresh pairs every 6 hours
            if time.time() - last_pair_refresh > 21600:
                PAIRS = refresh_top_pairs()
                logger.info(f"Refreshed pairs: {', '.join(PAIRS)}")

            logger.info("="*40)
            
            for symbol in PAIRS:
                logger.info(f"Processing {symbol}...")
                
                # Fetch OHLCV data
                df = fetch_ohlcv(symbol, settings.TIMEFRAME, 100)
                if df is None or len(df) < 50:
                    logger.warning(f"  Insufficient data for {symbol}")
                    continue

                # Calculate indicators
                df = calculate_indicators(df)
                if df is None:
                    logger.warning(f"  Indicator calculation failed for {symbol}")
                    continue

                # Get last candle data
                last = df.iloc[-1]
                logger.info(f"  Price: {last['close']:.4f}")
                logger.info(f"  RSI: Fast={last['rsi_fast']:.1f}, Slow={last['rsi_slow']:.1f}")
                logger.info(f"  MACD: Line={last['macd_line']:.4f}, Signal={last['macd_signal']:.4f}")

                # Check for signal
                signal = get_signal(df, symbol, "NEUTRAL")

                if signal:
                    logger.info(f"  ⚡ SIGNAL FOUND: {signal.signal_type}")
                    logger.info(f"  Entry: {signal.entry_price:.4f} | SL: {signal.sl_price:.4f} | TP: {signal.tp_price:.4f}")
                    
                    # Send signal via Telegram
                    send_telegram_message(generate_signal_message(signal, df))
                    logger.info("  ✅ Signal sent to Telegram")
                else:
                    logger.info("  No valid signal")

                logger.info("-" * 40)

            # Wait for next candle
            logger.info("Waiting for next candle...\n")
            time.sleep(60)

        except KeyboardInterrupt:
            logger.info("\nBot stopped manually")
            break
        except ccxt.RateLimitExceeded:
            logger.warning("Rate limit exceeded - pausing for 60 seconds")
            time.sleep(60)
        except Exception as e:
            logger.error(f"Main loop error: {str(e)}")
            time.sleep(30)

if __name__ == "__main__":
    run_signal_bot()