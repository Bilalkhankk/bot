import time
import pandas as pd
from data.fetcher import exchange, fetch_ohlcv
from strategy.indicators import calculate_indicators
from strategy.smc import check_market_condition, get_signal
from utils.helpers import setup_exchange
from config import settings
from datetime import datetime, timezone
import requests  # For Telegram API

# Telegram configuration (add these to your settings.py)
TELEGRAM_BOT_TOKEN = "your_bot_token"
TELEGRAM_CHAT_ID = "your_chat_id"

def send_telegram_message(message):
    """Send message to Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, data=payload)
        return response.json()
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return None

def generate_signal_message(symbol, signal, df, price):
    """Generate formatted signal message for Telegram"""
    atr = df["atr"].iloc[-1]
    rsi = df["rsi"].iloc[-1]
    volume = df["volume"].iloc[-1]
    
    # Calculate hypothetical SL/TP (for information only)
    sl_pct = 1.0  # 1 ATR for SL
    tp_pct = 2.0 if signal.market_condition == "NEUTRAL" else 3.0  # 2-3 ATR for TP
    
    sl_price = price - (sl_pct * atr) if signal.signal_type == "BUY" else price + (sl_pct * atr)
    tp_price = price + (tp_pct * atr) if signal.signal_type == "BUY" else price - (tp_pct * atr)
    
    message = (
        f"🚨 *{symbol} {signal.signal_type} Signal* 🚨\n"
        f"📊 *Price*: {price:.4f}\n"
        f"⏰ *Timeframe*: {settings.TIMEFRAME}\n"
        f"📈 *RSI*: {rsi:.2f}\n"
        f"📉 *ATR*: {atr:.4f}\n"
        f"💹 *Volume*: {volume:.2f}\n\n"
        f"🔴 *Suggested SL*: {sl_price:.4f} ({sl_pct}ATR)\n"
        f"🟢 *Suggested TP*: {tp_price:.4f} ({tp_pct}ATR)\n\n"
        f"⚡ *Market Condition*: {signal.market_condition}\n"
        f"📅 *Signal Time*: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    return message

def run_signal_bot():
    print("\n=== BINANCE FUTURES SIGNAL BOT ===")
    print(f"Pairs: {', '.join(settings.PAIRS)} | Timeframe: {settings.TIMEFRAME}\n")
    
    while True:
        try:
            market_condition = check_market_condition()
            
            for symbol in settings.PAIRS:
                df = fetch_ohlcv(symbol, settings.TIMEFRAME)
                if df is None:
                    continue
                    
                df = calculate_indicators(df)
                signal = get_signal(df, symbol, market_condition)
                
                if signal:
                    ticker = exchange.fetch_ticker(symbol)
                    if ticker is None:
                        continue
                        
                    price = ticker["last"]
                    message = generate_signal_message(symbol, signal, df, price)
                    
                    # Send signal to Telegram
                    send_telegram_message(message)
                    print(f"\nSignal generated for {symbol} at {price:.4f}")
                    print(message)  # Also print to console for logging
                    
            print("\nScanning for signals... Next check in 60 seconds")
            time.sleep(60)
            
        except KeyboardInterrupt:
            print("\nSignal bot stopped by user")
            break
        except Exception as e:
            print(f"\nSignal bot error: {str(e)[:100]}")
            time.sleep(30)

if __name__ == "__main__":
    setup_exchange()
    run_signal_bot()

