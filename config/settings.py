# Trading Parameters
PAIRS = ["XRPUSDT", "DOGEUSDT", "ADAUSDT", "ETHUSDT", "TRXUSDT", "SOLUSDT"]
TIMEFRAME = "15m"

# Telegram Configuration
TELEGRAM_BOT_TOKEN = "7981744692:AAEo4dmDLqrbIr0vUOCeQLnQFDHfaoTqcOw"  # Replace with your actual token
TELEGRAM_CHAT_ID = "-1002655134174"  # Replace with your actual chat ID

# Signal Parameters (for display in notifications)
LEVERAGE = 5
RISK_PERCENT = 1

# Technical Indicator Thresholds
ADX_THRESHOLDS = {
    "XRPUSDT": 22,    # Moderate volatility
    "DOGEUSDT": 20,   # High volatility
    "ADAUSDT": 24,    # Moderate-high volatility 
    "ETHUSDT": 25,    # Stable trending
    "TRXUSDT": 18,    # Extreme volatility
    "SOLUSDT": 26,    # Strong trends
    "BTCUSDT": 25     # Market benchmark
}
MAX_LEVERAGE = {
    "DOGEUSDT": 15,
    "TRXUSDT": 10,
    "XRPUSDT": 20,
    "ADAUSDT": 20,
    "ETHUSDT": 50,
    "SOLUSDT": 50
}
# Exchange configuration (read-only access, no account needed)
EXCHANGE_CONFIG = {
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',  # or 'spot' if you're using spot data
    }
}

# Signal Display Settings
SHOW_RSI = True
SHOW_MACD = True
SHOW_VOLUME = True
SHOW_SUPPORT_RESISTANCE = True
