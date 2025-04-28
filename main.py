import time
import pandas as pd
from data.fetcher import exchange, fetch_ohlcv
from strategy.indicators import calculate_indicators
from strategy.smc import check_market_condition, get_signal
from risk.risk_manager import RiskManager
from trade.executor import place_order
from trade.logger import log_trade
from utils.helpers import initialize_log_file, setup_exchange
from config import settings
from datetime import datetime, timezone
from utils.helpers import get_account_balance

risk_manager = RiskManager()

def manage_trades():
    if not risk_manager.active_trades:
        return
        
    print("\nActive Positions:")
    for symbol in list(risk_manager.active_trades.keys()):
        try:
            trade = risk_manager.active_trades[symbol]
            ticker = exchange.fetch_ticker(symbol)
            if ticker is None:
                continue
                
            price = ticker["last"]
            current_atr = (trade["tp"] - trade["sl"]) / 2
            is_long = trade["side"] == "long"
            entry = trade["entry"]
            
            # First check if position was already closed by SL/TP
            try:
                positions = exchange.fetch_positions([symbol])
                position = next((p for p in positions if p['symbol'] == symbol), None)
                
                if position and float(position['contracts']) == 0:
                    # Position was closed (likely by SL/TP)
                    reason = "SL" if ((price <= trade["sl"]) if is_long else (price >= trade["sl"])) else "TP"
                    full_pnl = (price - entry) / entry * 100 * settings.LEVERAGE if is_long else (entry - price) / entry * 100 * settings.LEVERAGE
                    
                    log_trade(symbol, "CLOSE", price, full_pnl, reason, risk_manager.active_trades)
                    
                    if full_pnl < 0:
                        risk_manager.consecutive_losses += 1
                    else:
                        risk_manager.consecutive_losses = max(0, risk_manager.consecutive_losses - 1)
                    
                    del risk_manager.active_trades[symbol]
                    print(f"  {symbol} CLOSED ({reason}) | PnL: {full_pnl:+.2f}%")
                    continue
            except Exception as e:
                print(f"  Position check error for {symbol}: {str(e)[:100]}")

            min_move = current_atr * 0.75
            has_sufficient_move = (price > entry + min_move) if is_long else (price < entry - min_move)
            
            def calculate_portion_pnl(portion_size):
                price_diff = (price - entry) if is_long else (entry - price)
                return (price_diff / entry * 100 * settings.LEVERAGE * portion_size)
            
            if risk_manager.market_condition == "NEUTRAL" and has_sufficient_move:
                for atr_mult, taken_flag in [(1.0, "taken_1.0x_atr"), (1.5, "taken_1.5x_atr")]:
                    if not trade.get(taken_flag, False):
                        profit_condition = (price >= entry + atr_mult * current_atr) if is_long else (price <= entry - atr_mult * current_atr)
                        if profit_condition:
                            df = fetch_ohlcv(symbol, settings.TIMEFRAME, 50)
                            if df is not None:
                                df = calculate_indicators(df)
                                last_rsi = df["rsi"].iloc[-1]
                                rsi_confirm = (last_rsi < 70) if is_long else (last_rsi > 30)
                                
                                if rsi_confirm:
                                    close_size = 0.4
                                    portion_pnl = calculate_portion_pnl(close_size)
                                    trade["size"] *= (1 - close_size)
                                    trade[taken_flag] = True
                                    
                                    try:
                                        close_order = exchange.create_order(
                                            symbol=symbol,
                                            type='limit',
                                            side='sell' if is_long else 'buy',
                                            amount=trade['size'] * close_size,
                                            price=price,
                                            params={'reduceOnly': True}
                                        )
                                        
                                        log_trade(symbol, f"PARTIAL_CLOSE_40%_{atr_mult}xATR", price, pnl=portion_pnl, active_trades=risk_manager.active_trades)
                                        print(f"  {symbol} PARTIALLY CLOSED (40%) at {atr_mult}x ATR | PnL: {portion_pnl:+.2f}%")
                                        break
                                    except Exception as e:
                                        print(f"  Partial close error for {symbol}: {str(e)[:100]}")
            elif has_sufficient_move:
                for atr_mult, taken_flag in [(1.5, "taken_1.5x_atr"), (2.5, "taken_2.5x_atr")]:
                    if not trade.get(taken_flag, False):
                        profit_condition = (price >= entry + atr_mult * current_atr) if is_long else (price <= entry - atr_mult * current_atr)
                        if profit_condition:
                            df = fetch_ohlcv(symbol, settings.TIMEFRAME, 50)
                            if df is not None:
                                df = calculate_indicators(df)
                                last_volume = df["volume"].iloc[-1]
                                volume_ma = df["volume_ma"].iloc[-1]
                                volume_confirm = last_volume > volume_ma * 1.2
                                
                                if volume_confirm:
                                    close_size = 0.3
                                    portion_pnl = calculate_portion_pnl(close_size)
                                    trade["size"] *= (1 - close_size)
                                    trade[taken_flag] = True
                                    
                                    try:
                                        close_order = exchange.create_order(
                                            symbol=symbol,
                                            type='limit',
                                            side='sell' if is_long else 'buy',
                                            amount=trade['size'] * close_size,
                                            price=price,
                                            params={'reduceOnly': True}
                                        )
                                        
                                        log_trade(symbol, f"PARTIAL_CLOSE_30%_{atr_mult}xATR", price, pnl=portion_pnl, active_trades=risk_manager.active_trades)
                                        print(f"  {symbol} PARTIALLY CLOSED (30%) at {atr_mult}x ATR | PnL: {portion_pnl:+.2f}%")
                                        break
                                    except Exception as e:
                                        print(f"  Partial close error for {symbol}: {str(e)[:100]}")
            
            # Manual SL/TP check if not already closed
            should_close = (price >= trade["tp"] if is_long else price <= trade["tp"]) or (price <= trade["sl"] if is_long else price >= trade["sl"])
            if should_close:
                reason = "TP" if ((price >= trade["tp"]) if is_long else (price <= trade["tp"])) else "SL"
                full_pnl = calculate_portion_pnl(1.0)
                
                try:
                    close_order = exchange.create_order(
                        symbol=symbol,
                        type='market',
                        side='sell' if is_long else 'buy',
                        amount=trade['size'],
                        params={'reduceOnly': True}
                    )
                    
                    log_trade(symbol, "CLOSE", price, full_pnl, reason, risk_manager.active_trades)
                    
                    if full_pnl < 0:
                        risk_manager.consecutive_losses += 1
                    else:
                        risk_manager.consecutive_losses = max(0, risk_manager.consecutive_losses - 1)
                    
                    del risk_manager.active_trades[symbol]
                    print(f"  {symbol} CLOSED ({reason}) | PnL: {full_pnl:+.2f}%")
                except Exception as e:
                    print(f"  Close order error for {symbol}: {str(e)[:100]}")
                    # Verify if position was actually closed
                    try:
                        positions = exchange.fetch_positions([symbol])
                        position = next((p for p in positions if p['symbol'] == symbol), None)
                        if position and float(position['contracts']) == 0:
                            log_trade(symbol, "CLOSE", price, full_pnl, reason, risk_manager.active_trades)
                            del risk_manager.active_trades[symbol]
                            print(f"  {symbol} position was closed despite error")
                    except Exception as e:
                        print(f"  Position verification error for {symbol}: {str(e)[:100]}")
            else:
                current_pnl = calculate_portion_pnl(1.0)
                print(f"  {symbol} {trade['side'].upper()}: {price:.2f} | PnL: {current_pnl:+.2f}%")
                
        except Exception as e:
            print(f"  Trade error for {symbol}: {str(e)[:100]}")
            # Check if position was closed despite the error
            try:
                positions = exchange.fetch_positions([symbol])
                position = next((p for p in positions if p['symbol'] == symbol), None)
                if position and float(position['contracts']) == 0 and symbol in risk_manager.active_trades:
                    del risk_manager.active_trades[symbol]
                    print(f"  {symbol} position was closed despite error")
            except:
                pass
    
    risk_manager.save_state()

def run_bot():
    print("\n=== BINANCE FUTURES TRADING BOT ===")
    print(f"Pairs: {', '.join(settings.PAIRS)} | Timeframe: {settings.TIMEFRAME}")
    
    # Get actual account balance
    account_balance = get_account_balance()
    # if account_balance < 10:  # Minimum $10 balance
    #     print("Account balance too low for trading")
    #     time.sleep(60)
    #     return
    
    print(f"Leverage: {settings.LEVERAGE}x | Fixed Risk: ${settings.TRADE_AMOUNT} per trade\n")
    
    risk_manager.load_state()
    
    while True:
        try:
            if risk_manager.consecutive_losses >= risk_manager.max_losses:
                print("\n! Trading paused due to consecutive losses !")
                time.sleep(3600)
                risk_manager.consecutive_losses = 0
                continue
                
            if not risk_manager.is_optimal_trading_time():
                print("\nOutside optimal hours, waiting...")
                time.sleep(300)
                continue
                
            risk_manager.market_condition = check_market_condition()
            
            current_max_trades = settings.NEUTRAL_MAX_TRADES if risk_manager.market_condition == "NEUTRAL" else settings.MAX_TRADES
            
            for symbol in settings.PAIRS:
                if len(risk_manager.active_trades) >= current_max_trades:
                    break
                    
                if symbol not in risk_manager.active_trades:
                    df = fetch_ohlcv(symbol, settings.TIMEFRAME)
                    if df is None:
                        continue
                        
                    df = calculate_indicators(df)
                    signal = get_signal(df, symbol, risk_manager.market_condition)
                    
                    if signal:
                        ticker = exchange.fetch_ticker(symbol)
                        if ticker is None:
                            continue
                            
                        price = ticker["last"]
                        atr = df["atr"].iloc[-1]
                        
                        sl = risk_manager.calculate_stop_loss(df, price, "long" if signal.signal_type == "BUY" else "short")
                        tp_multiplier = 2.0 if risk_manager.market_condition == "NEUTRAL" else 3.0
                        tp = price + (tp_multiplier * atr) if signal.signal_type == "BUY" else price - (tp_multiplier * atr)
                        
                        # Get current balance for position sizing
                        account_balance = get_account_balance()
                        position_size = risk_manager.get_position_size(symbol, atr, price, account_balance)
                        
                        if position_size <= 0:
                            print(f"  {symbol} - Position size too small or insufficient balance")
                            continue
                        
                        # Calculate required margin
                        required_margin = (position_size * price) / settings.LEVERAGE
                        
                        if required_margin > account_balance * 0.5:
                            print(f"  {symbol} - Insufficient margin for trade")
                            continue
                            
                        try:
                            # Place entry order
                            entry_order = exchange.create_order(
                                symbol=symbol,
                                type='MARKET',
                                side='buy' if signal.signal_type == "BUY" else 'sell',
                                amount=position_size
                            )
                            
                            # Place stop loss (OCO order)
                            exchange.create_order(
                                symbol=symbol,
                                type='STOP_MARKET',
                                side='sell' if signal.signal_type == "BUY" else 'buy',
                                amount=position_size,
                                params={
                                    'stopPrice': sl,
                                    'reduceOnly': True
                                }
                            )
                            
                            # Place take profit (LIMIT order)
                            exchange.create_order(
                                symbol=symbol,
                                type='TAKE_PROFIT_MARKET',
                                side='sell' if signal.signal_type == "BUY" else 'buy',
                                amount=position_size,
                                params={
                                    'stopPrice': tp,
                                    'reduceOnly': True
                                }
                            )
                            
                            risk_manager.active_trades[symbol] = {
                                "side": "long" if signal.signal_type == "BUY" else "short",
                                "entry": price,
                                "sl": sl,
                                "tp": tp,
                                "time": datetime.now(timezone.utc),
                                "size": position_size,
                                "market_condition": risk_manager.market_condition,
                                "taken_1.0x_atr": False if risk_manager.market_condition == "NEUTRAL" else None,
                                "taken_1.5x_atr": False,
                                "taken_2.5x_atr": False if risk_manager.market_condition != "NEUTRAL" else None
                            }
                            
                            log_trade(symbol, "OPEN", price, active_trades=risk_manager.active_trades)
                            print(f"\nENTERED {risk_manager.active_trades[symbol]['side'].upper()} {symbol} at {price:.2f}")
                            print(f"TP: {tp:.2f} | SL: {sl:.2f} | Size: {position_size:.4f}")
                            
                        except Exception as e:
                            print(f"  Order error for {symbol}: {str(e)[:100]}")
                            continue
            
            manage_trades()
            print("\nRefreshing in 30 seconds...")
            time.sleep(30)
            
        except KeyboardInterrupt:
            print("\nBot stopped by user")
            risk_manager.save_state()
            break
        except Exception as e:
            print(f"\nMain error: {str(e)[:100]}")
            risk_manager.save_state()
            time.sleep(30)

if __name__ == "__main__":
    initialize_log_file()
    setup_exchange()
    run_bot()