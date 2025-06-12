import time
import pandas as pd
from data.fetcher import exchange, fetch_ohlcv
from strategy.indicators import calculate_indicators
from strategy.smc import get_signal, check_market_condition
from utils.helpers import setup_exchange
from config import settings
import requests
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

active_trades = {}

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
    rr_ratio = round(abs(signal.tp_price - signal.entry_price) / abs(signal.entry_price - signal.sl_price), 2)
    sl_distance = abs(signal.entry_price - signal.sl_price) / signal.entry_price * 100
    return (
        f"🚨 *{signal.symbol} {signal.signal_type} Signal* 🚨\n"
        f"📊 Entry: {signal.entry_price:.4f}\n"
        f"🔴 SL: {signal.sl_price:.4f} ({sl_distance:.2f}%)\n"
        f"🟢 TP: {signal.tp_price:.4f}\n"
        f"📉 ATR: {signal.atr:.4f}\n"
        f"📈 RSI: {last['rsi']:.1f}\n"
        f"💹 Volume: {last['volume']:.2f}\n"
        f"⚡ Risk-Reward: 1:{rr_ratio}"
    )

def check_trade_exits():
    for symbol, trade in list(active_trades.items()):
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            if trade.signal_type == "BUY":
                hit_sl = current_price <= trade.sl_price
                hit_tp = current_price >= trade.tp_price
            else:
                hit_sl = current_price >= trade.sl_price
                hit_tp = current_price <= trade.tp_price

            if hit_sl or hit_tp:
                pl_pct = ((current_price - trade.entry_price) / trade.entry_price * 100) * (-1 if trade.signal_type == "SELL" else 1)
                msg = (
                    f"🔴 *TRADE CLOSED* {'🔴' if hit_sl else '🟢'}\n"
                    f"Pair: {symbol}\n"
                    f"Direction: {trade.signal_type}\n"
                    f"Entry: {trade.entry_price:.4f}\n"
                    f"Exit: {current_price:.4f}\n"
                    f"P/L: {pl_pct:.2f}%"
                )
                send_telegram_message(msg)
                logger.info(f"Trade closed: {symbol} {trade.signal_type} | P/L: {pl_pct:.2f}%")
                active_trades.pop(symbol)

        except Exception as e:
            logger.error(f"Exit check error ({symbol}): {str(e)[:100]}")

def run_signal_bot():
    logger.info("\n=== ALPHATREND CRYPTO TRADING BOT ===")
    logger.info(f"Pairs: {', '.join(settings.PAIRS)} | Timeframe: {settings.TIMEFRAME}\n")

    while True:
        try:
            # Market condition
            market_condition = check_market_condition()
            logger.info(f"MARKET CONDITION: {market_condition}")
            logger.info("="*40)
            
            for symbol in settings.PAIRS:
                # Fetch data
                logger.info(f"Processing {symbol}...")
                df = fetch_ohlcv(symbol, settings.TIMEFRAME, 100)
                if df is None or len(df) < 100:
                    logger.warning(f"  Insufficient data for {symbol}")
                    continue
                    
                # Calculate indicators
                df = calculate_indicators(df)
                if df is None:
                    logger.warning(f"  Indicator calculation failed for {symbol}")
                    continue
                    
                last = df.iloc[-1]
                
                # Skip low volatility pairs
                atr_pct = last['atr'] / last['close']
                if atr_pct < 0.005:  # 0.5% threshold
                    logger.info(f"  Skipping - Low volatility (ATR%: {atr_pct:.4f})")
                    continue
                
                # Log key metrics
                logger.info(f"  Price: {last['close']:.4f} | ATR%: {atr_pct*100:.2f}%")
                logger.info(f"  EMAs: 9={last['ema9']:.4f}, 18={last['ema18']:.4f} | MACD: {last['macd_line']:.4f}/{last['macd_signal']:.4f}")
                logger.info(f"  RSI: {last['rsi']:.1f} | Volume: {last['volume']:.0f} (MA: {last['volume_ma']:.0f})")
                
                # Check signal
                signal = get_signal(df, symbol, market_condition)
                
                if signal:
                    logger.info(f"  ⚡ SIGNAL FOUND: {signal.signal_type}")
                    logger.info(f"  Entry: {signal.entry_price:.4f} | SL: {signal.sl_price:.4f} | TP: {signal.tp_price:.4f}")
                    
                    if symbol not in active_trades:
                        active_trades[symbol] = signal
                        send_telegram_message(generate_signal_message(signal, df))
                        logger.info(f"  ✅ Trade executed")
                else:
                    logger.info("  No valid signal")
                
                logger.info("-"*40)

            # Check exits
            check_trade_exits()
            
            # Wait for next candle
            logger.info("Waiting for next candle...\n")
            time.sleep(60)

        except KeyboardInterrupt:
            logger.info("\nBot stopped manually")
            break
        except Exception as e:
            logger.error(f"Main loop error: {str(e)}")
            time.sleep(30)

if __name__ == "__main__":
    setup_exchange()
    run_signal_bot()