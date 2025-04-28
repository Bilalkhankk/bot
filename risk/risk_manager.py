# risk_manager.py
import json
import os
from datetime import datetime, timezone
from config import settings
from utils.helpers import get_account_balance

class RiskManager:
    def __init__(self):
        self.consecutive_losses = 0
        self.max_losses = 5
        self.active_trades = {}
        self.market_condition = "NEUTRAL"

    def save_state(self):
        """Save the current state of active trades to a file"""
        try:
            state_to_save = {}
            for symbol, trade in self.active_trades.items():
                state_to_save[symbol] = trade.copy()
                state_to_save[symbol]['time'] = trade['time'].isoformat()
            
            with open(settings.STATE_FILE, 'w') as f:
                json.dump({
                    'active_trades': state_to_save,
                    'market_condition': self.market_condition,
                    'consecutive_losses': self.consecutive_losses
                }, f)
        except Exception as e:
            print(f"Error saving state: {str(e)[:100]}")

    def load_state(self):
        """Load the saved state of active trades from file"""
        if not os.path.exists(settings.STATE_FILE):
            return
            
        try:
            with open(settings.STATE_FILE, 'r') as f:
                state = json.load(f)
                
            loaded_trades = {}
            for symbol, trade in state.get('active_trades', {}).items():
                loaded_trades[symbol] = trade.copy()
                loaded_trades[symbol]['time'] = datetime.fromisoformat(trade['time'])
                
            self.active_trades = loaded_trades
            self.market_condition = state.get('market_condition', "NEUTRAL")
            self.consecutive_losses = state.get('consecutive_losses', 0)
            
            print("\nLoaded previous state:")
            for symbol, trade in self.active_trades.items():
                print(f"  {symbol} {trade['side'].upper()}: Entry {trade['entry']:.2f}, Size {trade['size']:.2f}")
                
        except Exception as e:
            print(f"Error loading state: {str(e)[:100]}")

    def calculate_stop_loss(self, df, entry_price, side):
        """
        Calculate stop loss price based on market structure and volatility
        Args:
            df: DataFrame containing price data and indicators
            entry_price: Entry price for the position
            side: 'long' or 'short'
        Returns:
            float: Calculated stop loss price
        """
        try:
            atr = df["atr"].iloc[-1]
            recent_pivot = (df["low"].rolling(3).min().iloc[-1] if side == "long" 
                          else df["high"].rolling(3).max().iloc[-1])
            
            atr_pct = (atr / entry_price) * 100
            
            if self.market_condition == "NEUTRAL":
                buffer_pct = 1.5  # Wider buffer in neutral markets
                atr_multiplier = 1.2 + (atr_pct / 25)
            else:  # Trending market (BULLISH/BEARISH)
                buffer_pct = 0.8   # Tighter buffer in trends
                atr_multiplier = 0.8 + (atr_pct / 30)
            
            # Calculate structural SL (price-based)
            structural_sl = (recent_pivot * (1 - buffer_pct/100) if side == "long" 
                           else recent_pivot * (1 + buffer_pct/100))
            
            # Calculate ATR-based SL
            atr_sl = (entry_price - (atr_multiplier * atr) if side == "long"
                     else entry_price + (atr_multiplier * atr))
            
            # Use the more conservative (wider) SL
            return (max(atr_sl, structural_sl) if side == "long" 
                   else min(atr_sl, structural_sl))
                   
        except Exception as e:
            print(f"SL calculation error: {str(e)[:100]}")
            # Fallback to 1.5x ATR if calculation fails
            return (entry_price - 1.5 * atr if side == "long" 
                    else entry_price + 1.5 * atr)

    def get_position_size(self, symbol, atr, entry_price, account_balance=None):
        """
        Calculate safe position size with proper risk management
        Args:
            symbol: Trading pair symbol
            atr: Current ATR value
            entry_price: Entry price for the position
            account_balance: Optional account balance (will fetch if None)
        Returns:
            float: Position size in base currency
        """
        try:
            if account_balance is None:
                account_balance = get_account_balance()
            
            # Calculate risk per trade (1-2% of balance)
            risk_amount = account_balance * 0.02  # 2% risk per trade
            
            # Calculate stop distance (1.5x ATR)
            sl_distance = atr * 1.5
            
            # Position size in quote currency (USDT)
            position_size_quote = risk_amount / (sl_distance / entry_price)
            
            # Convert to base currency amount
            position_size = position_size_quote / entry_price
            
            # Apply leverage
            leveraged_size = position_size * settings.LEVERAGE
            
            # Check margin requirements (max 50% of balance)
            max_allowed = (account_balance * 0.5 * settings.LEVERAGE) / entry_price
            return min(leveraged_size, max_allowed)
            
        except Exception as e:
            print(f"Position size error for {symbol}: {str(e)[:100]}")
            return 0

    def is_optimal_trading_time(self):
        """
        Check if current time is optimal for trading
        Returns:
            bool: True if optimal trading time, False otherwise
        """
        now = datetime.now(timezone.utc)
        utc_hour = now.hour
        weekday = now.weekday()  # Monday is 0, Sunday is 6

        # Example restrictions (uncomment to activate)
        # if weekday in (5, 6):  # Avoid weekends
        #     return False
        # if 18 <= utc_hour <= 21:  # Avoid specific hours
        #     return False

        return True