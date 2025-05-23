import time
import pandas as pd
from data.fetcher import exchange, fetch_ohlcv
from strategy.indicators import calculate_indicators
from strategy.smc import check_market_condition, get_signal
from utils.helpers import setup_exchange
from config import settings
from datetime import datetime, timezone
import requests

# Global dict to track active trades
active_trades = {}  # Format: {symbol: SMCSignal}

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
    rsi = df["rsi"].iloc[-1]
    volume = df["volume"].iloc[-1]
    rr_ratio = round(abs(signal.tp_price - signal.entry_price) / abs(signal.entry_price - signal.sl_price), 2)

    return (
        f"🚨 *{signal.symbol} {signal.signal_type} Signal* 🚨\n"
        f"📊 Entry: {signal.entry_price:.4f}\n"
        f"🔴 SL: {signal.sl_price:.4f}\n"
        f"🟢 TP: {signal.tp_price:.4f}\n"
        f"📉 ATR: {signal.atr:.4f}\n"
        f"📈 RSI: {rsi:.2f}\n"
        f"💹 Volume: {volume:.2f}\n\n"
        f"⚡ Market: {signal.market_condition}\n"
        f"📊 Risk-Reward: 1:{rr_ratio}"
    )

def check_trade_exits():
    """Check if any active trades hit TP/SL"""
    for symbol, trade in list(active_trades.items()):
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # Check exit conditions
            if trade.signal_type == "BUY":
                hit_sl = current_price <= trade.sl_price
                hit_tp = current_price >= trade.tp_price
            else:  # SELL
                hit_sl = current_price >= trade.sl_price
                hit_tp = current_price <= trade.tp_price

            if hit_sl or hit_tp:
                pl_pct = ((current_price - trade.entry_price) / trade.entry_price * 100) * (-1 if trade.signal_type == "SELL" else 1)
                
                # Send closure alert
                send_telegram_message(
                    f"🔴 *TRADE CLOSED* 🔴\n"
                    f"Pair: {symbol}\n"
                    f"Direction: {trade.signal_type}\n"
                    f"Entry: {trade.entry_price:.4f}\n"
                    f"Exit: {current_price:.4f}\n"
                    f"Reason: {'SL Hit' if hit_sl else 'TP Hit'}\n"
                    f"P/L: {pl_pct:.2f}%"
                )
                
                # Remove from active trades
                active_trades.pop(symbol)

        except Exception as e:
            print(f"Error checking {symbol}: {str(e)[:100]}")

def run_signal_bot():
    print("\n=== BINANCE FUTURES SIGNAL BOT ===")
    print(f"Pairs: {', '.join(settings.PAIRS)} | Timeframe: {settings.TIMEFRAME}\n")

    while True:
        try:
            # Check for new signals
            market_condition = check_market_condition()
            for symbol in settings.PAIRS:
                df = fetch_ohlcv(symbol, settings.TIMEFRAME)
                if df is None:
                    continue

                df = calculate_indicators(df)
                signal = get_signal(df, symbol, market_condition)

                if signal and symbol not in active_trades:
                    active_trades[symbol] = signal
                    send_telegram_message(generate_signal_message(signal, df))
                    print(f"New trade: {symbol} {signal.signal_type}")

            # Check exits every minute
            check_trade_exits()
            time.sleep(60)

        except KeyboardInterrupt:
            print("\nBot stopped by user")
            break
        except Exception as e:
            print(f"\nError: {str(e)[:200]}")
            time.sleep(30)
def monitor_trades(active_signals: dict):
    """Enhanced exit monitoring with pair-specific logic"""
    for symbol, signal in list(active_signals.items()):
        try:
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # Update trailing stop
            trailing_stop = signal.update_trailing_stop(current_price)
            
            # Check exit conditions
            if signal.signal_type == "BUY":
                hit_sl = current_price <= (trailing_stop or signal.sl_price)
                hit_tp = current_price >= signal.tp_price
            else:  # SELL
                hit_sl = current_price >= (trailing_stop or signal.sl_price)
                hit_tp = current_price <= signal.tp_price

            if hit_sl or hit_tp:
                # Calculate P/L
                pl_pct = ((current_price - signal.entry_price) / signal.entry_price * 100) * (
                    -1 if signal.signal_type == "SELL" else 1
                )
                
                # Generate exit message
                message = (
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"✅ *TRADE CLOSED* {'🔴' if hit_sl else '🟢'}\n"
                    f"• Pair: {symbol}\n"
                    f"• Direction: {signal.signal_type}\n"
                    f"• Entry: {signal.entry_price:.4f}\n"
                    f"• Exit: {current_price:.4f}\n"
                    f"• Reason: {'SL Hit' if hit_sl else 'TP Hit'}\n"
                    f"• P/L: {pl_pct:.2f}%\n"
                    f"• ATR Used: {signal.atr:.2f}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯"
                )
                send_telegram_message(message)
                active_signals.pop(symbol)
                
        except Exception as e:
            print(f"Trade monitoring error ({symbol}): {str(e)[:100]}")
if __name__ == "__main__":
    setup_exchange()
    run_signal_bot()