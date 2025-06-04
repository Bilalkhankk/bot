import time
import pandas as pd
from data.fetcher import exchange, fetch_ohlcv
from strategy.indicators import calculate_indicators
from strategy.smc import get_signal, check_market_condition
from utils.helpers import setup_exchange
from config import settings
import requests

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
        print(f"Error sending Telegram message: {e}")
        return None

def generate_signal_message(signal, df):
    """Generate entry signal message"""
    last = df.iloc[-1]
    rr_ratio = round(abs(signal.tp_price - signal.entry_price) / abs(signal.entry_price - signal.sl_price), 2)

    return (
        f"🚨 *{signal.symbol} {signal.signal_type} Signal* 🚨\n"
        f"📊 Entry: {signal.entry_price:.4f}\n"
        f"🔴 SL: {signal.sl_price:.4f}\n"
        f"🟢 TP: {signal.tp_price:.4f}\n"
        f"📉 ATR: {signal.atr:.4f}\n"
        f"📈 RSI: {last['rsi']:.1f}\n"
        f"💹 Volume: {last['volume']:.2f}\n"
        f"⚡ Risk-Reward: 1:{rr_ratio}"
    )

def check_trade_exits():
    """Check if any active trades hit TP/SL"""
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
                
                send_telegram_message(
                    f"🔴 *TRADE CLOSED* {'🔴' if hit_sl else '🟢'}\n"
                    f"Pair: {symbol}\n"
                    f"Direction: {trade.signal_type}\n"
                    f"Entry: {trade.entry_price:.4f}\n"
                    f"Exit: {current_price:.4f}\n"
                    f"P/L: {pl_pct:.2f}%"
                )
                
                active_trades.pop(symbol)

        except Exception as e:
            print(f"Error checking {symbol}: {str(e)[:100]}")

def run_signal_bot():
    print("\n=== ALPHATREND CRYPTO TRADING BOT ===")
    print(f"Pairs: {', '.join(settings.PAIRS)} | Timeframe: {settings.TIMEFRAME}\n")

    while True:
        try:
            market_condition = check_market_condition()
            logger.info(f"Market Condition: {market_condition}")
            
            for symbol in settings.PAIRS:
                df = fetch_ohlcv(symbol, settings.TIMEFRAME, 100)
                if df is None or len(df) < 100:
                    continue
                    
                df = calculate_indicators(df)
                signal = get_signal(df, symbol, market_condition)

                if signal and symbol not in active_trades:
                    active_trades[symbol] = signal
                    send_telegram_message(generate_signal_message(signal, df))
                    print(f"New trade: {symbol} {signal.signal_type}")

            check_trade_exits()
            print("Waiting for next candle...")
            time.sleep(60)

        except KeyboardInterrupt:
            print("\nBot stopped manually")
            break
        except Exception as e:
            print(f"\nError: {str(e)[:200]}")
            time.sleep(30)

if __name__ == "__main__":
    setup_exchange()
    run_signal_bot()